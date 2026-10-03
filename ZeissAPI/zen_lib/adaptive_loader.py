import sys

from System.IO import Directory, Path

from zen_lib.runtime_config import log


###################### loading the adaptive experiment plugins ########################################
# An adaptive experiment is a function that rewrites an experiment just before it runs, using the
# properties of the object it is about to be run on. Those functions live in the adaptive/ package
# next to the macros, one file each, and are imported like any other module.
#
# They used to be read and exec'd in the macro's own namespace, because a plugin needed Zen and the
# experiment editing extension methods, and an imported module has neither. Both now reach a plugin
# through ZenApi, which the macro builds from the names ZEN injects and which imports the extension
# methods into its own compilation unit. A plugin never touches ZEN directly - it calls ctx.zen_api -
# so it needs nothing an ordinary module does not have.
#
# The adaptive package is dropped from sys.modules before it is imported, exactly the way the macros
# drop zen_lib. An edited plugin is therefore what runs, and the state a plugin keeps at module level
# (the learned focus offset, the detector background) starts empty at every macro run.

# Filled by @register_adaptive while the plugins are imported. This module is itself re-imported at
# every macro run, because the macros drop zen_lib, so the registry never outlives one run either.
_REGISTRY = {}


def register_adaptive(function):
    """
    Collects an adaptive experiment. The name of the decorated function is what the dropdown
    offers, the same way a class name is on the analysis side.
    :param function: the decorated function, taking an AdaptiveContext
    :return: the same function, unchanged
    """
    _REGISTRY[function.__name__] = function

    return function


class AdaptiveContext:
    """
    Everything an adaptive function is handed about the experiment it is about to rewrite.

    One object rather than a list of arguments, so that a field added later does not break the
    plugins that do not use it.

    param ZenApi zen_api: the only way a plugin touches the microscope
    param str experiment: name of the experiment about to run
    param str obj_id: the id the RESULT PATH is built from - None with object finding switched off,
    because the results are then filed under the overview point rather than under an obj_ folder
    param str stage: the pipeline stage, '_exp', '_reanalysis_z' or '_post'
    param dict obj: the record of the object the experiment is about to run on, or None when object
    finding is switched off and the pipeline is only visiting overview points. A plugin must cope
    with both.
    param str name: name of the overview point
    param PathManager path_manager: builds the result folder, so that a plugin's own files land next
    to what the experiment produces
    """

    def __init__(self, zen_api, experiment, obj_id, stage, obj, name, path_manager):

        self.zen_api = zen_api
        self.experiment = experiment
        self.obj_id = obj_id
        self.stage = stage
        self.obj = obj
        self.name = name
        self.path_manager = path_manager

    def result_dir(self):
        """
        The folder the experiment's results are saved in, created if missing.
        :return: str path to the folder
        """
        return self.path_manager.result_dir(self.obj_id, self.stage, self.name)


def load_adaptive_functions(config):
    """
    Imports every plugin in the adaptive folder and returns the functions they registered.

    :param RuntimeConfig config: configuration built by the macro, for the adaptive folder
    :return: dict of function name to function, empty when there are no plugins
    """
    _REGISTRY.clear()

    for cached in [name for name in sys.modules if name == "adaptive" or name.startswith("adaptive.")]:
        del sys.modules[cached]

    if not Directory.Exists(config.adaptive_path):
        log("No adaptive experiments: {} does not exist".format(config.adaptive_path))

        return dict(_REGISTRY)

    for plugin_path in Directory.GetFiles(config.adaptive_path, "*.py"):

        module_name = Path.GetFileNameWithoutExtension(plugin_path)

        # Files whose name starts with an underscore are helpers, not experiments - __init__ among them
        if module_name.startswith("_"):
            continue

        try:
            __import__("adaptive." + module_name)

        except Exception as error:
            # One broken plugin must not stop an acquisition that does not use it
            log("Adaptive experiment {} could not be loaded: {}".format(plugin_path, error))

            continue

        # The package resolves through sys.path, the folder through RuntimeConfig. They are the same
        # folder unless a second copy of adaptive/ is on the path, and then the wrong code would run.
        loaded_from = Path.GetDirectoryName(Path.GetFullPath(sys.modules["adaptive." + module_name].__file__))

        if loaded_from.rstrip("\\/").lower() != Path.GetFullPath(config.adaptive_path).rstrip("\\/").lower():
            log("WARNING: adaptive.{} was loaded from {}, not from {}".format(
                module_name, loaded_from, config.adaptive_path))

    log("Loaded adaptive experiments: {} from {}".format(
        ", ".join(sorted(_REGISTRY)) or "none", config.adaptive_path))

    return dict(_REGISTRY)
