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
PREPROCESSING_CONFIG_NAME = "preprocessing_config.json"

# Fallback log file, used before path_config.json has been read and when it does not
# name one. It is written next to the macros, in the same folder as the config, so that
# a failure to load the configuration is recorded right where the configuration lives
# and no drive letter has to be hardcoded.
BOOTSTRAP_LOG_NAME = "zen_log.txt"

_log_path = None


def macro_directory():
    """
    Return the ZEN runtime folder of this project, that is the folder holding the
    macros and their helper modules.
    :return: str absolute path to the folder containing this module
    """
    try:
        return Path.GetDirectoryName(Path.GetFullPath(__file__))
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


def preprocessing_config_file():
    """
    :return: str absolute path to preprocessing_config.json
    """
    return Path.Combine(config_dir(), PREPROCESSING_CONFIG_NAME)


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

        # The CPython installation started by PythonAnalysisRunner
        self.python_exe = self.config["python_exe"]
        self.python_script = self.config["python_script"]
        self.python_project_root = self.config["python_project_root"]

        # Passed to the CPython side on the command line, so that it does not have to
        # guess where the config folder is
        self.preprocessing_config_path = preprocessing_config_file()

        log("Loaded path configuration from {}".format(self.config_path))
        log("Logging to {}".format(self.log_path))

    def preprocessing_config(self):
        """
        Read the named analysis presets. Used by the macro to fill the GUI dropdowns.
        :return: dict of preset name to analysis arguments
        """
        return read_json(self.preprocessing_config_path)
