"""
The dictionary with the name of the algorithms available in this folder.
"""


_REGISTRY = {}

def register_class(cls):
    _REGISTRY[cls.__name__] = cls
    return cls

def get_image_analysis_type(name):
    return _REGISTRY.get(name)

def get_available_analysis():
    return list(_REGISTRY.keys())

def get_analysis_with_rois():
    """
    Names of the analyses which can hand out the outline of every object they found, and which
    can therefore be combined with an object selection.
    """
    return [name for name, cls in _REGISTRY.items() if getattr(cls, "provides_object_rois", False)]
