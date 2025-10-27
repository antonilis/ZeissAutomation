import numpy as np
from scipy.spatial import Delaunay
from scipy.cluster.vq import kmeans, vq
from skimage.filters import threshold_multiotsu
import cv2



from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class



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