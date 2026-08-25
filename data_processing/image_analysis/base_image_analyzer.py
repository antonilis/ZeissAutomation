from abc import ABC, abstractmethod
import uuid

from data_processing.image_analysis.pixel_stage_converter import PixelStageConverter


class ImageAnalysisTemplate(ABC):
    """
    Template for all the image analyzers.
    """

    # Whether this analyzer can hand out the outline of each object it found. Analyzers that only
    # produce coordinates, such as mesh nodes or the maximum of a Z-scan, leave this at False and
    # simply cannot be combined with an object selection.
    provides_object_rois = False

    def __init__(self, image, metadata, **analysis_details):
        self.image = image
        self.metadata = metadata
        self.analysis_details = analysis_details
        # Taking the PixelStage converter for obtaining the stage coordinates from pixels coordinates.
        self.pixel_converter = PixelStageConverter(metadata, image.shape)

    @staticmethod
    def new_object_id():
        """
        Identity of one found object. It is minted where the object is created and then travels
        unchanged through the outlines, through the object selection and into the JSON the macro
        reads, so that nothing along the way has to match objects up by their position in a list.
        :return: str
        """
        return str(uuid.uuid4())

    @abstractmethod
    def get_measurement_points(self):
        """
        Every returned point has to carry an 'id' from new_object_id().
        """
        pass

    def get_object_rois(self):
        """
        Outline of every object returned by get_measurement_points, keyed by the same id. The whole
        object is described, its interior included, so that an object selection can decide for
        itself which part of it matters.

        This is where the conversion between micrometers and pixels belongs, because the analyzer
        already holds the metadata and the pixel converter. Object selection algorithms never see
        either of them.

        The mask is cut to the bounding box of the object rather than to the size of the whole
        image, which for a tiled overview would be tens of megabytes per object, nearly all of it
        zeros.

        :return: dict of object id to a dict with the keys x_start, x_stop, y_start, y_stop and
                 mask, where mask is a boolean array of the size of that bounding box
        """
        raise NotImplementedError(
            "{} does not produce object outlines".format(type(self).__name__))
