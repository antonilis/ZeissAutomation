from System.Diagnostics import Process
import json


def log(msg):

    """
    Function for printing the logs to the txt file
    :param str msg: log to be printed
    :return: None
    """

    path = "D:\\Automation\\zen_log.txt"
    with open(path, "a") as f:
        f.write(msg + "\n")



class PythonAnalysisRunner:

    """
    Class responsible for the correct initialization of the main_processor Python script and loading correct arguments.

    param str config_path: path to the localization of the config folder

    """
    def __init__(self, config_path):

        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.python = self.config["python_exe"] #path to the virtual environment
        self.script = self.config["python_script"] #path to the python script - main_processor
        self.project = self.config["python_project_root"] #root of the main_processor localization


    def _make_args(self, **kwargs):
        """
        Function responsible for rewriting the dictionairy of the arguments for Python to the list of strings readable by the command line
        :param dict kwargs: dictionary of the arguments for Python initialization
        :return str args: arguments for initializing the Python from command line
        """
        args = []
        for k, v in kwargs.items():
            if v is not None:
                args.append("--{}={}".format(k, v))
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
