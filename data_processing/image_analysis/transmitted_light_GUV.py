from cellpose import models
import pandas as pd
from skimage.measure import regionprops_table
import numpy as np


from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class




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