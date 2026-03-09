from System.Diagnostics import Process
import json
from utils import log


class PythonAnalysisRunner:

    """
    Class responsible for the correct initialization of the main_processor Python script and loading correct arguments.

    param str config_path: path to the localization of the python_config folder

    """
    def __init__(self, config_path):

        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.python = self.config["python_exe"] #path to the virtual environment
        self.script = self.config["python_script"] #path to the python script - main_processor
        self.project = self.config["python_project_root"] #root of the main_processor localization

    def _make_args(self, **kwargs):
        """
        Convert dictionary of arguments to a list of CLI arguments.
        Works with strings, numbers, booleans, lists and dictionaries.
        """
        args = []
        for k, v in kwargs.items():
            if v is not None:
                if isinstance(v, (dict, list)):

                    v_str = json.dumps(v)
                else:
                    v_str = str(v)
                args.append(f"--{k}={v_str}")
        return args

    def run(self, **kwargs):
        """
        Function for Python initialization
        :param dict kwargs: dictionary of the arguments for Python initialization
        :return: None
        """
        log("Started run of python!")
        
        proc = Process()
        proc.StartInfo.FileName = self.python
        proc.StartInfo.WorkingDirectory = self.project
        proc.StartInfo.UseShellExecute = False
        proc.StartInfo.RedirectStandardOutput = True
        proc.StartInfo.RedirectStandardError = True
        env = proc.StartInfo.EnvironmentVariables
        env["PYTHONPATH"] = self.project

        args = [self.script] + self._make_args(**kwargs)
        
        log("Runner arguments:{}".format(args))
        
        proc.StartInfo.Arguments = " ".join(args)

        proc.Start()
        out = proc.StandardOutput.ReadToEnd()
        err = proc.StandardError.ReadToEnd()
        proc.WaitForExit()

        log(out)
        log(err)
