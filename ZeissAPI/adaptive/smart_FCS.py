import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# Sets the laser power of an FCS experiment from at most two short measurements, the way
# smart_SLB_imaging does it for an image:
#
#   1. focus, as the focus setting says
#   2. run scan_experiment, a short FCS measurement, at first_power and read ZEN's detector counting panel
#   3. work out the next power from the mode. Close enough to the power just used and it stops here
#   4. otherwise one more short measurement at that power, and the same step once more
#   5. set that power in the experiment; the pipeline then runs it
#
# The settings are the "smart_FCS" entry of config/adaptive_config.json:
#
#   mode            "constant_cpm": the same counts per molecule in every well, target_cpm_khz, which
#                   needs a longer scan. "constant_counts": the same count rate, target_khz
#   limit_khz       the power is held to what keeps the count rate at this, in both modes, assuming it
#                   follows the power, so the last step can pass it by a few percent. In a
#                   concentrated well it is the limit that decides the power, not the CPM. The very first
#                   reading can pass it, as it is made at a power chosen before seeing the sample
#   focus           "none", "surface" for Definite Focus, or "surface_offset" for Definite Focus and the
#                   offset of the objective from surface_offsets in path_config.json. A bilayer needs the
#                   offset; in solution it would put the spot at the level of the bilayer, on the glass
#   tolerance       a step smaller than this fraction of the power ends the search
#   min_signal_khz  below this the reading is "no signal", the step would run away
#   min_power, max_power, in %. Keep max_power low: a CPM read too low must not drive the power into
#                   saturation
#
# Before running: open the detector counting panel with its averaging set as wanted, and make
# scan_experiment run for about 10 s with constant_cpm and 6 s with constant_counts - the panel gives its
# first fresh value after about 3.8 s and then shows the two values in turn. It has to see the sample the
# way the experiment does, so the same detector, filters and pinhole: a scan on another detector read
# 4.9 times too low. Without the panel, or with no signal, the experiment runs at its own power.
#
# The power is changed in memory only, never in the .czexp. It stays at the last value after the run,
# so do not save the experiments from ZEN afterwards unless that is what you want. The short
# measurements leave their .fcs and .raw files in ZEN's autosave folder; only the real experiment is
# moved to the results. smart_FCS.json next to it records the readings the power was chosen from.


###################### state, empty at every macro run ################################################

# The power each experiment came with. Read once, because after the first well the experiment holds
# the power of the well before it
_SMART_FCS_OWN_POWER = {}


###################### helpers ########################################################################


def _smart_fcs_focus(ctx):
    """
    Focuses as the settings say. A failure leaves the focus where it is, the measurement still runs.
    """
    zen_api = ctx.zen_api
    focus = ctx.settings["focus"]

    if focus == "none":
        return

    try:
        surface = zen_api.find_surface()

        if focus == "surface_offset":
            magnification = str(zen_api.objective_magnification())

            if magnification not in ctx.surface_offsets:
                log("smart_FCS: WARNING - no surface offset for a {}x objective, staying on the "
                    "surface".format(magnification))
                return

            zen_api.move_focus(surface + ctx.surface_offsets[magnification])

    except Exception as error:
        log("smart_FCS: focusing failed, staying at the current z - {}".format(error))


def _smart_fcs_step(settings, power, reading):
    """
    The next power, assuming that the count rate and the CPM follow the power.
    :return: power in %, within the limit and the allowed range
    :raise ValueError: when the mode is not known
    """
    mode = settings["mode"]
    count_rate = reading["count_rate_khz"]

    if mode == "constant_counts":
        wanted = power * settings["target_khz"] / count_rate

    elif mode == "constant_cpm":
        cpm = reading["cpm_khz"]

        # With no CPM the power can only be held, the limit below still applies
        wanted = power * settings["target_cpm_khz"] / cpm if cpm is not None and cpm > 0 else power

    else:
        raise ValueError("unknown mode {}".format(mode))

    wanted = min(wanted, power * settings["limit_khz"] / count_rate)
    allowed = min(max(wanted, settings["min_power"]), settings["max_power"])

    if allowed != wanted:
        log("smart_FCS: {:.4f} % is outside {} - {} %".format(
            wanted, settings["min_power"], settings["max_power"]))

    return round(allowed, 4)


def _smart_fcs_close_enough(settings, power, next_power):
    """
    A step to the end of the allowed range is always taken, however small: the target is out of reach then, and the
    end of the range is as near to it as the power can get.
    """
    if next_power != power and (next_power >= settings["max_power"] or next_power <= settings["min_power"]):
        return False

    return abs(next_power - power) <= settings["tolerance"] * power


def _smart_fcs_usable(settings, reading):
    return reading["count_rate_khz"] is not None and reading["count_rate_khz"] >= settings["min_signal_khz"]


def _smart_fcs_measure(ctx, power, readings):
    """
    One short measurement at the power, recorded in readings.
    :return: dict with count_rate_khz and cpm_khz, None for what the panel did not give
    """
    zen_api = ctx.zen_api
    settings = ctx.settings
    scan = settings["scan_experiment"]

    zen_api.load_experiment(scan)
    zen_api.set_laser_power(scan, settings["laser_line"], power)

    reading = zen_api.fcs_panel_reading(scan, with_cpm=settings["mode"] == "constant_cpm")
    count_rate = reading["count_rate_khz"]
    cpm = reading["cpm_khz"]

    readings.append({"power_percent": power, "count_rate_khz": count_rate, "cpm_khz": cpm,
                     "molecules": count_rate / cpm if count_rate is not None and cpm else None})
    log("smart_FCS: {} % -> {} kHz, CPM {} kHz".format(power, count_rate, cpm))

    if count_rate is not None and count_rate > settings["limit_khz"]:
        log("smart_FCS: WARNING - above the limit of {} kHz".format(settings["limit_khz"]))

    return reading


def _smart_fcs_find_power(ctx, readings):
    """
    The power from at most two short measurements.
    :return: power in %, or None when no usable reading came from the first one
    """
    settings = ctx.settings

    power = settings["first_power"]
    reading = _smart_fcs_measure(ctx, power, readings)

    if not _smart_fcs_usable(settings, reading):
        return None

    next_power = _smart_fcs_step(settings, power, reading)

    if _smart_fcs_close_enough(settings, power, next_power):
        return power

    power = next_power
    reading = _smart_fcs_measure(ctx, power, readings)

    # The first step is still the best estimate when the second reading gives nothing
    if not _smart_fcs_usable(settings, reading):
        return power

    next_power = _smart_fcs_step(settings, power, reading)

    return power if _smart_fcs_close_enough(settings, power, next_power) else next_power


###################### the adaptive experiment ########################################################


@register_adaptive
def smart_FCS(ctx):
    """
    Chooses the laser power of the FCS experiment from at most two short measurements, as the settings
    in adaptive_config.json say. ctx.obj is not used: the power depends on the spot, not on an object,
    so the function works the same with and without object finding.
    """
    zen_api = ctx.zen_api
    experiment = ctx.experiment
    settings = ctx.settings

    if not settings:
        log("smart_FCS: no entry in adaptive_config.json - power left unchanged")
        return

    laser_line = settings["laser_line"]

    _smart_fcs_focus(ctx)

    zen_api.activate_experiment(experiment)

    power_now = zen_api.get_laser_power(experiment, laser_line)

    if power_now is None:
        log("smart_FCS: {} has no {} - power left unchanged".format(experiment, laser_line))
        return

    own_power = _SMART_FCS_OWN_POWER.setdefault(experiment, power_now)
    readings = []

    try:
        chosen = _smart_fcs_find_power(ctx, readings)
    except Exception as error:
        chosen = None
        log("smart_FCS: {} - no power chosen".format(error))

    zen_api.activate_experiment(experiment)

    if chosen is None:
        zen_api.set_laser_power(experiment, laser_line, own_power)
        log("smart_FCS: WARNING - no usable count rate, weak sample, empty spot or out of focus? {} runs at "
            "its own {} %".format(experiment, own_power))
    else:
        chosen = zen_api.set_laser_power(experiment, laser_line, chosen)
        log("smart_FCS: set {} to {} %".format(laser_line, chosen))

    record = {
        "experiment": experiment,
        "settings": settings,
        "focus_z": zen_api.focus_z(),
        "own_power_percent": own_power,
        "readings": readings,
        "chosen_power_percent": chosen,
    }

    with open(Path.Combine(ctx.result_dir(), "smart_FCS.json"), "w") as record_file:
        json.dump(record, record_file, indent=2)
