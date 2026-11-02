"""
RuntimeConfig is the single source of truth for every path of a run, and runtime_config the
only module that knows where the config folder is.
"""
import json
import os

import pytest

from zen_lib import runtime_config
from zen_lib.runtime_config import RuntimeConfig

CONFIG_PATH = "D:\\automation\\ZeissAPI\\config\\path_config.json"

REQUIRED = {
    "results_path": "D:\\automation\\results\\",
    "measuring_points_path": "D:\\automation\\temp\\",
    "image_for_analysis_path": "D:\\automation\\image_for_analysis\\",
    "zeiss_temp_file": "D:\\zeiss\\Pictures\\",
    "python_exe": "D:\\automation\\venv\\Scripts\\python.exe",
    "python_script": "D:\\automation\\data_processing\\main_processor.py",
    "python_project_root": "D:\\automation\\",
}
OPTIONAL = {
    "log_path": "D:\\automation\\zen_log.txt",
    "last_setup_path": "D:\\automation\\last_setup.json",
}


def write_config(disk, values):
    disk.write_file(CONFIG_PATH, json.dumps(values))


@pytest.fixture
def example_path(repo_root):
    return os.path.join(repo_root, "ZeissAPI", "config", "path_config.example.json")


###################### a missing or incomplete path_config.json #######################################


def test_missing_path_config_raises_with_template_name(zen_disk):
    with pytest.raises(IOError) as error:
        RuntimeConfig(CONFIG_PATH)

    assert "path_config.example.json" in str(error.value)
    assert "path_config.example.json" in zen_disk.read_file(runtime_config._log_path)


@pytest.mark.parametrize("key", sorted(REQUIRED))
def test_missing_required_key_raises(zen_disk, key):
    values = dict(REQUIRED, **OPTIONAL)
    del values[key]
    write_config(zen_disk, values)

    with pytest.raises(KeyError, match=key):
        RuntimeConfig(CONFIG_PATH)


###################### optional keys fall back next to the macros #####################################


def test_log_path_defaults_next_to_macros(zen_disk):
    write_config(zen_disk, REQUIRED)

    config = RuntimeConfig(CONFIG_PATH)

    assert config.log_path == runtime_config.macro_directory() + "\\zen_log.txt"


def test_log_path_from_config_is_used(zen_disk):
    write_config(zen_disk, dict(REQUIRED, **OPTIONAL))

    RuntimeConfig(CONFIG_PATH)
    runtime_config.log("hello")

    assert "hello" in zen_disk.read_file(OPTIONAL["log_path"])


def test_last_setup_path_defaults_next_to_macros(zen_disk):
    write_config(zen_disk, REQUIRED)

    config = RuntimeConfig(CONFIG_PATH)

    assert config.last_setup_path == runtime_config.macro_directory() + "\\last_setup.json"


def test_values_are_taken_verbatim(zen_disk):
    write_config(zen_disk, dict(REQUIRED, **OPTIONAL))

    config = RuntimeConfig(CONFIG_PATH)

    assert (config.results, config.measurements, config.analysis, config.zeiss_temp) == (
        REQUIRED["results_path"], REQUIRED["measuring_points_path"],
        REQUIRED["image_for_analysis_path"], REQUIRED["zeiss_temp_file"])
    assert (config.python_exe, config.python_script, config.python_project_root) == (
        REQUIRED["python_exe"], REQUIRED["python_script"], REQUIRED["python_project_root"])


###################### where the config folder is #####################################################


def test_macro_directory_is_parent_of_zen_lib():
    # runtime_config.py sits in ZeissAPI/zen_lib, one level below the macros
    assert runtime_config.macro_directory().endswith("\\ZeissAPI")


def test_config_files_live_in_config_dir(zen_disk):
    write_config(zen_disk, REQUIRED)
    macros = runtime_config.macro_directory()

    config = RuntimeConfig(CONFIG_PATH)

    assert config.processing_config_path == macros + "\\config\\processing_config.json"
    assert config.selection_config_path == macros + "\\config\\selection_config.json"
    assert config.adaptive_path == macros + "\\adaptive"


def test_missing_selection_config_returns_empty_dict(zen_disk):
    # The object selection is optional: no file means nothing to choose from, not an error
    write_config(zen_disk, REQUIRED)
    config = RuntimeConfig(CONFIG_PATH)

    assert config.selection_config() == {}
    assert "No object selection presets" in zen_disk.read_file(runtime_config._log_path)


###################### the template in the repository ################################################


def test_example_path_config_has_every_required_key(example_path):
    config = RuntimeConfig(example_path)

    assert config.results  # reading every key is what the constructor does


@pytest.mark.parametrize("key", sorted(list(REQUIRED) + list(OPTIONAL)))
def test_example_path_config_values_are_absolute_windows_paths(example_path, key):
    with open(example_path) as f:
        values = json.load(f)

    assert key in values
    assert values[key][1:3] == ":\\", values[key]


###################### the presets name analysers that exist ##########################################
# Importing the registries imports every analyser, and with them cellpose, torch and skimage.
# Without those installed the two tests are skipped, not failed.


def _import_or_skip(package):
    try:
        return __import__(package, fromlist=["*"])
    except ImportError as error:
        pytest.skip("{} cannot be imported here: {}".format(package, error))


def test_processing_presets_name_registered_analysers(repo_root):
    _import_or_skip("data_processing.image_analysis")
    from data_processing.image_analysis.analysis_registry import get_available_analysis

    with open(os.path.join(repo_root, "ZeissAPI", "config", "processing_config.json")) as f:
        presets = json.load(f)

    for name, preset in presets.items():
        assert preset["chosen_analysis"] in get_available_analysis(), name


def test_selection_presets_name_registered_selections(repo_root):
    _import_or_skip("data_processing.object_selection")
    from data_processing.object_selection.selection_registry import get_available_selections

    with open(os.path.join(repo_root, "ZeissAPI", "config", "selection_config.json")) as f:
        presets = json.load(f)

    for name, preset in presets.items():
        assert preset["chosen_selection"] in get_available_selections(), name
