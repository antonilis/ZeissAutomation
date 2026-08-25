from cellpose import models
import pandas as pd
from skimage.measure import regionprops_table
import numpy as np
import torch

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class
from data_processing.image_analysis.pixel_stage_converter import z_normal


@register_class
class Cellpose_algorithm(ImageAnalysisTemplate):
    """
    Class utilizing the Cellpose 3.0 algorithm for finding the objects on transmitted light and filter them by
    circularity, solidity and eccentricity.
    """

    provides_object_rois = True

    @staticmethod
    def filter_cellpose_masks(df, circ_thr=0.65, ecc_thr=0.5, sol_thr=0.85):
        """
        Function for the filtration of the founded objects.
        :param df: pandas DF with the founded objects.
        :param circ_thr: float minimal circularity filtering threshold
        :param ecc_thr: float maximal eccentricity filtering threshold
        :param sol_thr: float maximal solidity filtering threshold
        :return: filtered pandas df
        """

        df['circularity'] = 4 * np.pi * df['area'] / (df['perimeter'] ** 2)

        mask = ((df['circularity'] > circ_thr) & (df['solidity'] > sol_thr) & (df['eccentricity'] < ecc_thr))

        df_filtered = df.loc[mask].copy()

        return df_filtered

    def image_segmentation(self, objects_diameter=None, circ_thr=0.65, ecc_thr=0.5, sol_thr=0.85):
        """
        Initializing Cellpose algorithm.
        :param objects_diameter: float size in um, passed to Cellpose model eval
        :param circ_thr: float minimal circularity filtering threshold
        :param ecc_thr: float maximal eccentricity filtering threshold
        :param sol_thr: float maximal solidity filtering threshold
        :return: tuple (pandas df with objects center positions and their properties, labelled image)
        """
        model = models.Cellpose(model_type='cyto', gpu=True)

        scaling = self.metadata["scaling_um_per_pixel"]

        if objects_diameter is None:

            object_pixel_diameter = None

        else:
            object_pixel_diameter = int(
                np.round(objects_diameter / np.mean([scaling['X'] * 10 ** (6), scaling['Y'] * 10 ** (6)]), 0))

        masks, flows, styles, diam_mean = model.eval([self.image], diameter=object_pixel_diameter, channels=[0, 0])

        props_table = pd.DataFrame(regionprops_table(masks[0], properties=(
            'label', 'area', 'centroid', 'perimeter', 'eccentricity', 'solidity')))

        filtered_props_table = self.filter_cellpose_masks(props_table, circ_thr, ecc_thr, sol_thr)

        # the labelled image is kept, because every object can be cut out of it again with
        # labels_image == label, which is what get_object_rois does
        return filtered_props_table, masks[0]

    def get_measurement_points(self):
        """
        Utilizes methods above for image segmentation and obtains o
        :return: lists of dictionaries with the founded objects properties and their positions in the pixels coordinates
        and in the stage coordinates in um.
        """
        objects_df, self.labels_image = self.image_segmentation(
            **{k: v for k, v in self.analysis_details.items() if
               k in ["objects_diameter", "circ_thr", "ecc_thr", "sol_thr"]})

        scaling = self.metadata["scaling_um_per_pixel"]
        mean_scale = np.mean([scaling["X"] * 10 ** (6), scaling["Y"] * 10 ** (6)])

        objects_df["area"] = objects_df["area"] * (mean_scale ** 2)
        objects_df["radius"] = np.sqrt(objects_df["area"] / np.pi)

        objects_df['position'] = objects_df[['centroid-1', 'centroid-0']].values.tolist()

        measurement_points = (
            objects_df[['position', 'radius', 'area', 'circularity', 'solidity', 'eccentricity']].to_dict(
                orient='records'))

        # One id per object, minted here so that the outlines below and the points can be matched
        # without relying on their order. The Cellpose label is what cuts the object out of the
        # labelled image, so it is remembered under the same id.
        self.object_labels = {}

        for point, label in zip(measurement_points, objects_df['label'].tolist()):
            object_id = self.new_object_id()

            point['id'] = object_id
            self.object_labels[object_id] = label

        transformed_points = self.pixel_converter.convert_points(measurement_points, xy_mode='normal',
                                                                 z_strategy=z_normal)

        return measurement_points, transformed_points

    def get_object_rois(self):
        """
        Outline of every object that survived the filtering, keyed by the same id as the points and
        cut out of the labelled image Cellpose produced. The whole object is handed over, so that an
        object selection can decide for itself which part of it matters.
        :return: dict of object id to its bounding box and a boolean mask inside it
        """
        rois = {}

        for object_id, label in self.object_labels.items():
            object_mask = self.labels_image == label

            rows = np.where(np.any(object_mask, axis=1))[0]
            columns = np.where(np.any(object_mask, axis=0))[0]

            y_start, y_stop = int(rows[0]), int(rows[-1]) + 1
            x_start, x_stop = int(columns[0]), int(columns[-1]) + 1

            rois[object_id] = {'x_start': x_start, 'x_stop': x_stop,
                               'y_start': y_start, 'y_stop': y_stop,
                               'mask': object_mask[y_start:y_stop, x_start:x_stop]}

        return rois
