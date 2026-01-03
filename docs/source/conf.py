import os
import sys
import subprocess
import sphinx_rtd_theme


sys.path.insert(0, os.path.abspath('../../'))  # path to the main directory

# ------------------------------------------------------
# Automatically generate .rst files for Python modules
# ------------------------------------------------------
# Output directory for .rst files (same as source)
rst_output = os.path.abspath(os.path.dirname(__file__))

# List of module directories to document
module_dirs = ['../../data_processing', '../../IO']

for mod_dir in module_dirs:
    subprocess.call(['sphinx-apidoc', '-o', rst_output, mod_dir])

# -- Project information -----------------------------------------------------

project = 'ZeissAutomation'
author = 'Antoni Lis'
release = '0.1'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode'
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'titles_only': False
}

# -- Options for autodoc -----------------------------------------------------

autodoc_member_order = 'bysource'
autodoc_default_flags = ['members', 'undoc-members', 'show-inheritance']
