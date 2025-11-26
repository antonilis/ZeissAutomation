from System.IO import Directory, Path, File
import json


def log(msg):
    path = "D:\\Automation\\zen_log.txt"
    with open(path, "a") as f:
        f.write(msg + "\n")



class PathManager:

    def __init__(self, config_path):
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.results = self.config["results_path"]
        self.measurements = self.config["measuring_points_path"]
        self.analysis = self.config["image_for_analysis_path"]
        self.zeiss_temp = self.config["zeiss_temp_file"]

    def overview_image_path(self, obj_id, name=None):
        if name:
            prefix = "{}_".format(name)
        else:
            prefix = ""
        filename = "{}{}_Image_overview.czi".format(prefix, obj_id)
        
        return Path.Combine(self.analysis, filename)

    def temp_file_path(self, obj_id, reanalysis_type=None, name=None):
        if name:
            prefix = "{}_".format(name)
        else:
            prefix = ""

        if reanalysis_type is None:
            suffix = "measurements_points.json"
        elif reanalysis_type == "xy":
            suffix = "measurements_points_reanalysis_xy.json"
        elif reanalysis_type == "z":
            suffix = "measurements_points_reanalysis_z.json"
        elif reanalysis_type == "overview_points":
            suffix = "points_for_overview.json"
        else:
            raise ValueError("Unknown reanalysis type: {}".format(reanalysis_type))

        filename = "{}{}_{}".format(prefix, obj_id, suffix)
        log(filename)
        return Path.Combine(self.measurements, filename)

    def result_dir(self, obj_id, stage=None, name=None):
        """

        """
        if name:
            base = Path.Combine(self.results, name)
        else:
            base = self.results

        folder = Path.Combine(base, "obj_{}".format(obj_id))

        if not Directory.Exists(folder):
            Directory.CreateDirectory(folder)

        return folder

    def result_path(self, obj_id, stage, measurement, name=None):
        """

        """       
        
        log("Now it should have exp and post with suffix")
        
        folder = self.result_dir(obj_id, stage, name)
        
        if stage is None:
            suffix = ''
        else:
            suffix = stage      
        
        if name:
            file_name = "{}_{}_{}{}.czi".format(name, obj_id, measurement, suffix)
        else:
            file_name = "{}_{}{}.czi".format(obj_id, measurement, suffix)

        return Path.Combine(folder, file_name)

    def get_latest_fcs_and_raws(self):
        files = Directory.GetFiles(self.zeiss_temp)
        fcs_files = [f for f in files if f.lower().endswith(".fcs")]
        raw_files = [f for f in files if f.lower().endswith(".raw")]

        if len(fcs_files) == 0 or len(raw_files) == 0:
            log("No FCS or .raw in folder: {}".format(self.zeiss_temp))
            return []

     
        fcs_files.sort(key=lambda f: File.GetLastWriteTime(f), reverse=True)
        raw_files.sort(key=lambda f: File.GetLastWriteTime(f), reverse=True)

    
        newest_fcs = fcs_files[0]

        fcs_name = Path.GetFileNameWithoutExtension(newest_fcs)
     
    
        matching_raws = [r for r in raw_files if Path.GetFileName(r).startswith(fcs_name)]

        log("Znaleziono {} RAW z tym UUID.".format(len(matching_raws)))

        
        all_paths = [newest_fcs] + matching_raws
        
        
        return all_paths
        


