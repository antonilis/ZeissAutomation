from collections import defaultdict
import cv2
import numpy as np
from scipy import ndimage

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class
from data_processing.image_analysis.pixel_stage_converter import z_normal


@register_class
class Circles(ImageAnalysisTemplate):
    """
    Class for detecting circular objects. On fluorescence it uses Otsu thresholding and contour-based shape
    analysis. With the 'TL' key in the analysis details it reads the rim of a GUV on transmitted light instead:
    gradient pixels vote for circle centres, and the circle is then fitted to the rim ray by ray.
    """

    provides_object_rois = True

    # transmitted light: the rim is a few pixels wide, so the voting does not need the full resolution
    voting_pixel_um = 0.4
    smoothing_um = 0.26
    background_um = 5.2
    strong_gradient_percentile = 97
    min_separation_um = 3.9
    rim_search_window = 0.35
    number_of_rays = 180
    min_number_of_rays = 30

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
                    # the contour itself is carried along, because get_object_rois needs the real
                    # outline and not the enclosing circle
                    results[idx] = {"center": (cx, cy), "radius": int(radius), "fit ratio": fit_ratio,
                                    "contour": cnt}

        return results

    def _vote_for_circles(self, image, um_per_pixel, min_size_um, max_size_um, min_score):
        """
        Every strong gradient pixel votes along its own normal, on both sides, for a centre at every radius. The votes
        are divided by the circumference, so a score is roughly the share of a circle that agrees. The sign of the
        gradient is ignored, because a GUV can have a bright or a dark rim depending on where the focus is.
        Only the best score of each pixel is kept, an array over all radii would not fit a tiled overview in memory.
        :return: list of tuples (x, y, radius, score) in pixels of the given image, the best score first
        """
        factor = max(int(self.voting_pixel_um / um_per_pixel), 1)
        pixel_um = um_per_pixel * factor

        height, width = image.shape[0] // factor, image.shape[1] // factor
        coarse = image[:height * factor, :width * factor].reshape(height, factor, width, factor).mean(axis=(1, 3))

        band = (ndimage.gaussian_filter(coarse, self.smoothing_um / pixel_um)
                - ndimage.gaussian_filter(coarse, self.background_um / pixel_um))
        gradient_x, gradient_y = ndimage.sobel(band, axis=1), ndimage.sobel(band, axis=0)
        strength = np.hypot(gradient_x, gradient_y)

        rows, columns = np.nonzero(strength > np.percentile(strength, self.strong_gradient_percentile))
        normal_x = gradient_x[rows, columns] / strength[rows, columns]
        normal_y = gradient_y[rows, columns] / strength[rows, columns]

        min_radius = max(int(min_size_um / pixel_um), 3)
        max_radius = max(int(max_size_um / pixel_um), min_radius + 1)

        best_score = np.zeros(coarse.shape, dtype=np.float32)
        best_radius = np.zeros(coarse.shape, dtype=np.int32)

        for radius in range(min_radius, max_radius):
            votes = np.zeros(coarse.shape, dtype=np.float32)

            for side in (1, -1):
                x = np.rint(columns + side * radius * normal_x).astype(int)
                y = np.rint(rows + side * radius * normal_y).astype(int)
                inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
                np.add.at(votes, (y[inside], x[inside]), 1)

            votes = ndimage.gaussian_filter(votes, 1) / (2 * np.pi * radius)

            better = votes > best_score
            best_score[better] = votes[better]
            best_radius[better] = radius

        separation = max(int(self.min_separation_um / pixel_um), 3)
        peaks = (best_score == ndimage.maximum_filter(best_score, separation)) & (best_score >= min_score)

        # a radius stuck at the lower limit means the search found a blob and not a rim
        found = [((x + 0.5) * factor, (y + 0.5) * factor, best_radius[y, x] * factor, float(best_score[y, x]))
                 for y, x in zip(*np.nonzero(peaks)) if best_radius[y, x] > min_radius]

        return sorted(found, key=lambda circle: circle[3], reverse=True)

    @staticmethod
    def _fit_circle(x, y):
        """
        Algebraic least squares circle fit.
        :return: tuple (x of the centre, y of the centre, radius)
        """
        design = np.c_[2 * x, 2 * y, np.ones_like(x)]
        a, b, c = np.linalg.lstsq(design, x ** 2 + y ** 2, rcond=None)[0]

        return a, b, np.sqrt(c + a ** 2 + b ** 2)

    def _fit_rim(self, image, um_per_pixel, x, y, radius):
        """
        Takes the steepest point of the rim on every ray and fits a circle to them, rejecting outliers, so that a
        neighbour touching the rim drops out. Rays leaving the image are skipped, a GUV cut by the border still counts.
        :return: dict with the center, radius, fit ratio and contour in pixels, None when too few rays are left
        """
        smoothed = ndimage.gaussian_filter(image, self.smoothing_um / um_per_pixel)
        angles = np.linspace(0, 2 * np.pi, self.number_of_rays, endpoint=False)

        for _ in range(3):
            radii = np.arange(radius * (1 - self.rim_search_window), radius * (1 + self.rim_search_window), 0.5)

            ray_x, ray_y = x + np.outer(np.cos(angles), radii), y + np.outer(np.sin(angles), radii)
            on_image = ((ray_x >= 0) & (ray_x < image.shape[1]) & (ray_y >= 0) & (ray_y < image.shape[0])).all(axis=1)

            if on_image.sum() < self.min_number_of_rays:
                return None

            profiles = ndimage.map_coordinates(smoothed, [ray_y[on_image], ray_x[on_image]], order=1)
            slope = np.gradient(ndimage.gaussian_filter1d(profiles, 3, axis=1), axis=1)

            # the rim has one polarity all the way round, so the sign of the mean profile decides for every ray
            mean_slope = slope.mean(axis=0)
            polarity = np.sign(mean_slope[np.abs(mean_slope).argmax()])
            edge = radii[(polarity * slope).argmax(axis=1)]

            edge_x, edge_y = x + edge * np.cos(angles[on_image]), y + edge * np.sin(angles[on_image])
            keep = np.ones(len(edge), dtype=bool)

            for _ in range(5):
                if keep.sum() < self.min_number_of_rays:
                    return None

                x, y, radius = self._fit_circle(edge_x[keep], edge_y[keep])
                residual = np.hypot(edge_x - x, edge_y - y) - radius
                spread = 1.4826 * np.median(np.abs(residual[keep] - np.median(residual[keep])))
                keep = np.abs(residual) < max(2.5 * spread, 1.5)

        contour = cv2.ellipse2Poly((int(round(x)), int(round(y))), (int(round(radius)), int(round(radius))), 0, 0, 360, 5)

        # a GUV cut by the border would otherwise get an outline larger than the part of it in the image
        contour[:, 0] = np.clip(contour[:, 0], 0, image.shape[1] - 1)
        contour[:, 1] = np.clip(contour[:, 1], 0, image.shape[0] - 1)

        return {"center": (float(x), float(y)), "radius": float(radius), "fit ratio": float(keep.mean()),
                "contour": contour.reshape(-1, 1, 2)}

    def find_circles_on_transmitted_light(self, min_size_um=1, max_size_um=50, min_score=0.05, min_fit_ratio=0.2):
        """
        Finds GUVs by the rim they have on transmitted light. Unlike a threshold this does not need the object to differ
        from the background in brightness, which is what fails on a low contrast or uneven field.
        :return: dictionary mapping indices to center position, radius, fit ratio and contour in pixel coordinates
        """
        z_scan = self.metadata.get('z_scan') or {}

        # the rim of a GUV hardly moves with z on transmitted light, so one plane of a z-stack is enough
        if self.image.ndim == 3 and z_scan.get('is_activated'):
            image = self.image[self.image.shape[0] // 2].astype(float)

        elif self.image.ndim == 2:
            image = self.image.astype(float)

        else:
            print("Circles on transmitted light needs a plane or a z-stack, got an image of shape", self.image.shape)
            return {}

        scaling = self.metadata['scaling_um_per_pixel']
        um_per_pixel = np.mean([scaling['X'], scaling['Y']]) * 10 ** 6

        results = {}

        for x, y, radius, _ in self._vote_for_circles(image, um_per_pixel, min_size_um, max_size_um, min_score):
            rim = self._fit_rim(image, um_per_pixel, x, y, radius)

            if rim is None or rim["fit ratio"] < min_fit_ratio:
                continue

            # two peaks can settle on the same rim, the better scored one came first
            is_repeated = any(np.hypot(rim["center"][0] - other["center"][0], rim["center"][1] - other["center"][1])
                              < 0.5 * other["radius"] for other in results.values())

            if not is_repeated:
                results[len(results)] = rim

        return results

    def filter_by_size(self, GUVs_dict, min_size_um=1, max_size_um=50):
        """
        Filter detected objects by size range in micrometers.
        The contours are returned separately rather than inside the dictionaries, because those are
        written to JSON further down the pipeline and a numpy array would not survive the trip.
        :return: tuple (list of dictionaries with object positions in pixel coordinates and radii in
                 micrometers, dict of object id to the matching contour)
        """
        scale = np.mean([
            self.metadata['scaling_um_per_pixel']['X'],
            self.metadata['scaling_um_per_pixel']['Y']
        ])

        filtered = []
        contours = {}

        for v in GUVs_dict.values():
            radius_um = v['radius'] * scale * 10 ** (6)
            if min_size_um <= radius_um <= max_size_um:
                object_id = self.new_object_id()

                filtered.append({
                    'id': object_id,
                    'position': [v['center'][0], v['center'][1]],
                    'radius': radius_um, 'fit ratio': v['fit ratio']
                })
                contours[object_id] = v['contour']

        return filtered, contours

    def get_object_rois(self):
        """
        Filled outline of every object that survived the size filter, keyed by the same id as the
        points. The whole object is handed over, its interior included, so that an object selection
        can decide for itself whether it cares about the membrane, the lumen or both.
        :return: dict of object id to its bounding box and a boolean mask inside it
        """
        rois = {}

        for object_id, contour in self.object_contours.items():
            x, y, width, height = cv2.boundingRect(contour)

            # drawn into the bounding box only, with the contour shifted by the same offset
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, 1, thickness=-1, offset=(-x, -y))

            rois[object_id] = {'x_start': x, 'x_stop': x + width,
                               'y_start': y, 'y_stop': y + height,
                               'mask': mask.astype(bool)}

        return rois

    def get_measurement_points(self):
        """
        Detect circular objects, filter them by size, and convert their positions
        to stage coordinates.
        :return: lists of dictionaries with the founded objects properties and their positions
                 in the pixels coordinates and in the stage coordinates in um
        """

        # rim voting when circles on TL and findContours for FL
        if 'TL' in self.analysis_details.keys():
            center_radius_dict = self.find_circles_on_transmitted_light(
                **{k: v for k, v in self.analysis_details.items() if
                   k in ["min_size_um", "max_size_um", "min_score", "min_fit_ratio"]})

        else:
            normalized = cv2.normalize(self.image, None, 0, 255, cv2.NORM_MINMAX)

            blurred = cv2.GaussianBlur(normalized, (3, 3), 0)

            otsu_threshold, thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = np.ones((3, 3), np.uint8)
            for_contours_finding = cv2.morphologyEx(thresholded, cv2.MORPH_OPEN, kernel, iterations=1)

            found_contours, hierarchy = cv2.findContours(np.array(for_contours_finding, dtype=np.uint8), cv2.RETR_CCOMP,
                                                         cv2.CHAIN_APPROX_SIMPLE)

            classified_external = self._classify_contours_by_area(found_contours, hierarchy)

            center_radius_dict = self.get_contour_centers_and_radii(classified_external,
                                                                    self.analysis_details.get('min_fit_ratio', 0.2))

        measurement_point, self.object_contours = self.filter_by_size(
            center_radius_dict,
            **{k: v for k, v in self.analysis_details.items() if k in ["min_size_um", "max_size_um"]})

        transformed_points = self.pixel_converter.convert_points(measurement_point, xy_mode='normal',
                                                                 z_strategy=z_normal)

        return measurement_point, transformed_points
