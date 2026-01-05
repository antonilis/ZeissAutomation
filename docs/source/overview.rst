Overview
========

This repository provides a modular framework for **automated image acquisition and adaptive fluorescence spectroscopy experiments**
on confocal microscopes (Zeiss LSM series).

The framework integrates directly with the **Zen Blue graphical user interface**, enabling full microscope control
without leaving the GUI environment.

The software was developed to support:

* Automated imaging and fluorescence correlation techniques (FCS, RICS)
* Robust object detection and re-analysis
* Adaptive measurement workflows based on object properties
* Reproducible data organization and processing

Although originally designed for specific experimental setups, the framework is **highly modular**
and can be adapted to a wide range of microscopy workflows.

For full documentation, see:
`ZeissAutomation documentation <https://zeissautomation.readthedocs.io/en/latest/zeissapi.html>`_

Key Features
------------

* Automated acquisition pipelines for imaging and spectroscopy
* Grid-based overview scanning for rapid sample mapping
* Object detection and re-analysis in XY and Z dimensions
* Adaptive experiments triggered by detected object properties
* Automatic data organization using unique identifiers (UUIDs)

Typical Workflow
----------------

A typical experiment follows these steps:

#. Generate an **overview grid** defining measurement positions
#. Prepare **.czexp experiment files** describing acquisition settings
#. Acquire overview images and **detect objects of interest**
#. Re-analyze object positions to compensate for stage inaccuracies and object movement
#. Perform **Z-scans** to locate signal maxima
#. Trigger downstream experiments by specifying the corresponding **.czexp files**
   (e.g. RICS, FCS, time-lapse)
#. Dynamically modify experiments based on object-specific properties
#. Automatically store and organize all results

Architecture
------------

The framework is organized around several core components:

**ZeissAPI**
    Provides microscope control via the Zen Blue API using ``.czmac`` macros.
    Handles GUI integration and Python subprocess execution.

**data_processing**
    Contains data processors responsible for image analysis and generation of JSON files
    describing object positions and properties, which are then consumed by macros.

**Processors**
    * ``ZeissImageProcessor`` – image analysis and object detection
    * ``ZeissFCSProcessor`` – fluorescence correlation spectroscopy analysis

This modular architecture ensures that the codebase remains **flexible, maintainable, and extensible**.

Adaptive Measurements
---------------------

A key feature of the framework is support for **adaptive experiments**.

Adaptive behavior is defined using a simple dictionary structure that maps the name of a
``.czexp`` experiment to a Python function responsible for modifying the experiment parameters:

.. code-block:: python

    {
        "experiment_name": adaptive_function
    }

This mechanism allows experiments to be adjusted dynamically based on detected object properties
or intermediate measurement results.
