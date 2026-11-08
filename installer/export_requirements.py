"""
Writes the requirements files of pip from uv.lock, so that pip and the offline installer install exactly
what the lock pins, with its hashes. Run it after every change of pyproject.toml or uv.lock, on a
machine with uv; tests/contract/test_requirements_lock.py fails when the files fall behind the lock.

    python installer/export_requirements.py

    requirements.txt       the analysis, torch for the CPU
    requirements-gpu.txt   the analysis, torch for CUDA 12.6
    requirements-dev.txt   the tests, on top of one of the two

This is a tool of the developer, not of the installer: download.bat and install.bat only read the files.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# file name -> the arguments of uv export that make it
EXPORTS = {
    "requirements.txt": ["--no-dev", "--extra", "cpu"],
    "requirements-gpu.txt": ["--no-dev", "--extra", "gpu"],
    "requirements-dev.txt": ["--only-group", "dev"],
}


def export(arguments):
    """
    :return: str the requirements file uv makes from the lock, without its header of comments
    """
    command = ["uv", "export", "--frozen", "--no-emit-project", "--no-header", "--format", "requirements-txt"]
    out = subprocess.run(command + arguments, cwd=ROOT, capture_output=True, text=True)

    if out.returncode != 0:
        sys.exit("uv export failed:\n" + out.stderr)

    return out.stdout


def header(name):
    text = ("# Made from uv.lock by installer/export_requirements.py - do not edit, edit pyproject.toml,\n"
            "# run uv lock and this script instead.")

    if name == "requirements-dev.txt":
        return text + " The tests, on top of requirements.txt or requirements-gpu.txt.\n"

    return text + " torch comes from https://download.pytorch.org/whl/{}.\n".format("cu126" if "gpu" in name else "cpu")


def main():
    for name, arguments in EXPORTS.items():
        with open(os.path.join(ROOT, name), "w", encoding="utf-8", newline="\n") as file:
            file.write(header(name) + export(arguments))
        print("wrote", name)


if __name__ == "__main__":
    main()
