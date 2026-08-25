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
# arrives as --preprocessing_config from PythonAnalysisRunner. It is deliberately not
# resolved here: a fallback would be a second source of truth and could silently read a
# different preset file than the one the macro uses.
if 'preprocessing_config' not in command_args:
    raise ValueError(
        "Missing --preprocessing_config. It is the path to preprocessing_config.json and is "
        "passed automatically by PythonAnalysisRunner; supply it explicitly when running this "
        "script by hand.")

preprocessing_config_path = command_args['preprocessing_config']

print("[INFO] Reading analysis presets from: {}".format(preprocessing_config_path))

with open(preprocessing_config_path, 'r') as file:
    preprocessing_config = json.load(file)

if command_args['is_FCS'] == 'True':

    print('Analyzing FCS')

    folder_path = os.path.dirname(command_args['file_path'])

    print(folder_path)

    obj = ZeissFCSProcessor(folder_path)

    print(command_args['saving_path'])

    obj.save_measurement_points(command_args['saving_path'])

else:

    print("Analyzing Image")

    analysis_type = preprocessing_config[command_args['analysis_arguments']]

    obj = ZeissImageProcessor(command_args['file_path'], **analysis_type)

    if command_args['type'] == 'reanalysis_xy' and len(obj.measurement_points) > 1:
        print("Found multiple objects after reanalysis: {}".format(len(obj.measurement_points)))
        closest_point = choose_the_closest_point(obj.measurement_points, obj.metadata["stage_position"])
        obj.measurement_points = [closest_point]

    obj.save_measurement_points(command_args['saving_path'])

    # For xy reanalysis shows the image with the mark of the new measuring position
    if command_args['type'] != 'reanalysis_z':
        visualize_points(obj, Path(command_args['saving_path']).with_suffix(".png"))

    print("Finished overview analysis for: {}".format(command_args['file_path']))
