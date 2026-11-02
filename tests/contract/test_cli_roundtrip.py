"""
The contract between the two worlds: the keyword arguments of PythonAnalysisRunner.run() in
ZEN must arrive as the same dictionary from utils.parse_args_to_dict() in World B.

The path in between is the one on the microscope PC: _make_args -> " ".join -> one string in
Process.StartInfo.Arguments -> python.exe's C runtime splits it (tests/support/winargv.py)
-> sys.argv -> parse_args_to_dict.
"""
import sys
import types

import pytest

import winargv
import zen_fakes
from zen_lib.execute_python import PythonAnalysisRunner

PYTHON_EXE = "D:\\automation\\venv\\Scripts\\python.exe"
SCRIPT = "D:\\automation\\data_processing\\main_processor.py"
PROJECT = "D:\\automation\\"
PROCESSING = "D:\\automation\\ZeissAPI\\config\\processing_config.json"
SELECTION = "D:\\automation\\ZeissAPI\\config\\selection_config.json"


def make_runner(script=SCRIPT):
    config = types.SimpleNamespace(python_exe=PYTHON_EXE, python_script=script, python_project_root=PROJECT,
                                   processing_config_path=PROCESSING, selection_config_path=SELECTION)
    return PythonAnalysisRunner(config)


def started():
    assert len(zen_fakes.FakeProcess.started) == 1
    return zen_fakes.FakeProcess.started[0]


def as_world_b_sees_it(start_info, monkeypatch):
    """
    Split the command line the way python.exe does on Windows, then parse it as main_processor.
    :return: tuple (sys.argv as World B sees it, dict from parse_args_to_dict)
    """
    # .NET puts the quoted program name in front of Arguments
    argv = winargv.split('"{}" {}'.format(start_info.FileName, start_info.Arguments))
    # python.exe consumes its own name; sys.argv starts at the script
    monkeypatch.setattr(sys, "argv", argv[1:])

    from utils import parse_args_to_dict

    return argv[1:], parse_args_to_dict()


def roundtrip(monkeypatch, runner=None, **kwargs):
    (runner or make_runner()).run(**kwargs)
    return as_world_b_sees_it(started(), monkeypatch)


BASE = dict(type="overview", file_path="D:\\automation\\image_for_analysis\\A1_x_Image_overview.czi",
            saving_path="D:\\automation\\temp\\A1_x_measurements_points.json",
            analysis_arguments="FLGUV", is_FCS=False)


def expected(**kwargs):
    out = {k: str(v) for k, v in kwargs.items() if v is not None}
    out.update(processing_config=PROCESSING, selection_config=SELECTION)
    return out


###################### the emulator itself ############################################################


@pytest.mark.parametrize("line, argv", [
    # the examples of "Parsing C++ command-line arguments", learn.microsoft.com
    ('"abc" d e', ["abc", "d", "e"]),
    ('a\\\\\\b d"e f"g h', ["a\\\\\\b", "de fg", "h"]),
    ('a\\\\\\"b c d', ['a\\"b', "c", "d"]),
    ('a\\\\\\\\"b c" d e', ["a\\\\b c", "d", "e"]),
    ('a"b"" c d', ['ab" c d']),
])
def test_winargv_matches_microsoft_examples(line, argv):
    assert winargv.split("prog " + line)[1:] == argv


###################### _make_args #####################################################################


def test_make_args_quotes_every_value():
    assert make_runner()._make_args(file_path="D:\\a b\\c.czi", is_FCS=True) == \
        ['--file_path="D:\\a b\\c.czi"', '--is_FCS="True"']


def test_make_args_drops_none():
    # "None" chosen in the GUI must give exactly the command line from before the second stage
    assert make_runner()._make_args(type="overview", selection_arguments=None) == ['--type="overview"']


###################### the whole way ##################################################################


def test_roundtrip_plain_values(monkeypatch):
    argv, parsed = roundtrip(monkeypatch, **BASE)

    assert argv[0] == SCRIPT
    assert parsed == expected(**BASE)


def test_roundtrip_paths_with_spaces(monkeypatch):
    args = dict(BASE, file_path="D:\\automation\\results\\my sample 1\\obj_x\\x_exp.czi",
                saving_path="D:\\automation\\temp\\my sample 1_x_measurements_points_reanalysis_xy.json")

    argv, parsed = roundtrip(monkeypatch, **args)

    assert parsed == expected(**args)


def test_roundtrip_without_selection_has_no_selection_flag(monkeypatch):
    argv, parsed = roundtrip(monkeypatch, selection_arguments=None, **BASE)

    assert "selection_arguments" not in parsed
    assert not any(a.startswith("--selection_arguments") for a in argv)


def test_roundtrip_with_selection(monkeypatch):
    argv, parsed = roundtrip(monkeypatch, selection_arguments="green_membrane", **BASE)

    assert parsed["selection_arguments"] == "green_membrane"


def test_roundtrip_value_with_equals_sign(monkeypatch):
    args = dict(BASE, analysis_arguments="a=b")

    argv, parsed = roundtrip(monkeypatch, **args)

    assert parsed["analysis_arguments"] == "a=b"


def test_is_fcs_arrives_as_string(monkeypatch):
    argv, parsed = roundtrip(monkeypatch, **dict(BASE, is_FCS=True))

    assert parsed["is_FCS"] == "True"


def test_run_adds_config_paths_and_env(monkeypatch):
    make_runner().run(**BASE)
    info = started()

    assert info.FileName == PYTHON_EXE
    assert info.WorkingDirectory == PROJECT
    assert info.EnvironmentVariables["PYTHONPATH"] == PROJECT
    assert info.UseShellExecute is False
    assert '--processing_config="{}"'.format(PROCESSING) in info.Arguments
    assert '--selection_config="{}"'.format(SELECTION) in info.Arguments


def test_run_argument_order_irrelevant(monkeypatch):
    # IronPython 2.7 dictionaries have no order, so kwargs reach _make_args in any order
    forward = roundtrip(monkeypatch, **BASE)[1]
    zen_fakes.FakeProcess.started = []
    backward = roundtrip(monkeypatch, **dict(reversed(list(BASE.items()))))[1]

    assert forward == backward


###################### known bugs #####################################################################


@pytest.mark.xfail(strict=True, reason=(
    "BUG execute_python.py:63-67: the script path is joined into Arguments unquoted, so a "
    "python_script with a space (D:\\my automation\\...) reaches python.exe as two arguments "
    "and python tries to run 'D:\\my'."))
def test_script_path_with_space_survives(monkeypatch):
    script = "D:\\my automation\\data_processing\\main_processor.py"

    argv, parsed = roundtrip(monkeypatch, runner=make_runner(script), **BASE)

    assert argv[0] == script
    assert parsed == expected(**BASE)


@pytest.mark.xfail(strict=True, reason=(
    "LATENT BUG execute_python.py:38 (_make_args): a value ending in a backslash becomes "
    "--k=\"D:\\dir\\\" and the C runtime reads \\\" as a literal quote, so the argument swallows "
    "the rest of the command line. Dormant today: every value passed is a file path, never a "
    "folder ending in a backslash."))
def test_value_with_trailing_backslash_survives(monkeypatch):
    args = dict(BASE, saving_path="D:\\automation\\temp\\")

    argv, parsed = roundtrip(monkeypatch, **args)

    assert parsed == expected(**args)
