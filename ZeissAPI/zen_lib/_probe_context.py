###################### diagnostic module, delete once the question is answered ########################
# This file exists to answer one question: what can a NORMALLY IMPORTED module inside zen_lib
# see of the names ZEN injects into a macro?
#
# It has to live here, in zen_lib, and it has to be reached by a plain import, because that is
# exactly the situation being measured. Running the same checks from an exec'd string would
# measure the plugin mechanism instead, which is already understood.
#
# Two independent mechanisms are tested, and they must not be confused:
#
#   A. name visibility - is there any way for this module to reach Zen on its own?
#      Checked against this module's globals, against builtins, and against __main__.
#
#   B. extension methods - once a ZenExperiment is in hand, do the experiment editing members
#      appear here after clr.ImportExtensions at the top of THIS file? This is expected to
#      work, and the point is to confirm it in a module rather than in an exec'd plugin.
#
# Nothing here moves the stage, executes an experiment, activates anything or writes a file.
# It calls GetByName, dir, hasattr and getattr, and nothing else.

import sys


###################### mechanism B: extension methods, imported in THIS compilation unit ##############
# These three lines are the whole fix for the missing experiment editing members. They are at the
# top level of this module on purpose: IronPython surfaces extension methods only in the
# compilation unit that imported their namespace, and this file is its own compilation unit.

EXTENSIONS_IMPORTED = False
EXTENSIONS_ERROR = None

try:
    import clr
    import Zeiss.Micro.LM.Scripting

    clr.ImportExtensions(Zeiss.Micro.LM.Scripting)

    EXTENSIONS_IMPORTED = True

except Exception as _error:
    EXTENSIONS_ERROR = str(_error)


# The names ZEN puts into a macro that this project actually uses
INJECTED_NAMES = ("Zen", "ZenWindow", "ZenSpecialFolder")

# Members that are extension methods, absent unless the compilation unit imported them
EXTENSION_TARGETS = ("ClearTileRegionsAndPositions",
                     "ClearExperimentRegionsAndPositions",
                     "AddSinglePosition")


###################### mechanism A: where could a name possibly come from #############################


def _builtins_module():
    """
    The builtins module under whichever name this interpreter uses.
    :return: the module object
    """
    try:
        import __builtin__ as module

    except ImportError:
        import builtins as module

    return module


def _in_module_globals(name):
    """
    Is the name in this module's own globals? Expected to be false: the import machinery
    starts a module with an almost empty namespace.
    :param str name: name to look for
    :return: bool
    """
    return name in globals()


def _in_builtins(name):
    """
    Is the name in builtins? This is the one realistic way a plain import could see Zen for
    free, because builtins is shared by every module in the process.
    :param str name: name to look for
    :return: bool
    """
    return hasattr(_builtins_module(), name)


def _in_main_module(name):
    """
    Is the name on the __main__ module? If ZEN runs a macro as __main__, its namespace would be
    reachable from here through sys.modules, which is a back door rather than a design, but a
    working one.
    :param str name: name to look for
    :return: bool or str when there is no __main__ at all
    """
    main_module = sys.modules.get("__main__")

    if main_module is None:
        return "no __main__ in sys.modules"

    return hasattr(main_module, name)


def _modules_holding(name, limit=12):
    """
    Every already loaded module whose namespace holds the name. Answers "if not builtins, then
    where did ZEN actually put it", which is worth knowing even when the answer is unusable.
    :param str name: name to look for
    :param int limit: how many module names to report
    :return: list of module names
    """
    holders = []

    for module_name in sorted(sys.modules):
        module = sys.modules.get(module_name)

        if module is None:
            continue

        try:
            if hasattr(module, name):
                holders.append(module_name)

        except Exception:
            # A half initialised module can raise on attribute access, and that is not
            # an answer to anything asked here
            continue

        if len(holders) == limit:
            break

    return holders


def zen_reachable_from_here():
    """
    The Zen object this module can get hold of without anybody handing it one, or None.
    The three sources are tried in the order of how much they would be worth: own globals,
    builtins, then the __main__ back door.
    :return: the Zen object or None
    """
    if "Zen" in globals():
        return globals()["Zen"]

    builtins_module = _builtins_module()

    if hasattr(builtins_module, "Zen"):
        return getattr(builtins_module, "Zen")

    main_module = sys.modules.get("__main__")

    if main_module is not None and hasattr(main_module, "Zen"):
        return getattr(main_module, "Zen")

    return None


###################### putting an experiment in front of both mechanisms ##############################


def _experiment_lines(label, zen, experiment_name):
    """
    Loads an experiment through the given Zen and reports what it looks like from inside this
    module. GetByName only reads, and SetActive is deliberately not called.
    :param str label: what to call this case in the report
    :param zen: the Zen object to use, or None
    :param str experiment_name: name of an existing .czexp
    :return: list of report lines
    """
    lines = []

    if zen is None:
        lines.append("    {}: no Zen available, nothing to test".format(label))

        return lines

    try:
        experiment = zen.Acquisition.Experiments.GetByName(experiment_name)

    except Exception as error:
        lines.append("    {}: GetByName failed: {}".format(label, error))

        return lines

    members = dir(experiment)

    lines.append("    {}: len(dir(exp)) is {}".format(label, len(members)))

    for target in EXTENSION_TARGETS:
        lines.append("        {} present: {}".format(target, target in members))

    return lines


def experiment_members(zen, experiment_name):
    """
    The members a ZenExperiment appears to have when dir() is called from inside THIS module.
    Kept apart from _experiment_lines, which only formats counts, because the macro has to
    compare this list against its own: the difference between them is the only way to name the
    members that a macro has and an imported module does not.
    :param zen: the Zen object handed over by the macro
    :param str experiment_name: name of an existing .czexp
    :return: list of member names
    """
    return dir(zen.Acquisition.Experiments.GetByName(experiment_name))


def report(zen_from_macro=None, experiment_name=None):
    """
    Runs every check and returns the result as text. The macro passes its own Zen in, so that
    the fallback of handing the object over explicitly is measured in the same run as the
    attempts to find it without help.
    :param zen_from_macro: the Zen object taken from the macro's namespace
    :param str experiment_name: name of an existing .czexp to load, or None to skip mechanism B
    :return: list of report lines
    """
    lines = []

    lines.append("probe module file: {}".format(globals().get("__file__", "unknown")))
    lines.append("probe module name: {}".format(__name__))
    lines.append("")

    lines.append("=== A. can this module see the injected names on its own ===")

    for name in INJECTED_NAMES:
        lines.append("  {}".format(name))
        lines.append("    in this module's globals : {}".format(_in_module_globals(name)))
        lines.append("    in builtins              : {}".format(_in_builtins(name)))
        lines.append("    on __main__              : {}".format(_in_main_module(name)))

    lines.append("")
    lines.append("  loaded modules whose namespace holds 'Zen':")

    holders = _modules_holding("Zen")

    if holders:
        for holder in holders:
            lines.append("    {}".format(holder))
    else:
        lines.append("    none")

    lines.append("")
    lines.append("  Zen reachable from here without help: {}".format(
        zen_reachable_from_here() is not None))

    lines.append("")
    lines.append("=== B. extension methods inside an imported module ===")
    lines.append("  clr.ImportExtensions at the top of this file succeeded: {}".format(
        EXTENSIONS_IMPORTED))

    if EXTENSIONS_ERROR is not None:
        lines.append("  it failed with: {}".format(EXTENSIONS_ERROR))

    if experiment_name is None:
        lines.append("  no experiment name was given, skipping")

        return lines

    lines.append("  experiment: {}".format(experiment_name))

    lines.extend(_experiment_lines("using the Zen found by this module",
                                   zen_reachable_from_here(), experiment_name))

    lines.extend(_experiment_lines("using the Zen handed over by the macro",
                                   zen_from_macro, experiment_name))

    return lines
