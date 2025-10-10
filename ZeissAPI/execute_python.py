from System.Diagnostics import Process


def log(msg):
    path = "D:\\zeiss\\Desktop\\zen_log.txt"
    with open(path, "a") as f:
        f.write(msg + "\n")



python_exe = "D:\\zeiss\\Desktop\\automation\\venv\\Scripts\\python.exe"
python_script = "D:\\zeiss\\Desktop\\automation\\image_preprocessing\\preprocessing.py"

def run_python_script(args=None, script_path = python_script, python_path = python_exe):

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

