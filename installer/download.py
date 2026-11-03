"""
Run by download.bat, on a computer WITH internet, in the portable Python it has just put into
env\\python. Fills the bundle so that install.bat needs no internet at all:

    env\\wheels   every package of requirements.txt, torch in the chosen variant
    env\\python   the same packages, installed (needed here to fetch the model)
    env\\models   the cellpose model, which cellpose would otherwise download on first use

    download.bat            asks GPU or CPU
    download.bat --gpu      torch with CUDA 12.6 (about 2.5 GB), needs an NVIDIA driver
    download.bat --cpu      torch for the CPU only (about 200 MB)
"""
import datetime
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import TORCH_INDEX, env_dir, read_json, write_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = env_dir(ROOT)
WHEELS = os.path.join(ENV, "wheels")
MODELS = os.path.join(ENV, "models")
VARIANT_FILE = os.path.join(ENV, "variant.json")
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")


def ask_variant():
    if "--gpu" in sys.argv:
        return "gpu"
    if "--cpu" in sys.argv:
        return "cpu"
    while True:
        answer = input("Does the microscope PC have an NVIDIA graphics card? [Y/N]: ").strip().lower()
        if answer in ("t", "y"):
            return "gpu"
        if answer == "n":
            return "cpu"


def pip(*args):
    command = [sys.executable, "-m", "pip", "--disable-pip-version-check"] + list(args)
    print("\n> " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def main():
    variant = ask_variant()
    print("\nVariant: {} (torch from {})".format(variant, TORCH_INDEX[variant]))

    # wheels of the other variant would sit next to these and pip could pick either torch
    if os.path.isfile(VARIANT_FILE) and read_json(VARIANT_FILE).get("torch") != variant:
        print("The bundle held the other torch variant; its wheels are removed.")
        shutil.rmtree(WHEELS, ignore_errors=True)

    os.makedirs(WHEELS, exist_ok=True)

    # 1. the wheels, for this Python (3.12, Windows) exactly, as nothing gets built on the target
    pip("download", "-r", REQUIREMENTS, "--extra-index-url", TORCH_INDEX[variant],
        "--only-binary=:all:", "--dest", WHEELS)

    # 2. install them into the portable Python, from the folder only - the same command
    #    install.bat runs on the microscope PC, so a missing wheel shows up here, not there
    pip("install", "--no-index", "--find-links", WHEELS, "-r", REQUIREMENTS, "--no-warn-script-location")

    # 3. the cellpose model, fetched by cellpose itself rather than from a hardcoded URL
    os.makedirs(MODELS, exist_ok=True)
    env = dict(os.environ, CELLPOSE_LOCAL_MODELS_PATH=MODELS)
    print("\nFetching the cellpose model into {}".format(MODELS), flush=True)
    subprocess.run([sys.executable, "-c",
                    "from cellpose import models; models.Cellpose(model_type='cyto', gpu=False)"],
                   check=True, env=env)
    fetched = sorted(f for f in os.listdir(MODELS) if not f.endswith(".txt"))
    if not fetched:
        sys.exit("ERROR: cellpose did not put any model into {}".format(MODELS))
    print("Models: {}".format(", ".join(fetched)))

    write_json(VARIANT_FILE, {"torch": variant, "python": sys.version.split()[0],
                              "downloaded": datetime.date.today().isoformat()})

    print("\nDone. The folder {} is ready.".format(ROOT))
    print("Copy the WHOLE folder to the microscope PC (a pendrive is fine) and run install.bat there.")


if __name__ == "__main__":
    main()
