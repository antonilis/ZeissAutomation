import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# Aims a z-stack at the top of a GUV before it runs. GUVs rest on the bottom and Definite Focus settles a
# few um above it, so the top lies about 2R minus that height above Definite Focus:
#
#   1. Definite Focus                                      zen_api.find_surface()
#   2. focus to that position + aim_slope * R + aim_offset_um
#   3. the centre of the z-stack to the same z           zen_api.center_z_stack()
#
# Both have to move: the stack runs between the positions set in step 3 and not around the focus, while
# the analysis GUVTopZScan counts from the focus stored in the image. The range and the interval stay
# as saved in the experiment.
#
# Measured on 8 GUVs of 06.11, R 4.4-9.5 um on transmitted light: top - Definite Focus = 2.15 R - 6.26 um,
# rms 0.18 um. guv_top_stack.json next to the results records the numbers needed to check that again.
#
# When there is no object or FindSurface fails, the focus goes back where it was and the stack runs
# around it. A stack in the wrong place costs one object, not the plate.


###################### settings ########################################################################
# The "guv_top_stack" entry of config/adaptive_config.json:
#
#   aim_slope        um of the aim per um of the radius of the object
#   aim_offset_um    added to the aim
#   max_radius_um    a larger radius is not trusted, the same check as in fcs_zscan


@register_adaptive
def guv_top_stack(ctx):
    """
    Moves the focus to where the top of the GUV is expected, for a z-stack in centre mode to run around it.
    """
    start_z = ctx.zen_api.focus_z()
    radius = ctx.obj['radius'] if ctx.obj else None

    record = {"start_z": start_z, "radius_um": radius, "objective_magnification": ctx.zen_api.objective_magnification(),
              "aim_slope": ctx.settings.get("aim_slope", 2.0), "aim_offset_um": ctx.settings.get("aim_offset_um", 0.0)}

    reason = None

    if radius is None or radius > ctx.settings.get("max_radius_um", 200):
        reason = "no usable radius: {}".format(radius)

    else:
        try:
            record["z_surface"] = ctx.zen_api.find_surface()
        except Exception as error:
            reason = "FindSurface failed: {}".format(error)

    if reason is None:
        record["z_aim"] = record["z_surface"] + record["aim_slope"] * radius + record["aim_offset_um"]
    else:
        record["z_aim"] = start_z
        log("guv_top_stack stays at the current focus: {}".format(reason))

    record["fallback_reason"] = reason

    ctx.zen_api.move_focus(record["z_aim"])
    record["z_stack_first"], record["z_stack_last"] = ctx.zen_api.center_z_stack(ctx.experiment, record["z_aim"])

    log("guv_top_stack: radius {}, focus {} -> {}".format(radius, start_z, record["z_aim"]))

    path = Path.Combine(ctx.result_dir(), "guv_top_stack.json")

    with open(path, "w") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)
