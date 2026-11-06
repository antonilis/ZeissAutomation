from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.
#
# Runs Definite Focus before an experiment, so that it is taken at a repeatable height and not wherever
# the focus was left. It can be paired with any experiment, the overview included.
#
# When Definite Focus fails the experiment still runs, at the current focus.


###################### settings ########################################################################
# The "definite_focus" entry of config/adaptive_config.json:
#
#   offset_um    added to the position Definite Focus settled at


@register_adaptive
def definite_focus(ctx):
    """
    Moves the focus to the Definite Focus position plus offset_um.
    """
    start_z = ctx.zen_api.focus_z()

    try:
        surface = ctx.zen_api.find_surface()
    except Exception as error:
        log("definite_focus stays at {}: FindSurface failed: {}".format(start_z, error))
        ctx.zen_api.move_focus(start_z)
        return

    offset = ctx.settings.get("offset_um", 0.0)

    if offset:
        ctx.zen_api.move_focus(surface + offset)

    log("definite_focus: focus {} -> {}, Definite Focus at {}".format(start_z, surface + offset, surface))
