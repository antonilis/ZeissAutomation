from System.IO import Directory, Path

from zen_lib.runtime_config import log


###################### the windows both macros build the same way #####################################
# The windows themselves stay in the macros: their order is the logic of the dialogue and reads
# best next to the decisions it makes. What lives here is only what both macros were doing
# identically - listing the saved experiments, refusing to continue after a cancel, and saying
# what is wrong before anything moves.
#
# Every function takes the ZenApi object, because ZenWindow and ZenSpecialFolder are injected into
# a macro's namespace and are not visible from an imported module.

EXPERIMENT_FOLDER_NAME = "Experiment Setups"
EXPERIMENT_EXTENSION = "*.czexp"


def list_experiments(zeiss_api):
    """
    Names of the experiments saved in ZEN, without the .czexp extension, which is what the
    dropdowns offer and what Zen.Acquisition.Experiments.GetByName expects.
    :param ZenApi zeiss_api: the ZEN runtime handed over by the macro
    :return: list of experiment names
    """
    docfolder = zeiss_api.user_documents_folder()
    expfiles = Directory.GetFiles(Path.Combine(docfolder, EXPERIMENT_FOLDER_NAME), EXPERIMENT_EXTENSION)

    return [Path.GetFileNameWithoutExtension(item) for item in expfiles]


def show_or_exit(window):
    """
    Shows a window and ends the macro if it was cancelled. Continuing past a cancelled window
    would read the selections out of a dialogue the user had just abandoned, which is how a run
    ends up doing something nobody confirmed.
    :param window: the ZenWindow to show
    :return: the result object
    """
    result = window.Show()

    if not result or result.HasCanceled:
        raise SystemExit

    return result


def show_problems(zeiss_api, problems, title="Cannot start"):
    """
    Shows what is wrong and ends the macro. Nothing has moved by the time this is called, which is
    the whole reason the checks run before the pipeline is built.
    :param ZenApi zeiss_api: the ZEN runtime handed over by the macro
    :param list problems: messages to show
    :param str title: heading of the window
    :return: None, it never returns
    """
    log("Setup rejected: {}".format(problems))

    problems_window = zeiss_api.window_class()
    problems_window.Initialize(title)
    problems_window.AddMultiLineTextBox('problems_box', 'Fix these and run the macro again:',
                                        "\n\n".join(problems))
    problems_window.Show()

    raise SystemExit
