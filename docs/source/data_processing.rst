data_processing
=====

Module for cPython analysis of the .czi, .raw files and writing the objects or positions
for the microscope to measure.


main_processor
==============

Main processor script for handling .czi and .raw file analysis.

This module is initialized by the PythonRunner. It takes the arguments
from PythonRunner, decides whether to run an FCS or image analysis,
initializes the corresponding processor objects, and saves the results
to JSON files. In the case of image analysis, it can optionally visualize
the measurement points.

Usage
-----

- Parses command-line arguments using `parse_args_to_dict()`.
- For FCS analysis:
  - Initializes `ZeissFCSProcessor`.
  - Saves measurement points to JSON.
- For image analysis:
  - Reads preprocessing configuration.
  - Initializes `ZeissImageProcessor` with the appropriate analysis type.
  - Handles reanalysis by choosing the closest measurement point if necessary.
  - Saves measurement points to JSON.
  - Optionally generates a visualization of the measurement points (if not reanalysis_z).

Notes
-----

- This module depends on `config/preprocessing_config.json`, `utils`, and processor classes.
- Designed to be run by PythonRunner, not directly in production scripts.
- File paths and arguments are passed via PythonRunner.


.. automodule:: data_processing
   :members:
   :undoc-members:
   :show-inheritance: