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
        metadata['z_scan'] = self._extract_z_scan_informations(root)
        metadata['tiles'] = self._extract_tiles_informations(root)

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

    def _extract_z_scan_informations(self, root):

        z_scan_info = {
            'is_activated': False,
            'is_center_mode': False,
            'is_interval_kept': False
        }

        z_stack_setup = root.find('.//ZStackSetup')

        if z_stack_setup is not None:
            # Check if Z-stack is activated
            is_activated = z_stack_setup.get('IsActivated', 'false').lower() == 'true'
            z_scan_info['is_activated'] = is_activated

            # Get center mode
            is_center_mode = z_stack_setup.find('IsCenterMode')
            if is_center_mode is not None and is_center_mode.text:
                z_scan_info['is_center_mode'] = is_center_mode.text.lower() == 'true'

            # Get interval kept
            is_interval_kept = z_stack_setup.find('IsIntervalKept')
            if is_interval_kept is not None and is_interval_kept.text:
                z_scan_info['is_interval_kept'] = is_interval_kept.text.lower() == 'true'
            return z_scan_info

        else:
            return None

    def _extract_tiles_informations(self, root):
        positions = []
        for elem in root.iter():
            if elem.tag.endswith("SingleTileRegion"):
                name = elem.get("Name")

                def get_float(tag):
                    for child in elem:
                        if child.tag.endswith(tag) and child.text:
                            try:
                                return float(child.text)
                            except ValueError:
                                return None
                    return None

                positions.append({
                    "name": name,
                    "x": get_float("X"),
                    "y": get_float("Y"),
                    "z": get_float("Z")
                })

        return positions

    def get_image_to_analyze(self, czidoc, analysis_channel):
        # pobieramy bounding box i listę dostępnych wymiarów

        bbox = czidoc.total_bounding_box
        available_dims = list(bbox.keys())

        z_size = bbox['Z'][1] - bbox['Z'][0]


        if z_size > 1:
            z_stack = []

            for z in range(z_size):
                plane = {}
                for dim in available_dims:
                    if dim in ['C', 'Z', 'T', 'H', 'S', 'B']:
                        if dim == 'C':
                            plane['C'] = analysis_channel
                        elif dim == 'Z':
                            plane['Z'] = z
                        else:
                            plane[dim] = 0

                img = czidoc.read(plane=plane)
                img_array = np.squeeze(np.array(img))
                z_stack.append(img_array)

            z_stack = np.stack(z_stack, axis=0)
            return z_stack
        else:
            plane = {}
            for dim in available_dims:
                if dim in ['C', 'Z', 'T', 'H', 'S', 'B']:
                    if dim == 'C':
                        plane['C'] = analysis_channel
                    else:
                        plane[dim] = 0

            if len(czidoc.scenes_bounding_rectangle_no_pyramid) > 1:

                scene_stack = []

                for i in range(len(czidoc.scenes_bounding_rectangle_no_pyramid)):

                    img = czidoc.read(scene=i, plane=plane)
                    img_array = np.squeeze(np.array(img))
                    scene_stack.append(img_array)

                scene_stack = np.stack(scene_stack, axis=0)

                return scene_stack

            img = czidoc.read(plane=plane)
            img_array = np.squeeze(np.array(img))


            return img_array


if __name__ == '__main__':

    path = '../positions_image.czi'

    czi_obj = CziFileReader(path,  analysis_channel=0)

    tiles = czi_obj.metadata['tiles']
    index_found = 2
    wanted_image = None
    for image in tiles:
        point_index = int(image['name'][-1])

        if index_found == point_index:
            wanted_image = image






