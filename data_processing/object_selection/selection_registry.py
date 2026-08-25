"""
The dictionary with the name of the object selection algorithms available in this folder.
"""


_REGISTRY = {}

def register_class(cls):
    _REGISTRY[cls.__name__] = cls
    return cls

def get_object_selection_type(name):
    return _REGISTRY.get(name)

def get_available_selections():
    return list(_REGISTRY.keys())
