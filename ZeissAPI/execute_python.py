from System.Diagnostics import Process
import json


def log(msg):
    path = "D:\\zeiss\\Desktop\\zen_log.txt"
    with open(path, "a") as f:
        f.write(msg + "\n")



class PythonAnalysisRunner:
    def __init__(self, config_path):

        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.python = self.config["python_exe"]
        self.script = self.config["python_script"]
        self.project = self.config["python_project_root"]


    def _make_args(self, **kwargs):

        args = []
        for k, v in kwargs.items():
            if v is not None:
                args.append("--{}={}".format(k, v))
        return args

    def run(self, **kwargs):
        
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
