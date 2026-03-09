from System.IO import Path
import json


CONFIG_PATH = r".\config\path_config.json"



def log(msg):
    """
    Function for printing the logs to the txt file
    :param str msg: log to be printed
    :return: None
    """
    name = "zen_log.txt"

    with open(CONFIG_PATH, "r") as f:
        conf_paths_dict = json.load(f)

    path = conf_paths_dict["python_project_root"]
    logging_path = Path.Combine(path, name)

    with open(logging_path, "a") as f:
        f.write(msg + "\n")