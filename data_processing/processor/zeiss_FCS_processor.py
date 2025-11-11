import os
import numpy as np
import json
from IO.read_raw_corr_file import read_confo_cor3
import re
from datetime import datetime


class ZeissFCSProcessor:
    """
    Processes Zeiss ConfoCor3 .raw files and identifies the file
    with the highest mean photon intensity.
    """

    def __init__(self, folder_path):
        """
        Initialize the FCS processor.

        :param folder_path: Path to the folder containing .raw files
        """
        self.folder_path = folder_path

        print(os.listdir(folder_path))

        # Collect all .raw files from the folder
        self.raw_files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".raw")
        ]

        with open(os.path.join(self.folder_path, 'FCS_points.json'), 'r') as file:
            data = json.load(file)

        self.FCS_measurements_points = data

        if not self.raw_files:
            print("No .raw files found in:", folder_path)

    def mean_intensity_from_photon_data(self, photon_data):
        """
        Calculate mean photon intensity (photons per second)
        from photon arrival time data.

        :param photon_data: Dictionary containing photon timing data
        :return: Mean photon intensity [photons/s]
        """
        ph_sync = photon_data["ph_sync"]  # photon tick times
        sync_rate = photon_data["TTResult_SyncRate"]  # clock frequency [Hz]

        # Convert ticks to seconds
        time_s = ph_sync / sync_rate

        # Compute histogram of photon arrivals in time bins
        bin_width = 0.1  # seconds
        bins = np.arange(0, time_s[-1] + bin_width, bin_width)
        counts, _ = np.histogram(time_s, bins=bins)

        # Mean photon rate (counts per second)
        return np.mean(counts / bin_width)

    def find_highest_intensity_file(self):
        """
        Process all .raw files, compute their mean intensity,
        and return the file with the highest intensity.

        :return: (best_file_path, max_intensity)
        """
        results = []

        for raw_path in self.raw_files:
            try:
                ph_data = read_confo_cor3(raw_path)
                mean_intensity = self.mean_intensity_from_photon_data(ph_data)
                results.append((raw_path, mean_intensity))
                print(os.path.basename(raw_path), ":", round(mean_intensity, 2))
            except Exception as e:
                print("Error reading file:", raw_path, ":", str(e))

        if not results:
            print("No valid photon data found.")
            return None

        # Select the file with the maximum mean intensity
        best_file, max_intensity = max(results, key=lambda x: x[1])

        print("\nHighest mean intensity:", round(max_intensity, 2), "photons/s")
        print("File:", os.path.basename(best_file))

        return best_file, max_intensity

    def get_measurement_points(self):  # connects best file with the stage position

        best_file, max_intensity = self.find_highest_intensity_file()

        pattern = r"P(\d+)"

        match = re.search(pattern, best_file)
        if match:
            p_tag = match.group()
        else:
            raise ValueError('Could not find the FCS_points.json file')

        positions = self.FCS_measurements_points[p_tag]

        # build dictionary for that point
        point_entry = {
            "position": [positions["x"], positions["y"], positions["z"]],
            "intensity": max_intensity,  # assuming your dict has it
            "source": self.folder_path,  # source path of data
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        measurement_points = {p_tag: point_entry}

        return measurement_points

    def save_measurement_points(self, saving_path):
        """Saves measurement_points dict to a JSON file."""

        data = self.get_measurement_points()

        with open(saving_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print("Saved measurement points to:", saving_path)








