# Automated Confocal Microscopy Pipeline

📖 **Full documentation:** https://your-project.readthedocs.io

## Overview

This repository contains a modular framework for **automated image acquisition and adaptive fluorescence spectroscopy experiments** on confocal microscopes (Zeiss LSM series).  

The framework integrates directly with the **Zen Blue GUI**, allowing seamless control of microscopes without leaving the graphical interface.

The software was developed to enable:
- 🔁 Automated imaging and fluorescence correlation (FCS, RICS) techniques
- 🧭 Robust object detection and re-analysis
- 🧠 Adaptive measurement workflows (experiments adapt based on object properties)
- 📁 Reproducible data organization and processing

Although originally designed for specific experimental setups, the framework is **highly modular** and can be adapted to other microscopy workflows.

---

## Key Features

- 🔁 **Automated acquisition pipelines** for imaging and spectroscopy
- 🗺️ **Grid-based overview scanning** for fast sample mapping
- 🎯 **Object detection and re-analysis** in XY and Z
- 🧠 **Adaptive experiments** triggered by object properties
- 💾 **Automatic data organization** with unique identifiers (UUIDs)

---

## Typical Workflow

1. 🖼️ Generate an **overview grid** of measurement positions
2. 📝 Prepare your **.czexp files** with experiment details
3. 🔬 Acquire overview images and **detect objects of interest**
4. 🎯 Re-analyze object positions to compensate for stage inaccuracies and object movements
5. 🔍 Perform **Z-scans** to find signal maxima
6. 🚀 Trigger downstream experiments by specifying the **.czexp files** (e.g., RICS, FCS, time-lapse)
7. 🧠 Modify experiments dynamically based on object properties
8. 💾 Automatically store and organize all results

---

## Architecture

The framework is organized around a set of core components:

- **`ZeissAPI`**  
  Utilizes Zen Blue API (.czmac macro) for microscope control, **GUI integration**, and Python subprocess handling

- **`data_processing`**  
  Contains processors for data analysis and producing JSON files with object positions and properties for macros

- **Processors**
  - `ZeissImageProcessor` – image analysis
  - `ZeissFCSProcessor` – fluorescence correlation spectroscopy

This design makes the codebase **flexible, maintainable, and extensible**.

---

## Adaptive Measurements

One of the key features of the framework is support for **adaptive experiments**.

Adaptive logic is defined using a simple dictionary structure, mapping the name of a **.czexp experiment** to a Python function specifying the experiment modification:

```python
{
    "experiment_name": adaptive_function
}
