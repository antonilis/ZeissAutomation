import json

from System.IO import File, Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# Aims a z-stack at the top of a GUV before it runs. A GUV rests on the bottom, so its top lies 2R above
# it, and Definite Focus settles a height h above the bottom:
#
#   top = Definite Focus + 2R - h
#
# 2R is geometry. h depends on the plate, so it is learned during the run:
#
#   1. the top the analysis found for the GUV before gives one more value of h
#   2. h is the median of the largest group of values that agree with each other. Until two values agree
#      it stays start_height_um, so one wrong top moves nothing, however early it comes: a first wrong
#      top once sent every next stack higher, and each of them found more wrong tops
#   3. until three values agree, the stack runs search_half_range_um around the aim, afterwards
#      half_range_um, because a narrow stack aimed from a wrong h would miss the tops it needs to recover.
#      Only found tops away from the edge of the scan count
#
# A new plate therefore takes over after a few GUVs, without any setting. A wrong top still costs its own
# GUV, the z-reanalysis sends the focus there.
#
# The focus and the centre of the stack both go to the aim: the stack runs between the positions set here
# and not around the focus, while the analysis GUVTopZScan counts from the focus stored in the image.
# Measured on 15 GUVs of 06.11, R 4.3-9.5 um: top - Definite Focus = 2.01 R - 5.35 um, rms 0.31 um.
#
# The learned state is kept here at module level, so it starts empty at every macro run.
# guv_top_stack.json next to the results records what each aim was made from.
#
# When there is no object or FindSurface fails, the stack runs around the current focus. A stack in the
# wrong place costs one object, not the plate.


###################### settings ########################################################################
# The "guv_top_stack" entry of config/adaptive_config.json:
#
#   start_height_um        h before anything was learned
#   search_half_range_um   half of the range of the stack until three tops are in
#   half_range_um          half of the range of the stack afterwards
#   max_radius_um          a larger radius is not trusted, the same check as in fcs_zscan


###################### state, empty at every macro run ################################################

_GUV_TOP_HEIGHTS = []       # the values of h learned so far
_GUV_TOP_PENDING = []       # the last GUV, whose top is not read yet: obj_id, name, z_surface, radius
_GUV_TOP_AGREEING = 2       # values that have to agree before h leaves its starting value
_GUV_TOP_TRUSTED = 3        # values that have to agree before the stack gets narrow
_GUV_TOP_AGREEMENT_UM = 1.0     # the width of a group, three times the 0.31 um rms of h on 15 GUVs


###################### helpers ########################################################################


def _guv_top_learn(ctx):
    """
    Reads the top found for the GUV before, and adds its height to what was learned.
    """
    if not _GUV_TOP_PENDING:
        return

    obj_id, name, z_surface, radius = _GUV_TOP_PENDING.pop()
    path = ctx.path_manager.temp_file_path(obj_id, "z", name)

    if not File.Exists(path):
        return

    try:
        with open(path) as file:
            data = json.load(file)

        top = data[list(data.keys())[0]]

        if top["top_found"] and not top["at_scan_edge"]:
            _GUV_TOP_HEIGHTS.append(z_surface + 2 * radius - top["position"][2])

    except Exception as error:
        log("guv_top_stack could not read the top of {}: {}".format(obj_id, error))


def _guv_top_agreeing():
    """
    :return: list of the sorted heights of the largest group that fits in _GUV_TOP_AGREEMENT_UM
    """
    heights = sorted(_GUV_TOP_HEIGHTS)
    best = []

    for index, low in enumerate(heights):
        group = [height for height in heights[index:] if height - low <= _GUV_TOP_AGREEMENT_UM]

        if len(group) > len(best):
            best = group

    return best


def _guv_top_height(start_height):
    """
    :return: the median of the agreeing heights, the starting one until enough of them agree
    """
    heights = _guv_top_agreeing()

    if len(heights) < _GUV_TOP_AGREEING:
        return start_height

    middle = len(heights) // 2

    return heights[middle] if len(heights) % 2 else (heights[middle - 1] + heights[middle]) / 2.0


###################### the adaptive experiment ########################################################


@register_adaptive
def guv_top_stack(ctx):
    """
    Moves the focus and the z-stack to where the top of the GUV is expected.
    """
    _guv_top_learn(ctx)

    settings = ctx.settings
    start_z = ctx.zen_api.focus_z()
    radius = ctx.obj['radius'] if ctx.obj else None
    agreeing = len(_guv_top_agreeing())
    trusted = agreeing >= _GUV_TOP_TRUSTED
    half_range = settings["half_range_um"] if trusted else settings["search_half_range_um"]

    record = {"start_z": start_z, "radius_um": radius, "objective_magnification": ctx.zen_api.objective_magnification(),
              "height_um": _guv_top_height(settings["start_height_um"]), "learned_tops": agreeing,
              "all_tops": len(_GUV_TOP_HEIGHTS), "half_range_um": half_range}

    reason = None

    if radius is None or radius > settings["max_radius_um"]:
        reason = "no usable radius: {}".format(radius)

    else:
        try:
            record["z_surface"] = ctx.zen_api.find_surface()
        except Exception as error:
            reason = "FindSurface failed: {}".format(error)

    if reason is None:
        record["z_aim"] = record["z_surface"] + 2 * radius - record["height_um"]
        del _GUV_TOP_PENDING[:]
        _GUV_TOP_PENDING.append((ctx.obj_id, ctx.name, record["z_surface"], radius))
    else:
        record["z_aim"] = start_z
        log("guv_top_stack stays at the current focus: {}".format(reason))

    record["fallback_reason"] = reason

    ctx.zen_api.move_focus(record["z_aim"])
    record["z_stack_first"], record["z_stack_last"] = ctx.zen_api.center_z_stack(ctx.experiment, record["z_aim"], half_range)

    log("guv_top_stack: radius {}, h {} from {} agreeing of {} tops, focus {} -> {}".format(
        radius, record["height_um"], agreeing, record["all_tops"], start_z, record["z_aim"]))

    path = Path.Combine(ctx.result_dir(), "guv_top_stack.json")

    with open(path, "w") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)
