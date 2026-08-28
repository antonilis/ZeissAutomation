from System.IO import Directory, Path, File
import json


###################### configuration location #########################################################
# This module is the ONLY place that knows where the configuration lives.
#
# The config folder belongs to the ZEN runtime: it sits next to the macros, in the
# same folder as this file. It is therefore found relative to this module rather
# than relative to ZEN's working directory, which is not something a macro can rely
# on, and never as an absolute "D:\..." literal.
#
# Everything else - PathManager, PythonAnalysisRunner, AcquisitionPipeline, and the
# CPython side started by the runner - receives its paths from a RuntimeConfig
# object built here, and does not read the configuration itself.

CONFIG_DIR_NAME = "config"
PATH_CONFIG_NAME = "path_config.json"
PROCESSING_CONFIG_NAME = "processing_config.json"
SELECTION_CONFIG_NAME = "selection_config.json"

# Folder holding the adaptive experiment plugins. They are not imported: main_macro reads
# each file and runs it in its own namespace, which is the only way a file outside the macro
# can reach the names ZEN injects into it.
ADAPTIVE_DIR_NAME = "adaptive"

# Fallback log file, used before path_config.json has been read and when it does not
# name one. It is written next to the macros, in the same folder as the config, so that
# a failure to load the configuration is recorded right where the configuration lives
# and no drive letter has to be hardcoded.
BOOTSTRAP_LOG_NAME = "zen_log.txt"

# Fallback destination of the settings of the last run, used when path_config.json does not
# name one. Same rule as the log above: a missing key must not stop an acquisition, the file
# then simply lives next to the macros.
LAST_SETUP_NAME = "last_setup.json"

_log_path = None


def macro_directory():
    """
    Return the ZEN runtime folder of this project, that is the folder holding the
    macros, the config folder and the adaptive plugins.
    :return: str absolute path to the folder one level above this module
    """
    try:
        # This module lives in zen_lib, one level below the macros, so the folder that matters
        # is the parent of the one holding this file
        return Path.GetDirectoryName(Path.GetDirectoryName(Path.GetFullPath(__file__)))
    except Exception:
        # __file__ is undefined when code is pasted straight into the ZEN editor
        # instead of being imported. Fall back to the working directory, which is
        # what the old ".\config\..." literals assumed.
        return Directory.GetCurrentDirectory()


def config_dir():
    """
    :return: str absolute path to the config folder inside the ZEN runtime folder
    """
    return Path.Combine(macro_directory(), CONFIG_DIR_NAME)


def path_config_file():
    """
    :return: str absolute path to path_config.json
    """
    return Path.Combine(config_dir(), PATH_CONFIG_NAME)


def processing_config_file():
    """
    :return: str absolute path to processing_config.json
    """
    return Path.Combine(config_dir(), PROCESSING_CONFIG_NAME)


def selection_config_file():
    """
    :return: str absolute path to selection_config.json
    """
    return Path.Combine(config_dir(), SELECTION_CONFIG_NAME)


def adaptive_dir():
    """
    :return: str absolute path to the folder with the adaptive experiment plugins
    """
    return Path.Combine(macro_directory(), ADAPTIVE_DIR_NAME)


def read_json(path):
    """
    Read a JSON file.
    :param str path: full path to the file
    :return: dict or list with the parsed content
    """
    with open(path, "r") as file:
        data = json.load(file)

    return data


###################### logging ########################################################################
# One log function for the whole ZEN side. Its destination comes from "log_path" in
# path_config.json and is set once, when RuntimeConfig is built.


def bootstrap_log_path():
    """
    Fallback destination of log(), next to the macros. Resolved on demand rather than at
    import time, so that it follows the same rule as the config folder.
    :return: str full path to the fallback log file
    """
    return Path.Combine(macro_directory(), BOOTSTRAP_LOG_NAME)


def default_last_setup_path():
    """
    Fallback destination of the saved setup, next to the macros.
    :return: str full path to the saved setup
    """
    return Path.Combine(macro_directory(), LAST_SETUP_NAME)


def set_log_path(path):
    """
    Point the logger at the file configured in path_config.json.
    :param str path: full path to the log file
    :return: None
    """
    global _log_path
    _log_path = path


def log(msg):
    """
    Function for printing the logs to the txt file
    :param str msg: log to be printed
    :return: None
    """
    path = _log_path or bootstrap_log_path()

    with open(path, "a") as f:
        f.write(msg + "\n")


###################### runtime configuration ##########################################################


class RuntimeConfig:
    """
    Single source of truth for every path used by the automation. It is built once at
    the start of a macro and passed to PathManager, PythonAnalysisRunner and
    AcquisitionPipeline, so that no other module has to locate the config folder.

    param str config_path: full path to path_config.json, defaults to the copy in the
    config folder next to the macros
    """

    def __init__(self, config_path=None):

        self.config_path = config_path or path_config_file()
        self.config = read_json(self.config_path)

        # Destination of every log() call on the ZEN side
        self.log_path = self.config.get("log_path", bootstrap_log_path())
        set_log_path(self.log_path)

        # Directories the pipeline reads from and writes to
        self.results = self.config["results_path"]
        self.measurements = self.config["measuring_points_path"]
        self.analysis = self.config["image_for_analysis_path"]
        self.zeiss_temp = self.config["zeiss_temp_file"]

        # Where main_macro records the settings it was last run with, so that the next run can
        # start from them instead of from an empty set of dropdowns
        self.last_setup_path = self.config.get("last_setup_path", default_last_setup_path())

        # The CPython installation started by PythonAnalysisRunner
        self.python_exe = self.config["python_exe"]
        self.python_script = self.config["python_script"]
        self.python_project_root = self.config["python_project_root"]

        # Passed to the CPython side on the command line, so that it does not have to
        # guess where the config folder is
        self.processing_config_path = processing_config_file()
        self.selection_config_path = selection_config_file()

        # Read by main_macro itself rather than handed to World B: the plugins in there are
        # ZEN code and never leave this side
        self.adaptive_path = adaptive_dir()

        log("Loaded path configuration from {}".format(self.config_path))
        log("Logging to {}".format(self.log_path))

    def processing_config(self):
        """
        Read the named analysis presets. Used by the macro to fill the GUI dropdowns.
        :return: dict of preset name to analysis arguments
        """
        return read_json(self.processing_config_path)

    def selection_config(self):
        """
        Read the named object selection presets. The object selection is an optional second stage,
        so a file that is not there means that there is nothing to choose from, not that the
        configuration is broken: the macro then offers "None" alone and runs exactly as it did
        before the second stage existed.
        :return: dict of preset name to selection arguments, empty when the file does not exist
        """
        if not File.Exists(self.selection_config_path):
            log("No object selection presets: {} does not exist".format(self.selection_config_path))

            return {}

        return read_json(self.selection_config_path)
