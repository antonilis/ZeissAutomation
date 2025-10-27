from collections import defaultdict
import cv2
import numpy as np

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class



@register_class
class FluorescentGUV(ImageAnalysisTemplate):
    @staticmethod
    def _classify_contours_by_area(contours, hierarchy, top_n=None):
        """
        Finds external contours and their internal contours, sorted by area in descending order.
        Args:
            contours (list): List of contours.
            hierarchy (numpy.ndarray): Contour hierarchy information.
            top_n (int, optional): Number of top external contours to return. If None, returns all.
        Returns:
            list: Tuples of (external_contour, internal_contours_list) sorted by external contour area.
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
    def get_contour_centers_and_radii(contours, min_fit_ratio=0.2):
        """
        Returns a dictionary mapping contour indices to dicts {center: (cx, cy), radius: r}
        Only keeps contours that are reasonably circular.
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

        normalized = cv2.normalize(self.image, None, 0, 255, cv2.NORM_MINMAX)

        blurred = cv2.GaussianBlur(normalized, (3, 3), 0)

        otsu_threshold, thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = np.ones((3, 3), np.uint8)
        # Otwarcie (erozja then dylatacja) usunie małe połączenia
        opened = cv2.morphologyEx(thresholded, cv2.MORPH_OPEN, kernel, iterations=1)


        found_contours, hierarchy = cv2.findContours(np.array(opened, dtype=np.uint8), cv2.RETR_CCOMP,
                                                     cv2.CHAIN_APPROX_SIMPLE)

        classified_external = self._classify_contours_by_area(found_contours, hierarchy)

        center_radius_dict = self.get_contour_centers_and_radii(classified_external)

        measurement_point = self.filter_by_size(center_radius_dict, **{k: v for k, v in self.analysis_details.items() if k in ["min_size_um", "max_size_um"]})

        return measurement_point