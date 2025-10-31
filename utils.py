import matplotlib.pyplot as plt


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

    #plt.close()