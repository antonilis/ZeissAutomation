import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive

# Imported rather than looked up at run time: if smart_focus.py fails to load, this module fails with
# it, and the log says why when the macro starts - not halfway through a plate
from adaptive.smart_focus import smart_focus


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# Focuses, then sets the laser power of an imaging experiment so that every well is recorded at the
# same brightness, instead of saturating the bright wells and drowning the dim ones in noise:
#
#   1. smart_focus - Definite Focus + a narrow autofocus, or the experiment's own wide autofocus
#      (use_surface)
#   2. set the reference power and take one test frame of the same experiment, on the same field
#   3. the chosen metric of that frame (mean or median), background subtracted
#   4. power = reference * (target - background) / (metric - background)
#      lowered if the 99th percentile would saturate, then clamped to [min, max]
#   5. set that power; the pipeline then acquires the real image with it
#
# The metric decides WHAT comes out equal. "mean" equalises the integral of the image, because the
# integral is the mean times the number of pixels and every image has the same number of pixels.
# "median" equalises the brightness of the bilayer itself and ignores bright aggregates, which is why
# wells full of vesicles then end up with a larger integral.
#
# All of it was measured on the instrument with probe_smart_SLB_imaging_3.czmac (40x, SLB_A655_imaging,
# 0.2 %): the signal is linear in the laser power ((2x - bg) / (1x - bg) = 2.06), the background with
# the laser at zero is 55 counts, and a test frame bleaches nothing measurable.
#
# smart_focus is another plugin and is called directly: a run can pair only one adaptive function with
# an experiment, so this one does both.
#
# The power is changed in memory only, never in the .czexp. It stays at the last well's value after
# the run, so do not save the experiment from ZEN afterwards unless that is what you want.
# The power used is written into the .czi metadata by ZEN anyway (LightSourceSettings/Transmission);
# smart_SLB_imaging.json next to it additionally records the test frame it was chosen from.


###################### settings ########################################################################
# The "smart_SLB_imaging" entry of config/adaptive_config.json:
#
#   laser_line        id of the laser line
#   use_surface       focus with Definite Focus + a narrow autofocus, see smart_focus.py
#   metric            "mean": equal integrals; "median": equal bilayer brightness
#   reference_power   % - the test frame is always taken at this power
#   target            counts per pixel - what the metric of every well should come out at
#   background        counts - median with the laser at 0; re-measure after changing objective, detector
#                     or gain
#   p99_limit         counts - the 99th percentile must stay below this (16-bit: 65535)
#   min_power, max_power, in %
#   pixel_step        every n-th pixel goes into the statistics
#   min_signal        counts above background below which the test frame is "no signal"


###################### helpers ########################################################################


def _smart_slb_choose_power(settings, statistics):
    """
    The power that brings the chosen metric to the target, assuming - as measured - that the signal
    above background is proportional to the power.
    :return: tuple (power in %, reason it was limited or None)
    """
    background = settings["background"]
    reference_power = settings["reference_power"]
    signal = statistics[settings["metric"]] - background

    if signal < settings["min_signal"]:
        return settings["max_power"], "no signal in the test frame"

    power = reference_power * (settings["target"] - background) / signal
    limited = None

    # The brightest objects must not saturate at the chosen power either
    bright = statistics["p99"] - background
    if bright > 0:
        saturation_power = reference_power * (settings["p99_limit"] - background) / bright
        if power > saturation_power:
            power = saturation_power
            limited = "99th percentile would saturate"

    if power > settings["max_power"]:
        power, limited = settings["max_power"], "maximum power"

    if power < settings["min_power"]:
        power, limited = settings["min_power"], "minimum power"

    return power, limited


###################### the adaptive experiment ########################################################


@register_adaptive
def smart_SLB_imaging(ctx):
    """
    Focuses with smart_focus, then chooses the laser power of the imaging experiment from a test
    frame, so that the metric of the image comes out at the target. ctx.obj is not used: the power
    depends on the field, not on an object, so the function works the same with and without object
    finding.
    """
    zen_api = ctx.zen_api
    experiment = ctx.experiment
    settings = ctx.settings

    if not settings:
        log("smart_SLB_imaging: no entry in adaptive_config.json - nothing done")
        return

    laser_line = settings["laser_line"]
    reference_power = settings["reference_power"]
    metric = settings["metric"]

    smart_focus(ctx, use_surface=settings["use_surface"])

    zen_api.activate_experiment(experiment)

    if zen_api.get_laser_power(experiment, laser_line) is None:
        log("smart_SLB_imaging: {} has no {} - power left unchanged".format(experiment, laser_line))
        return

    # Always from the reference, never from whatever the previous well left behind
    zen_api.set_laser_power(experiment, laser_line, reference_power)

    statistics = zen_api.frame_statistics(experiment, settings["pixel_step"])

    power, limited = _smart_slb_choose_power(settings, statistics)

    chosen = zen_api.set_laser_power(experiment, laser_line, round(power, 4))

    log("smart_SLB_imaging: test frame at {} % -> mean {:.0f}, median {:.0f}, p99 {:.0f}; "
        "{} target {:.0f}; set {} to {} %{}".format(
            reference_power, statistics["mean"], statistics["median"], statistics["p99"],
            metric, settings["target"], laser_line, chosen,
            " ({})".format(limited) if limited else ""))

    if limited == "no signal in the test frame":
        log("smart_SLB_imaging: WARNING - {} {:.0f} is barely above the background {}; empty well or "
            "out of focus?".format(metric, statistics[metric], settings["background"]))

    record = {
        "experiment": experiment,
        "laser_line": laser_line,
        "metric": metric,
        "target": settings["target"],
        "background": settings["background"],
        "reference_power_percent": reference_power,
        "test_mean": statistics["mean"],
        "test_median": statistics["median"],
        "test_p99": statistics["p99"],
        "chosen_power_percent": chosen,
        "limited_by": limited,
        "focus_z": zen_api.focus_z(),
    }

    with open(Path.Combine(ctx.result_dir(), "smart_SLB_imaging.json"), "w") as record_file:
        json.dump(record, record_file, indent=2)
