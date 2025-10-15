from System.Diagnostics import Process
import json


def log(msg):
    path = "D:\\zeiss\\Desktop\\zen_log.txt"
    with open(path, "a") as f:
        f.write(msg + "\n")


conf_path = "D:\\zeiss\\Desktop\\automation\\config\\preprocessing_config.json"

with open('config/preprocessing_config.json', 'r') as file:
    path_config = json.load(file)


def run_python_script(args=None, script_path=path_config['python_script'], python_path=path_config['python_exe']):
    proc = Process()
    proc.StartInfo.FileName = python_path

    arguments = [script_path]

    if args:
        arguments.extend(args)

    proc.StartInfo.Arguments = " ".join(arguments)
    proc.StartInfo.UseShellExecute = False
    proc.StartInfo.RedirectStandardOutput = True
    proc.StartInfo.RedirectStandardError = True

    proc.Start()
    output = proc.StandardOutput.ReadToEnd()
    error = proc.StandardError.ReadToEnd()
    log(output)
    log(error)

    proc.WaitForExit()
