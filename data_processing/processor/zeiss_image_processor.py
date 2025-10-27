import os
import numpy as np

from IO.read_czi_file import CziFileReader

import json
import copy
import uuid
from datetime import datetime
import data_processing.image_analysis
from data_processing.image_analysis.analysis_registry import get_image_analysis_type, get_available_analysis


class ZeissImageProcessor:
    def __init__(self, czi_file_path, analysis_channel=1, chosen_analysis='FluorescentGUV', **analysis_details):
        self.czi_file_path = czi_file_path
        self.analysis_channel = analysis_channel

        czi_obj = CziFileReader(self.czi_file_path, self.analysis_channel)
        self.image_to_analyze = czi_obj.czi_file
        self.metadata = czi_obj.metadata

        self.image_analyzer = self.get_analysis_type(chosen_analysis, **analysis_details)
        self.measurement_points, self.not_scaled_points = self.get_measurement_points()


    def get_analysis_type(self, chosen_analysis, **kwargs):

        strategy_class = get_image_analysis_type(chosen_analysis)
        if not strategy_class:
            raise ValueError(
                f"Unknown analysis type: {chosen_analysis}, please choose from {get_available_analysis()}")

        return strategy_class(
            image=self.image_to_analyze,
            metadata=self.metadata, **kwargs)

    def get_measurement_points(self):
        points = self.image_analyzer.get_measurement_points()
        points_table_coordinates = (
            self.pixel_positions_to_stage_positions(points)
            if points is not None else None
        )
        return points_table_coordinates, points

    def pixel_positions_to_stage_positions(self, points_list):

        if len(self.image_to_analyze.shape) == 2:
            height, width = self.image_to_analyze.shape
        elif len(self.image_to_analyze.shape) == 3:
            z_size, height, width = self.image_to_analyze.shape

        else:
            raise ValueError(f"Unexpected image shape: {self.image_to_analyze}")

        stage_pos = self.metadata.get("stage_position")
        scaling = self.metadata["scaling_um_per_pixel"]

        transformed_points = copy.deepcopy(points_list)
        for point in transformed_points:
            px = np.array(point["position"], dtype=float)

            x_um = stage_pos["x"] + (px[0] - height / 2 + 0.5) * scaling["X"] * 10 ** 6
            y_um = stage_pos["y"] + (px[1] - height / 2 + 0.5) * scaling["Y"] * 10 ** 6

            if len(px) == 2:
                z_um = np.full_like(x_um, stage_pos["z"], dtype=float)
            elif len(px) == 3:
                z_um = stage_pos['z'] + px[2] * scaling['Z'] * 10 ** 6
            else:
                raise ValueError(f"Unexpected point length: {self.image_to_analyze}")

            point["position"] = np.column_stack((x_um, y_um, z_um))[0].tolist()
        return transformed_points






    def save_measurement_points(self, filename):

        data = {}

        for p in self.measurement_points:
            point_id = str(uuid.uuid4())
            entry = dict(p)  # kopiujemy wszystkie istniejące pola tak jak są
            entry["source"] = self.czi_file_path
            entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
            data[point_id] = entry

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    def choose_chi_files(main_path):
        files = [f for f in os.listdir(main_path) if f.lower().endswith('.czi')]
        directions = [os.path.join(main_path, file_path) for file_path in files]

        return directions


    main_path = '../../result_processing/data/2025.10.01/image_for_analysis'

    main_directions = choose_chi_files(main_path)

    with open('../../config/preprocessing_config.json', 'r') as file:
        preprocessing_config = json.load(file)

    details = preprocessing_config['FLGUV']

    obj_main = ZeissImageProcessor(main_directions[11], **details)
    #
    obj_main.save_measurement_points('measurement_points_FL.json')
