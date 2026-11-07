import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks

from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class


@register_class
class GUVTopZScan(ImageAnalysisTemplate):
    """
    Finds the top of a GUV on a z-stack centred on the object, for the z-reanalysis. The fluorescence in a small disc on
    the axis peaks where the flat top of the membrane is in focus. The whole frame cannot be used for this: below the
    top the ring of the membrane still fills it, which moved the maximum 1.1 um below the top of a measured GUV.

    The macro cannot go on without a position, so a stack without a clear top returns its own centre with top_found
    set to False, and whatever runs next should be read with that in mind.
    """

    smoothing_um = 0.3
    edge_margin_um = 1.0

    def get_axis_pixels(self, roi_radius_um):
        """
        :param roi_radius_um: float radius of the disc on the axis
        :return: 2D array of the pixels of the disc, one row per plane of the stack
        """
        scaling = self.metadata['scaling_um_per_pixel']
        um_per_pixel = np.mean([scaling['X'], scaling['Y']]) * 10 ** 6

        height, width = self.image.shape[1:]
        rows, columns = np.indices((height, width))
        distance = np.hypot(columns - (width - 1) / 2, rows - (height - 1) / 2) * um_per_pixel

        return self.image[:, distance < roi_radius_um].astype(float)

    def find_top(self, pixels, z_step_um, min_peak_sigma):
        """
        Takes the highest peak that stands out from the counting noise. The highest and not the strongest one, because a
        scan reaching the bottom of the GUV, or a vesicle inside it, would give a second peak below the top.
        The noise is that of counting events and not of grey values. One event can be worth tens of grey values, depending
        on the detector settings, and the square root of the grey values then makes a few stray photons above a weak GUV
        look like a peak. The size of an event is read from the planes without the membrane.
        :param pixels: 2D array of the pixels of the disc, one row per plane, plane index growing with z
        :param z_step_um: float distance between the planes
        :param min_peak_sigma: float how many sigma of the background a peak has to stand out
        :return: tuple (plane index as a float or None when there is no peak, peak height above the background in sigma)
        """
        signal = pixels.sum(axis=1)
        smoothed = ndimage.gaussian_filter1d(signal, max(self.smoothing_um / z_step_um, 0.5), mode='nearest')

        background = np.percentile(smoothed, 25)

        quiet = pixels[smoothed <= np.median(smoothed)]
        event_size = quiet[quiet > 0].mean() if (quiet > 0).any() else 1.0
        noise = event_size * np.sqrt(max(background / event_size, 1))

        peaks, _ = find_peaks(smoothed, prominence=min_peak_sigma * noise)

        if len(peaks) == 0:
            return None, float((smoothed.max() - background) / noise)

        top = peaks[-1]

        # parabola through the top three planes, so that the result is not stuck to the planes of the scan
        left, centre, right = smoothed[top - 1:top + 2]
        shift = 0.5 * (left - right) / (left - 2 * centre + right)

        return float(top + shift), float((smoothed[top] - background) / noise)

    def get_measurement_points(self):
        """
        One point on the axis of the frame, at the top of the GUV.
        :return: lists of dictionaries with the founded objects properties and their positions
                 in the pixels coordinates and in the stage coordinates in um
        """
        if self.image.ndim != 3:
            raise ValueError("GUVTopZScan needs a z-stack, got an image of shape {}".format(self.image.shape))

        number_of_planes = self.image.shape[0]
        z_step_um = self.metadata['scaling_um_per_pixel']['Z'] * 10 ** 6

        pixels = self.get_axis_pixels(self.analysis_details.get('roi_radius_um', 1.5))
        top, peak_sigma = self.find_top(pixels, z_step_um, self.analysis_details.get('min_peak_sigma', 5))

        top_found = top is not None
        centre_plane = (number_of_planes - 1) / 2

        if not top_found:
            print("No top of a GUV in this stack, staying at its centre. Best signal:", round(peak_sigma, 1), "sigma")
            top = centre_plane

        # a peak at the end of the scan may be the side of a peak lying outside it
        margin = self.edge_margin_um / z_step_um
        at_scan_edge = top_found and (top < margin or top > number_of_planes - 1 - margin)

        if at_scan_edge:
            print("The top of the GUV is at the edge of the scan, plane", round(top, 1), "of", number_of_planes)

        # counted from the centre in either mode of the z-stack: guv_top_stack and center_stack_on_focus both put the
        # focus stored in the image at the centre of the stack
        z_plane = top - centre_plane

        x, y = self.image.shape[2] / 2 - 1, self.image.shape[1] / 2 - 1

        measurement_points = [{'id': self.new_object_id(), 'position': [x, y, z_plane], 'top_found': top_found,
                               'at_scan_edge': bool(at_scan_edge), 'peak_sigma': peak_sigma,
                               'axis_signal': pixels.sum(axis=1).tolist()}]

        transformed_points = self.pixel_converter.convert_points(measurement_points, xy_mode="center",
                                                                 z_strategy=self.pixel_converter.convert_z_auto)

        return measurement_points, transformed_points
