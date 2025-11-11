from cellpose import models
import pandas as pd
from skimage.measure import regionprops_table
import numpy as np
import torch

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class


@register_class
class Cellpose_algorithm(ImageAnalysisTemplate):

    @staticmethod
    def filter_cellpose_masks(df, circ_thr=0.65, ecc_thr=0.5, sol_thr=0.85):
        # Obliczanie circularity
        df['circularity'] = 4 * np.pi * df['area'] / (df['perimeter'] ** 2)
        
       
        mask = ((df['circularity'] > circ_thr) & (df['solidity'] > sol_thr) &(df['eccentricity'] < ecc_thr))
        
        # Filtracja wierszy
        df_filtered = df.loc[mask].copy()

        return df_filtered

    def image_segmentation(self, objects_diameter=None, circ_thr=0.65, ecc_thr=0.5, sol_thr=0.85):
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

        return filtered_props_table

    def get_measurement_points(self):
        objects_df = self.image_segmentation(**{k: v for k, v in self.analysis_details.items() if
                                                k in ["objects_diameter", "circ_thr", "ecc_thr", "sol_thr"]})

        scaling = self.metadata["scaling_um_per_pixel"]
        mean_scale = np.mean([scaling["X"] * 10 ** (6), scaling["Y"] * 10 ** (6)])

        objects_df["area"] = objects_df["area"] * (mean_scale ** 2)
        objects_df["radius"] = np.sqrt(objects_df["area"] / np.pi)

        objects_df['position'] = objects_df[['centroid-1', 'centroid-0']].values.tolist()

        measurement_points = (
            objects_df[['position', 'radius', 'area', 'circularity', 'solidity', 'eccentricity']].to_dict(
                orient='records'))

        return measurement_points
