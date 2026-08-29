###################### adaptive experiment plugin #####################################################
# main_macro prepends PLUGIN_PREAMBLE to this file before running it, which imports the .NET
# extension methods that carry ClearExperimentRegionsAndPositions, AddSinglePosition and the rest
# of the experiment editing API. Without that a plugin sees 71 members on a ZenExperiment instead
# of 96 and those calls raise AttributeError. Nothing to do here - it is prepended automatically.
#
# This file is NOT imported. main_macro reads it and runs it in ITS OWN global namespace, so that Zen,
# ZenWindow, ZEISS_API, PathManager, CONFIG, log, json, time, uuid and the System.IO names
# are already defined here and must not be imported. That is the whole point: an adaptive experiment
# needs the names ZEN injects into the macro, and a normally imported module cannot see them.
#
# Whatever is decorated with @register_adaptive appears in the macro's dropdown under the function's
# own name, exactly the way @register_class works for analysers and object selections.
#
# Because the namespace is shared rather than copied, do NOT assign at module level to a name the
# macro uses - log, json, Path, CONFIG and so on. Anything overwritten is reported in the log, but
# it would still be the macro that breaks, not this file.
#
# The signature is fixed, because _run_experiment calls it: (exp_item, obj_id, stage, obj, name).
# obj is the record of the object the experiment is about to run on, or None when the run has object
# finding switched off and the pipeline is simply visiting overview points. A plugin has to cope with
# both, because the same function is used in both modes.
# A linter will complain about undefined names in this file. That is expected.


@register_adaptive
def fcs_zscan(exp_item, obj_id, stage, obj, name):
    """
    Example of the function suited for adaptive experiments. Based on the radius of the object it moves from the focus
    by the object radius and set this as the center of z-scan with FCS, useful for finding the top of GUVs when combined
    when the experiment is chosen for the z-reanalysis.
    """
    # With object finding switched off there is no object at all and the pipeline hands over
    # obj=None. The scan is then centred on the current focus instead of on the top of a GUV,
    # which is exactly what is wanted when visiting bare overview points.
    radius = obj['radius'] if obj else 0

    if radius > 200:
        radius = 0

    actual_position = ZEISS_API.get_stage_focus_position()
    log("I could have move by radius of {}".format(str(obj)))

    modified_position = [actual_position[0], actual_position[1], actual_position[2] + radius]

    exp_obj = Zen.Acquisition.Experiments.GetByName(exp_item)

    exp_obj.ClearExperimentRegionsAndPositions(0)
    exp_obj.ClearTileRegionsAndPositions(0)

    z_offset = [modified_position[2] - 0.2, modified_position[2] - 0.1, modified_position[2],
                modified_position[2] + 0.1, modified_position[2] + 0.2]

    positions_dict = {}

    for i in range(len(z_offset)):
        name_for_dict = "P{}".format(i + 1)

        positions_dict[name_for_dict] = {'x': modified_position[0], 'y': modified_position[1], 'z': z_offset[i]}

    path_menager = PathManager(CONFIG)

    res_dir = path_menager.result_dir(obj_id, stage, name)

    # At this point one needs to save the positions of the FCS measurements, because there is no information about the
    # positions in the metadata
    path = Path.Combine(res_dir, "FCS_points.json")

    with open(path, "w") as file:
        json.dump(positions_dict, file, indent=2, ensure_ascii=False)

    for z_position in z_offset:
        exp_obj.AddSinglePosition(blockIndex=0, x=modified_position[0], y=modified_position[1], z=z_position)

    exp_obj.SetActive()
