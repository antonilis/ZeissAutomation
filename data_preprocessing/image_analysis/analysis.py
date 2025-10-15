import numpy as np
from scipy.spatial import Delaunay
from scipy.cluster.vq import kmeans, vq
from skimage.filters import threshold_multiotsu
import cv2
from abc import ABC, abstractmethod
from collections import defaultdict
from cellpose import models
import pandas as pd
from skimage.measure import regionprops_table


_REGISTRY = {}


def register_class(cls):
    _REGISTRY[cls.__name__] = cls
    return cls


def get_image_analysis_type(name):
    return _REGISTRY.get(name)


def get_available_analysis():
    return _REGISTRY.keys()


class ImageAnalysisTemplate(ABC):
    def __init__(self, image, metadata, **analysis_details):
        self.image = image
        self.metadata = metadata
        self.analysis_details = analysis_details

    @abstractmethod
    def get_measurement_points(self):
        pass


@register_class
class HexagonalMesh(ImageAnalysisTemplate):

    def get_mesh_nodes(self):
        # Blur
        blurred = cv2.GaussianBlur(self.image, (7, 7), 0)

        # Multi-Otsu
        thresholds = threshold_multiotsu(blurred, classes=3)
        t_high = thresholds[1]
        _, thresh = cv2.threshold(blurred, t_high, 255, cv2.THRESH_BINARY)

        # Morfologia
        thresholded = cv2.morphologyEx(
            thresh, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
        )

        # Connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresholded)

        return centroids

    def get_delaunay_edges(self, points):

        tri = Delaunay(points)
        triangles = tri.simplices

        edges = set()
        for triangle in triangles:
            for i in range(3):
                edge = tuple(sorted([triangle[i], triangle[(i + 1) % 3]]))
                edges.add(edge)

        return np.array(list(edges))

    def filter_edges_by_distance(self, points, edges, n_clusters=3, remove_outliers=False):

        # Obliczanie odległości dla każdej krawędzi
        edge_distances = []
        for edge in edges:
            dist = np.linalg.norm(points[edge[0]] - points[edge[1]])
            edge_distances.append(dist)

        edge_distances = np.array(edge_distances).reshape(-1, 1)
        edges = np.array(edges)

        if remove_outliers:
            # Obliczanie IQR i górnej granicy
            q75, q25 = np.percentile(edge_distances, [75, 25])
            iqr = q75 - q25
            upper_bound = q75 + 1.5 * iqr
            # Stworzenie maski dla nie-outlierów
            mask = (edge_distances <= upper_bound).flatten()
            edge_distances = edge_distances[mask]
            edges = edges[mask]

        if len(edge_distances) < n_clusters:
            n_clusters = len(edge_distances)

        # Znajdowanie klastrów w odległościach
        if n_clusters > 0:
            cluster_centers, _ = kmeans(edge_distances, n_clusters)
            cluster_labels, _ = vq(edge_distances, cluster_centers)
        else:
            # Jeśli nie ma krawędzi, zwróć puste listy
            return [], np.array([]), np.array([])

        # Grupowanie krawędzi według klastrów
        clustered_edges = [[] for _ in range(n_clusters)]
        for i, edge in enumerate(edges):
            cluster_idx = cluster_labels[i]
            clustered_edges[cluster_idx].append(edge)

        # Sortowanie klastrów według odległości (od najmniejszej do największej)
        sorted_indices = np.argsort(cluster_centers.flatten())
        clustered_edges = [clustered_edges[i] for i in sorted_indices]
        cluster_centers = cluster_centers[sorted_indices]

        return clustered_edges, cluster_centers, cluster_labels

    def find_midpoints_and_centroids(self, points, n_clusters=3, remove_outliers=True):

        points = np.array(points)

        # 1. Znajdź krawędzie z triangulacji Delaunay
        edges = self.get_delaunay_edges(points)

        # 2. Pogrupuj krawędzie na podstawie odległości
        clustered_edges, cluster_centers, cluster_labels = self.filter_edges_by_distance(points, edges, n_clusters,
                                                                                         remove_outliers)

        edge_midpoints = []
        for edges_group in clustered_edges:
            if len(edges_group) > 0:
                midpoints = np.mean(points[edges_group], axis=1)
                edge_midpoints.append(midpoints)

        if len(clustered_edges) > 0:
            longest_edges = clustered_edges[-1]
            polygon_centroids = np.mean(points[longest_edges], axis=1)
        else:
            polygon_centroids = np.array([])

        if len(edge_midpoints) > 0:
            return edge_midpoints[0], polygon_centroids
        else:
            return np.array([]), polygon_centroids

    def get_measurement_points(self):
        nodes = self.get_mesh_nodes()
        edge_midpoints, polygon_centroids = self.find_midpoints_and_centroids(nodes)

        measurement_points = []

        # lista par (zbiór_punktów, typ)
        groups = [
            (nodes, "node"),
            (edge_midpoints, "edge midpoint"),
            (polygon_centroids, "polygon centroid"),
        ]

        for group, point_type in groups:
            for pos in group:
                measurement_points.append({
                    "position": pos,
                    "type": point_type
                })

        return measurement_points


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

                # filtr na okrągłość
                if fit_ratio >= min_fit_ratio:
                    results[idx] = {"center": (cx, cy), "radius": int(radius)}

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
                    'radius': radius_um
                })

        return filtered

    def get_measurement_points(self):

        blurred = cv2.GaussianBlur(self.image, (5, 5), 0)

        otsu_threshold, thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        found_contours, hierarchy = cv2.findContours(np.array(thresholded, dtype=np.uint8), cv2.RETR_CCOMP,
                                                     cv2.CHAIN_APPROX_SIMPLE)

        classified_external = self._classify_contours_by_area(found_contours, hierarchy)

        center_radius_dict = self.get_contour_centers_and_radii(classified_external)

        measurement_point = self.filter_by_size(center_radius_dict, **{k: v for k, v in self.analysis_details.items() if k in ["min_size_um", "max_size_um"]})

        return measurement_point


@register_class
class TLGUV(ImageAnalysisTemplate):

    def image_segmentation(self, objects_diameter=None):
        model = models.Cellpose(model_type='cyto', gpu=True)

        masks, flows, styles, diam_mean = model.eval([self.image], diameter=objects_diameter, channels=[0, 0])

        props_table = regionprops_table(masks[0], properties=('label', 'area', 'centroid'))
        df = pd.DataFrame(props_table)

        return df



    def get_measurement_points(self):

        objects_df = self.image_segmentation(**{k: v for k, v in self.analysis_details.items() if k in ["objects_diameter"]})

        objects_df['radius'] = np.sqrt(objects_df['area'] / np.pi)

        objects_df['position'] = objects_df[['centroid-1', 'centroid-0']].values.tolist()

        measurement_points = (objects_df[['position', 'radius', 'area']].to_dict(orient='records'))

        return measurement_points
