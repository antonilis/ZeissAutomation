import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# Sets the laser power of an FCS experiment so that its count rate comes out at the target, the way
# smart_SLB_imaging does it for an image:
#
#   1. run SMART_FCS_SCAN_EXPERIMENT, a short FCS measurement, at the first power and read the count
#      rate from ZEN's detector counting panel
#   2. the count rate follows the power, so power = first * target / count rate. Close enough to the
#      target already and it stops here
#   3. otherwise one more short measurement at that power, and the same step once more
#   4. set that power in the experiment; the pipeline then runs it
#
# The limit is the count rate that must not be passed. The target has to sit below it, so a reading
# above the limit only means the power goes down; it is written to the log and the record. The very
# first reading can pass it, as it is one short measurement at a power chosen before seeing the sample.
#
# Before running: open the detector counting panel with its averaging set as wanted, and make
# SMART_FCS_SCAN_EXPERIMENT run for about 6 s - the panel gives its first fresh value after about 3.8 s.
# Without the panel, or with no signal, the power of the experiment stays as it is.
#
# Reading the panel is in zen_lib/fcs_panel.py; the route was measured with
# diagnostics/probe_fcs_live_values.czmac, on an LSM 880 with ZEN 2 blue.
#
# The power is changed in memory only, never in the .czexp. It stays at the last value after the run,
# so do not save the experiments from ZEN afterwards unless that is what you want. The short
# measurements leave their .fcs and .raw files in ZEN's autosave folder; only the real experiment is
# moved to the results. smart_FCS.json next to it records the readings the power was chosen from.


###################### settings ########################################################################

SMART_FCS_FIRST_POWER = 1.0         # % - where a person would start on this sample
SMART_FCS_TARGET_KHZ = 40.0         # count rate the experiment should run at
SMART_FCS_LIMIT_KHZ = 50.0          # count rate that must not be passed

SMART_FCS_SCAN_EXPERIMENT = "scan_FCS"
SMART_FCS_LASER_LINE = "MTBLKM980LaserLine639"

SMART_FCS_TOLERANCE = 0.1           # within this fraction of the target no more measurements are made
SMART_FCS_MIN_SIGNAL_KHZ = 1.0      # below this the reading is "no signal", the step would run away
SMART_FCS_MIN_POWER = 0.01          # %
SMART_FCS_MAX_POWER = 10.0          # %


###################### helpers ########################################################################


def _smart_fcs_step(power, count_rate):
    """
    The power that should bring the count rate to the target, assuming that it follows the power.
    :return: power in %, within the allowed range
    """
    target = min(SMART_FCS_TARGET_KHZ, SMART_FCS_LIMIT_KHZ)
    power = power * target / count_rate

    return round(min(max(power, SMART_FCS_MIN_POWER), SMART_FCS_MAX_POWER), 4)


def _smart_fcs_close_enough(count_rate):
    return abs(count_rate - SMART_FCS_TARGET_KHZ) <= SMART_FCS_TOLERANCE * SMART_FCS_TARGET_KHZ


def _smart_fcs_usable(count_rate):
    return count_rate is not None and count_rate >= SMART_FCS_MIN_SIGNAL_KHZ


def _smart_fcs_measure(zen_api, power, readings):
    """
    One short measurement at the power, recorded in readings.
    :return: float count rate in kHz, or None when the panel gave none
    """
    zen_api.load_experiment(SMART_FCS_SCAN_EXPERIMENT)
    zen_api.set_laser_power(SMART_FCS_SCAN_EXPERIMENT, SMART_FCS_LASER_LINE, power)

    count_rate = zen_api.fcs_count_rate(SMART_FCS_SCAN_EXPERIMENT)
    readings.append({"power_percent": power, "count_rate_khz": count_rate})
    log("smart_FCS: {} % -> {} kHz".format(power, count_rate))

    if count_rate is not None and count_rate > SMART_FCS_LIMIT_KHZ:
        log("smart_FCS: WARNING - above the limit of {} kHz".format(SMART_FCS_LIMIT_KHZ))

    return count_rate


def _smart_fcs_find_power(zen_api, readings):
    """
    The power for the target from at most two short measurements.
    :return: power in %, or None when no usable reading came from the first one
    """
    power = SMART_FCS_FIRST_POWER
    count_rate = _smart_fcs_measure(zen_api, power, readings)

    if not _smart_fcs_usable(count_rate):
        return None

    if _smart_fcs_close_enough(count_rate):
        return power

    power = _smart_fcs_step(power, count_rate)
    count_rate = _smart_fcs_measure(zen_api, power, readings)

    # The first step is still the best estimate when the second reading gives nothing
    if not _smart_fcs_usable(count_rate) or _smart_fcs_close_enough(count_rate):
        return power

    return _smart_fcs_step(power, count_rate)


###################### the adaptive experiment ########################################################


@register_adaptive
def smart_FCS(ctx):
    """
    Chooses the laser power of the FCS experiment from at most two short measurements, so that its
    count rate comes out at SMART_FCS_TARGET_KHZ. ctx.obj is not used: the power depends on the spot,
    not on an object, so the function works the same with and without object finding.
    """
    zen_api = ctx.zen_api
    experiment = ctx.experiment

    zen_api.activate_experiment(experiment)

    if zen_api.get_laser_power(experiment, SMART_FCS_LASER_LINE) is None:
        log("smart_FCS: {} has no {} - power left unchanged".format(experiment, SMART_FCS_LASER_LINE))
        return

    readings = []

    try:
        chosen = _smart_fcs_find_power(zen_api, readings)
    except Exception as error:
        chosen = None
        log("smart_FCS: {} - power left unchanged".format(error))

    zen_api.activate_experiment(experiment)

    if chosen is None:
        log("smart_FCS: WARNING - no usable count rate, empty spot or out of focus? {} stays at its own "
            "power".format(experiment))
    else:
        chosen = zen_api.set_laser_power(experiment, SMART_FCS_LASER_LINE, chosen)
        log("smart_FCS: set {} to {} %".format(SMART_FCS_LASER_LINE, chosen))

    record = {
        "experiment": experiment,
        "scan_experiment": SMART_FCS_SCAN_EXPERIMENT,
        "laser_line": SMART_FCS_LASER_LINE,
        "first_power_percent": SMART_FCS_FIRST_POWER,
        "target_khz": SMART_FCS_TARGET_KHZ,
        "limit_khz": SMART_FCS_LIMIT_KHZ,
        "readings": readings,
        "chosen_power_percent": chosen,
    }

    with open(Path.Combine(ctx.result_dir(), "smart_FCS.json"), "w") as record_file:
        json.dump(record, record_file, indent=2)
