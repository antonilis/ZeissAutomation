import time

# System.Windows is not loaded into ZEN's IronPython by default. ZenApi imports this module only when
# it is asked for a count rate, so a failure here can never stop an acquisition that does not use it.
import clr
clr.AddReference("WindowsBase")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")

from System import Action, Enum, TimeSpan
from System.Threading import Thread, ThreadStart
from System.Windows import Application
from System.Windows.Media import VisualTreeHelper
from System.Windows.Threading import DispatcherOperationStatus, DispatcherPriority


###################### the detector counting panel of FCS #############################################
# The count rate ZEN shows during an FCS measurement has no scripting API. It is read from the panel
# on screen, whose DataContext in the WPF visual tree is an FcsDetectorCountingViewModel. Measured
# with diagnostics/probe_fcs_live_values.czmac:
#
#   - the macro runs on the UI thread, and Execute keeps that thread running, so a second thread can
#     hand it a reading while the macro waits for Execute to return
#   - the panel keeps showing the PREVIOUS measurement until its list empties, about 2 s after the
#     start. A value counts only after the list has been seen empty
#   - the first fresh value comes about 3.8 s after the start, so an experiment read this way has to
#     run for longer than that
#
# The early values of a measurement are not reliable: right after a large drop in power the panel
# showed the old level for over a second. The reader therefore keeps the LAST fresh value.

VIEW_MODEL_NAME = "FcsDetectorCountingViewModel"

SAMPLE_SECONDS = 0.5        # pause between readings of the panel
UI_WAIT_SECONDS = 3.0       # how long one reading waits for the UI thread
MAX_SAMPLES = 3600          # a stop, in case a measurement never reports its end


def find_view_model():
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

            if context is not None and context.GetType().Name == VIEW_MODEL_NAME:
                return context

            for index in xrange(VisualTreeHelper.GetChildrenCount(element)):
                stack.append(VisualTreeHelper.GetChild(element, index))

    return None


def count_rate_method(view_model):
    """
    :return: the member of the DetectorCountingMethod enum that shows the count rate
    :raise ValueError: when the enum has no such member
    """
    for method in Enum.GetValues(view_model.SelectedCountingMethod.GetType()):
        if "countrate" in str(method).lower():
            return method

    raise ValueError("the detector counting panel has no count rate method")


def parse_khz(text):
    """
    :param str text: what the panel shows, such as '37.568 kHz'
    :return: the number as a float, or None when there is none
    """
    try:
        return float(text.split()[0].replace(",", "."))
    except (IndexError, ValueError):
        return None


class CountRateReader:
    """
    Reads the panel from a second thread while something else keeps the macro's thread busy.

    param view_model: the FcsDetectorCountingViewModel from find_view_model
    """

    def __init__(self, view_model):

        self.view_model = view_model
        self.stop = False
        self.fresh = False
        self.count_rate = None

    def _tick(self):
        """
        One reading, on the UI thread. An exception here must end neither the thread nor the
        measurement, so a reading that fails counts as no reading.
        """
        try:
            values = [str(entry.Value) for entry in self.view_model.CountRateValues]

            if len(values) == 0:
                self.fresh = True
                return

            number = parse_khz(values[0])

            if self.fresh and number is not None:
                self.count_rate = number

        except Exception:
            pass

    def _loop(self):
        dispatcher = Application.Current.Dispatcher

        for index in xrange(MAX_SAMPLES):
            if self.stop:
                return

            operation = dispatcher.BeginInvoke(DispatcherPriority.Normal, Action(self._tick))

            if operation.Wait(TimeSpan.FromSeconds(UI_WAIT_SECONDS)) != DispatcherOperationStatus.Completed:
                operation.Abort()

            time.sleep(SAMPLE_SECONDS)

    def read_during(self, measurement):
        """
        :param measurement: function without arguments that runs the measurement and returns at its end
        :return: float the last fresh count rate in kHz, or None when the panel gave none
        """
        thread = Thread(ThreadStart(self._loop))
        thread.IsBackground = True
        thread.Start()

        try:
            measurement()
        finally:
            self.stop = True
            thread.Join(TimeSpan.FromSeconds(UI_WAIT_SECONDS + SAMPLE_SECONDS + 1))

        return self.count_rate
