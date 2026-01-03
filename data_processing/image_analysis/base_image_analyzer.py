from abc import ABC, abstractmethod
from data_processing.image_analysis.pixel_stage_converter import PixelStageConverter


class ImageAnalysisTemplate(ABC):
    """
    Template for all the image analyzers.
    """
    def __init__(self, image, metadata, **analysis_details):
        self.image = image
        self.metadata = metadata
        self.analysis_details = analysis_details
        # Taking the PixelStage converter for obtaining the stage coordinates from pixels coordinates.
        self.pixel_converter = PixelStageConverter(metadata, image.shape)

    @abstractmethod
    def get_measurement_points(self):
        pass
