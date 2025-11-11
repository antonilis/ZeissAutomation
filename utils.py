import matplotlib.pyplot as plt
import sys
import numpy as np


def visualize_points(ZIP_object, save_path=None):
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
    Parser of the arguments from the line command
    """
    args_dict = {}
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            # usuń początkowe '--'
            kv = arg[2:]
            # rozdziel pierwszy '='
            if "=" in kv:
                key, value = kv.split("=", 1)
                # opcjonalnie usuń cudzysłowy, jeśli ktoś przekazał np. --'obj id'="42"
                key = key.strip("'\"")
                value = value.strip("'\"")
                args_dict[key] = value
            else:
                # argument flagowy bez wartości
                args_dict[kv] = True
    return args_dict


def choose_the_closest_point(measurement_points, stage_position):
    stage = np.array([stage_position['x'], stage_position['y'], stage_position['z']])

    distances = [np.linalg.norm(np.array(p["position"]) - stage) for p in measurement_points]

    closest_idx = int(np.argmin(distances))

    return measurement_points[closest_idx]