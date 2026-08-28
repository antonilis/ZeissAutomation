import json
import os
from data_processing.processor.zeiss_image_processor import ZeissImageProcessor
from data_processing.processor.zeiss_FCS_processor import ZeissFCSProcessor
from utils import visualize_points, parse_args_to_dict, choose_the_closest_point
from pathlib import Path

"""
Script initialized by the PythonRunner, takes the argumets from PythonRunner and initializes objects: ZeissFCSProcessor
or ZeissImageProcessor and saves the results of the analysis to JSON files.
"""

print("Started main_processor")

command_args = parse_args_to_dict()

print("[INFO] Parsed arguments: {}".format(command_args))

# The analysis presets live in the config folder of the ZEN runtime, and their location
# arrives as --processing_config from PythonAnalysisRunner. It is deliberately not
# resolved here: a fallback would be a second source of truth and could silently read a
# different preset file than the one the macro uses.
if 'processing_config' not in command_args:
    raise ValueError(
        "Missing --processing_config. It is the path to processing_config.json and is "
        "passed automatically by PythonAnalysisRunner; supply it explicitly when running this "
        "script by hand.")

processing_config_path = command_args['processing_config']

print("[INFO] Reading analysis presets from: {}".format(processing_config_path))

with open(processing_config_path, 'r') as file:
    processing_config = json.load(file)

if command_args['is_FCS'] == 'True':

    print('Analyzing FCS')

    folder_path = os.path.dirname(command_args['file_path'])

    print(folder_path)

    obj = ZeissFCSProcessor(folder_path)

    print(command_args['saving_path'])

    obj.save_measurement_points(command_args['saving_path'])

else:

    print("Analyzing Image")

    analysis_type = dict(processing_config[command_args['analysis_arguments']])

    # The object selection is the optional second stage. Without --selection_arguments nothing is
    # added here and ZeissImageProcessor runs exactly as it did before that stage existed.
    selection_preset_name = command_args.get('selection_arguments')

    if selection_preset_name:

        if 'selection_config' not in command_args:
            raise ValueError(
                "Missing --selection_config, which is needed to resolve the object selection preset "
                "'{}'. It is the path to selection_config.json and is passed automatically by "
                "PythonAnalysisRunner; supply it explicitly when running this script by "
                "hand.".format(selection_preset_name))

        print("[INFO] Reading object selection presets from: {}".format(command_args['selection_config']))

        with open(command_args['selection_config'], 'r') as file:
            selection_config = json.load(file)

        if selection_preset_name not in selection_config:
            raise ValueError(
                "Unknown object selection preset: {}, please choose from {}".format(
                    selection_preset_name, list(selection_config.keys())))

        # A selection preset is flat, exactly like an analysis preset: chosen_selection names the
        # class and everything else is handed to that class as its arguments
        selection_preset = dict(selection_config[selection_preset_name])

        if 'chosen_selection' not in selection_preset:
            raise ValueError(
                "The object selection preset '{}' has no 'chosen_selection' key, so there is no way "
                "to tell which selection algorithm to run.".format(selection_preset_name))

        analysis_type['chosen_selection'] = selection_preset.pop('chosen_selection')
        analysis_type['selection_arguments'] = selection_preset

    obj = ZeissImageProcessor(command_args['file_path'], **analysis_type)

    if command_args['type'] == 'reanalysis_xy':
        # Only objects the selection kept are candidates for the corrected position, otherwise the stage could be sent
        # to something that was measured and rejected a moment earlier
        selected_points = [p for p in obj.measurement_points if p['selected']]

        if len(selected_points) > 1:
            print("Found multiple objects after reanalysis: {}".format(len(selected_points)))
            selected_points = [choose_the_closest_point(selected_points, obj.metadata["stage_position"])]

        obj.measurement_points = selected_points

    obj.save_measurement_points(command_args['saving_path'])

    # For xy reanalysis shows the image with the mark of the new measuring position
    if command_args['type'] != 'reanalysis_z':
        visualize_points(obj, Path(command_args['saving_path']).with_suffix(".png"))

    print("Finished overview analysis for: {}".format(command_args['file_path']))
