import json
from data_preprocessing.preprocessing import ZeissImageProcessor
from utils import visualize_points
import sys
import os

with open('config/preprocessing_config.json', 'r') as file:
    preprocessing_config = json.load(file)

with open('config/path_config.json', 'r') as file:
    path_config = json.load(file)

file_name = sys.argv[1]
file_path = os.path.join(path_config['image_for_analysis_path'], file_name)

measuring_points_path = path_config['measuring_points_path']
points_for_measurement = f"{file_name}_measurement_points.json"
picture_with_found_points_name = f"{file_name}_found_points.png"

analysis_type = preprocessing_config[sys.argv[2]]

obj_main = ZeissImageProcessor(file_path, **analysis_type)

obj_main.save_measurement_points(os.path.join(measuring_points_path, points_for_measurement))

visualize_points(obj_main, os.path.join(measuring_points_path, picture_with_found_points_name))
