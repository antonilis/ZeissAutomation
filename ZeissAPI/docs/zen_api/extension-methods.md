# Extension methods — the visibility rule

The most confusing behaviour in the whole ZEN API, and the reason a working call can vanish when you
move the code into a `.py` file.

## The symptom

```python
experiment.ClearExperimentRegionsAndPositions(0)
# AttributeError: 'ZenExperiment' object has no attribute 'ClearExperimentRegionsAndPositions'
```

…in an adaptive plugin under `ZeissAPI/adaptive/`, while the identical line works when pasted into
the `.czmac`. Same object, same type, same ZEN session.

## The cause

`ClearExperimentRegionsAndPositions` is not a member of `ZenExperiment`. It is a **.NET extension
method**: a static method whose first parameter is the type it appears to extend, declared in
`Zeiss.Micro.LM.Scripting.ZenExperimentExtensions`.

IronPython surfaces extension methods only inside a **compilation unit that has imported their
namespace**. ZEN performs that import when it compiles a macro, so macro code sees them. Code
compiled at runtime — an `exec`'d string, an imported module, an `execfile`'d script — gets its own
compilation unit, and therefore does not. A probe on the instrument counted 71 visible members on
the object inside a plugin versus 95 inside the macro.

## The fix

Three lines, in the same compilation unit as the code that uses them — so at the top of the plugin
source, or prepended by the loader before `exec`:

```python
import clr
import Zeiss.Micro.LM.Scripting
clr.ImportExtensions(Zeiss.Micro.LM.Scripting)
```

Confirmed on the instrument. With this in place a plugin in a plain `.py` file works normally; no
build step and no inlining of plugin text into the `.czmac` is needed.

## Explanations that are wrong

Each of these was tested and changed nothing. Do not propose them again:

- handing the plugin the macro's real `globals()` instead of a copy
- the code object's `co_filename`
- activating the experiment with `SetActive()` before rewriting it
- using the `exec` statement rather than the `execfile` builtin

None of them affects which extension methods a compilation unit has imported, which is the only
thing that matters.

## Diagnosing a similar case

If some other member is "only available inside the macro":

1. Run the same few lines in several contexts within one macro — top level, inside a macro function,
   `exec` of a string, `exec` of a string compiled under the macro's own `co_filename`, and
   `execfile` of a real `.py` — and report `len(dir(obj))` for each.
2. If the counts differ, it is an extension-method problem. Find the declaring static class by
   reflecting over `AppDomain.CurrentDomain.GetAssemblies()`, or look it up in the dump: every
   extension method is listed under the type it extends, with its declaring namespace.

Measuring beat three rounds of guessing.

## What lives where

Which namespace to import depends on the feature. Several of these are licensed ZEN modules — if the
import fails, the module is not installed, and that is a clearer error than a missing attribute.

### `Zeiss.Micro.LM.Scripting`

Everything the acquisition macro needs. On **`ZenExperiment`**, from `ZenExperimentExtensions`:

| Method |
|---|
| `ClearExperimentRegionsAndPositions(blockIndex)` |
| `ClearTileRegionsAndPositions(blockIndex)` |
| `AddSinglePosition(blockIndex, x, y, z)` |
| `AddRectangleTileRegion(blockIndex, centerX, centerY, width, height, z)` |
| `AddEllipseTileRegion(blockIndex, centerX, centerY, width, height, z)` |
| `AddPolygonTileRegion(blockIndex, polygonPoints, z)` |
| `AddRectangleExperimentRegion(scaling, stagePositionLeftTop, blockIndex, centerX, centerY, width, height, color, forAcquisition, forBleaching, forAnalysis)` |
| `AddEllipseExperimentRegion(scaling, stagePositionLeftTop, blockIndex, centerX, centerY, radiusX, radiusY, color, forAcquisition, forBleaching, forAnalysis)` |
| `AddPolygonExperimentRegion(scaling, stagePositionLeftTop, blockIndex, polygonPoints, color, forAcquisition, forBleaching, forAnalysis)` |
| `AddExperimentMarkerPosition(scaling, stagePositionLeftTop, blockIndex, x, y, color, forBleaching)` |
| `GetTileRegionInfos(blockIndex)` |
| `GetSinglePositionInfos(blockIndex)` |
| `IsTilesExperiment(blockIndex)` |
| `ModifyTileRegionsSize(blockIndex, newWidth, newHeight)` |
| `ModifyTileRegionsZ(blockIndex, newZ)` |
| `ModifyTileRegionsWithXYZOffset(blockIndex, offsetX, offsetY, offsetZ)` |
| `SetPositionRegionsRelativeToImage(blockIndex, relativeToImage)` |
| `DistributeSupportPointsToAllTileRegionsGeneric(blockIndex, columns, rows)` |
| `DistributeSupportPointsToAllTileRegionsOnionSkin(blockIndex, density, margin, maxNumberOfPoints)` |
| `GetDetectorSettings(blockIndex)` / `SetDetectorSettings(blockIndex, settings)` |
| `GetStageTopLeftOfImage(scaling, image)` |

And from `ZenSoftwareAutofocusExperimentExtensions`: `GetAutofocusParameters([block])`,
`SetAutofocusParameters(...)` — see [acquisition.md](acquisition.md#focus).

### `Zeiss.Micro.Scripting`

| Extends | Method |
|---|---|
| `ZenImage` | `GetPositionLeftTop(image)` → `Point` |
| `ZenTable` | `GetBoundsColumnInfoFromImageAnalysis(singleObjectTable, includeSizeColumns)` |

### Licensed modules

| Namespace | Adds |
|---|---|
| `Zeiss.Micro.Trainable.Scripting` | `Segmentation.TrainableSegmentation(...)`, `…WithConfidenceMap`, `Segmentation.MinimumConfidence`, `ObjectClassification.Classify`, `ImageToImage.Denoise`, `Whitening.NoiseWhitening` (Intellesis) |
| `Zeiss.Micro.Cryo.Processing.Scripting` | `Adjust.EnhanceLocalContrast`, `Adjust.ZStackEqualization`, `Adjust.SlicesReplacement`, `Adjust.SortSmartFibTiffs`, `Filter.Smooth.RemoveStripes`, `Transformation.Geometric.CoarseZStackAlignment`, plus their `*Setting()` factories |
| `Zeiss.Micro.CorrelativeWorkspace.Scripting` | `Utilities.ImportSmartFibTiffs`, `ZenDocumentBase.IsZenConnectImage` |
| `Zeiss.Micro.BioFormatsImport.Scripting` | `Application.GetOmeTiffFile([input, output])` |
| `Zeiss.Micro.AMP.CustomSampleDetectionBase` | `ZenImage.PerformImageAnalysis(iasName, error)` |

Note the pattern in the Cryo and Trainable rows: a licensed module extends the *existing*
`Zen.Processing` tree rather than adding a new root. So `Zen.Processing.Filter.Smooth` genuinely
has more methods on a Cryo-licensed machine than on ours, and the dump reflects whichever machine
produced it.

## Where to put the import in this project

In `ZeissAPI/zen_lib/zen_api.py`, and nowhere else. Every call that edits an experiment is a
`ZenApi` method, and the adaptive plugins under `ZeissAPI/adaptive/` — ordinary imported modules —
call those methods instead of the extension methods themselves. A plugin that needs a new edit gets
a new `ZenApi` method, so the import stays in one compilation unit.

(The plugins used to be read and `exec`'d by the macro, with the import prepended to every plugin
source. That is the history behind the "exec" items in the list above.)
