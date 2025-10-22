import os
import pandas as pd
import json
from data_preprocessing.preprocessors.zeiss_image_preprocessor import ZeissImageProcessor
import re
import numpy as np
from utils import visualize_points


class ZeissResultProcessor:

    def __init__(self, path):

        self.stage_position_record = self.initialize_stage_record(path)
        self.json_files = self.read_temp_folder(path)
        self.results = self.process_results_folder(path)

    @staticmethod
    def get_files_in_folder(path, extension):
        """
        Zwraca listę pełnych ścieżek do plików w folderze `path` o danym rozszerzeniu.
        """
        files = os.listdir(path)
        files_path = []

        for file in files:
            if file.lower().endswith(extension.lower()):
                full_path = os.path.join(path, file)
                if os.path.isfile(full_path):
                    files_path.append(full_path)

        return files_path

    def initialize_stage_record(self, path):

        stage_position_record_list = []

        ovearview_path = os.path.join(path, 'image_for_analysis')

        #final_overview_path = os.path.join(path, 'results/ovearview')

        overview_files = self.get_files_in_folder(ovearview_path, 'czi')
        #final_overview_files = self.get_files_in_folder(final_overview_path, 'czi')

        files_path = overview_files #+ final_overview_files

        for file in files_path:
            obj = ZeissImageProcessor(file, analysis_channel=0, chosen_analysis='FluorescentGUV')
            obj_properties = self.extract_object_properties(obj)
            date = os.path.getmtime(file)
            obj_properties['creation date'] = date
            stage_position_record_list.append(obj_properties)

        return stage_position_record_list

    @staticmethod
    def read_json_file(file_path):

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        df = pd.DataFrame.from_dict(data, orient='index')
        return df

    def read_temp_folder(self, path):
        """
        Zwraca listę plików z folderu 'temp' znajdującego się w `path`.
        Jeśli folder nie istnieje – tworzy go i zwraca pustą listę.
        """
        temp_path = os.path.join(path, 'temp')

        files_path = self.get_files_in_folder(temp_path, 'json')

        data_frames = []

        for file in files_path:
            dat = self.read_json_file(file)
            data_frames.append(dat)

        final_df = pd.concat(data_frames)

        return final_df

    @staticmethod
    def choose_the_closest_point(measurement_points, stage_position):

        stage = np.array([stage_position['x'], stage_position['y'], stage_position['z']])

        # Obliczamy odległość euklidesową dla każdego punktu
        distances = [
            np.linalg.norm(np.array(p["position"]) - stage)
            for p in measurement_points
        ]

        # Indeks najbliższego punktu
        closest_idx = int(np.argmin(distances))

        # Zwracamy cały słownik najbliższego punktu
        return measurement_points[closest_idx]

    def extract_object_properties(self, obj):
        properties_dict = {}

        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-5][0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12}'
        uuids = re.findall(uuid_pattern, obj.czi_file_path)[0]
        stage_position = obj.metadata['stage_position']

        if len(obj.measurement_points) > 0:
            closest_measurements_point = self.choose_the_closest_point(obj.measurement_points, stage_position)
        else:
            closest_measurements_point = {'position': None, 'radius': None}

        properties_dict['points found again'] = closest_measurements_point['position']
        properties_dict['radius found again'] = closest_measurements_point['radius']
        properties_dict['stage position'] = [stage_position['x'], stage_position['y'], stage_position['z']]
        properties_dict['ID'] = uuids

        return properties_dict

    def calculate_displacement_vectors_numpy(self):

        position_col, date_col = 'stage position', 'creation date'

        df = pd.DataFrame(self.stage_position_record.copy())

        # Sortowanie
        df_sorted = df.sort_values(by=date_col).reset_index(drop=True)

        # Konwersja pozycji do tablicy NumPy
        positions = np.array(df_sorted[position_col].tolist())

        # Obliczanie przesunięć
        displacements = np.zeros_like(positions)
        displacements[1:] = positions[1:] - positions[:-1]

        # Dodanie do DataFrame
        df_sorted['displacement vector'] = displacements.tolist()

        return df_sorted


    def process_results_folder(self, path):

        results_path = os.path.join(path, 'results')

        files_path = self.get_files_in_folder(results_path, 'czi')

        obj_properties_list = []

        for file in files_path:
            date = os.path.getmtime(file)

            obj = ZeissImageProcessor(file, analysis_channel=0, chosen_analysis='FluorescentGUV', min_size_um=3.5, max_size_um=20)
            obj_properties = self.extract_object_properties(obj)

            obj_properties['creation date'] = date

            self.stage_position_record.append(obj_properties)

            visualize_points(obj, os.path.join('./founded_points', obj_properties['ID']))

            obj_properties_list.append(obj_properties)

        df = pd.DataFrame(obj_properties_list)
        merged_df = pd.merge(self.json_files, df, left_index=True, right_on='ID')

        self.stage_position_record = self.calculate_displacement_vectors_numpy()

        on_columns = ['creation date', 'ID']

        columns_from_b = on_columns + ['displacement vector']

        final_df = pd.merge(merged_df, self.stage_position_record[columns_from_b], on=on_columns, how='left')

        return final_df


if __name__ == '__main__':
    path = './data/2025_10_20/20_objective_blue_tack'

    obj = ZeissResultProcessor(path)
    result_df = obj.results

    result_df.to_pickle('20_objective_blue_tack_table_movement_analysis_result.pkl')
