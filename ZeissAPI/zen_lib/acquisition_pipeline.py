import uuid

from System.IO import Path, File

from zen_lib.runtime_config import log, read_json
from zen_lib.path_manager_main_macro import PathManager
from zen_lib.execute_python import PythonAnalysisRunner


# ==============================================================================
# PIPELINE CLASS
# ==============================================================================

class AcquisitionPipeline:
    """
    A comprehensive pipeline encompassing object detection, motion control toward the detected objects,
    visualization, and post-processing steps involving reanalysis of spatial coordinates (XY and Z)
    and quantitative measurements of the identified objects.

    param RuntimeConfig config: configuration built by the macro. The pipeline never locates
    the config folder itself, it only passes this object on to its helpers.
    param ZenApi zeiss_api: the ZEN runtime built by the macro. Everything that touches the
    microscope goes through it, because the names ZEN injects into a macro are not visible from
    an imported module.
    param dict adaptive_experiments: experiment name to the function that rewrites it,
    already resolved. It arrives resolved, so that a mistake in it is reported before the
    stage moves rather than in the middle of a run.
    """

    def __init__(self,
                 config,
                 zeiss_api,
                 object_visualization_experiment=None,
                 reanalysis_dict=None,
                 post_reanalysis_experiments=None, adaptive_experiments=None):

        self.config = config
        self.zeiss_api = zeiss_api

        # arguments collecting the experiments names and arguments for Python analysis, which will be used at different
        # stages of the pipeline
        self.object_visualization_experiment = object_visualization_experiment
        self.reanalysis_dict = reanalysis_dict
        self.post_reanalysis_experiments = post_reanalysis_experiments or []
        self.adaptive_experiments = adaptive_experiments or {}

        # Initializing objects for the directories management for reading/saving the results and for initializing python
        # with the arguments. Both receive the already loaded configuration.
        self.path_manager = PathManager(self.config)
        self.python_analysis_runner = PythonAnalysisRunner(self.config)

        self.points_for_overview = self.get_overview_points() # points on which the pipeline will be executed
        self.overview_id = str(uuid.uuid4())
        self.measurements_objects = {}

        # Said out loud, because an adaptive experiment that was never armed is otherwise
        # invisible: it simply does not run, and leaves nothing behind explaining why
        if not self.adaptive_experiments:
            log("Pipeline built with no adaptive experiments")
        else:
            log("Pipeline built with adaptive experiments: {}".format(", ".join(
                ["{} rewriting {}".format(function.__name__, experiment)
                 for experiment, function in sorted(self.adaptive_experiments.items())])))

    def get_overview_points(self):
        """
        Reads the points in which the full pipeline needs to be executed.
        """
        points_path = Path.Combine(self.path_manager.measurements, "points_for_overview.json")

        if File.Exists(points_path):

            points_for_overview = read_json(points_path)
        else:

            points_for_overview = None

        return points_for_overview


    def acquire_overview(self, overview_experiment, analysis_args=None, selection_args=None, name=None):

        """
        Method for loading, executing and saving the overview experiment. Activating the analysis of the results and
        reading the JSON with positions of the objects for the measurement from Python analysis.

        param str selection_args: name of a preset in selection_config.json, deciding which of the
        found objects are worth measuring, or None to measure all of them
        """

        log('Initializing overview experiment')

        self.zeiss_api.load_experiment(overview_experiment)
        self.zeiss_api.execute_current_experiment()

        # The name of the overview image is the combination of pipeline overview id and the name of the point in which
        # the pipeline is executed
        overview_file_name = self.path_manager.overview_image_path(self.overview_id, name)
        overview_analysis_path = self.path_manager.temp_file_path(self.overview_id, None, name)

        self.zeiss_api.save_experiment_result(overview_file_name)

        log('Overview experiment finished')

        if analysis_args:
            args_overview = {'type': 'overview', 'file_path': overview_file_name,
                             'saving_path': overview_analysis_path, 'analysis_arguments': analysis_args,
                             'selection_arguments': selection_args, 'is_FCS': False}

            log("Initializing the overview image analysis: {}".format(args_overview))
            self.python_analysis_runner.run(**args_overview)

            # Loading JSON with the objects positions, crucial for the capture_objects method
            self.measurements_objects = self.load_measurements(self.overview_id, name=name)

        log("Overview finished")

    def load_measurements(self, obj_id, reanalysis_type=None, name=None):
        """
        Loads JSON files for the reanalysis of the objects positions.
        """
        points_path = self.path_manager.temp_file_path(obj_id, reanalysis_type, name)

        data = read_json(points_path)
        log("Loaded measurement data for object {} [{}] from {}".format(
            obj_id, reanalysis_type or "overview", points_path))

        return data

    def capture_objects(self, object_ids=None, name=None):
        """
        Method for performing objects visualizationexperiment, calling functions for reanalysis of xy and z position and
        executing all the post reanalysis experiments on all of founded objects in the pipeline
        :param object_ids: uuids of the founded objects in the current pipeline position
        :param name: Name of the position in which the pipeline will be executed
        :return: None
        """

        if not self.measurements_objects:
            log("No overview results for {}".format(self.overview_id))
            return

        if object_ids is None:
            # The analysis side marks every object it found with 'selected'. Rejected ones stay in the
            # JSON together with whatever was measured on them, they are simply not driven to.
            object_ids = [obj_id for obj_id, obj in self.measurements_objects.items() if obj['selected']]

            skipped = len(self.measurements_objects) - len(object_ids)

            if skipped:
                log("Object selection rejected {} of {} objects".format(skipped, len(self.measurements_objects)))

        log("Initialized capturing objects")

        for obj_id in object_ids:
            obj = self.measurements_objects[obj_id]
            self.zeiss_api.move(obj["position"])

            # --- 1 Do object visualization experiment, which results are used for xy-reanalysis ---
            self._run_experiment(obj_id, self.object_visualization_experiment, stage='_exp', name=name, obj=obj)

            log('Finished visualization of object {}'.format(obj_id))

            # --- 2 Reanalysis ---
            if self.reanalysis_dict is not None:
                log("Initialized reanalysis of object: {}".format(obj_id))

                # Reanalysis XY
                if self.reanalysis_dict.get('xy'):
                    self._perform_reanalysis_xy(obj_id, name)

                # Reanalysis Z. Both halves are required: without an experiment there is nothing to
                # acquire and load_experiment would be handed None, without an analysis there is
                # nothing to read the corrected position from.
                z_data = self.reanalysis_dict.get('z')

                if z_data and z_data.get('z_experiment') is not None and z_data.get('z_analysis') is not None:
                    self._perform_reanalysis_z(obj_id, name, obj)

                elif z_data and (z_data.get('z_experiment') is not None or z_data.get('z_analysis') is not None):
                    log("Skipping Z reanalysis for object {}: it needs both an experiment and an "
                        "analysis, got experiment={} and analysis={}".format(
                            obj_id, z_data.get('z_experiment'), z_data.get('z_analysis')))

            for exp_name in self.post_reanalysis_experiments:
                log('Running experiment {} on object {}'.format(exp_name, obj_id, obj=obj))

                self._run_experiment(obj_id, exp_name, stage="_post", name=name, obj=obj)

            log("Finished capturing object {}".format(obj_id))
            # Clearing the experiments from the view for resources saving
            self.zeiss_api.remove_all_documents()

    def _perform_reanalysis_xy(self, obj_id, name=None, obj=None):
        """
        Function responsible for initializing Python xy reanalysis on object from object_visualization experiment result and
        reading the new-corrected positions of object.
        """
        log('Initialized reanalysis of object {}'.format(obj_id))

        file_name = self.path_manager.result_path(obj_id, '_exp', self.object_visualization_experiment, name)
        saving_path = self.path_manager.temp_file_path(obj_id, 'xy', name)

        # The type has to be reanalysis_xy, not overview: it is what makes the analysis
        # side reduce several detections to the one nearest the current stage position,
        # instead of returning them all and letting the line below pick an arbitrary one.
        args_xy = {'type': 'reanalysis_xy', 'file_path': file_name,
                   'saving_path': saving_path, 'analysis_arguments': self.reanalysis_dict['xy'], 'is_FCS': False}

        log("Running XY reanalysis script with args: {}".format(args_xy))
        self.python_analysis_runner.run(**args_xy)

        new_data = self.load_measurements(obj_id, reanalysis_type="xy", name=name)

        if not new_data:
            log("Warning: No XY reanalysis points found for object {}".format(obj_id))
            return

        new_position = new_data[list(new_data.keys())[0]]['position']

        self.zeiss_api.move(new_position)
        log("Moved stage to XY reanalysis position for object {}".format(obj_id))

    def _perform_reanalysis_z(self, obj_id, name=None, obj=None):
        """
        Function responsible for executing the z-reanalysis experiments, initializing the Python analysis and reading
        the JSON with new positions
        """

        z_cfg = self.reanalysis_dict['z']

        z_exp = z_cfg['z_experiment']
        z_analysis = z_cfg['z_analysis']

        self._run_experiment(obj_id, z_exp, stage="_reanalysis_z", name=name, obj=obj)

        file_name = self.path_manager.result_path(obj_id, "_reanalysis_z", z_exp, name)
        saving_path = self.path_manager.temp_file_path(obj_id, 'z', name)

        args_z = {'type': 'reanalysis_z', 'file_path': file_name, 'saving_path': saving_path,
                  'analysis_arguments': z_analysis, 'is_FCS': z_cfg['is_FCS']}

        log("Running Z reanalysis script with args: {}".format(args_z))
        self.python_analysis_runner.run(**args_z)

        z_data = self.load_measurements(obj_id, reanalysis_type="z", name=name)

        new_positions = z_data[list(z_data.keys())[0]]['position']

        self.zeiss_api.move(new_positions)

        log("Moved stage to Z reanalysis position for object {}".format(obj_id))

        log("Finished reanalysis for object {}".format(obj_id))

    def _run_experiment(self, obj_id, exp_item, stage, name=None, obj=None):
        """
        Function responsible for loading, executing experiments and saving the results in correct directory with
        proper name. If an adaptive function is paired with this experiment it runs first and rewrites
        it, using the properties of the object the experiment is about to be run on.
        """

        adaptive = self.adaptive_experiments.get(exp_item)

        if adaptive is not None:
            log('Doing adaptive experiment {} on {}'.format(adaptive.__name__, exp_item))

            adaptive(exp_item, obj_id, stage, obj, name)

            log('Rewrote experiment {} with {}'.format(exp_item, adaptive.__name__))

        self.zeiss_api.load_experiment(exp_item)
        self.zeiss_api.execute_current_experiment()

        # Different approaches for saving for .fcs files (which gives None) and .czi files
        if self.zeiss_api.active_document() is None:

            file_name = self.path_manager.result_dir(obj_id, stage, name)
            base_name = Path.GetFileNameWithoutExtension(self.path_manager.result_path(obj_id, stage, exp_item, name))

        else:
            file_name = self.path_manager.result_path(obj_id, stage, exp_item, name)
            base_name = None

        self.zeiss_api.save_experiment_result(file_name, base_name)

        log("Saved the result: {}".format(file_name))
