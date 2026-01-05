ZeissAPI
========

The ``ZeissAPI`` module provides the execution layer of the automated confocal
microscopy framework.

It is responsible for microscope control, experiment orchestration,
GUI integration inside Zen Blue, and communication with external
Python analysis processes.

The module consists of Zen macros (``.czmac``) and IronPython helper modules.

Overview
--------

The ZeissAPI layer connects the Zen Blue microscope control software
with the Python-based analysis pipeline.

Its main responsibilities include:

* Executing automated acquisition workflows
* Managing microscope stage and focus movements
* Running overview scans and object-based reanalysis
* Triggering adaptive and post-analysis experiments
* Delegating computational analysis to external Python processes

---

Main Macro: ``main_macro.czmac``
-------------------------------

This macro defines the core acquisition logic and user interface.

It contains two main logical components: low-level API wrappers and
the high-level acquisition pipeline.

ZeissApiProcessor
~~~~~~~~~~~~~~~~~

.. class:: ZeissApiProcessor

   A collection of static methods wrapping core Zen Blue API calls
   for microscope control and experiment execution.

   **Responsibilities:**

   * Reading configuration files
   * Querying and updating stage and focus positions
   * Loading and executing ``.czexp`` experiments
   * Saving experiment results for imaging and spectroscopy

   .. method:: get_stage_focus_position()

      Return the current stage and focus position as ``[x, y, z]``.

   .. method:: move(points_to_move)

      Move the microscope stage and focus to the specified coordinates.

   .. method:: load_experiment(chosen_experiment)

      Load and activate a ``.czexp`` experiment by name.

   .. method:: execute_current_experiment()

      Execute the currently active experiment.

   .. method:: save_experiment_result(name, base_name=None)

      Save experiment results using the configured directory layout.

---

AcquisitionPipeline
~~~~~~~~~~~~~~~~~~~

.. class:: AcquisitionPipeline(object_visualization_experiment=None, reanalysis_dict=None, post_reanalysis_experiments=None, adaptive_experiment=None)

   Implements a complete automated acquisition workflow.

   The pipeline combines overview acquisition, object detection,
   spatial reanalysis (XY and Z), adaptive experiment execution,
   and post-processing measurements.

   **Main stages:**

   #. Overview acquisition and analysis
   #. Object-based navigation
   #. XY and Z reanalysis
   #. Adaptive experiment execution
   #. Post-analysis measurements

   .. method:: acquire_overview(overview_experiment, analysis_args=None, name=None)

      Execute an overview experiment and optionally trigger Python-based analysis.

   .. method:: capture_objects(object_ids=None, name=None)

      Perform visualization, reanalysis, and post-analysis experiments
      for detected objects.

   .. method:: _perform_reanalysis_xy(obj_id, name=None)

      Perform XY reanalysis of object position.

   .. method:: _perform_reanalysis_z(obj_id, name=None, obj=None)

      Perform Z reanalysis and update focus position.

---

Adaptive Experiments
--------------------

The acquisition pipeline supports **adaptive experiments**, where
experiment parameters are modified dynamically based on object
properties obtained during analysis.

Adaptive behavior is implemented using user-defined Python functions
executed before experiment runs.

An example adaptive function is ``fcs_zscan``, which modifies the
center of a Z-scan based on the detected object radius.

---

Overview Grid Generation: ``find_overview_positions.czmac``
-----------------------------------------------------------

AcquisitionGrid
~~~~~~~~~~~~~~~

.. class:: AcquisitionGrid(mode="experiment", experiment_name="AI_sample_finder", manual_points=None)

   Generates spatial grids for automated overview acquisition.

   **Supported modes:**

   * ``experiment`` – read tile center positions from a ``.czexp`` experiment
   * ``manual`` – generate a regular grid using plate-style coordinates

   .. method:: calculate_points_for_overview()

      Read tile center positions from the selected experiment.

   .. method:: generate_grid_from_args()

      Generate a regular grid based on manual configuration.

   .. method:: save_overview_points()

      Save generated grid points as a JSON file compatible with the acquisition pipeline.

---

Python Analysis Bridge
---------------------

The following helper modules are implemented in IronPython.

execute_python
~~~~~~~~~~~~~~

.. automodule:: execute_python
   :members:
   :undoc-members:
   :show-inheritance:

path_manager_main_macro
~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: path_manager_main_macro
   :members:
   :undoc-members:
   :show-inheritance:
