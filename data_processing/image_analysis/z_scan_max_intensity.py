import numpy as np

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class


@register_class
class Max_intensity_Z_Scan(ImageAnalysisTemplate):
    """
     CLass for finding the measurement points at maximum intensity along Z axis.
     """

    def get_max_intensity(self):
        """
        Find the index along Z axis with maximum summed intensity.
        :return: int, index of Z slice with maximum intensity
        """
        z_sums = np.sum(self.image, axis=tuple(range(1, self.image.ndim)))
        return np.argmax(z_sums)

    def get_measurement_points(self):
        """
        Generate measurement points at maximum intensity and convert them to stage coordinates.
        :return: lists of dictionaries with the founded objects properties and their positions
                 in the pixels coordinates and in the stage coordinates in um
        """

        max_z_index = self.get_max_intensity()

        x, y = self.image.shape[1] / 2 - 1, self.image.shape[2] / 2 - 1

        if self.metadata['z_scan']['is_center_mode']:

            z_dim = self.image.shape[0]

            center = np.round(z_dim / 2 + 0.5)

            moved_z_index = max_z_index - center

            measurement_points = [{'position': [x, y, moved_z_index]}]

        else:

            measurement_points = [{'position': [x, y, max_z_index]}]

        transformed_points = self.pixel_converter.convert_points(measurement_points, xy_mode="center",
                                                                 z_strategy=self.pixel_converter.convert_z_auto)

        return measurement_points, transformed_points
