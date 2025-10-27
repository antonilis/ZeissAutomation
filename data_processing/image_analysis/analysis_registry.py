_REGISTRY = {}

def register_class(cls):
    _REGISTRY[cls.__name__] = cls
    return cls

def get_image_analysis_type(name):
    return _REGISTRY.get(name)

def get_available_analysis():
    return list(_REGISTRY.keys())
