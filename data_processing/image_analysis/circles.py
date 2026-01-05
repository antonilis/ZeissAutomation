from collections import defaultdict
import cv2
import numpy as np

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class
from data_processing.image_analysis.pixel_stage_converter import z_normal


@register_class
class Circles(ImageAnalysisTemplate):
    """
    Class for detecting circular objects using Otsu thresholding
    and contour-based shape analysis.
    """

    @staticmethod
    def _classify_contours_by_area(contours, hierarchy, top_n=None):
        """
        Classify external contours by area and return them sorted in descending order.
        :return: list of external contours sorted by area
        """
        # Map parent indices to their child contours
        parent_children_map = defaultdict(list)
        external_contours = []
        # Identify external contours and collect their largest internal
        for i in range(len(contours)):
            if hierarchy[0][i][3] == -1:  # External contour has no parent
                ext_contour = contours[i]
                area = cv2.contourArea(ext_contour)
                internal_contours = parent_children_map.get(i, [])
                # Find the largest internal contour if any
                largest_internal = None
                if internal_contours:
                    largest_internal = max(internal_contours, key=lambda c: cv2.contourArea(c))
                external_contours.append((area, ext_contour, largest_internal))
        # Sort by external contour area (descending)
        external_contours.sort(reverse=True, key=lambda x: x[0])
        # Apply top_n limit
        if top_n is not None:
            external_contours = external_contours[:top_n]
        # Return tuples (external_contour, largest_internal_contour)
        return [(ext) for (_, ext, largest_internal) in external_contours]

    @staticmethod
    def get_contour_centers_and_radii(contours, min_fit_ratio):
        """
        Compute centers and radii of contours fitting a circular shape.
        :return: dictionary mapping contour indices to center position, radius,
                 and fit ratio in pixel coordinates
        """
        results = {}
        for idx, cnt in enumerate(contours):
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])

                (x, y), radius = cv2.minEnclosingCircle(cnt)
                cnt_area = cv2.contourArea(cnt)
                circle_area = np.pi * (radius ** 2)

                # area ratio
                fit_ratio = cnt_area / circle_area if circle_area > 0 else 0

                if fit_ratio >= min_fit_ratio:
                    results[idx] = {"center": (cx, cy), "radius": int(radius), "fit ratio": fit_ratio}

        return results

    def filter_by_size(self, GUVs_dict, min_size_um=1, max_size_um=50):
        """
        Filter detected objects by size range in micrometers.
        :return: list of dictionaries with object positions in pixel coordinates
                 and radii in micrometers
        """
        scale = np.mean([
            self.metadata['scaling_um_per_pixel']['X'],
            self.metadata['scaling_um_per_pixel']['Y']
        ])

        filtered = []
        for v in GUVs_dict.values():
            radius_um = v['radius'] * scale * 10 ** (6)
            if min_size_um <= radius_um <= max_size_um:
                filtered.append({
                    'position': [v['center'][0], v['center'][1]],
                    'radius': radius_um, 'fit ratio': v['fit ratio']
                })

        return filtered

    def get_measurement_points(self):
        """
        Detect circular objects, filter them by size, and convert their positions
        to stage coordinates.
        :return: lists of dictionaries with the founded objects properties and their positions
                 in the pixels coordinates and in the stage coordinates in um
        """

        normalized = cv2.normalize(self.image, None, 0, 255, cv2.NORM_MINMAX)

        blurred = cv2.GaussianBlur(normalized, (3, 3), 0)

        # Canny algorhitm when circles on TL and findContours for FL
        if 'TL' not in self.analysis_details.keys():
            otsu_threshold, thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = np.ones((3, 3), np.uint8)
            for_contours_finding = cv2.morphologyEx(thresholded, cv2.MORPH_OPEN, kernel, iterations=1)

        else:
            try:
                for_contours_finding = cv2.Canny(blurred, 5, 15)
            except cv2.error as e:
                print(f"OpenCV2 problem: {e}")
                for_contours_finding = np.zeros_like(self.image, dtype=np.uint8)

        found_contours, hierarchy = cv2.findContours(np.array(for_contours_finding, dtype=np.uint8), cv2.RETR_CCOMP,
                                                     cv2.CHAIN_APPROX_SIMPLE)

        classified_external = self._classify_contours_by_area(found_contours, hierarchy)

        center_radius_dict = self.get_contour_centers_and_radii(classified_external,
                                                                self.analysis_details.get('min_fit_ratio', 0.2))

        measurement_point = self.filter_by_size(center_radius_dict, **{k: v for k, v in self.analysis_details.items() if
                                                                       k in ["min_size_um", "max_size_um"]})

        transformed_points = self.pixel_converter.convert_points(measurement_point, xy_mode='normal',
                                                                 z_strategy=z_normal)

        return measurement_point, transformed_points
