"""
Import one World B module by its file path, without running the __init__.py of its package.

data_processing/image_analysis/__init__.py imports every analyser, and with them cellpose,
torch and skimage. A test of a module that needs none of them (pixel_stage_converter needs
numpy alone) loads it directly, so that it runs without the heavy dependencies installed.
"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(relative_path, name):
    """
    :param str relative_path: path from the project root, for example "DecisionEngine/IO/read_czi_file.py"
    :param str name: module name to register it under, distinct from the package name
    :return: module
    """
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relative_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
