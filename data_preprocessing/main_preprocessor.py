import json
from data_preprocessing.preprocessors.zeiss_image_preprocessor import ZeissImageProcessor
from data_preprocessing.preprocessors.fcs_preprocessor import ZeissFCSProcessor
from utils import visualize_points
import sys
import os

with open('config/preprocessing_config.json', 'r') as file:
    preprocessing_config = json.load(file)

with open('config/path_config.json', 'r') as file:
    path_config = json.load(file)


experiment_progress = sys.argv[1]  # 'overview' lub 'reanalysis'
analysis_mode = sys.argv[3]

if experiment_progress == 'overview':
    file_name = sys.argv[2]
    file_id = file_name.split("_")[0]

    file_path = os.path.join(path_config['image_for_analysis_path'], file_name)
    measuring_dir = path_config['measuring_points_path']
    analysis_type = preprocessing_config[analysis_mode]

    obj = ZeissImageProcessor(file_path, **analysis_type)

    obj.save_measurement_points(os.path.join(measuring_dir, f"{file_id}_measurements_points.json"))
    visualize_points(obj, os.path.join(measuring_dir, f"{file_id}_found_points.png"))

    print(f"Zakonczono analize overview dla: {file_name}")

elif experiment_progress == 'reanalysis':
    obj_id = sys.argv[2]
    reanalysis_dir = os.path.join(path_config['results_path'], f"obj_{obj_id}")

    # znajdź pierwszy plik .czi
    czi_files = [f for f in os.listdir(reanalysis_dir) if f.lower().endswith(".czi")]
    if not czi_files:
        raise FileNotFoundError(f"Brak plików .czi w katalogu {reanalysis_dir}")

    file_path = os.path.join(reanalysis_dir, czi_files[0])
    measuring_dir = path_config['measuring_points_path']
    analysis_type = preprocessing_config[analysis_mode]

    obj = ZeissImageProcessor(file_path, **analysis_type)

    obj.save_measurement_points(os.path.join(measuring_dir, f"{obj_id}_measurements_points_reanalysis.json"))
    visualize_points(obj, os.path.join(measuring_dir, f"{obj_id}_found_points_reanalysis.png"))

    print(f"[INFO] Zakonczono reanalize obiektu: {obj_id}")

else:
    raise ValueError(f"Niepoprawny tryb eksperymentu: {experiment_progress}")

