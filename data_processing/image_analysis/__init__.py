import pkgutil
import importlib
import sys

"""
Loads all of the existing Python algorhitms to the register
"""


package = sys.modules[__name__]

for loader, module_name, is_pkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(module_name)
