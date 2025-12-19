# conf.py

import os
import sys
sys.path.insert(0, os.path.abspath('../../'))  # ścieżka do katalogu głównego projektu

# -- Project information -----------------------------------------------------

project = 'ZeissAutomation'
author = 'Your Name'
release = '0.1'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',     # generuje dokumentację z docstringów
    'sphinx.ext.napoleon',    # obsługuje docstringi Google/NumPy
    'sphinx.ext.viewcode',    # dodaje linki do źródła kodu
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'  # popularny theme dla Read the Docs
html_static_path = ['_static']

# -- Options for autodoc -----------------------------------------------------

autodoc_member_order = 'bysource'  # porządek według kolejności w kodzie
autodoc_default_flags = ['members', 'undoc-members', 'show-inheritance']
