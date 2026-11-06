import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# Aims a z-stack at the top of a GUV before it runs. A GUV resting on the bottom has its top 2R above it:
#
#   1. Definite Focus finds the cover-slip surface         zen_api.find_surface()
#   2. the bottom of the well is the surface plus the offset of the objective, from path_config.json
#   3. focus to bottom + 2R + aim_offset_um
#
# The experiment has to be a z-stack in centre mode, which then runs around this focus. The analysis
# GUVTopZScan reads the top from it.
#
# surface_offsets were measured on SLBs on another plate, so on a new plate this aim may be off by a few
# um. guv_top_stack.json next to the results records the numbers needed to correct that afterwards.
#
# When there is no object, no offset for the objective or FindSurface fails, the focus goes back where it
# was and the stack runs around it. A stack in the wrong place costs one object, not the plate.


###################### settings ########################################################################
# The "guv_top_stack" entry of config/adaptive_config.json:
#
#   aim_offset_um    added to the aim, to correct it after looking at a run
#   max_radius_um    a larger radius is not trusted, the same check as in fcs_zscan


@register_adaptive
def guv_top_stack(ctx):
    """
    Moves the focus to where the top of the GUV is expected, for a z-stack in centre mode to run around it.
    """
    start_z = ctx.zen_api.focus_z()
    radius = ctx.obj['radius'] if ctx.obj else None
    magnification = ctx.zen_api.objective_magnification()

    record = {"start_z": start_z, "radius_um": radius, "objective_magnification": magnification,
              "aim_offset_um": ctx.settings.get("aim_offset_um", 0.0)}

    reason = None

    if radius is None or radius > ctx.settings.get("max_radius_um", 200):
        reason = "no usable radius: {}".format(radius)

    elif str(magnification) not in ctx.surface_offsets:
        reason = "no surface offset for a {}x objective in path_config.json".format(magnification)

    else:
        try:
            record["z_surface"] = ctx.zen_api.find_surface()
        except Exception as error:
            reason = "FindSurface failed: {}".format(error)

    if reason is None:
        record["z_bottom"] = record["z_surface"] + ctx.surface_offsets[str(magnification)]
        record["z_aim"] = record["z_bottom"] + 2 * radius + record["aim_offset_um"]
    else:
        record["z_aim"] = start_z
        log("guv_top_stack stays at the current focus: {}".format(reason))

    record["fallback_reason"] = reason

    ctx.zen_api.move_focus(record["z_aim"])

    log("guv_top_stack: radius {}, focus {} -> {}".format(radius, start_z, record["z_aim"]))

    path = Path.Combine(ctx.result_dir(), "guv_top_stack.json")

    with open(path, "w") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)
