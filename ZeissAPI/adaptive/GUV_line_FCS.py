import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive

from adaptive.smart_FCS import smart_FCS


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.


###################### what it does ####################################################################
# FCS on the top of a GUV, along a line in z. The focus has to be on the top already, which is where the
# z-reanalysis with GUVTopZScan leaves it:
#
#   1. smart_FCS sets the power once, on the top, with the settings of this plugin
#   2. the experiment gets one position per entry of z_offsets_um around the top
#
# One power for all the positions, because N and tau against z are only comparable at the same power.
# Several positions around the top, because the top itself is known to a few hundred nm. N and tau have
# their minimum where the membrane is in the focus.
#
# With no usable reading the GUV is skipped and the pipeline goes to the next one: the spot is then off the
# membrane or the dye is gone, and a measurement there costs minutes for nothing. skip_without_signal false
# runs it anyway, at the power saved in the experiment, so keep a safe power saved in it.
# FCS_points.json and smart_FCS.json next to the results record the positions and the readings.


###################### settings ########################################################################
# The "GUV_line_FCS" entry of config/adaptive_config.json. Everything smart_FCS reads, see smart_FCS.py,
# with focus "none" to stay on the top, and:
#
#   z_offsets_um          the positions, relative to the top
#   skip_without_signal   optional, true when missing


@register_adaptive
def GUV_line_FCS(ctx):
    """
    Sets the power of the FCS experiment on the top of the GUV and then the positions around it.
    """
    settings = ctx.settings

    if not settings:
        log("GUV_line_FCS: no entry in adaptive_config.json - experiment left unchanged")
        return

    # read before smart_FCS runs its short measurements
    x, y, z = ctx.zen_api.get_stage_focus_position()

    record = smart_FCS(ctx)

    if record is not None and record["chosen_power_percent"] is None and settings.get("skip_without_signal", True):
        log("GUV_line_FCS: no usable count rate on the top, skipping the FCS of this GUV")
        return False

    positions = [[x, y, z + offset] for offset in settings["z_offsets_um"]]

    # there is no information about the positions in the metadata of an FCS measurement
    points = {}

    for index, position in enumerate(positions):
        points["P{}".format(index + 1)] = {'x': position[0], 'y': position[1], 'z': position[2]}

    with open(Path.Combine(ctx.result_dir(), "FCS_points.json"), "w") as file:
        json.dump(points, file, indent=2, ensure_ascii=False)

    ctx.zen_api.set_single_positions(ctx.experiment, positions)

    log("GUV_line_FCS: {} positions around z = {}".format(len(positions), z))
