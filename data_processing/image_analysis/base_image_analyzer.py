from abc import ABC, abstractmethod


class ImageAnalysisTemplate(ABC):
    def __init__(self, image, metadata, **analysis_details):
        self.image = image
        self.metadata = metadata
        self.analysis_details = analysis_details

    @abstractmethod
    def get_measurement_points(self):
        pass
