import json
import time

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.
#
# Chosen from the dropdown the function always runs the plain wide autofocus. use_surface is an extra
# keyword that only other plugins pass - smart_SLB_imaging imports this module and calls it directly.


###################### what it does ####################################################################
# use_surface=False (the dropdown, and the default):
#   the software autofocus with the autofocus settings of the experiment itself - for SLB_A655_imaging
#   a relative range of 200 um.
#
# use_surface=True (smart_SLB_imaging):
#   1. Definite Focus finds the cover-slip surface         zen_api.find_surface()
#   2. move to surface + the offset of the objective       the SLB sits 6.5 um below it at 40x
#   3. narrow software autofocus around that point         with narrow_experiment
#   and falls back to the wide autofocus of use_surface=False when there is no offset for the
#   objective, when FindSurface or the narrow autofocus raises, or when the narrow autofocus ends up
#   more than max_correction_um from the target - at the edge of its window, which means the
#   bilayer is probably outside it.
#
# Measured on the instrument (probe_smart_SLB_imaging.czmac and _2, 40x): FindSurface takes ~5 s and
# repeats to 0.01-0.09 um; the software autofocus settled 6.62 and 6.47 um below the surface it found.
# At 20x (FRAP run of 02.10) the bilayer sat 16.65 +- 0.08 um below it, and the narrow path worked in
# 27 of 27 points.
#
# The narrow window comes from a separate experiment rather than from rewriting the autofocus range of
# the experiment: that experiment is only used to focus and is never acquired or saved. It runs before
# smart_SLB_imaging touches the laser power of the imaging experiment, so switching to it and back
# cannot undo that change.
#
# smart_focus.json next to the results of every well records what happened, for the notebook.


###################### settings ########################################################################
# The "smart_focus" entry of config/adaptive_config.json, whichever plugin calls this one:
#
#   narrow_experiment   a copy of the imaging experiment, with an autofocus range of 10 um
#   max_correction_um   a narrow autofocus that moves further than this falls back to wide
#
# The um from the Definite Focus surface to the bilayer, per objective magnification, belong to the
# microscope: surface_offsets in path_config.json. An objective that is not listed gets the wide
# autofocus, because an offset from another objective would be wrong.


###################### helpers ########################################################################


def _smart_focus_surface_then_narrow(zen_api, settings, surface_offsets, record):
    """
    Definite Focus, the objective's offset, then the narrow autofocus. Everything measured on the way
    goes into record.
    :return: the reason to fall back to the wide autofocus, or None when this succeeded
    """
    if not settings:
        return "no smart_focus entry in adaptive_config.json"

    narrow_experiment = settings["narrow_experiment"]

    magnification = zen_api.objective_magnification()
    record["objective_magnification"] = magnification

    if str(magnification) not in surface_offsets:
        return "no surface offset for a {}x objective in path_config.json".format(magnification)

    offset = surface_offsets[str(magnification)]

    started = time.time()
    try:
        record["z_surface"] = zen_api.find_surface()
    except Exception as error:
        return "FindSurface failed: {}".format(error)

    record["surface_seconds"] = time.time() - started

    target = record["z_surface"] + offset
    record["z_target"] = target
    zen_api.move_focus(target)

    started = time.time()
    try:
        record["z_narrow"] = zen_api.autofocus(narrow_experiment)
    except Exception as error:
        return "narrow autofocus with {} failed: {}".format(narrow_experiment, error)

    record["narrow_seconds"] = time.time() - started
    record["narrow_correction"] = record["z_narrow"] - target

    if abs(record["narrow_correction"]) > settings["max_correction_um"]:
        return "narrow autofocus moved {:+.2f} um from the target".format(record["narrow_correction"])

    return None


###################### the adaptive experiment ########################################################


@register_adaptive
def smart_focus(ctx, use_surface=False):
    """
    Focuses before the experiment runs: either with its own (wide) autofocus, or, with use_surface,
    with Definite Focus and a narrow autofocus, falling back to the wide one when that fails.
    """
    zen_api = ctx.zen_api
    experiment = ctx.experiment

    record = {"experiment": experiment, "use_surface": use_surface, "z_start": zen_api.focus_z()}
    fallback = None

    if use_surface:
        fallback = _smart_focus_surface_then_narrow(zen_api, ctx.settings_for("smart_focus"),
                                                    ctx.surface_offsets, record)

        if fallback:
            log("smart_focus: falling back to the wide autofocus - {}".format(fallback))

    if not use_surface or fallback:
        started = time.time()
        record["z_wide"] = zen_api.autofocus(experiment)
        record["wide_seconds"] = time.time() - started

    # Leave the experiment that is about to run active, whichever one was used to focus
    zen_api.activate_experiment(experiment)

    record["mode"] = "surface + narrow" if use_surface and not fallback else "wide"
    record["fallback_reason"] = fallback
    record["z_final"] = zen_api.focus_z()

    log("smart_focus: {} autofocus for {}, z {:.3f} -> {:.3f}".format(
        record["mode"], experiment, record["z_start"], record["z_final"]))

    with open(Path.Combine(ctx.result_dir(), "smart_focus.json"), "w") as record_file:
        json.dump(record, record_file, indent=2)
