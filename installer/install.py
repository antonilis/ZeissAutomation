"""
Run by install.bat on the microscope PC, in the portable Python of env\\python. Needs no internet.

1. installs the packages from env\\wheels (a no-op when they are in already)
2. puts the cellpose model where cellpose looks for it (%USERPROFILE%\\.cellpose\\models)
3. copies what is inside ZeissAPI straight into ZEN's macro folder, keeping the path_config.json already
   there and the other macros of that folder
4. makes path_config.json there, or brings an existing one up to date
5. checks that the analysis runs: imports, GPU, and main_processor.py on the test image

The project runs where its folder lies. Moving the folder later is fine: run install.bat again.
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (PATH_CONFIG, PATH_CONFIG_TEMPLATE, build_path_config, env_dir, missing_keys,  # noqa: E402
                    read_json, requirements_file, update_project_paths, was_moved, write_json)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = env_dir(ROOT)
WHEELS = os.path.join(ENV, "wheels")
MODELS = os.path.join(ENV, "models")
VARIANT_FILE = os.path.join(ENV, "variant.json")
SOURCE_API = os.path.join(ROOT, "ZeissAPI")

# Remembered per machine and per user, not in the folder: the folder travels between machines
SETTINGS = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ZeissAutomation", "install.json")


###################### asking ##########################################################################


def ask(question, default=""):
    suffix = " [{}]".format(default) if default else ""
    answer = input("{}{}: ".format(question, suffix)).strip().strip('"')
    return answer or default


def ask_yes_no(question, default=True):
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input("{} [{}]: ".format(question, hint)).strip().lower()
        if not answer:
            return default
        if answer in ("y", "t"):
            return True
        if answer == "n":
            return False


def step(text):
    print("\n=== {}".format(text), flush=True)


def fail(text):
    print("\nERROR: {}".format(text))
    sys.exit(1)


###################### the steps #######################################################################


def check_bundle():
    if not os.path.isdir(WHEELS) or not os.path.isfile(VARIANT_FILE):
        fail("{} is missing or incomplete. Run download.bat first, on a computer with internet, "
             "then copy the whole folder here.".format(ENV))

    # A space would break the command line ZEN builds: the script path is not quoted
    # (execute_python.py, tests/contract/test_cli_roundtrip.py::test_script_path_with_space_survives)
    if " " in ROOT:
        fail("The project folder must not contain spaces: {}\nMove it, for example to D:\\automation, "
             "and run install.bat again.".format(ROOT))

    return read_json(VARIANT_FILE)


def install_packages(variant):
    requirements = requirements_file(ROOT, variant["torch"])
    step("Packages, from {}, as {} says".format(WHEELS, os.path.basename(requirements)))
    run = subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check", "install", "--no-index",
                          "--find-links", WHEELS, "-r", requirements, "--no-warn-script-location", "-q"])
    if run.returncode != 0:
        fail("pip could not install the packages from {} (see above). The bundle is incomplete or older than "
             "{}: run download.bat again on a computer with internet.".format(WHEELS, os.path.basename(requirements)))
    print("OK")


def install_models():
    target = os.path.join(os.path.expanduser("~"), ".cellpose", "models")
    step("Cellpose model -> {}".format(target))
    os.makedirs(target, exist_ok=True)
    for name in os.listdir(MODELS):
        shutil.copy2(os.path.join(MODELS, name), os.path.join(target, name))
        print("  {}".format(name))


def zen_macro_folder(settings):
    step("ZEN macro folder")
    print("The files of ZeissAPI go straight into the folder ZEN runs its macros from.")
    while True:
        folder = ask("Path of that folder", settings.get("zen_macro_folder", ""))
        if folder and os.path.isdir(folder):
            return folder
        print("  Not a folder: '{}'".format(folder))


def copy_zeissapi(source, macro_folder, confirm=ask_yes_no):
    """
    Copy what is inside ZeissAPI straight into the macro folder, the layout ZEN imports zen_lib from.
    Each folder and file of ZeissAPI replaces its namesake there, so a plugin removed from the project
    disappears from adaptive\\ too. Everything else in the macro folder, the other macros of the
    microscope, is left alone, and so is the machine's own config\\path_config.json.
    :return: str the macro folder, or None when the user declined
    """
    entries = [name for name in sorted(os.listdir(source)) if name != "__pycache__"]
    present = [name for name in entries if os.path.exists(os.path.join(macro_folder, name))]

    if present and not confirm("{} already holds {}. Replace them with the version from this folder? "
                               "The other macros there stay.".format(macro_folder, ", ".join(present))):
        return None

    live = os.path.join(macro_folder, "config", PATH_CONFIG)
    kept = None

    if os.path.isfile(live):
        with open(live, "rb") as f:
            kept = f.read()

    for name in entries:
        origin, target = os.path.join(source, name), os.path.join(macro_folder, name)

        if os.path.isdir(origin):
            if os.path.isdir(target):
                shutil.rmtree(target)
            shutil.copytree(origin, target, ignore=shutil.ignore_patterns("__pycache__", PATH_CONFIG))
        else:
            shutil.copy2(origin, target)

    if kept is not None:
        with open(live, "wb") as f:
            f.write(kept)

    return macro_folder


def make_path_config(api_folder, ask_text=ask, confirm=ask_yes_no):
    """
    Create <ZeissAPI>\\config\\path_config.json for this folder, or bring an existing one up to date.
    :return: str path of the file
    """
    live = os.path.join(api_folder, "config", PATH_CONFIG)
    template = read_json(os.path.join(api_folder, "config", PATH_CONFIG_TEMPLATE))

    if not os.path.isfile(live):
        zeiss_temp = ask_text("Folder ZEN autosaves to (FCS .fcs/.raw files)", template["zeiss_temp_file"])
        write_json(live, build_path_config(ROOT, zeiss_temp))
        print("Created {}".format(live))
        return live

    current = read_json(live)

    if was_moved(current, ROOT):
        print("path_config.json points at {}, this folder is {}".format(
            current.get("python_project_root"), ROOT))
        if confirm("Point it at this folder?"):
            current = update_project_paths(current, ROOT)

    for key in missing_keys(current, template):
        current[key] = build_path_config(ROOT, current.get("zeiss_temp_file", template["zeiss_temp_file"]))[key]
        print("Added the missing key {} = {}".format(key, current[key]))

    write_json(live, current)
    print("Up to date: {}".format(live))
    return live


def make_project_folders():
    for name in ("results", "temp", "image_for_analysis"):
        os.makedirs(os.path.join(ROOT, name), exist_ok=True)


def check_analysis(variant, api_folder):
    step("Checking the analysis")
    probe = ("import torch, cellpose, pylibCZIrw, skimage, cv2; "
             "print(torch.__version__); print(torch.cuda.is_available())")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    if out.returncode != 0:
        fail("The packages do not import:\n" + out.stderr[-1500:])
    torch_version, cuda = out.stdout.split()
    print("torch {}, CUDA available: {}".format(torch_version, cuda))

    if variant.get("torch") == "gpu" and cuda != "True":
        print("WARNING: this bundle has the GPU build of torch, but CUDA does not work here. Cellpose will run "
              "on the CPU, many times slower. Update the NVIDIA driver to a version that supports CUDA 12.6.")

    image = os.path.join(ROOT, "tests", "fixtures", "guv_overview.czi")
    if not os.path.isfile(image):
        print("No test image, the run of main_processor.py is skipped.")
        return

    result = os.path.join(ENV, "install_check.json")
    command = [sys.executable, os.path.join(ROOT, "data_processing", "main_processor.py"),
               "--type=overview", "--file_path=" + image, "--saving_path=" + result,
               "--analysis_arguments=Cellpose", "--is_FCS=False",
               "--processing_config=" + os.path.join(api_folder, "config", "processing_config.json")]
    run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT), capture_output=True, text=True)
    if run.returncode != 0 or not os.path.isfile(result):
        fail("main_processor.py failed on the test image:\n" + run.stderr[-2000:])

    with open(result, encoding="utf-8") as f:
        found = len(json.load(f))
    print("main_processor.py on the test image: {} object(s) found".format(found))
    if found == 0:
        print("WARNING: nothing found on an image that has GUVs on it")


def main():
    print("Installing the ZEISS automation from {}".format(ROOT))
    variant = check_bundle()
    settings = read_json(SETTINGS) if os.path.isfile(SETTINGS) else {}

    install_packages(variant)
    install_models()

    macro_folder = zen_macro_folder(settings)
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    write_json(SETTINGS, dict(settings, zen_macro_folder=macro_folder))

    step("ZeissAPI -> {}".format(macro_folder))
    api_folder = copy_zeissapi(SOURCE_API, macro_folder)
    if api_folder is None:
        api_folder = macro_folder
        print("Kept the files that are there.")
    else:
        print("Copied.")

    step("path_config.json")
    make_path_config(api_folder)
    make_project_folders()

    check_analysis(variant, api_folder)

    print("\nDone. In ZEN, run main_macro.czmac from {}".format(api_folder))


if __name__ == "__main__":
    main()
