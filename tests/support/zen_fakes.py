"""
Stand-ins for the .NET and ZEN modules World A imports, so that ZeissAPI/zen_lib can be
imported and exercised by CPython 3 under pytest.

What these fakes are, and what they are not:

- System.IO.Path behaves like Windows paths (ntpath), so a test sees the paths that the
  microscope PC will see - D:\\automation\\results\\<name>\\obj_<id> - and not Linux ones.
- System.IO.Directory and File are an in-memory file system. Nothing is written to disk.
  File.Exists also answers True for a real file on disk, so that a test can point
  RuntimeConfig at the real path_config.example.json of the repository.
- They are an interpretation of .NET, not .NET. Where Path.Combine differs from ntpath.join
  (for example a drive-relative "D:x" second argument) these tests cannot notice. The
  autotest inside ZEN is what checks the real thing.
- The tests run in CPython 3, not IronPython 2.7. They check the logic of World A, not its
  compatibility with the interpreter; tests/contract/test_runtime_rule.py guards the syntax.
"""
import io
import ntpath
import os
import sys
import types


def _key(path):
    return ntpath.normcase(ntpath.normpath(path))


def is_windows_path(path):
    """
    :return: True for the paths World A builds (drive letter or backslashes), which live in
    the in-memory file system, False for real paths on the machine running the tests
    """
    path = str(path)
    return "\\" in path or (len(path) > 1 and path[1] == ":")


class FakeFileSystem:
    """
    The in-memory disk behind the fake System.IO. One instance per test, see conftest.py.
    """

    def __init__(self):
        self.dirs = set()
        self.files = {}
        self.mtimes = {}
        self._clock = 0

    # ---- helpers for tests ----------------------------------------------------------

    def write_file(self, path, text="", mtime=None):
        self._clock += 1
        self.files[_key(path)] = text
        self.mtimes[_key(path)] = self._clock if mtime is None else mtime
        self.make_dirs(ntpath.dirname(path))

    def read_file(self, path):
        return self.files[_key(path)]

    def make_dirs(self, path):
        while path and _key(path) not in self.dirs:
            self.dirs.add(_key(path))
            parent = ntpath.dirname(path)
            if parent == path:
                break
            path = parent

    def has_dir(self, path):
        return _key(path) in self.dirs

    def has_file(self, path):
        return _key(path) in self.files

    # ---- builtin open() replacement for the World A modules -------------------------

    def open(self, path, mode="r", *args, **kwargs):
        """
        open() as seen by the World A modules: Windows paths go to memory, anything else to
        the real disk.
        """
        if not is_windows_path(path):
            return io.open(path, mode, *args, **kwargs)

        fs = self
        if "r" in mode:
            if not self.has_file(path):
                raise IOError("No such file: {}".format(path))
            return io.StringIO(self.read_file(path))

        class _Writer(io.StringIO):
            def close(self_inner):
                previous = fs.files.get(_key(path), "") if "a" in mode else ""
                fs.write_file(path, previous + self_inner.getvalue())
                io.StringIO.close(self_inner)

        return _Writer()


# ---- System.IO ------------------------------------------------------------------------


def build_system_io(fs):
    """
    :param FakeFileSystem fs: the disk the module operates on
    :return: module standing in for System.IO
    """
    mod = types.ModuleType("System.IO")

    class Path(object):
        Combine = staticmethod(lambda *parts: ntpath.join(*parts))
        GetDirectoryName = staticmethod(ntpath.dirname)
        GetFileName = staticmethod(ntpath.basename)
        GetFileNameWithoutExtension = staticmethod(lambda p: ntpath.splitext(ntpath.basename(p))[0])
        GetFullPath = staticmethod(lambda p: ntpath.normpath(p if ntpath.isabs(p) else ntpath.join("C:\\cwd", p)))

    class Directory(object):
        Exists = staticmethod(fs.has_dir)
        CreateDirectory = staticmethod(fs.make_dirs)
        GetCurrentDirectory = staticmethod(lambda: "C:\\cwd")

        @staticmethod
        def GetFiles(path):
            folder = _key(path)
            return [k for k in fs.files if ntpath.dirname(k) == folder]

    class File(object):
        @staticmethod
        def Exists(path):
            if is_windows_path(path):
                return fs.has_file(path)
            return os.path.isfile(path)

        @staticmethod
        def GetLastWriteTime(path):
            return fs.mtimes[_key(path)]

    mod.Path, mod.Directory, mod.File = Path, Directory, File
    return mod


# ---- System.Diagnostics ---------------------------------------------------------------


class _Stream(object):
    def __init__(self, text=""):
        self.text = text

    def ReadToEnd(self):
        return self.text


class _StartInfo(object):
    def __init__(self):
        self.FileName = None
        self.WorkingDirectory = None
        self.Arguments = None
        self.UseShellExecute = True
        self.RedirectStandardOutput = False
        self.RedirectStandardError = False
        self.EnvironmentVariables = {}


class FakeProcess(object):
    """
    System.Diagnostics.Process that starts nothing. Every started process is recorded in
    FakeProcess.started, so a test can read the command line the runner built.
    """
    started = []

    def __init__(self):
        self.StartInfo = _StartInfo()
        self.StandardOutput = _Stream()
        self.StandardError = _Stream()

    def Start(self):
        FakeProcess.started.append(self.StartInfo)
        return True

    def WaitForExit(self):
        return None


def build_system_diagnostics():
    mod = types.ModuleType("System.Diagnostics")
    mod.Process = FakeProcess
    return mod


# ---- installation ---------------------------------------------------------------------


# One disk for the whole session. The zen_lib modules bind Path, Directory and File when they
# are imported, so the fakes must stay the same objects; conftest.py empties the disk before
# every test instead.
FS = FakeFileSystem()


def reset():
    FS.__init__()
    FakeProcess.started = []


def install(fs=FS):
    """
    Put the fakes into sys.modules. Called once, before any zen_lib module is imported.
    :param FakeFileSystem fs: the disk the fake System.IO operates on
    :return: None
    """
    system = types.ModuleType("System")
    system.IO = build_system_io(fs)
    system.Diagnostics = build_system_diagnostics()

    clr = types.ModuleType("clr")
    clr.ImportExtensions = lambda namespace: None
    clr.AddReference = lambda name: None

    zeiss = types.ModuleType("Zeiss")
    micro = types.ModuleType("Zeiss.Micro")
    lm = types.ModuleType("Zeiss.Micro.LM")
    scripting = types.ModuleType("Zeiss.Micro.LM.Scripting")
    zeiss.Micro, micro.LM, lm.Scripting = micro, lm, scripting

    sys.modules.update({
        "System": system,
        "System.IO": system.IO,
        "System.Diagnostics": system.Diagnostics,
        "clr": clr,
        "Zeiss": zeiss,
        "Zeiss.Micro": micro,
        "Zeiss.Micro.LM": lm,
        "Zeiss.Micro.LM.Scripting": scripting,
    })
    FakeProcess.started = []
