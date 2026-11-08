"""
The logic of installer/ (download.py, install.py, common.py). The .bat files themselves only
fetch Python and start these scripts; they can only be run on Windows.
"""
import json
import os

import pytest

from load_module import load

common = load("installer/common.py", "installer_common_under_test")
install = load("installer/install.py", "installer_install_under_test")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "ZeissAPI", "config", "path_config.example.json")

with open(TEMPLATE) as _f:
    TEMPLATE_VALUES = json.load(_f)


###################### path_config.json ###############################################################


def test_built_config_has_exactly_the_template_keys():
    assert sorted(common.build_path_config("D:\\automation", "D:\\zeiss\\Pictures")) == sorted(TEMPLATE_VALUES)


def test_built_config_for_d_automation_is_the_template():
    # The template describes the layout on the microscope PC: built for the same folder, every path
    # must come out the same, except Python, which is now the portable one of the bundle
    built = common.build_path_config("D:\\automation", "D:\\zeiss\\Pictures")

    assert built.pop("python_exe") == "D:\\automation\\env\\python\\python.exe"
    assert built == {k: v for k, v in TEMPLATE_VALUES.items() if k != "python_exe"}


def test_built_config_is_read_by_runtime_config(zen_disk):
    # The contract with World A: what the installer writes is what the macro reads
    from zen_lib.runtime_config import RuntimeConfig

    path = "E:\\zeiss_auto\\ZeissAPI\\config\\path_config.json"
    zen_disk.write_file(path, json.dumps(common.build_path_config("E:\\zeiss_auto", "E:\\zen_autosave")))

    config = RuntimeConfig(path)

    assert config.python_exe == "E:\\zeiss_auto\\env\\python\\python.exe"
    assert config.python_project_root == "E:\\zeiss_auto\\"
    assert config.results == "E:\\zeiss_auto\\results\\"
    assert config.zeiss_temp == "E:\\zen_autosave\\"


@pytest.mark.parametrize("recorded, moved", [
    ("D:\\automation\\", False),
    ("d:\\AUTOMATION", False),
    ("E:\\automation\\", True),
    ("", True),
])
def test_was_moved(recorded, moved):
    assert common.was_moved({"python_project_root": recorded}, "D:\\automation") is moved


def test_update_project_paths_keeps_what_only_the_user_knows():
    current = dict(common.build_path_config("D:\\old", "D:\\zen_saves"), extra_key="mine")

    updated = common.update_project_paths(current, "E:\\new")

    assert updated["results_path"] == "E:\\new\\results\\"
    assert updated["python_exe"] == "E:\\new\\env\\python\\python.exe"
    assert updated["zeiss_temp_file"] == "D:\\zen_saves\\"
    assert updated["extra_key"] == "mine"


def test_missing_keys():
    assert common.missing_keys({"a": 1}, {"a": 1, "b": 2, "c": 3}) == ["b", "c"]


###################### install.py: path_config on disk ################################################


@pytest.fixture
def api(tmp_path):
    """A ZeissAPI folder with its template, as it lies in ZEN's macro folder after copying."""
    config = tmp_path / "ZeissAPI" / "config"
    config.mkdir(parents=True)
    (config / "path_config.example.json").write_text(json.dumps(TEMPLATE_VALUES))
    return tmp_path / "ZeissAPI"


def no_questions(*args, **kwargs):
    raise AssertionError("asked a question it should not have: {}".format(args))


def test_make_path_config_creates_it(api, monkeypatch):
    monkeypatch.setattr(install, "ROOT", "D:\\automation")

    live = install.make_path_config(str(api), ask_text=lambda q, d: "D:\\zeiss\\Pictures", confirm=no_questions)

    with open(live) as f:
        assert json.load(f) == common.build_path_config("D:\\automation", "D:\\zeiss\\Pictures")


def test_make_path_config_follows_a_moved_folder(api, monkeypatch):
    monkeypatch.setattr(install, "ROOT", "E:\\new")
    live = api / "config" / "path_config.json"
    live.write_text(json.dumps(common.build_path_config("D:\\old", "D:\\zen_saves")))

    install.make_path_config(str(api), ask_text=no_questions, confirm=lambda q: True)

    data = json.loads(live.read_text())
    assert data["python_project_root"] == "E:\\new\\"
    assert data["zeiss_temp_file"] == "D:\\zen_saves\\"


def test_make_path_config_leaves_paths_when_declined(api, monkeypatch):
    monkeypatch.setattr(install, "ROOT", "E:\\new")
    live = api / "config" / "path_config.json"
    live.write_text(json.dumps(common.build_path_config("D:\\old", "D:\\zen_saves")))

    install.make_path_config(str(api), ask_text=no_questions, confirm=lambda q: False)

    assert json.loads(live.read_text())["python_project_root"] == "D:\\old\\"


def test_make_path_config_adds_a_missing_key(api, monkeypatch):
    monkeypatch.setattr(install, "ROOT", "D:\\automation")
    live = api / "config" / "path_config.json"
    old = common.build_path_config("D:\\automation", "D:\\zeiss\\Pictures")
    del old["last_setup_path"]
    live.write_text(json.dumps(old))

    install.make_path_config(str(api), ask_text=no_questions, confirm=no_questions)

    assert json.loads(live.read_text())["last_setup_path"] == "D:\\automation\\last_setup.json"


###################### install.py: copying ZeissAPI ###################################################


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "project" / "ZeissAPI"
    (src / "config").mkdir(parents=True)
    (src / "zen_lib" / "__pycache__").mkdir(parents=True)
    (src / "main_macro.czmac").write_text("new macro")
    (src / "config" / "processing_config.json").write_text("{}")
    (src / "config" / "path_config.json").write_text("the developer's own paths")
    (src / "zen_lib" / "__pycache__" / "x.pyc").write_text("cache")
    return src


def test_copy_into_an_empty_macro_folder(source, tmp_path):
    macros = tmp_path / "zen_macros"
    macros.mkdir()

    target = install.copy_zeissapi(str(source), str(macros), confirm=no_questions)

    assert (macros / "ZeissAPI" / "main_macro.czmac").read_text() == "new macro"
    # never ship one machine's paths to another
    assert not (macros / "ZeissAPI" / "config" / "path_config.json").exists()
    assert not (macros / "ZeissAPI" / "zen_lib" / "__pycache__").exists()
    assert target == str(macros / "ZeissAPI")


def test_copy_replaces_everything_but_the_machine_path_config(source, tmp_path):
    old = tmp_path / "zen_macros" / "ZeissAPI"
    (old / "config").mkdir(parents=True)
    (old / "main_macro.czmac").write_text("old macro")
    (old / "removed_since.py").write_text("stale")
    (old / "config" / "path_config.json").write_text("this machine's paths")

    install.copy_zeissapi(str(source), str(old.parent), confirm=lambda q: True)

    assert (old / "main_macro.czmac").read_text() == "new macro"
    assert not (old / "removed_since.py").exists()
    assert (old / "config" / "path_config.json").read_text() == "this machine's paths"


def test_copy_declined_leaves_everything(source, tmp_path):
    old = tmp_path / "zen_macros" / "ZeissAPI"
    old.mkdir(parents=True)
    (old / "main_macro.czmac").write_text("old macro")

    assert install.copy_zeissapi(str(source), str(old.parent), confirm=lambda q: False) is None
    assert (old / "main_macro.czmac").read_text() == "old macro"


###################### install.py: refusing what cannot work ##########################################


def test_refuses_a_folder_with_spaces(tmp_path, monkeypatch):
    root = tmp_path / "my automation"
    (root / "env" / "wheels").mkdir(parents=True)
    (root / "env" / "variant.json").write_text('{"torch": "cpu"}')
    monkeypatch.setattr(install, "ROOT", str(root))
    monkeypatch.setattr(install, "WHEELS", str(root / "env" / "wheels"))
    monkeypatch.setattr(install, "VARIANT_FILE", str(root / "env" / "variant.json"))

    with pytest.raises(SystemExit):
        install.check_bundle()


def test_refuses_a_missing_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "WHEELS", str(tmp_path / "env" / "wheels"))
    monkeypatch.setattr(install, "VARIANT_FILE", str(tmp_path / "env" / "variant.json"))

    with pytest.raises(SystemExit):
        install.check_bundle()


###################### the .bat files #################################################################


@pytest.mark.parametrize("name", ["download.bat", "install.bat"])
def test_bat_files_are_ascii_with_crlf(name):
    with open(os.path.join(ROOT, name), "rb") as f:
        data = f.read()

    data.decode("ascii")
    assert data.count(b"\r\n") == data.count(b"\n")


@pytest.mark.parametrize("name, script", [("download.bat", "download.py"), ("install.bat", "install.py")])
def test_bat_files_start_a_script_that_exists(name, script):
    with open(os.path.join(ROOT, name)) as f:
        assert "installer\\{}".format(script) in f.read()
    assert os.path.isfile(os.path.join(ROOT, "installer", script))
