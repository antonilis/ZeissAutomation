###################### adaptive experiment plugin #####################################################
# This file is NOT imported. main_macro reads it and runs it in its own namespace, so that Zen,
# ZenWindow, ZEISS_API, PathManager, CONFIG, log, json, time, uuid and the System.IO names
# are already defined here and must not be imported. That is the whole point: an adaptive experiment
# needs the names ZEN injects into the macro, and a normally imported module cannot see them.
#
# Whatever is decorated with @register_adaptive appears in the macro's dropdown under the function's
# own name, exactly the way @register_class works for analysers and object selections.
#
# The signature is fixed, because _run_experiment calls it: (exp_item, obj_id, stage, obj, name).
# obj_id is the id the RESULT PATH is built from, not always the id of the measured thing: with
# object finding switched off it is None, because the results are then filed under the overview
# point instead of under an obj_ folder. Passing it to PathManager.result_dir is what keeps a
# plugin's own files in the same folder as the .czi the experiment produced.
# A linter will complain about undefined names in this file. That is expected.


@register_adaptive
def smart_focus(exp_item, obj_id, stage, obj, name):
    """
    Example of the function suited for adaptive experiments.
    """
    
    log('Jest w pyte')
    
    exp_obj = Zen.Acquisition.Experiments.GetByName(exp_item)

    exp_obj.SetActive()

    Zen.Acquisition.FindAutofocus(Zen.Acquisition.Experiments.ActiveExperiment, timeoutSeconds=0)
  
    
    actual_position = ZEISS_API.get_stage_focus_position()

    exp_obj.ClearTileRegionsAndPositions(0)

    z_offset = [actual_position[2] + i for i in range(-10, 11)]

    for z_position in z_offset:
        exp_obj.AddSinglePosition(blockIndex=0, x=actual_position[0], y=actual_position[1], z=z_position)

    exp_obj.SetActive()
