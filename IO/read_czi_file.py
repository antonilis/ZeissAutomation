import xml.etree.ElementTree as ET
from pylibCZIrw import czi as pyczi
import numpy as np


class CziFileReader:

    def __init__(self, path, analysis_channel):

        self.path = path
        self.analysis_channel = analysis_channel
        self.czi_file, self.metadata = self.read_czi_file(path)

    def read_czi_file(self, path):

        with pyczi.open_czi(path) as czidoc:
            metadata = self.extract_metadata(czidoc.raw_metadata)
            image_data = self.get_image_to_analyze(czidoc, self.analysis_channel)

        return image_data, metadata

    def extract_metadata(self, metadata_str):

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
