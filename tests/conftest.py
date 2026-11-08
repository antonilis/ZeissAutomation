"""
Shared setup. World A (ZeissAPI/zen_lib) cannot be imported without System.*, clr and
Zeiss.*, so their fakes go into sys.modules here, before any test module imports zen_lib.
See tests/support/zen_fakes.py for what the fakes do and do not cover.
"""
import os

import pytest

import zen_fakes

zen_fakes.install()

# utils.py imports matplotlib.pyplot at the top; never open a window during tests
os.environ.setdefault("MPLBACKEND", "Agg")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where a World A log() goes during a test: the in-memory disk, never the real one
TEST_LOG = "C:\\testlog\\zen_log.txt"


@pytest.fixture(autouse=True)
def zen_disk(monkeypatch):
    """
    Empty in-memory disk for every test, with World A's open() and log() pointed at it.
    :return: zen_fakes.FakeFileSystem
    """
    zen_fakes.reset()

    from zen_lib import runtime_config

    monkeypatch.setattr(runtime_config, "open", zen_fakes.FS.open, raising=False)
    monkeypatch.setattr(runtime_config, "_log_path", TEST_LOG)

    return zen_fakes.FS


@pytest.fixture
def repo_root():
    return REPO_ROOT
