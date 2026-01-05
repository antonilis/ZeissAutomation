config
======

The ``config`` directory contains JSON configuration files responsible for:

* Defining paths and project-level settings
* Configuring preprocessing and segmentation algorithms

Files
-----

``path_config.json``
~~~~~~~~~~~~~~~~~~~~
Contains paths related to the project setup, including:

* Path to the Python virtual environment
* Path to the project root directory
* Paths for saving and loading experiment results
* Default Zeiss file save location

``preprocessing_config.json``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Contains a dictionary defining available segmentation algorithms.

* **Keys**: names of classes located in ``data.processing.image_analysis``
* **Values**: dictionaries mapping argument names to values required by the selected class

