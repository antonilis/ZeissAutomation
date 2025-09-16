import os
import numpy as np
import xml.etree.ElementTree as ET
import czifile
from image_analysis.analysis import GUV, HexagonalMesh
import json



class ZeissImageProcessor:
    def __init__(self, czi_file_path, analysis_channel=1, chosen_analysis='hexagonal'):
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
        tree = ET.ElementTree(root)
        tree.write('metadata', encoding="utf-8", xml_declaration=True)
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
        """Extract stage positions from Scenes/Positions/Position nodes in CZI metadata."""
        positions = []
        for pos in root.findall(".//{*}Scenes/{*}Scene/{*}Positions/{*}Position"):
            x = pos.attrib.get("X")
            y = pos.attrib.get("Y")
            z = pos.attrib.get("Z")
            positions.append({
                "x": float(x) if x else None,
                "y": float(y) if y else None,
                "z": float(z) if z else None,
            })
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

            points_table_coordinates = self.pixel_to_stage(points)

        else:
            points_table_coordinates = None

        return points_table_coordinates, points

    def pixel_to_stage(self, measurement_points):
        """
        Convert measurement points (in pixels) into stage coordinates (in µm).
        Keeps the same dict structure as measurement_points,
        but values are np.ndarray of shape (N, 3).
        """

        results = {}

        # Image size
        height, width = self.image_to_analyze.shape

        # Scaling (µm/pixel)
        sx = self.metadata["scaling_um_per_pixel"].get("X", 1.0)
        sy = self.metadata["scaling_um_per_pixel"].get("Y", 1.0)

        # Stage position (center of image)
        stage_pos = (
            self.metadata["stage_position"][0]
            if self.metadata["stage_position"]
            else {"x": 0, "y": 0, "z": 0}
        )
        X_stage, Y_stage, Z_stage = stage_pos["x"], stage_pos["y"], stage_pos["z"]

        def transform(points: np.ndarray) -> np.ndarray:
            """Transform (N,2) array of pixel points into (N,3) array in µm."""
            # Rozdziel na i, j
            i = points[:, 1]  # y-pixels (col index)
            j = points[:, 0]  # x-pixels (row index)

            x_um = X_stage + (i - width / 2) * sx
            y_um = Y_stage + (j - height / 2) * sy
            z_um = np.full_like(x_um, Z_stage, dtype=float)

            return np.column_stack((x_um, y_um, z_um))

        for key, pts in measurement_points.items():
            pts = np.asarray(pts).reshape(-1, 2)  # upewnij się, że (N,2)
            results[key] = transform(pts)

        return results

    def save_metadata(metadata_str, out_file="czi_metadata.xml"):
        """Zapisuje pełne metadane XML do pliku."""
        root = ET.fromstring(metadata_str)
        tree = ET.ElementTree(root)
        tree.write(out_file, encoding="utf-8", xml_declaration=True)


    def save_measurement_points(self, path):
        # Tworzymy kopię słownika, w której tablice numpy zamieniamy na listy
        serializable_dict = {}
        for key, value in self.measurement_points.items():
            if isinstance(value, np.ndarray):
                serializable_dict[key] = value.tolist()
            else:
                serializable_dict[key] = value

        # Zapisujemy do pliku JSON
        with open(path, 'w') as f:
            json.dump(serializable_dict, f)


if __name__ == '__main__':

    def choose_chi_files(main_path):

        files = [f for f in os.listdir(main_path) if f.lower().endswith('.czi')]
        directions = [os.path.join(main_path, file_path) for file_path in files]

        return directions



    main_path_GUVs = 'GUVs_Laura'
    main_path_hexagonal = '01092025-onchip-3rd'

    GUVs_directions = choose_chi_files(main_path_GUVs)
    hexagonal_directions = choose_chi_files(main_path_hexagonal)


    obj_GUVs = ZeissImageProcessor(GUVs_directions[0], chosen_analysis='GUVs')
    obj_hex = ZeissImageProcessor(hexagonal_directions[0], chosen_analysis='hexagonal')


    #obj_GUVs.save_measurement_points('measurement_points.json')
