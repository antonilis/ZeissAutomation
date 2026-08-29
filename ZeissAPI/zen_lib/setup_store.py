import json

from System.IO import Path, File

from zen_lib.runtime_config import log, read_json


###################### reading, checking and remembering the GUI selections ###########################
# Everything the user can get wrong is caught here, before the pipeline is built and before anything
# moves. A run started from main_macro is unattended, so a bad combination of settings that only
# surfaces halfway through costs an experiment and a plate position.
#
# Nothing in this module builds a window. What used to end the macro from inside load_setup now
# raises ValueError, and the macro decides how to say it - which is what keeps this module free of
# ZenWindow, a name an imported module cannot see anyway.


def none_or_value(x):
    """
    Reads the "None" entry of a dropdown as the absence of a choice.
    :param x: value taken from the GUI
    :return: None when the user chose "None", otherwise the value unchanged
    """
    return None if x == "None" else x


def build_adaptive_experiments(pairs, adaptive_functions, adaptive_path):
    """
    Resolves the pairs the GUI collected into the mapping the pipeline uses: experiment name to
    the function that rewrites it. Keyed by the experiment, because two functions rewriting the
    same experiment would fight over it and the second would quietly win.
    :param list pairs: list of [function name, experiment name] pairs, possibly empty
    :param dict adaptive_functions: the plugins that were loaded, by name
    :param str adaptive_path: the folder they were loaded from, named in the error message
    :return: tuple (dict of experiment name to function, error message or None)
    """
    adaptive_experiments = {}

    for pair in pairs:
        function_name, target_experiment = pair[0], pair[1]

        function = adaptive_functions.get(function_name)

        if function is None:
            return {}, "The adaptive function '{}' was not loaded from {}. Available: {}".format(
                function_name, adaptive_path, ", ".join(sorted(adaptive_functions)) or "none")

        if target_experiment is None:
            return {}, "The adaptive function '{}' has no experiment to rewrite.".format(function_name)

        if target_experiment in adaptive_experiments:
            return {}, "The experiment '{}' is paired with two adaptive functions, '{}' and " \
                       "'{}'. Only one function can rewrite an experiment.".format(
                           target_experiment,
                           adaptive_experiments[target_experiment].__name__, function_name)

        adaptive_experiments[target_experiment] = function

    return adaptive_experiments, None


def validate_setup(setup, config, processing_data, selection_data, experiments):
    """
    Collects everything that is wrong with the chosen combination of settings. It reads no globals:
    the configuration, the two preset files and the list of saved experiments all arrive as
    arguments, so the same check can be run over a setup that came from a file and over one that
    came from the dropdowns.
    :param dict setup: the selections read from the GUI
    :param RuntimeConfig config: configuration built by the macro
    :param dict processing_data: contents of processing_config.json
    :param dict selection_data: contents of selection_config.json
    :param list experiments: names of the experiments saved in ZEN
    :return: list of messages, empty when the setup can be run
    """
    problems = []

    z_experiment = setup['z_experiment']
    z_analysis = setup['z_analysis']

    if (z_experiment is None) != (z_analysis is None):
        problems.append(
            "Z reanalysis needs both an experiment and an analysis, or neither of them. The chosen "
            "experiment is {} and the chosen analysis is {}.".format(z_experiment, z_analysis))

    # Without object finding the macro visits the overview points and does whatever was asked
    # for at each of them. A Z reanalysis alone is enough, post-analysis experiments alone are
    # enough, and so is both. Only asking for neither is pointless: the stage would drive from
    # point to point without acquiring anything.
    if not setup['finding_objects'] and z_experiment is None and not setup['post_experiments']:
        problems.append(
            "With finding objects mode switched off there has to be either a Z reanalysis or at "
            "least one post-analysis experiment, otherwise this macro would only move the stage "
            "from point to point without acquiring anything.")

    if setup['multiple_overviews']:
        points_path = Path.Combine(config.measurements, "points_for_overview.json")

        if not File.Exists(points_path):
            problems.append(
                "Multiple overviews mode needs the file {}. Run find_overview_positions.czmac "
                "first, or switch the mode off.".format(points_path))

        else:
            try:
                overview_points = read_json(points_path)
            except Exception as error:
                overview_points = None
                problems.append("The overview points file {} could not be read: {}".format(points_path, error))

            # An empty list would send the macro straight through every loop below without
            # acquiring anything, and look like a run that simply finished very quickly
            if overview_points is not None and not overview_points:
                problems.append(
                    "The overview points file {} contains no points. Run find_overview_positions.czmac "
                    "again, or switch multiple overviews mode off.".format(points_path))

    # A preset without chosen_analysis makes the analysis side fall back to a name that is not
    # a registered algorithm, which only shows up once the overview has already been acquired
    for label, preset_name in (("overview analysis", setup['overview_analysis']),
                               ("XY reanalysis", setup['reanalysis_xy']),
                               ("Z analysis", setup['z_analysis'])):
        if preset_name is None:
            continue

        preset = processing_data.get(preset_name)

        if preset is None:
            problems.append(
                "The {} preset '{}' is not in processing_config.json.".format(label, preset_name))

        elif not preset.get('chosen_analysis'):
            problems.append(
                "The {} preset '{}' has no 'chosen_analysis' key, so the analysis side would not "
                "know which algorithm to run.".format(label, preset_name))

    # The object selection is optional and lives in its own config file, but a preset that is
    # named and then not found would only show up once the overview had been acquired
    selection_name = setup['overview_selection']

    if selection_name is not None:
        selection_preset = selection_data.get(selection_name)

        if selection_preset is None:
            problems.append(
                "The object selection preset '{}' is not in selection_config.json.".format(selection_name))

        elif not selection_preset.get('chosen_selection'):
            problems.append(
                "The object selection preset '{}' has no 'chosen_selection' key, so the analysis "
                "side would not know which algorithm to run.".format(selection_name))

    # A loaded setup can name an experiment that has since been renamed or deleted in ZEN, and
    # Zen.Acquisition.Experiments.GetByName then returns null, which only surfaces as
    # "Value cannot be null" once the run is already going. Names coming from the dropdowns are
    # always real, so this only ever catches a setup that was read back from a file.
    named_experiments = [("overview", setup['overview_experiment']),
                         ("object visualization", setup['visualization_experiment']),
                         ("Z", setup['z_experiment'])]

    named_experiments += [("post-analysis", name) for name in setup['post_experiments']]

    named_experiments += [("adaptive", experiment) for experiment in setup['adaptive_experiments']]

    for label, experiment_name in named_experiments:
        if experiment_name is not None and experiment_name not in experiments:
            problems.append(
                "The {} experiment '{}' is no longer among the experiments saved in ZEN.".format(
                    label, experiment_name))

    return problems


###################### the settings of the last run ###################################################

# Keys a saved setup has to carry. A file written by an older version of this macro would
# otherwise fail somewhere inside validate_setup, with a message about the wrong thing.
REQUIRED_SETUP_KEYS = ('finding_objects', 'multiple_overviews', 'overview_experiment',
                       'overview_analysis', 'overview_selection', 'visualization_experiment',
                       'reanalysis_xy', 'z_experiment', 'z_analysis', 'is_FCS',
                       'post_experiments', 'adaptive_pairs')


def load_setup(path, adaptive_functions, adaptive_path):
    """
    Reads back the settings of the last run. Anything that makes the file unusable raises, naming
    the file, so that the macro can say it in a window instead of the run failing halfway through
    an acquisition.
    :param str path: full path to the saved setup
    :param dict adaptive_functions: the plugins that were loaded, by name
    :param str adaptive_path: the folder they were loaded from
    :return: tuple (setup dict, error message from the adaptive experiment or None)
    :raise ValueError: when the file cannot be read or was written by an older version
    """
    log("Loading the setup of the last run from {}".format(path))

    try:
        setup = read_json(path)

    except Exception as error:
        raise ValueError("The saved setup {} could not be read: {}".format(path, error))

    missing = [key for key in REQUIRED_SETUP_KEYS if key not in setup]

    if missing:
        raise ValueError(
            "The saved setup {} is missing the keys: {}. It was most likely written by an older "
            "version of this macro. Run once without loading it and it will be written "
            "again.".format(path, ", ".join(missing)))

    # Functions cannot be written to a file, so the saved setup names the plugins instead and the
    # pairs are resolved again here, exactly as they are when they come from the dropdowns
    adaptive_experiments, adaptive_error = build_adaptive_experiments(
        setup['adaptive_pairs'], adaptive_functions, adaptive_path)

    setup['adaptive_experiments'] = adaptive_experiments

    return setup, adaptive_error


def save_setup(path, setup):
    """
    Records the confirmed settings, so that the next run can start from them. The evaluated
    adaptive experiments are left out because they hold functions; 'adaptive_pairs', which names
    them, is saved in their place.
    :param str path: full path to write to
    :param dict setup: the confirmed selections
    :return: None
    """
    saveable = dict(setup)
    saveable.pop('adaptive_experiments', None)

    with open(path, "w") as file:
        json.dump(saveable, file, indent=2)
