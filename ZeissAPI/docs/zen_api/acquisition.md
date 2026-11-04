# Zen.Acquisition — running the microscope

`Zen.Acquisition` is a `ZenBlueAcquisition`. Its members are spread over four base classes
(`ZenLmAcquisition` → `ZenAcquisitionLM` → `ZenAcquisition` → `ZenAcquisitionCore`), which is why the
dump lists them in several places; the union is below.

## Properties

| Member | Type | Note |
|---|---|---|
| `Experiments` | `ZenExperiments` | the collection of `.czexp` documents |
| `ActiveCamera` | `ZenCamera` | see [devices.md](devices.md) |
| `CameraSettings` | `ZenCameraSettings` | saved camera presets |
| `IsLiveRunning` | `bool` | |
| `IsContinuousRunning` | `bool` | |
| `Options.IsImagePyramidEnabled` | `bool` | pyramids cost time on big tile scans |

## Acquiring

| Call | Returns | Use for |
|---|---|---|
| `Execute(experiment)` | `ZenImage` | the normal case: run an experiment to completion |
| `AcquireImage()` | `ZenImage` | a single snap with the current settings - **fails on the LSM**, see below |
| `AcquireImage(addToDocumentsCollection)` | `ZenImage` | pass `False` to keep it out of the GUI document list - **fails on the LSM** |
| `AcquireImage(experiment)` | `ZenImage` | one frame using an experiment's settings - works, same frame time as `Execute` |
| `ExecuteMultiImages(experiment)` | `ZenImage[]` | experiments that yield several images |
| `ExecuteMultiBlockImages(experiment)` | `ZenMultiBlockImage` | multi-block experiments |
| `ExecutePanoramaExperiment(experiment)` | `ZenImage` | panorama |
| `Run(experiment, stopped)` | `ZenImage` | `stopped` is a `ref` parameter — see below |
| `StartLive()` / `StartLive(experiment)` | `ZenImage` | live view; the image keeps updating |
| `StopLive()` / `StopLive(experiment)` | | |
| `StartContinuous()` / `StopContinuous()` | | continuous acquisition |
| `IsLive()` | `bool` | |
| `GetImageName(name)` | `str` | the name ZEN would give this acquisition |

On the LSM 880 the two overloads without an experiment raise `The provided imaging devices are not
alive`: there is no "current settings" for the scanner outside an experiment. Pass the experiment.
Measured: `AcquireImage(experiment)` and `Execute(experiment)` both take ~20 s for a 1633 x 1633
frame without averaging and ~36 s with averaging 2.

`Run` is declared `ZenImage Run(ZenExperiment experiment, Boolean& stopped)`. IronPython returns
`ref`/`out` parameters alongside the return value, so the result is a tuple rather than a bare
image. **Not verified on the instrument** — check the shape before depending on it; `Execute` has no
such wrinkle and is the safer default.

```python
experiment = Zen.Acquisition.Experiments.GetByName("overview.czexp")
experiment.SetActive()

image = Zen.Acquisition.Execute(experiment)
image.Save(saving_path)
image.Close()
```

Closing matters. Acquired images sit in memory until closed, and a long unattended run that keeps
every field of view alive will exhaust it. `image.Close(True)` also deletes the file.

## Focus

Two unrelated mechanisms, easy to confuse:

**Software autofocus** — analyses image contrast, takes time, returns the z it settled on:

| Call | Returns |
|---|---|
| `FindAutofocus()` | `float` (z position) |
| `FindAutofocus(timeoutSeconds)` | `float` |
| `FindAutofocus(experiment)` | `float` |
| `FindAutofocus(experiment, timeoutSeconds)` | `float` |

Always prefer an overload with a timeout in an unattended run — the default has none.

**Definite Focus / hardware focus stabilisation** — no image analysis, near-instant:

| Call | Meaning |
|---|---|
| `FindSurface()` | drive to the detected cover-slip surface |
| `StoreFocus()` | remember the current offset from that surface |
| `RecallFocus()` | drive back to the stored offset |

The usual pattern is `FindSurface()` once, `StoreFocus()` at a good focus, then `RecallFocus()` at
every new position — far faster and gentler on the sample than autofocusing per field.

**Autofocus parameters inside an experiment** are set through extension methods, not properties:

```python
experiment.SetAutofocusParameters(block, mode, contrastMeasure, searchStrategy, sampling,
                                  reflectionModeOffset, useAcquisitionRoi, referenceChannelName,
                                  relativeRangeIsAutomatic, relativeRangeSize,
                                  fixedRangeLowerLimit, fixedRangeUpperLimit)
setting = experiment.GetAutofocusParameters(block)   # -> ZenSoftwareAutofocusSetting
```

Every parameter after `block` is nullable, so pass only the ones you mean to change. Declared in
`Zeiss.Micro.LM.Scripting.ZenSoftwareAutofocusExperimentExtensions` — the import rule in
[extension-methods.md](extension-methods.md) applies. The dump does not descend into
`ZenSoftwareAutofocusSetting`, `ZenSoftwareAutofocusMode`, `…ContrastMeasure` or `…Sampling`, so
their members and enum values are unknown from the dump alone; enumerate them at runtime with
`dir()`.

## Exposure

`AutoExposure()` or `AutoExposure(experiment)`. No return value — it writes into the camera/experiment
settings. Re-read `Zen.Acquisition.ActiveCamera.ExposureTime` if you need the resulting value.

## Zen.Acquisition.Experiments

| Member | Note |
|---|---|
| `ActiveExperiment` | get/set the one the GUI shows |
| `Count`, `[i]`, `CurrentItem` | |
| `GetByName(name)` / `GetByFileName(fileName)` / `Find(fileName)` | |
| `Contains(exp)`, `Add(exp)`, `Delete(exp)`, `Clear()` | |
| `Available` | `IList<...>` of what exists on disk without loading it |
| `FindDataFiles()` / `FindTemplateFiles()` | user vs. template directories |
| `LoadAll()` | forces every experiment to load — slow |

`GetByName` wants the file name as ZEN shows it, extension included.

## ZenExperiment

A `ZenCategorisedDocument`, so it has the whole `Load` / `Save` / `SaveAs` / `SetActive` / `Delete` /
`Rename` / `Import` / `Close` family described in the [README](README.md#rules-that-hold-across-the-whole-api).
On top of that:

| Member | Note |
|---|---|
| `AutoSave` | `ZenExperimentAutoSaveData`, below |
| `AutomationData` | `ZenExperimentAutomationData`, below |
| `LoadFromImage(image)` | recover the experiment an image was acquired with |
| `Core` | the internal `HardwareExperiment` |

### Laser power

Not reachable through the scripting layer; it takes `Core`. Measured on the instrument (LSM 880,
ZEN 3.28) with `probe_smart_SLB_imaging_3.czmac`.

In the `.czexp` the power is a property of the **track**, in percent:

```xml
<Track>
  <DetectionModeSetup>
    <Zeiss.Micro.LSM.Acquisition.Lsm880ChannelTrackDetectionMode>
      <TrackLaserSettings>
        <ParameterCollection Id="MTBLKM980LaserLine639">
          <IsEnabled>true</IsEnabled>
          <Intensity>0.2</Intensity>
```

The in-memory object has the same shape:

```python
def laser_intensity(experiment, laser_line="MTBLKM980LaserLine639"):
    block = experiment.Core.CurrentExperimentBlock          # the acquisition block
    for setup in block.SubDimensionSetups:                  # tracks, z-stack, tiles, ... setups
        if not hasattr(setup, "ActivatedTracks"):           # only the multi-track setup has tracks
            continue
        for track in setup.ActivatedTracks:
            laser_lines = track.SelectedDetectionModeSetup.TrackLaserSettings.ParameterCollections
            for laser in laser_lines:                       # one ParameterCollection per laser line
                if str(laser.Id) == laser_line:
                    return laser["Intensity"]               # a Parameter object, not a number
    return None

intensity = laser_intensity(experiment)
intensity.Value            # '0.2' - a STRING, in percent
intensity.Value = "0.4"    # the next AcquireImage / Execute of this experiment uses 0.4 %
```

- `laser["Intensity"]` returns a `Zeiss.Micro.Hardware.Common.Parameter`. Its `.Value` is read and
  written as a string; treating the `Parameter` itself as the number is the mistake that is easy
  to make. It also has `Minimum`, `Maximum`, `Unit`, `IsReadOnly`, `SetValue` and friends.
- The change lives in memory only. The `.czexp` on disk is untouched unless the experiment is saved.
- Measured on an SLB at 40x: 0.2 % -> 0.4 % took the median from 3724 to 7618 with a background of
  55 at 0 %, so `(2x - bg) / (1x - bg) = 2.06` - the signal is linear in `Value`. Two frames in
  between bleached nothing measurable.
- ZEN writes the power actually used into the `.czi` (`LightSourceSettings/Transmission`, as a
  fraction: `0.002` for 0.2 %).

Two routes that look right and do **not** reach the laser:

- `experiment.GetDetectorSettings(0)` holds a single component, `MTBLSMImagingDevice` - scan
  parameters only, no laser.
- The stand's setting (`Zen.Devices.ReadHardwareSetting()`) does have
  `MTBLKM980LaserLine639.Intensity`, but the experiment sets its own track's power when it runs.

`Core` is the unversioned internal layer (see the README), so this path can move in a ZEN update.
If `laser_intensity` returns `None` after one, dump `experiment.Core` again along the XML path above.

### FCS count rate

There is no scripting API for it, and the FCS assemblies (`Zeiss.Micro.LSM.FCS*`) are not reachable
from `Zen`, so `dump_zen_api.czmac` never shows them. `diagnostics/probe_fcs_live_counts.czmac` lists
them. The live values are read from the detector counting panel on screen: its `DataContext` in the
WPF visual tree is an `FcsDetectorCountingViewModel`, with `CountRateValues` (entries with a string
`Value`, such as `37.568 kHz`) and a settable `SelectedCountingMethod`. `ZenApi.fcs_count_rate` does
this; the details are at the top of `zen_lib/zen_api.py`. Measured on an LSM 880, ZEN 2 blue:

- `Execute` keeps the UI thread running, so a second thread can read while the macro waits.
- The panel shows the previous measurement until its list empties, about 2 s after the start.
- The first fresh value comes about 3.8 s after the start.
- Right after a large drop in power the panel showed the old level for over a second, so take the
  last value of a measurement, not the first.
- Counts per molecule needs the panel's averaging set, or it jumps around, down to negative values.

### AutoSave

Controls what ZEN writes to disk on its own during the run. Relevant when a macro also wants to
save — decide which of the two owns the output, because both will happily write.

`IsActivated`, `Name`, `FullName`, `StorageFolder`, `AutoSubFolder`, `IsAutoSubFolder`,
`IsAutoSubFolderExternal`, `IsClosedOnCompletion`, `AlwaysAddFileIndex`, `UseChannelNames`,
`DimensionsForSeparateFolders`, `CompressionMethod`, `Quality`, `ConvertTo8Bit`,
`ApplyDisplayMappings`, `AddXmlMetadata`, `SaveOriginalData`, `EnableSingleFileSave`,
`SingleFileName`, `SingleFileSaveFormat`, `SingleFileSaveDestinationFolder`.

### AutomationData

`IsActivated`, `RunMacroBeforeExperiment`, `MacroBeforeExperiment`, `RunMacroAfterExperiment`,
`MacroAfterExperiment`, `SetDefault()`. This is ZEN's own hook for chaining macros around an
experiment — an alternative to driving everything from one macro, though it makes control flow
harder to follow.

## Tile regions and positions

All of this is extension methods on `ZenExperiment`, from
`Zeiss.Micro.LM.Scripting.ZenExperimentExtensions`. `blockIndex` is the acquisition block, `0` for a
single-block experiment.

**Clearing** (do this before writing new positions, or they accumulate):

```python
experiment.ClearTileRegionsAndPositions(0)
experiment.ClearExperimentRegionsAndPositions(0)
```

**Adding positions and tile regions** — coordinates in stage micrometres:

| Call |
|---|
| `AddSinglePosition(blockIndex, x, y, z)` |
| `AddRectangleTileRegion(blockIndex, centerX, centerY, width, height, z)` |
| `AddEllipseTileRegion(blockIndex, centerX, centerY, width, height, z)` |
| `AddPolygonTileRegion(blockIndex, polygonPoints, z)` |

**Adding overlay regions** (bleaching / analysis ROIs drawn relative to an image) — these need the
image's scaling and its top-left stage position:

| Call |
|---|
| `AddRectangleExperimentRegion(scaling, stagePositionLeftTop, blockIndex, centerX, centerY, width, height, color, forAcquisition, forBleaching, forAnalysis)` |
| `AddEllipseExperimentRegion(scaling, stagePositionLeftTop, blockIndex, centerX, centerY, radiusX, radiusY, color, forAcquisition, forBleaching, forAnalysis)` |
| `AddPolygonExperimentRegion(scaling, stagePositionLeftTop, blockIndex, polygonPoints, color, forAcquisition, forBleaching, forAnalysis)` |
| `AddExperimentMarkerPosition(scaling, stagePositionLeftTop, blockIndex, x, y, color, forBleaching)` |

`stagePositionLeftTop` comes from `experiment.GetStageTopLeftOfImage(scaling, image)`, and `color`
is a `System.Windows.Media.Color`, not a `ZenColor`.

**Reading back and editing:**

| Call | Note |
|---|---|
| `GetTileRegionInfos(blockIndex)` | `IList<ZenTileRegionInfo>` |
| `GetSinglePositionInfos(blockIndex)` | `IList<ZenSinglePositionInfo>` |
| `IsTilesExperiment(blockIndex)` | |
| `ModifyTileRegionsSize(blockIndex, newWidth, newHeight)` | |
| `ModifyTileRegionsZ(blockIndex, newZ)` | |
| `ModifyTileRegionsWithXYZOffset(blockIndex, offsetX, offsetY, offsetZ)` | |
| `SetPositionRegionsRelativeToImage(blockIndex, relativeToImage)` | |
| `DistributeSupportPointsToAllTileRegionsGeneric(blockIndex, columns, rows)` | focus support points |
| `DistributeSupportPointsToAllTileRegionsOnionSkin(blockIndex, density, margin, maxNumberOfPoints)` | |
| `GetDetectorSettings(blockIndex)` / `SetDetectorSettings(blockIndex, hardwareSetting)` | a `ZenHardwareSetting` |

`ZenTileRegionInfo` and `ZenSinglePositionInfo` are past the dump's walk depth, so their members are
not captured here. Inspect one with `dir()` the first time you use them.
