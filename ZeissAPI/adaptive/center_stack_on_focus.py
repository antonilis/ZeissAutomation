from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader; see fcs_zscan.py for what the AdaptiveContext
# holds. Everything that touches the microscope goes through ctx.zen_api.
#
# A z-stack runs between the positions last set with the Center button of the Z-Stack tool, and not around
# the current focus. This is that button: the stack runs around wherever the focus is now, for instance
# on the top a z-reanalysis has just moved to. Range and interval stay as saved in the experiment.


@register_adaptive
def center_stack_on_focus(ctx):
    """
    Centres the z-stack of the experiment on the current focus.
    """
    focus = ctx.zen_api.focus_z()
    first, last = ctx.zen_api.center_z_stack(ctx.experiment, focus)

    log("center_stack_on_focus: z-stack of {} now runs {} to {}".format(ctx.experiment, first, last))
