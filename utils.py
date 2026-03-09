import matplotlib.pyplot as plt
import sys
import json
import numpy as np


def visualize_points(ZIP_object, save_path=None):
    """
    Function for plotting the founded points on the image used for analysis
    :param object ZIP_object: ZeissImageProcessor Object
    :param str save_path: path to which the png will be saved
    :return: None
    """
    plt.imshow(ZIP_object.image_to_analyze, cmap='gray')

    plt.colorbar()
    meas_points = ZIP_object.not_scaled_points

    for item in meas_points:
        point = item['position']
        plt.scatter(point[0], point[1], s=10)

    plt.title('Points for measurement')

    if save_path is not None:
        plt.savefig(save_path)
    plt.close()


def parse_args_to_dict():
    """
    Parser of command line arguments to dictionary.
    Automatically converts JSON strings to dict/list.
    Also converts "True"/"False" strings to booleans.
    Returns: dict
    """
    args_dict = {}
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            kv = arg[2:]
            if "=" in kv:
                key, value = kv.split("=", 1)
                key = key.strip("'\"")
                value = value.strip("'\"")

                # Spróbuj najpierw zamienić na JSON
                try:
                    value_parsed = json.loads(value)
                except json.JSONDecodeError:
                    # Jeśli to nie JSON, spróbuj rozpoznać True/False
                    if value.lower() == "true":
                        value_parsed = True
                    elif value.lower() == "false":
                        value_parsed = False
                    else:
                        value_parsed = value

                args_dict[key] = value_parsed
            else:
                args_dict[kv] = True
    return args_dict


def choose_the_closest_point(measurement_points, stage_position):
    """
    Function to choose the closest point from the founded to the stage position
    :param list measurement_points: list coordinates of the points which will be compared
    :param dict stage_position: position of the stage
    :return: list coordinates of the closest point
    """
    stage = np.array([stage_position['x'], stage_position['y'], stage_position['z']])

    distances = [np.linalg.norm(np.array(p["position"]) - stage) for p in measurement_points]

    closest_idx = int(np.argmin(distances))

    return measurement_points[closest_idx]