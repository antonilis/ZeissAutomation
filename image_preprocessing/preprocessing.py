import os
import numpy as np
import xml.etree.ElementTree as ET
import czifile
from image_analysis.analysis import GUV, HexagonalMesh
import json
import copy
import uuid
from datetime import datetime

class ZeissImageProcessor:
    def __init__(self, czi_file_path, analysis_channel=1, chosen_analysis='GUVs'):
        self.czi_file_path = czi_file_path
        self.analysis_channel = analysis_channel

        self.metadata, self.image_to_analyze = self.load_czi_data(czi_file_path, analysis_channel)

        self.image_analyzer = self.get_analysis_type(chosen_analysis)
        self.measurement_points, self.not_scaled_points = self.get_measurement_points()

    def load_czi_data(self, file_path, analysis_channel):

        with czifile.CziFile(file_path) as czi:

            metadata_str = czi.metadata()
            metadata = self.extract_metadata(metadata_str)

            image_data = czi.asarray()
            axes = czi.axes  # np. "STCZYX"

            image_to_analyze = self.get_image_to_analyze(image_data, axes, analysis_channel)

            return metadata, image_to_analyze

    def extract_metadata(self, metadata_str):
        # Parsowanie metadanych z XML
        root = ET.fromstring(metadata_str)
        #tree = ET.ElementTree(root)
        #tree.write('metadata', encoding="utf-8", xml_declaration=True)
        metadata = {}
        metadata["scaling_um_per_pixel"] = self._extract_scaling(root)
        metadata["channels"] = self._extract_channels(root)
        metadata["stage_position"] = self._extract_positions(root)
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

    def get_image_to_analyze(self, image, axes, analysis_channel):


        slicer = []
        for ax in axes:
            if ax == "C":
                slicer.append(analysis_channel)
            elif ax in ["S", "T", "Z"]:  # wybieramy 0 jeśli nie analizujemy stacków/czasu
                slicer.append(0)
            else:
                slicer.append(slice(None))  # zostawiamy całość, np. YX

        img_channel = image[tuple(slicer)]

        return np.squeeze(img_channel)

    def get_analysis_type(self, chosen_analysis):
        available_analysis = {
            'hexagonal': HexagonalMesh,
            'GUVs': GUV
        }
        strategy_class = available_analysis.get(chosen_analysis)
        if not strategy_class:
            raise ValueError(
                f"Unknown analysis type: {chosen_analysis}, please choose from {available_analysis.keys()}")

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
        stage_pos = self.metadata.get("stage_position", {"x": 10**(-6), "y": 10**(-6), "z": 10**(-6)})[0]
        scaling = self.metadata["scaling_um_per_pixel"]

        transformed_points = copy.deepcopy(points_list)
        for point in transformed_points:
            px = np.array(point["position"], dtype=float)

            x_um = stage_pos["x"] + (px[0] - width / 2) * scaling["X"] * 10**(6)
            y_um = stage_pos["y"] + (px[1] - height / 2) * scaling["Y"]* 10**(6)
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



    main_path_GUVs = './czi_files/GUVs_Laura'
    main_path_hexagonal = './czi_files/01092025-onchip-3rd'
    main_path = './czi_files/image_for_analysis'

    main_directions = choose_chi_files(main_path)
    GUVs_directions = choose_chi_files(main_path_GUVs)
    hexagonal_directions = choose_chi_files(main_path_hexagonal)


    obj_GUVs = ZeissImageProcessor(GUVs_directions[0], analysis_channel=0, chosen_analysis='GUVs')
    obj_hex = ZeissImageProcessor(hexagonal_directions[0], chosen_analysis='hexagonal')
    obj_main = ZeissImageProcessor(main_directions[6], analysis_channel=0, chosen_analysis='GUVs')

    obj_main.save_measurement_points('measurement_points.json')
