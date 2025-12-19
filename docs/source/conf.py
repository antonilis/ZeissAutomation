# conf.py

import os
import sys
sys.path.insert(0, os.path.abspath('../../'))  # ścieżka do katalogu głównego projektu

# -- Project information -----------------------------------------------------

project = 'ZeissAutomation'
author = 'Antoni Lis'
release = '0.1'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.viewcode',    
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = 'alabaster'  # default, not necesseary the best visually
html_static_path = ['_static']

# -- Options for autodoc -----------------------------------------------------

autodoc_member_order = 'bysource'  # porządek według kolejności w kodzie
autodoc_default_flags = ['members', 'undoc-members', 'show-inheritance']
