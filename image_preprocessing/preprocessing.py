import os
import numpy as np
import xml.etree.ElementTree as ET
from pylibCZIrw import czi as pyczi
from image_preprocessing.image_analysis.analysis import get_image_analysis_type, get_available_analysis
import json
import copy
import uuid
from datetime import datetime
import sys
import matplotlib.pyplot as plt


class ZeissImageProcessor:
    def __init__(self, czi_file_path, analysis_channel=1, chosen_analysis='FluorescentGUV'):
        self.czi_file_path = czi_file_path
        self.analysis_channel = analysis_channel

        self.metadata, self.image_to_analyze = self.load_czi_data(czi_file_path, analysis_channel)

        self.image_analyzer = self.get_analysis_type(chosen_analysis)
        self.measurement_points, self.not_scaled_points = self.get_measurement_points()

    def load_czi_data(self, file_path, analysis_channel):
        """
        Ładuje dane z pliku CZI przy użyciu pylibCZIrw (obsługuje Zstd).
        """
        with pyczi.open_czi(file_path) as czidoc:
            # wyciągamy i parsujemy metadane XML
            metadata = self.extract_metadata(czidoc.raw_metadata)
            image_data = self.get_image_to_analyze(czidoc, analysis_channel)

        return metadata, image_data

    def extract_metadata(self, metadata_str):
        # Parsowanie metadanych z XML
        root = ET.fromstring(metadata_str)

        metadata = {}
        metadata["scaling_um_per_pixel"] = self._extract_scaling(root)
        metadata["channels"] = self._extract_channels(root)
        metadata["stage_position"] = self._extract_positions(root)[0]


        return metadata

    def _extract_scaling(self, root):
        scaling = {}
        for dist in root.findall(".//{*}Distance"):
            axis = dist.attrib.get("Id")
            val = dist.find(".//{*}Value")
            if axis and val is not None:
                scaling[axis] = float(val.text)
        return scaling

    def _extract_channels(self, root):
        channels = []
        for ch in root.findall(".//{*}Channel"):
            ch_id = ch.attrib.get("Id")
            ch_name = ch.findtext(".//{*}Name")
            em = ch.findtext(".//{*}EmissionWavelength")
            ex = ch.findtext(".//{*}ExcitationWavelength")
            channels.append({
                "id": ch_id,
                "name": ch_name,
                "emission_nm": float(em) if em else None,
                "excitation_nm": float(ex) if ex else None
            })
        return channels

    def _extract_positions(self, root):
        """Extract stage positions from CZI metadata (supports both Scene/Position and ParameterCollection)."""
        positions = []

        # --- 1. Standardowe pozycje w Scenes/Positions ---
        for pos in root.findall(".//{*}Scenes/{*}Scene/{*}Positions/{*}Position"):
            x = pos.attrib.get("X")
            y = pos.attrib.get("Y")
            z = pos.attrib.get("Z")
            positions.append({
                "x": float(x) if x else None,
                "y": float(y) if y else None,
                "z": float(z) if z else None,
            })

        # --- 2. Parametry osi w ParameterCollection ---
        axis_map = {"MTBStageAxisX": "x", "MTBStageAxisY": "y", "MTBFocus": "z"}
        axis_values = {}

        for pc in root.findall(".//{*}ParameterCollection"):
            axis_id = pc.attrib.get("Id")
            if axis_id in axis_map:
                pos_elem = pc.find("{*}Position")
                if pos_elem is not None and pos_elem.text:
                    try:
                        axis_values[axis_map[axis_id]] = float(pos_elem.text)
                    except ValueError:
                        axis_values[axis_map[axis_id]] = None

        if axis_values:
            positions.append(axis_values)

        return positions

    def get_image_to_analyze(self, czidoc, analysis_channel):

        # pobieramy bounding box i listę dostępnych wymiarów
        bbox = czidoc.total_bounding_box
        available_dims = list(bbox.keys())

        # przygotowujemy plane – ustawiamy 0 tylko dla wymiarów planowych
        plane = {}
        plan_dims = ('C', 'Z', 'T', 'S', 'H', 'B')
        for dim in available_dims:
            if dim in plan_dims:
                plane[dim] = 0
        # ustawiamy wybrany kanał
        if 'C' in available_dims:
            plane['C'] = analysis_channel

        # wczytujemy obraz
        img = czidoc.read(plane=plane)

        # konwertujemy na numpy i usuwamy singletony
        img_channel = np.squeeze(np.array(img))

        return np.squeeze(img_channel)

    def get_analysis_type(self, chosen_analysis):

        strategy_class = get_image_analysis_type(chosen_analysis)
        if not strategy_class:
            raise ValueError(
                f"Unknown analysis type: {chosen_analysis}, please choose from {get_available_analysis()}")

        return strategy_class(
            image=self.image_to_analyze,
            metadata=self.metadata
        )

    def get_measurement_points(self):

        points = self.image_analyzer.get_measurement_points()

        if points is not None:

            points_table_coordinates = self.pixel_positions_to_stage_positions(points)

        else:
            points_table_coordinates = None

        return points_table_coordinates, points

    def pixel_positions_to_stage_positions(self, points_list):
        width, height = self.image_to_analyze.shape
        stage_pos = self.metadata.get("stage_position", {"x": 10 ** (-6), "y": 10 ** (-6), "z": 10 ** (-6)})
        scaling = self.metadata["scaling_um_per_pixel"]

        transformed_points = copy.deepcopy(points_list)
        for point in transformed_points:
            px = np.array(point["position"], dtype=float)

            x_um = stage_pos["x"] + (px[0] - height / 2 + 0.5) * scaling["X"] * 10 ** (6)
            y_um = stage_pos["y"] + (px[1] - height / 2 + 0.5) * scaling["Y"] * 10 ** (6)
            z_um = np.full_like(x_um, stage_pos["z"], dtype=float)
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


    #main_path = './czi_files/problem_results'

    main_path = '../result_processing/data/2025.10.01/image_for_analysis'

    main_directions = choose_chi_files(main_path)

    obj_main = ZeissImageProcessor(main_directions[11], analysis_channel=2, chosen_analysis='TLGUV')
    #
    obj_main.save_measurement_points('measurement_points_TL.json')
