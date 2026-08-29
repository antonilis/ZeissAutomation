from System.IO import Directory, Path

from zen_lib.runtime_config import log


###################### loading the adaptive experiment plugins ########################################
# An adaptive experiment is a function that rewrites an experiment just before it runs, using the
# properties of the object it is about to be run on. Those functions live in their own folder next
# to the macros, one file each, and are NOT imported.
#
# They cannot be imported, and this is now measured rather than assumed: probe_zen_context.czmac
# showed that a normally imported module sees no Zen, no ZenWindow and no ZenSpecialFolder, in its
# own namespace, in builtins, or through __main__. A plugin needs those names, so it is instead
# read and run in a namespace that already holds them - the macro's own - which is the same thing
# as pasting its text into the macro, only done by the code instead of by hand.
#
# That is why load_adaptive_functions has to be given the macro's globals(). Running the plugins in
# this module's namespace would put them somewhere Zen has never been.

# The experiment editing members are .NET extension methods on ZenExperiment, declared in
# Zeiss.Micro.LM.Scripting, and IronPython surfaces them only in a compilation unit that imported
# their namespace. ZEN does that when it compiles a macro; a plugin is compiled separately and
# therefore sees 71 members instead of 96. Prepending this line makes the plugin's own compilation
# unit import them too, and it is what makes an adaptive experiment work from a .py file at all.
# It is one line, so a line number in a plugin traceback is one higher than in the file.
PLUGIN_PREAMBLE = "import clr; import Zeiss.Micro.LM.Scripting; clr.ImportExtensions(Zeiss.Micro.LM.Scripting)\n"


def load_adaptive_functions(config, macro_globals):
    """
    Reads every plugin in the adaptive folder and returns the functions they registered.

    The decorator the plugins use is created here and put into the macro's namespace before they
    run, so that a plugin file needs nothing but @register_adaptive - the same way an analyser on
    the CPython side needs nothing but @register_class.

    :param RuntimeConfig config: configuration built by the macro, for the adaptive folder
    :param dict macro_globals: the macro's own globals(), which is where the plugins are run
    :return: dict of function name to function, empty when there are no plugins
    """
    functions = {}

    def register_adaptive(function):
        """
        Collects an adaptive experiment. The name of the decorated function is what the dropdown
        offers, the same way a class name is on the analysis side.
        :param function: the decorated function
        :return: the same function, unchanged
        """
        functions[function.__name__] = function

        return function

    macro_globals['register_adaptive'] = register_adaptive

    if not Directory.Exists(config.adaptive_path):
        log("No adaptive experiments: {} does not exist".format(config.adaptive_path))

        return functions

    for plugin_path in Directory.GetFiles(config.adaptive_path, "*.py"):

        # Files whose name starts with an underscore are helpers, not experiments
        if Path.GetFileName(plugin_path).startswith("_"):
            continue

        try:
            with open(plugin_path, "r") as plugin_file:
                plugin_source = plugin_file.read()

            exec(PLUGIN_PREAMBLE + plugin_source, macro_globals)

        except Exception as error:
            # One broken plugin must not stop an acquisition that does not use it
            log("Adaptive experiment {} could not be loaded: {}".format(plugin_path, error))

    log("Loaded adaptive experiments: {}".format(", ".join(sorted(functions)) or "none"))

    return functions
