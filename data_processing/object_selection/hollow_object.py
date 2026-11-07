import numpy as np

from data_processing.object_selection.base_object_selection import ObjectSelectionTemplate
from data_processing.object_selection.selection_registry import register_class


@register_class
class HollowObject(ObjectSelectionTemplate):
    """
    Class for rejecting the objects which are not hollow. A GUV carries the dye on its membrane, so a plane through it
    shows a ring around a dark centre, wherever it cuts the GUV. The ring is smaller than the outline away from the
    equator, so it is searched for and not assumed at the edge. A filled object or a heap of vesicles is as bright in its
    centre as anywhere else.

    The measure is the centre over the brightest ring, both above the background. It is a ratio of two signals of the same
    object, so it does not depend on the power, the detector or the amount of dye. An object without any signal above the
    background is rejected too, there is nothing to measure on it.

    Reads from selection_details: channel, max_centre_over_ring and min_ring_sigma, how many sigma of the counting noise
    the ring has to stand out by. An object with a few stray photons is not a ring.
    """

    number_of_rings = 6     # of equal width across the radius
    centre_rings = 2        # the inner ones make the centre

    @classmethod
    def required_channels(cls, **selection_details):
        """
        :return: list with the single channel the fluorescence is measured on
        """
        return [selection_details["channel"]]

    def measure(self, object_id, channel):
        """
        :return: float centre over the brightest ring, None when no ring stands out from the counting noise
        """
        roi = self.rois[object_id]
        mask = roi['mask']
        pixels = roi['pixels'][channel].astype(float)

        background = np.median(pixels[~mask]) if (~mask).any() else 0.0

        rows, columns = np.nonzero(mask)
        radius = np.sqrt(mask.sum() / np.pi)
        distance = np.hypot(rows - rows.mean(), columns - columns.mean())

        ring = np.minimum((distance / radius * self.number_of_rings).astype(int), self.number_of_rings - 1)
        values = pixels[rows, columns] - background

        means = [values[ring == k].mean() if (ring == k).any() else 0.0 for k in range(self.number_of_rings)]

        brightest_ring = self.centre_rings + int(np.argmax(means[self.centre_rings:]))
        brightest = means[brightest_ring]
        centre = values[ring < self.centre_rings].mean()

        ring_pixels = (ring == brightest_ring).sum()
        noise = np.sqrt(max((brightest + background) * ring_pixels, 1))

        if brightest * ring_pixels < self.selection_details["min_ring_sigma"] * noise:
            return None

        return float(centre / brightest)

    def get_kept_ids(self):
        """
        Measures every found object and keeps the hollow ones. The measured value is written onto every object, rejected
        ones included.
        :return: list of the ids of the objects which are kept
        """
        channel = self.selection_details["channel"]
        limit = self.selection_details["max_centre_over_ring"]

        kept_ids = []

        for point in self.points:
            value = self.measure(point['id'], channel)

            point['centre_over_ring'] = value

            if value is not None and value < limit:
                kept_ids.append(point['id'])

        return kept_ids
