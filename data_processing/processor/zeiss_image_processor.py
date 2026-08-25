import os
import numpy as np

from IO.read_czi_file import CziFileReader

import json
import copy
from datetime import datetime
import data_processing.image_analysis
import data_processing.object_selection
from data_processing.image_analysis.analysis_registry import (get_image_analysis_type, get_available_analysis,
                                                              get_analysis_with_rois)
from data_processing.object_selection.selection_registry import get_object_selection_type, get_available_selections


class ZeissImageProcessor:
    """
    Processes Zeiss .czi files, by reading them, calling for the segmentation algorithm from image_analysis and saving
    the results as JSON files. When an object selection algorithm is configured, the objects it rejects are dropped
    before anything is saved.
    """
    def __init__(self, czi_file_path, analysis_channel=1, chosen_analysis='FluorescentGUV',
                 chosen_selection=None, selection_arguments=None, **analysis_details):

        # reading the image and metadata from .czi file with the CziFileReader and choosing the channel for analysis
        self.czi_file_path = czi_file_path
        self.analysis_channel = analysis_channel

        # optional second stage, running on the objects the analyzer found
        self.chosen_selection = chosen_selection
        self.selection_arguments = selection_arguments or {}

        if self.chosen_selection:
            self.check_analysis_supports_selection(chosen_analysis)

        czi_obj = CziFileReader(self.czi_file_path, self.analysis_channel,
                                extra_channels=self.get_required_channels())
        self.image_to_analyze = czi_obj.czi_file
        self.metadata = czi_obj.metadata
        self.channels_data = czi_obj.channels_data

        # calling for the segmentation algorithm and initializing it
        self.image_analyzer = self.get_analysis_type(chosen_analysis, **analysis_details)
        self.measurement_points, self.not_scaled_points = self.get_measurement_points()

        # Every object counts unless an object selection says otherwise. The flag is always written, so that nothing
        # downstream ever has to treat a missing one as a default.
        self.mark_selected(set(p['id'] for p in self.not_scaled_points))

        if self.chosen_selection:
            self.apply_object_selection()

        self.copy_properties_to_stage_points()

    def get_analysis_type(self, chosen_analysis, **kwargs):
        """
        Method for initialization of the segmentation algorithm
        :param chosen_analysis: name of the class in image_analysis folder for segmentation
        :param kwargs: additional arguments for the analyzing script like:
        :return: initialized object of the segmentation class
        """
        strategy_class = get_image_analysis_type(chosen_analysis)
        if not strategy_class:
            raise ValueError(
                f"Unknown analysis type: {chosen_analysis}, please choose from {get_available_analysis()}")

        return strategy_class(
            image=self.image_to_analyze,
            metadata=self.metadata, **kwargs)

    def get_selection_type(self, chosen_selection, **kwargs):
        """
        Method for initialization of the object selection algorithm
        :param chosen_selection: name of the class in object_selection folder
        :param kwargs: additional arguments for the selection script
        :return: initialized object of the selection class
        """
        selection_class = get_object_selection_type(chosen_selection)
        if not selection_class:
            raise ValueError(
                f"Unknown object selection: {chosen_selection}, please choose from {get_available_selections()}")

        return selection_class(
            points=self.not_scaled_points,
            rois=self.build_object_rois(), **kwargs)

    def check_analysis_supports_selection(self, chosen_analysis):
        """
        An object selection measures the pixels belonging to each found object, so the analyzer has to be able to hand
        out their outlines. Checked on the class, before the .czi file is even opened.
        :param chosen_analysis: name of the class in image_analysis folder
        :return: None
        """
        strategy_class = get_image_analysis_type(chosen_analysis)

        if strategy_class and not strategy_class.provides_object_rois:
            raise ValueError(
                f"Analysis {chosen_analysis} does not produce object outlines, so it cannot be combined with an "
                f"object selection. Analyses that can: {get_analysis_with_rois()}")

    def build_object_rois(self):
        """
        Combines the outlines from the analyzer with the channels the object selection asked for, so that the selection
        receives pixels and nothing else. Each entry gets, for every requested channel, the same rectangle of the image
        that its mask describes.
        :return: dict of object id to its outline plus a 'pixels' dict of channel number to the cut out image
        """
        outlines = self.image_analyzer.get_object_rois()

        # Projected once rather than once per object. The outlines only carry X and Y, so a Z-stack has to be flattened
        # before anything can be cut out of it.
        flat_channels = {}

        for channel, image in self.channels_data.items():
            flat_channels[channel] = np.max(image, axis=0) if image.ndim == 3 else image

        rois = {}

        for object_id, outline in outlines.items():
            roi = dict(outline)
            roi['pixels'] = {
                channel: image[outline['y_start']:outline['y_stop'], outline['x_start']:outline['x_stop']]
                for channel, image in flat_channels.items()}

            rois[object_id] = roi

        return rois

    def get_required_channels(self):
        """
        Asks the configured object selection which channels it needs. The .czi file is read in one pass and closed
        afterwards, so this has to be known before the file is opened.
        :return: list of channel numbers, empty when no selection is configured
        """
        if not self.chosen_selection:
            return []

        selection_class = get_object_selection_type(self.chosen_selection)
        if not selection_class:
            raise ValueError(
                f"Unknown object selection: {self.chosen_selection}, please choose from {get_available_selections()}")

        return selection_class.required_channels(**self.selection_arguments)

    def get_measurement_points(self):
        """
        Initializes the image segmentation in the chosen algorhitm.
        :return: list of dictionaries with positions and properties of segmented objects
        """
        # returns both the positions in the coordinates of the image pixels and real positions in stage coordinated
        points, measurement_points = self.image_analyzer.get_measurement_points()

        # The id keys the outlines, the object selection and the saved JSON, so an analyzer that forgets to mint one
        # has to say so here rather than at saving time, where the message would point at the wrong place.
        for point in points:
            if 'id' not in point:
                raise ValueError(
                    f"{type(self.image_analyzer).__name__} returned a point without an 'id'. Every analyzer has to "
                    f"give each object an id from new_object_id().")

        return measurement_points, points

    def mark_selected(self, selected_ids):
        """
        Writes the 'selected' flag onto every found object. Nothing is removed: a rejected object stays in the results
        together with whatever the selection measured on it, and only the flag says whether the macro should drive to
        it.
        :param set selected_ids: ids of the objects which are taken into account
        :return: None
        """
        for point in self.not_scaled_points:
            point['selected'] = point['id'] in selected_ids

    def apply_object_selection(self):
        """
        Runs the configured object selection and marks the objects it rejected.
        :return: None
        """
        selection = self.get_selection_type(self.chosen_selection, **self.selection_arguments)

        kept_ids = set(selection.get_kept_ids())

        self.mark_selected(kept_ids)

        print("[INFO] Object selection {} selected {} of {} objects".format(
            self.chosen_selection, len(kept_ids), len(self.not_scaled_points)))

    def copy_properties_to_stage_points(self):
        """
        The object selection works on the pixel coordinate list, while the JSON is written from the stage coordinate
        one, so everything it measured has to be copied across. Objects are matched by id and never by their position
        in the list. Only 'position' is left alone, because that is the one thing which genuinely differs between them.
        :return: None
        """
        properties_by_id = {p['id']: p for p in self.not_scaled_points}

        for point in self.measurement_points:
            for key, value in properties_by_id[point['id']].items():
                if key != 'position':
                    point[key] = value


    def save_measurement_points(self, filename):
        """
        Function responsible for saving the positions and properties of the found objects in the stage coordinates in
        the JSON file.
        :param filename: saving path of the JSON file
        :return: None
        """
        data = {}

        for p in self.measurement_points:
            entry = dict(p)  # copying all of the existing properties
            # the id was minted at detection time and becomes the key here, so that the same identifier runs from the
            # outlines through the object selection all the way to the macro
            point_id = entry.pop("id")
            entry["source"] = self.czi_file_path
            entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
            data[point_id] = entry

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    def choose_chi_files(main_path):
        files = [f for f in os.listdir(main_path) if f.lower().endswith('.czi')]
        directions = [os.path.join(main_path, file_path) for file_path in files]

        return directions


    main_path = '../../Snap-10242.czi'

    #main_directions = choose_chi_files(main_path)

    with open('../../ZeissAPI/config/preprocessing_config.json', 'r') as file:
        preprocessing_config = json.load(file)

    details = preprocessing_config['FLGUV']

    obj_main = ZeissImageProcessor(main_path, **details)
    #
    obj_main.save_measurement_points('measurement_points_FL.json')
