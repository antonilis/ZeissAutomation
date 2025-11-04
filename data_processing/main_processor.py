import json
from data_processing.processor.zeiss_image_processor import ZeissImageProcessor
from utils import visualize_points
import sys
import os
import numpy as np
import re

with open('config/preprocessing_config.json', 'r') as file:
    preprocessing_config = json.load(file)

with open('config/path_config.json', 'r') as file:
    path_config = json.load(file)


experiment_progress = sys.argv[1] 
analysis_mode = sys.argv[3]

def choose_the_closest_point(measurement_points, stage_position):
    
    stage = np.array([stage_position['x'], stage_position['y'], stage_position['z']])
    
    distances = [np.linalg.norm(np.array(p["position"]) - stage) for p in measurement_points]
    
    closest_idx = int(np.argmin(distances))
    
    return measurement_points[closest_idx]

def is_uuid(s: str) -> bool:
    """Sprawdza, czy string wyglada jak UUID (w formacie 8-4-4-4-12)."""
    return bool(re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        s
    ))



if experiment_progress == 'overview':
    file_name = sys.argv[2]
    
    parts = os.path.splitext(file_name)[0].split("_")

    uuid_idx = next((i for i, p in enumerate(parts) if is_uuid(p)), None)

    if uuid_idx is not None:
        # mamy uuid — zwracamy np. name_uuid
        if uuid_idx > 0:
            file_id = f"{parts[uuid_idx - 1]}_{parts[uuid_idx]}"
        else:
            file_id = parts[uuid_idx]
    else:
        # brak uuid — zwracamy np. 0
        file_id = parts[0]

    file_path = os.path.join(path_config['image_for_analysis_path'], file_name)
    measuring_dir = path_config['measuring_points_path']
    analysis_type = preprocessing_config[analysis_mode]

    obj = ZeissImageProcessor(file_path, **analysis_type)
       
    print(os.path.join(measuring_dir, f"{file_id}_measurements_points.json"))
    
    obj.save_measurement_points(os.path.join(measuring_dir, f"{file_id}_measurements_points.json"))
    visualize_points(obj, os.path.join(measuring_dir, f"{file_id}_found_points.png"))

    print(f"Finished overview analysis for: {file_name}")

elif experiment_progress == 'reanalysis_z':
    file_name = sys.argv[2]

    if '|' in file_name:
        folder_name, obj_id = file_name.split('|', 1)
        
        print("1: {}, 2: {}".format(folder_name, obj_id))
        
        reanalysis_dir = os.path.join(path_config['results_path'], folder_name, f"obj_{obj_id}")
        
        saving_name = f"{folder_name}_{obj_id}"
        
    else:
        obj_id = file_name
        saving_name = obj_id
        reanalysis_dir = os.path.join(path_config['results_path'], f"obj_{obj_id}")

    
    # znajdź pierwszy plik .czi
    czi_files = [f for f in os.listdir(reanalysis_dir) if f.lower().endswith("reanalysis_z.czi")]
 
    if not czi_files:
        raise FileNotFoundError(f"Brak plikow .czi w katalogu {reanalysis_dir}")

    file_path = os.path.join(reanalysis_dir, czi_files[0])
    measuring_dir = path_config['measuring_points_path']
    analysis_type = preprocessing_config[analysis_mode]

    obj = ZeissImageProcessor(file_path, **analysis_type)   
    
    obj.save_measurement_points(os.path.join(measuring_dir, f"{saving_name}_measurements_points_reanalysis_z.json"))


    print(f"Finished z reanalysis of object: {obj_id}")


elif experiment_progress == 'reanalysis_xy':
    file_name = sys.argv[2]

    if '|' in file_name:
        folder_name, obj_id = file_name.split('|', 1)
        
        print("1: {}, 2: {}".format(folder_name, obj_id))
        
        reanalysis_dir = os.path.join(path_config['results_path'], folder_name, f"obj_{obj_id}")
        
        saving_name = f"{folder_name}_{obj_id}"
        
    else:
        obj_id = file_name
        saving_name = obj_id
        reanalysis_dir = os.path.join(path_config['results_path'], f"obj_{obj_id}")

    # znajdź pierwszy plik .czi
    czi_files = [k for k in os.listdir(reanalysis_dir) if k.endswith('.czi')]


    if not czi_files:
        raise FileNotFoundError(f"No czi files in the: {reanalysis_dir}")

    file_path = os.path.join(reanalysis_dir, czi_files[0])
    measuring_dir = path_config['measuring_points_path']
    analysis_type = preprocessing_config[analysis_mode]

    obj = ZeissImageProcessor(file_path, **analysis_type)
    
    if len(obj.measurement_points) > 1:
        print("Found multiple objects after reanalysis: {}".format(len(obj.measurement_points)))
        closest_point = choose_the_closest_point(obj.measurement_points, obj.metadata["stage_position"])
        obj.measurement_points = [closest_point]
        
    elif len(obj.measurement_points) == 0:
        
        print("Did not found any objects after xy-reanalysis")
        
    else:
        
        print("Found exactly one object after xy-reanalysis")
        
    
    obj.save_measurement_points(os.path.join(measuring_dir, f"{saving_name}_measurements_points_reanalysis_xy.json"))
    visualize_points(obj, os.path.join(measuring_dir, f"{saving_name}_found_points_reanalysis_xy.png"))

    print(f"Finished reanalysis of the object: {obj_id}")



else:
    raise ValueError(f"Wrong analysis type: {experiment_progress}")

