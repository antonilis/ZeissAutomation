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
# It is also why every call that edits an experiment lives in ZenApi and nowhere else. The adaptive
# plugins call these methods instead of the extension methods themselves, so this file stays the one
# compilation unit that needs the import. A plugin that needs a new edit gets a new method here.
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


###################### the detector counting panel of FCS #############################################
# The count rate ZEN shows during an FCS measurement has no scripting API. It is read from the panel
# on screen, whose DataContext in the WPF visual tree is an FcsDetectorCountingViewModel. Measured
# with diagnostics/probe_fcs_live_values.czmac:
#
#   - the macro runs on the UI thread, and Execute keeps that thread running, so a second thread can
#     hand it a reading while the macro waits for Execute to return
#   - the panel keeps showing the PREVIOUS measurement until its list empties, about 2 s after the
#     start, for about a second. Readings can be up to 1.6 s apart then, because starting a measurement
#     keeps the UI thread busy, so the empty list can be missed. A value therefore counts once the
#     list has been seen empty OR once it differs from what the panel showed before the start
#   - the panel keeps its last value after the measurement, so one more reading is taken at the end
#   - the first fresh value comes about 3.8 s after the start, so an experiment read this way has to
#     run for longer than that
#
# The early values of a measurement are not reliable: right after a large drop in power the panel
# showed the old level for over a second, in one measurement until about 5 s after the start. The
# reading therefore keeps the LAST fresh value.
#
# The panel shows one method at a time. Reading the count rate first and counts per molecule after it
# took the count rate from those unreliable early values, so with counts per molecule the panel
# alternates between the two, and each keeps its last value. The reading right after a switch is
# skipped, because it may still show the other method. Switching once within a measurement was
# measured; switching repeatedly was not, the first run with it is what verifies it.

# System.Windows is not loaded into ZEN's IronPython by default. Guarded, because a failure here must
# never stop an acquisition that does not read the panel; reading it then raises a NameError.
try:
    clr.AddReference("WindowsBase")
    clr.AddReference("PresentationCore")
    clr.AddReference("PresentationFramework")

    from System import Action, Enum, TimeSpan
    from System.Threading import Thread, ThreadStart
    from System.Windows import Application
    from System.Windows.Media import VisualTreeHelper
    from System.Windows.Threading import DispatcherOperationStatus, DispatcherPriority

except Exception as _error:
    log("WPF is not available, the FCS count rate cannot be read: {}".format(_error))

FCS_VIEW_MODEL_NAME = "FcsDetectorCountingViewModel"

FCS_SAMPLE_SECONDS = 0.5        # pause between readings of the panel
FCS_UI_WAIT_SECONDS = 3.0       # how long one reading waits for the UI thread
FCS_MAX_SAMPLES = 3600          # a stop, in case a measurement never reports its end


def _find_fcs_view_model():
    """
    Walks the windows of ZEN for the view model of the panel. Has to run on the UI thread, the only
    one allowed to touch them.
    :return: the view model, or None when the panel is not open
    """
    for window in Application.Current.Windows:
        stack = [window]

        while stack:
            element = stack.pop()
            context = getattr(element, "DataContext", None)

            if context is not None and context.GetType().Name == FCS_VIEW_MODEL_NAME:
                return context

            for index in xrange(VisualTreeHelper.GetChildrenCount(element)):
                stack.append(VisualTreeHelper.GetChild(element, index))

    return None


def _fcs_method(view_model, word):
    """
    :param str word: part of the name of the method, in lower case
    :return: the member of the DetectorCountingMethod enum with word in its name
    :raise ValueError: when the enum has no such member
    """
    for method in Enum.GetValues(view_model.SelectedCountingMethod.GetType()):
        if word in str(method).lower():
            return method

    raise ValueError("the detector counting panel has no {} method".format(word))


def _parse_khz(text):
    """
    :param str text: what the panel shows, such as '37.568 kHz'
    :return: the number as a float, or None when there is none
    """
    try:
        return float(text.split()[0].replace(",", "."))
    except (IndexError, ValueError):
        return None


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

    Every method below runs a call that has already run on the instrument, either in the pipeline
    or in one of the adaptive plugins before they were moved onto this class.

    param zen: the Zen object from the macro's namespace
    param window_class: the ZenWindow class from the macro's namespace, used by zen_gui
    param special_folder: the ZenSpecialFolder enum from the macro's namespace
    param pixel_type: the ZenPixelType enum from the macro's namespace, for reading pixels
    param RuntimeConfig config: configuration built by the macro
    """

    def __init__(self, zen, window_class, special_folder, pixel_type, config):

        self.zen = zen
        self.window_class = window_class
        self.special_folder = special_folder
        self.pixel_type = pixel_type
        self.config = config

        # Built once rather than per call. PathManager only copies paths out of the configuration,
        # it creates nothing and touches no file, so there is nothing to delay.
        self.path_manager = PathManager(config)

        # The view model of the FCS detector counting panel, found once per run, see fcs_panel_reading
        self.fcs_view_model = None

    ###################### stage and focus #############################################################

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

    def focus_z(self):
        """
        :return: the current focus position in micrometres
        """
        return self.zen.Devices.Focus.ActualPosition

    def move_focus(self, z):
        """
        Move the focus only, leaving the stage where it is.
        :param float z: focus position in micrometres
        :return: None
        """
        self.zen.Devices.Focus.MoveTo(z)

    def objective_magnification(self):
        """
        :return: int magnification of the objective in the light path, e.g. 40
        """
        return int(round(self.zen.Devices.ObjectiveChanger.Magnification))

    ###################### focusing ####################################################################

    def find_surface(self):
        """
        Definite Focus: moves the focus onto the cover-slip surface it detects. Raises when it fails.
        Measured at 40x: ~5 s, repeats to 0.01-0.09 um.
        :return: the focus z it settled at
        """
        self.zen.Acquisition.FindSurface()

        return self.focus_z()

    def autofocus(self, experiment_name):
        """
        Software autofocus with the autofocus settings stored in the named experiment, which is left
        active. Raises when the autofocus fails.
        :param str experiment_name: name of the experiment as saved in ZEN
        :return: the focus z it settled at
        """
        self.activate_experiment(experiment_name)

        self.zen.Acquisition.FindAutofocus(self.zen.Acquisition.Experiments.ActiveExperiment, timeoutSeconds=0)

        return self.focus_z()

    ###################### experiments #################################################################

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

    def activate_experiment(self, experiment_name):
        """
        Make an experiment the active one, without the pause and the log line of load_experiment -
        for the plugins, which switch experiments several times per well.
        :param str experiment_name: name of the experiment as saved in ZEN
        :return: the ZenExperiment
        """
        experiment = self.zen.Acquisition.Experiments.GetByName(experiment_name)
        experiment.SetActive()

        return experiment

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

    def set_single_positions(self, experiment_name, points):
        """
        Replaces every tile region and position of the experiment with single positions, and leaves
        it active. Extension methods, which is why this has to live in this file.
        :param str experiment_name: name of the experiment as saved in ZEN
        :param list points: [x, y, z] in stage micrometres, one per position
        :return: None
        """
        experiment = self.zen.Acquisition.Experiments.GetByName(experiment_name)

        experiment.ClearExperimentRegionsAndPositions(0)
        experiment.ClearTileRegionsAndPositions(0)

        for x, y, z in points:
            experiment.AddSinglePosition(blockIndex=0, x=x, y=y, z=z)

        experiment.SetActive()

    def _dimension_setups(self, experiment_name):
        """
        Every setup of the acquisition block, however deep. With Tiles switched on the tracks do not sit
        in the block itself but under RegionsSetup and TilesSetup.
        :return: list of the setups
        """
        experiment = self.zen.Acquisition.Experiments.GetByName(experiment_name)

        setups = []
        waiting = list(experiment.Core.CurrentExperimentBlock.SubDimensionSetups)

        while waiting:
            setup = waiting.pop()
            setups.append(setup)
            waiting.extend(setup.SubDimensionSetups)

        return setups

    def center_z_stack(self, experiment_name, z):
        """
        Moves the z-stack of the experiment so that its centre is at z, keeping its range and interval.
        A z-stack runs between absolute positions, the ones the Center button of the Z-Stack tool sets,
        and not around the current focus. It lives in the internal .Core layer, like the laser power,
        and the change is in memory only.
        :param str experiment_name: name of the experiment as saved in ZEN
        :param float z: focus position of the centre in micrometres
        :return: tuple (first, last) of the z-stack after the change
        """
        for setup in self._dimension_setups(experiment_name):
            if hasattr(setup, "IsCenterMode"):
                half_range = (setup.Last - setup.First) / 2.0
                setup.Define(z - half_range, z + half_range, setup.Interval)

                return setup.First, setup.Last

        raise ValueError("Experiment {} has no z-stack".format(experiment_name))

    ###################### laser power #################################################################
    # The power lives in the internal .Core layer, found along the path in docs/zen_api/acquisition.md.
    # It is unversioned, so this is the one place to fix after a ZEN update. The change is in memory
    # only - the .czexp on disk is untouched unless the experiment is saved from ZEN.

    def _laser_intensity(self, experiment_name, laser_line):
        """
        The Intensity parameter of a laser line in the experiment's active track. Looked up again on
        every call, because a plugin may have switched to another experiment and back in between.
        :return: the Parameter object, or None when the experiment has no such laser line
        """
        for setup in self._dimension_setups(experiment_name):
            if not hasattr(setup, "ActivatedTracks"):
                continue

            for track in setup.ActivatedTracks:
                for collection in track.SelectedDetectionModeSetup.TrackLaserSettings.ParameterCollections:
                    if str(collection.Id) == laser_line:
                        return collection["Intensity"]

        return None

    def get_laser_power(self, experiment_name, laser_line):
        """
        :param str experiment_name: name of the experiment as saved in ZEN
        :param str laser_line: id of the laser line, e.g. 'MTBLKM980LaserLine639'
        :return: float power in percent, or None when the experiment has no such laser line
        """
        intensity = self._laser_intensity(experiment_name, laser_line)

        if intensity is None:
            return None

        return float(intensity.Value)

    def set_laser_power(self, experiment_name, laser_line, percent):
        """
        Sets the power the next acquisition of the experiment uses. Measured: the signal follows it
        linearly, and ZEN writes the power used into the .czi (LightSourceSettings/Transmission).
        :param str experiment_name: name of the experiment as saved in ZEN
        :param str laser_line: id of the laser line, e.g. 'MTBLKM980LaserLine639'
        :param float percent: power in percent
        :return: float power read back from the experiment
        :raise ValueError: when the experiment has no such laser line
        """
        intensity = self._laser_intensity(experiment_name, laser_line)

        if intensity is None:
            raise ValueError("{} has no laser line {}".format(experiment_name, laser_line))

        # The parameter's Value is a string in percent ('0.2'), not a number
        intensity.Value = str(percent)

        return float(intensity.Value)

    ###################### FCS count rate ##############################################################

    def _fcs_panel_values(self):
        return [str(entry.Value) for entry in self.fcs_view_model.CountRateValues]

    def _fcs_panel_tick(self, reading):
        """
        One reading of the panel, on the UI thread. An exception here must end neither the thread nor
        the measurement, so a reading that fails counts as no reading.
        :param dict reading: the state of the reading, see fcs_panel_reading
        """
        try:
            values = self._fcs_panel_values()

            if values not in reading["seen"]:
                reading["seen"].append(values)

            if len(values) == 0 or values != reading["stale"]:
                reading["fresh"] = True

            if len(values) == 0:
                return

            if reading["skip"]:
                reading["skip"] = False
                return

            number = _parse_khz(values[0])

            if not reading["fresh"] or number is None:
                return

            showing_count_rate = str(self.fcs_view_model.SelectedCountingMethod) == str(reading["count_method"])

            if showing_count_rate:
                reading["count_rate_khz"] = number
            else:
                reading["cpm_khz"] = number

            if reading["cpm_method"] is not None:
                self.fcs_view_model.SelectedCountingMethod = (
                    reading["cpm_method"] if showing_count_rate else reading["count_method"])
                reading["skip"] = True

        except Exception:
            pass

    def _fcs_panel_loop(self, reading):
        dispatcher = Application.Current.Dispatcher

        for index in xrange(FCS_MAX_SAMPLES):
            if reading["stop"]:
                return

            operation = dispatcher.BeginInvoke(DispatcherPriority.Normal,
                                               Action(lambda: self._fcs_panel_tick(reading)))

            if operation.Wait(TimeSpan.FromSeconds(FCS_UI_WAIT_SECONDS)) != DispatcherOperationStatus.Completed:
                operation.Abort()

            time.sleep(FCS_SAMPLE_SECONDS)

    def fcs_panel_reading(self, experiment_name, with_cpm=False):
        """
        Runs an FCS experiment and reads ZEN's detector counting panel, which has to be open, live from
        a second thread. Measured with diagnostics/probe_fcs_live_values.czmac, see the top of this file.
        The panel is put back on the method it showed. The view model is found once and kept: that is
        how it read seven measurements in a row, while searching again before every measurement read
        the first one and then nothing, probably because the windows then hold more than one.
        :param str experiment_name: name of the experiment as saved in ZEN
        :param bool with_cpm: also read counts per molecule, which the experiment needs longer for
        :return: dict with the last count_rate_khz and cpm_khz of the measurement, None for a value the
        panel did not give
        :raise ValueError: when the panel is not open
        """
        if self.fcs_view_model is None:
            self.fcs_view_model = _find_fcs_view_model()

        view_model = self.fcs_view_model

        if view_model is None:
            raise ValueError("the detector counting panel is not open")

        experiment = self.zen.Acquisition.Experiments.GetByName(experiment_name)
        original_method = view_model.SelectedCountingMethod

        reading = {"count_method": _fcs_method(view_model, "countrate"),
                   "cpm_method": _fcs_method(view_model, "molecule") if with_cpm else None,
                   "count_rate_khz": None, "cpm_khz": None, "stop": False, "fresh": False, "skip": False,
                   "stale": None,   # what the panel showed before the start
                   "seen": []}      # everything it showed, for the log when no value came

        view_model.SelectedCountingMethod = reading["count_method"]

        try:
            reading["stale"] = self._fcs_panel_values()

            thread = Thread(ThreadStart(lambda: self._fcs_panel_loop(reading)))
            thread.IsBackground = True
            thread.Start()

            try:
                self.zen.Acquisition.Execute(experiment)
            finally:
                reading["stop"] = True
                thread.Join(TimeSpan.FromSeconds(FCS_UI_WAIT_SECONDS + FCS_SAMPLE_SECONDS + 1))

            # The macro runs on the UI thread, so this reading needs no hand-over
            self._fcs_panel_tick(reading)

        finally:
            view_model.SelectedCountingMethod = original_method

        if reading["count_rate_khz"] is None or (with_cpm and reading["cpm_khz"] is None):
            log("fcs_panel_reading: a value is missing, the panel showed {}".format(reading["seen"]))

        time.sleep(2)  # Rest for hardware adjustment

        return {"count_rate_khz": reading["count_rate_khz"], "cpm_khz": reading["cpm_khz"]}

    ###################### pixels ######################################################################

    def frame_statistics(self, experiment_name, pixel_step):
        """
        Acquires one frame of the experiment with its current settings and returns statistics of the
        counts. The frame is not saved. CopyPixelsToArray returns raw bytes; for Gray16 every pixel
        is two of them, low byte first.
        :param str experiment_name: name of the experiment as saved in ZEN
        :param int pixel_step: every n-th pixel goes into the statistics
        :return: dict with mean, median and p99, in counts
        """
        experiment = self.zen.Acquisition.Experiments.GetByName(experiment_name)
        image = self.zen.Acquisition.AcquireImage(experiment)

        try:
            data = image.CopyPixelsToArray(self.pixel_type.Gray16)
        finally:
            image.Close()

        values = sorted(data[i] + 256 * data[i + 1] for i in xrange(0, data.Length - 1, 2 * pixel_step))
        count = len(values)

        return {
            "mean": float(sum(values)) / count,
            "median": float(values[count // 2]),
            "p99": float(values[int(count * 0.99)]),
        }

    ###################### documents and results #######################################################

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
