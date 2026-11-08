"""
What download.py and install.py share: where the bundle lives, and how path_config.json is made.

The installer is a third program next to the two worlds of CLAUDE.md. It runs in the portable
CPython that download.bat puts into env\\python, on Windows, and never imports anything from
the project. The functions here are pure so that tests/installer/ can check them on any OS;
the paths they build are Windows paths (ntpath), whatever the machine running the tests.
"""
import json
import ntpath
import os

# The bundle, inside the project folder: env\python (portable CPython with every package),
# env\wheels (the wheels it was installed from, for repairs), env\models (cellpose model).
ENV_DIR = "env"

TORCH_INDEX = {
    # The oldest CUDA build of torch 2.8.0: the widest range of NVIDIA drivers that run it
    "gpu": "https://download.pytorch.org/whl/cu126",
    "cpu": "https://download.pytorch.org/whl/cpu",
}

PATH_CONFIG = "path_config.json"
PATH_CONFIG_TEMPLATE = "path_config.example.json"


def env_dir(root):
    return os.path.join(root, ENV_DIR)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _folder(path):
    """
    :return: str the path with one trailing backslash, the way path_config.example.json writes folders
    """
    return path.rstrip("\\") + "\\"


def build_path_config(root, zeiss_temp):
    """
    path_config.json for a project folder that runs where it lies ("in place").
    :param str root: the project folder on the microscope PC, for example D:\\automation
    :param str zeiss_temp: ZEN's autosave folder, which only the user knows
    :return: dict with every key of path_config.example.json
    """
    root = root.rstrip("\\")
    return {
        "python_exe": ntpath.join(root, ENV_DIR, "python", "python.exe"),
        "python_script": ntpath.join(root, "data_processing", "main_processor.py"),
        "measuring_points_path": _folder(ntpath.join(root, "temp")),
        "results_path": _folder(ntpath.join(root, "results")),
        "image_for_analysis_path": _folder(ntpath.join(root, "image_for_analysis")),
        "python_project_root": _folder(root),
        "zeiss_temp_file": _folder(zeiss_temp),
        "log_path": ntpath.join(root, "zen_log.txt"),
        "last_setup_path": ntpath.join(root, "last_setup.json"),
    }


def missing_keys(current, template):
    """
    :return: list of the keys the template has and the machine's path_config.json does not
    """
    return [key for key in template if key not in current]


def was_moved(current, root):
    """
    :return: True when path_config.json points at a different project folder than this one,
    which is what happens after the folder was moved or copied to another machine
    """
    recorded = current.get("python_project_root", "")
    return ntpath.normcase(recorded.rstrip("\\")) != ntpath.normcase(root.rstrip("\\"))


def update_project_paths(current, root):
    """
    Point every project path of an existing path_config.json at this folder, keeping what only
    the user knows (zeiss_temp_file) and any key that is not a project path.
    :return: dict
    """
    updated = dict(current)
    fresh = build_path_config(root, current.get("zeiss_temp_file", ""))
    for key, value in fresh.items():
        if key != "zeiss_temp_file":
            updated[key] = value
    return updated
