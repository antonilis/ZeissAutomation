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
        self.measurement_points = self.get_measurement_points()

    def load_czi_data(self, file_path, analysis_channel):

        with czifile.CziFile(file_path) as czi:

            metadata_str = czi.metadata()
            metadata = self.extract_metadata(metadata_str)

            image_data = czi.asarray()
            image_to_analyze = self.get_image_to_analyze(image_data, analysis_channel)

            return metadata, image_to_analyze

    def extract_metadata(self, metadata_str):
        # Parsowanie metadanych z XML
        root = ET.fromstring(metadata_str)
        metadata = {}
        metadata["scaling_um_per_pixel"] = self._extract_scaling(root)
        metadata["channels"] = self._extract_channels(root)
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

    def get_image_to_analyze(self, image, analysis_channel):


        img_channel = image[0,0,analysis_channel,0,0, Ellipsis,0]

        return img_channel

    def get_analysis_type(self, chosen_analysis):
        available_analysis = {
            'hexagonal': HexagonalMesh,
            'GUVS': GUV
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

        return points

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
    main_path = '01092025-onchip-3rd'
    files = [f for f in os.listdir(main_path) if f.lower().endswith('.czi')]

    directions = [os.path.join(main_path, file_path) for file_path in files]

    obj = ZeissImageProcessor(directions[0])
    obj.save_measurement_points('measurement_points.json')
