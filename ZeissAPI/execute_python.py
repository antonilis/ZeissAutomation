from System.Diagnostics import Process

from runtime_config import log


class PythonAnalysisRunner:

    """
    Class responsible for the correct initialization of the main_processor Python script and loading correct arguments.

    param RuntimeConfig config: configuration built by the macro, this class does not read it from disk itself

    """
    def __init__(self, config):

        self.config = config

        self.python = config.python_exe #path to the virtual environment
        self.script = config.python_script #path to the python script - main_processor
        self.project = config.python_project_root #root of the main_processor localization

        # The CPython side does not know where the ZEN runtime folder is, so the location
        # of preprocessing_config.json is handed to it with every call
        self.preprocessing_config = config.preprocessing_config_path


    def _make_args(self, **kwargs):
        """
        Function responsible for rewriting the dictionairy of the arguments for Python to the list of strings readable by the command line
        Values are quoted, because result folders are named after the sample and may contain spaces.
        :param dict kwargs: dictionary of the arguments for Python initialization
        :return str args: arguments for initializing the Python from command line
        """
        args = []
        for k, v in kwargs.items():
            if v is not None:
                args.append('--{}="{}"'.format(k, v))
        return args

    def run(self, **kwargs):
        """
        Function for Python initialization
        :param dict kwargs: dictionary of the arguments for Python initialization
        :return: None
        """
        log("Started run of python!")

        # The location of the analysis presets travels with every call, so that the
        # CPython side never has to guess where the config folder is
        kwargs["preprocessing_config"] = self.preprocessing_config

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
