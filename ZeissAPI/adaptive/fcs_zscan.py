import json

from System.IO import Path

from zen_lib.runtime_config import log
from zen_lib.adaptive_loader import register_adaptive


###################### adaptive experiment plugin #####################################################
# An ordinary module, imported by zen_lib.adaptive_loader. Whatever is decorated with
# @register_adaptive appears in the macro's dropdown under the function's own name, exactly the way
# @register_class works for analysers and object selections.
#
# The function takes one argument, an AdaptiveContext (see adaptive_loader.py):
#
#   ctx.zen_api      everything that touches the microscope - a plugin never calls ZEN directly, so
#                    the experiment editing extension methods stay in zen_api.py, the one file that
#                    imports them. A plugin that needs a new edit gets a new ZenApi method.
#   ctx.experiment   name of the experiment about to run
#   ctx.obj          the object it runs on, or None with object finding switched off - the pipeline
#                    is then only visiting overview points, and a plugin has to cope with both
#   ctx.result_dir() the folder the experiment's results are saved in, for the plugin's own files
#   ctx.settings     the entry of the function in config/adaptive_config.json, empty without one
#   ctx.settings_for(name)  the entry of another plugin, for a plugin called by this one
#   ctx.surface_offsets     um from the Definite Focus surface to the sample, per objective, from
#                    path_config.json of this microscope
#
# Settings, the "fcs_zscan" entry of config/adaptive_config.json:
#
#   max_radius_um    a larger radius is not believed, the scan is then centred on the current focus
#   z_offsets_um     the positions of the scan, relative to its centre


@register_adaptive
def fcs_zscan(ctx):
    """
    Example of the function suited for adaptive experiments. Based on the radius of the object it moves from the focus
    by the object radius and set this as the center of z-scan with FCS, useful for finding the top of GUVs when combined
    when the experiment is chosen for the z-reanalysis.
    """
    settings = ctx.settings

    if not settings:
        log("fcs_zscan: no entry in adaptive_config.json - positions left unchanged")
        return

    # With object finding switched off there is no object at all and the pipeline hands over
    # obj=None. The scan is then centred on the current focus instead of on the top of a GUV,
    # which is exactly what is wanted when visiting bare overview points.
    radius = ctx.obj['radius'] if ctx.obj else 0

    if radius > settings["max_radius_um"]:
        radius = 0

    actual_position = ctx.zen_api.get_stage_focus_position()
    log("I could have move by radius of {}".format(str(ctx.obj)))

    modified_position = [actual_position[0], actual_position[1], actual_position[2] + radius]

    z_offset = [modified_position[2] + offset for offset in settings["z_offsets_um"]]

    positions_dict = {}

    for i in range(len(z_offset)):
        name_for_dict = "P{}".format(i + 1)

        positions_dict[name_for_dict] = {'x': modified_position[0], 'y': modified_position[1], 'z': z_offset[i]}

    # At this point one needs to save the positions of the FCS measurements, because there is no information about the
    # positions in the metadata
    path = Path.Combine(ctx.result_dir(), "FCS_points.json")

    with open(path, "w") as file:
        json.dump(positions_dict, file, indent=2, ensure_ascii=False)

    ctx.zen_api.set_single_positions(ctx.experiment,
                                     [[modified_position[0], modified_position[1], z] for z in z_offset])
