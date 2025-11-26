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
        points, measurement_points = self.image_analyzer.get_measurement_points()

        return measurement_points, points


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


    main_path = '../../Snap-10242.czi'

    #main_directions = choose_chi_files(main_path)

    with open('../../config/preprocessing_config.json', 'r') as file:
        preprocessing_config = json.load(file)

    details = preprocessing_config['FLGUV']

    obj_main = ZeissImageProcessor(main_path, **details)
    #
    obj_main.save_measurement_points('measurement_points_FL.json')
