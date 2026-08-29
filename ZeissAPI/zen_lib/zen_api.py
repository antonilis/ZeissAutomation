import time

from System.IO import Path, File

from zen_lib.runtime_config import log
from zen_lib.path_manager_main_macro import PathManager


###################### extension methods, imported into THIS compilation unit #########################
# The experiment editing members - ClearExperimentRegionsAndPositions, AddSinglePosition and about
# twenty more - are .NET extension methods on ZenExperiment, not members of it. IronPython surfaces
# an extension method only in the compilation unit that imported its namespace, and every .py file
# is its own compilation unit. That is why these lines cannot be moved into a shared helper: a
# function in another module would import them into that module's scope and not into this one.
#
# Measured with probe_zen_context.czmac: an imported module sees 71 members without this, 95 with
# it, and the macro itself sees 96. The one member of the difference is IsZenConnectImage, from the
# correlative workspace add-on, which is why that namespace is imported below as well.

import clr

import Zeiss.Micro.LM.Scripting
clr.ImportExtensions(Zeiss.Micro.LM.Scripting)

# Guarded, because an add-on that is not installed makes the import itself raise, and a missing
# add-on must never stop an acquisition that does not use it.
try:
    import Zeiss.Micro.CorrelativeWorkspace.Scripting
    clr.ImportExtensions(Zeiss.Micro.CorrelativeWorkspace.Scripting)

except Exception as _error:
    log("Correlative workspace extensions are not available: {}".format(_error))

# The gap between a macro and a module was measured for ZenExperiment only. Other types take their
# extension methods from other namespaces, listed in docs/zen_api/extension-methods.md. If a member
# that the ZEN documentation promises turns out to be missing here, add the namespace the same way
# as above: Zeiss.Micro.Trainable.Scripting (Intellesis), Zeiss.Micro.Cryo.Processing.Scripting,
# Zeiss.Micro.BioFormatsImport.Scripting, Zeiss.Micro.AMP.CustomSampleDetectionBase.


###################### the ZEN runtime, handed over by the macro ######################################


class ZenApi:
    """
    Everything this project does to the microscope, and the names ZEN injects to do it with.

    ZEN puts about 500 names into a MACRO's namespace - Zen, ZenWindow, ZenSpecialFolder and the
    rest. An imported module gets none of them: it starts with an almost empty namespace of its
    own, they are not in builtins, and there is no __main__ to reach through. That was measured,
    not assumed, by probe_zen_context.czmac. So the macro hands them over here, exactly the way it
    already hands over RuntimeConfig, and library code takes this object instead of reaching for
    a global that does not exist outside a macro.

    param zen: the Zen object from the macro's namespace
    param window_class: the ZenWindow class from the macro's namespace, used by zen_gui
    param special_folder: the ZenSpecialFolder enum from the macro's namespace
    param RuntimeConfig config: configuration built by the macro
    """

    def __init__(self, zen, window_class, special_folder, config):

        self.zen = zen
        self.window_class = window_class
        self.special_folder = special_folder
        self.config = config

        # Built once rather than per call. PathManager only copies paths out of the configuration,
        # it creates nothing and touches no file, so there is nothing to delay.
        self.path_manager = PathManager(config)

    def get_stage_focus_position(self):
        """
        Return current stage (X, Y) and focus (Z) positions as [x,y,z] list.
        :return: list of the x, y, z coordinates of the stage position
        """
        x = self.zen.Devices.Stage.ActualPositionX
        y = self.zen.Devices.Stage.ActualPositionY
        z = self.zen.Devices.Focus.ActualPosition

        return [x, y, z]

    def move(self, points_to_move):
        """
        Move stage and focus to the given [X, Y, Z] coordinates.
        :param list points_to_move: [x, y, z] in stage micrometres
        :return: None
        """
        self.zen.Devices.Stage.MoveTo(points_to_move[0], points_to_move[1])
        self.zen.Devices.Focus.MoveTo(points_to_move[2])

    def load_experiment(self, chosen_experiment):
        """
        Load and activate an experiment (.czexp file) by name.
        :param str chosen_experiment: name of the experiment as saved in ZEN
        :return: None
        """
        exp = self.zen.Acquisition.Experiments.GetByName(chosen_experiment)
        exp.SetActive()
        time.sleep(2)  # Rest for hardware adjustment
        log("Loaded experiment {}".format(chosen_experiment))

    def execute_current_experiment(self):
        """
        Execute the currently active experiment.
        :return: None
        """
        self.zen.Acquisition.Execute(self.zen.Acquisition.Experiments.ActiveExperiment)
        time.sleep(2)  # Rest for hardware adjustment

    def get_experiment(self, chosen_experiment):
        """
        The experiment object itself, without activating it. Used where something has to be read
        off an experiment rather than run, such as the tile regions of an overview grid.
        :param str chosen_experiment: name of the experiment as saved in ZEN
        :return: the ZenExperiment
        """
        return self.zen.Acquisition.Experiments.GetByName(chosen_experiment)

    def active_document(self):
        """
        The document ZEN currently has open, or None. It is None after an FCS experiment, which is
        how the calling code tells the two kinds of result apart.
        :return: the active document or None
        """
        return self.zen.Application.Documents.ActiveDocument

    def remove_all_documents(self):
        """
        Close everything ZEN has open, to keep a long run from filling up with result windows.
        :return: None
        """
        self.zen.Application.Documents.RemoveAll()

    def user_documents_folder(self):
        """
        The Documents folder ZEN saves user content in, which is where the .czexp experiments live.
        :return: str path to the folder
        """
        return self.zen.Application.Environment.GetFolderPath(self.special_folder.UserDocuments)

    def save_experiment_result(self, name, base_name=None):
        """
        Saves the results of the experiments in the results folder. For the .czi files it utilizes
        the API call, but for .fcs and .raw files it moves them from autosave folder.
        :param str name: full path to save to, or the folder to move the FCS results into
        :param str base_name: name the moved FCS and raw files are built from
        :return: None
        """
        document = self.active_document()

        if document is not None:  # The document is None for the .fcs experiments
            document.Save(name)

        else:
            files = self.path_manager.get_latest_fcs_and_raws()

            log(str(files))

            for file in files:
                file_name = Path.GetFileNameWithoutExtension(file)
                extenion = Path.GetExtension(file)

                parts = file_name.split("_")

                if len(parts) > 1:

                    final_name = "{}_{}{}".format(base_name, "_".join(parts[1:]), extenion)

                else:

                    final_name = "{}{}".format(base_name, extenion)

                File.Move(file, Path.Combine(name, final_name))
