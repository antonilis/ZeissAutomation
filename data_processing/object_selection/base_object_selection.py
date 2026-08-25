from abc import ABC, abstractmethod


class ObjectSelectionTemplate(ABC):
    """
    Template for all the object selection algorithms. They run after an image analyzer has found the
    objects and decide which of them are kept, optionally writing the properties they measured back
    onto them.

    A selection algorithm sees pixels and nothing else. Positions, radii, image scaling and the
    conversion between micrometers and pixels all stay on the analysis side, where the metadata and
    the pixel converter already live, so that a selection algorithm cannot get any of them wrong.
    """
    def __init__(self, points, rois, **selection_details):
        self.points = points
        self.rois = rois
        self.selection_details = selection_details

    @classmethod
    def required_channels(cls, **selection_details):
        """
        Channels that have to be read from the .czi file before this algorithm can run. The whole
        file is read inside a single with block and closed afterwards, so the list has to be known
        before the file is opened, which is why this works on the arguments alone and needs no
        instance.
        :param dict selection_details: the arguments this algorithm was configured with
        :return: list of channel numbers, empty when only the analysis channel is needed
        """
        return []

    def values_of(self, object_id, channel):
        """
        Pixel values of one object on one channel.

        This is boolean indexing, not a multiplication by the mask. The background inside the
        bounding box is left out entirely rather than turned into zeros, because zeros would drag
        every statistic towards zero by however much of the box that particular object happens not
        to fill, which differs from object to object.

        :param str object_id: id of the object, taken from its point
        :param int channel: number of the channel
        :return: 1D ndarray of the pixel values inside the object
        """
        roi = self.rois[object_id]

        return roi['pixels'][channel][roi['mask']]

    @abstractmethod
    def get_kept_ids(self):
        """
        :return: list of the ids of the objects which are kept
        """
        pass
