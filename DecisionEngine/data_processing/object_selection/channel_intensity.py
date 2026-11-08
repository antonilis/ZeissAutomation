import numpy as np

from data_processing.object_selection.base_object_selection import ObjectSelectionTemplate
from data_processing.object_selection.selection_registry import register_class


@register_class
class ChannelIntensity(ObjectSelectionTemplate):
    """
    Class for rejecting the objects whose intensity, measured on a channel of the same image other
    than the one they were found on, falls outside a configured range. Useful for discarding objects
    which were detected on transmitted light or on one dye but carry no signal on another, for
    example GUVs without a fluorescent membrane.

    Reads from selection_details: channel, min_value, max_value and statistic.
    """

    @classmethod
    def required_channels(cls, **selection_details):
        """
        :return: list with the single channel the intensity is measured on
        """
        return [selection_details["channel"]]

    def apply_statistic(self, values):
        """
        Reduces the pixels of one object to a single number.
        :param values: 1D ndarray of the pixel values inside the object
        :return: float
        """
        statistic = self.selection_details.get("statistic", "mean")

        if statistic == "mean":
            return float(np.mean(values))

        if statistic == "median":
            return float(np.median(values))

        if statistic == "max":
            return float(np.max(values))

        raise ValueError("Unknown statistic: {}, please choose from mean, median, max".format(statistic))

    def get_kept_ids(self):
        """
        Measures every found object and keeps the ones inside the configured range. The measured
        value is written onto every object, rejected ones included, so that the PNG overlay and the
        JSON show how close to the threshold each object was.
        :return: list of the ids of the objects which are kept
        """
        channel = self.selection_details["channel"]
        min_value = self.selection_details.get("min_value")
        max_value = self.selection_details.get("max_value")

        if min_value is None and max_value is None:
            raise ValueError("ChannelIntensity needs min_value, max_value or both to be configured.")

        property_name = "intensity_ch{}".format(channel)

        kept_ids = []

        for point in self.points:
            values = self.values_of(point['id'], channel)

            value = self.apply_statistic(values) if values.size else None

            point[property_name] = value

            if value is None:
                continue

            if min_value is not None and value < min_value:
                continue

            if max_value is not None and value > max_value:
                continue

            kept_ids.append(point['id'])

        return kept_ids
