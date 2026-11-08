"""
pyproject.toml, uv.lock and the requirements files are one source written three times: pip and the offline
installer read the requirements files, uv the lock. These tests fail as soon as one of them falls behind,
with the command that brings it back. They need uv and are skipped without it.
"""
import importlib.util
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_requirements",
                                                  os.path.join(ROOT, "installer", "export_requirements.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_matches_pyproject():
    run = subprocess.run(["uv", "lock", "--check", "--offline"], cwd=ROOT, capture_output=True, text=True)

    assert run.returncode == 0, "uv.lock is behind pyproject.toml, run: uv lock\n" + run.stderr


@pytest.mark.parametrize("name", ["requirements.txt", "requirements-gpu.txt", "requirements-dev.txt"])
def test_requirements_file_matches_lock(name):
    exporter = load_exporter()
    expected = exporter.header(name) + exporter.export(exporter.EXPORTS[name])

    with open(os.path.join(ROOT, name), encoding="utf-8") as file:
        actual = file.read()

    assert actual == expected, "{} is behind uv.lock, run: python installer/export_requirements.py".format(name)
