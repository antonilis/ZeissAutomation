# Zen.Processing — image processing

`Zen.Processing` is a `ZenProcessingLM`. Every function takes a `ZenImage` and returns a **new**
`ZenImage`; none of them modify the input. That means every step allocates, and every step has to be
closed — see [images.md](images.md#saving-and-closing).

## The call shape

Nearly every function comes in up to four overloads:

```python
f(image)
f(image, interactive)
f(image, setting)
f(image, setting, interactive)
```

**`interactive=True` opens a ZEN dialog and blocks until a human clicks OK.** In an unattended
acquisition that is a hang, not a prompt. Pass `False`, or use an overload without the flag.

The `setting` is an object from the area's `Settings` factory:

```python
setting = Zen.Processing.Filter.Settings.GaussSetting()
setting.AllChannels.SigmaX = 1.5
setting.AllChannels.SigmaY = 1.5

smoothed = Zen.Processing.Filter.Smooth.Gauss(image, setting, False)
```

Per-channel settings expose `AllChannels` (writes to every channel) and `GetChannel(i)`. Every
setting object also has `Load(name[, directory])`, `SaveAs(name[, directory])` and an `XML` property,
so a preset tuned by hand in the ZEN GUI can be loaded by name from a macro — usually a better idea
than encoding a dozen parameters in Python.

`Zen.Processing` itself carries `ResetLastParameters()` and `SaveLastParameters()`, which act on the
"last used" values the GUI remembers, and an `Options` object:

| `Zen.Processing.Options` | Note |
|---|---|
| `AdjustPerChannel` | whether adjustments apply per channel by default |
| `IsImagePyramidEnabled` | pyramids cost time and disk on large tile scans |
| `TryToOverwrite` | overwrite behaviour when a result is saved |

## The families

### Adjust

Intensity and colour, not geometry.

`ShadingCorrection`, `ShadingReferenceFromTileImage`, `BrightnessContrastGamma`,
`BackgroundSubtraction`, `WhiteBalance`, `HistogramEqualization`, `StackCorrection`,
`LinearUnmixingWithDyes`, `LinearUnmixingWithSpectra`.

`StackCorrection` compensates the intensity falloff down a z-stack; `ShadingCorrection` the uneven
illumination across a field, which matters before any intensity-based object selection.

### Filter

Split into `Smooth`, `Sharpen` and `Edges`, with `Settings` alongside.

- `Filter.Smooth` — `Gauss`, `Median`, `Lowpass`, and the rest of the usual kernels
- `Filter.Sharpen` — including `EDF` (extended depth of focus, an `…LM` addition)
- `Filter.Edges` — `Sobel`, `Laplace` and friends
- `Filter.LocalMaxOrMin` — also an `…LM` addition

### Segmentation

`Threshold`, `ThresholdAutomatic`, `ThresholdDynamic`, `RegionGrowing`, `Canny`, `Marr`, `Valleys`.

These produce binary images. For *measuring* objects, `Zen.Analyzing` is the higher-level route —
see [analysis.md](analysis.md).

### Binary

Operations on binary images: `Scrap` (remove objects outside a size range), `Separation` (watershed),
`FillHoles`, `LabelImage`, `MarkRegions`, `Distance`, `Thinning`, `UltimateErode`, `Exoskeleton`,
`ApplyMask`, and the logic operators `And`, `Or`, `Xor`, `Invert`.

`Scrap` followed by `Separation` is the standard clean-up before counting touching objects.

### Morphology

Erode, dilate, open, close, with structuring-element parameters in the settings object.

### Transformation.Geometric

| Function | Note |
|---|---|
| `Stitching` | tile scans |
| `UndoStitching` | back to tiles |
| `ZStackAlignment`, `ChannelAlignment` | registration |
| `SIFTRegistration` | (under `Utilities`) feature-based registration |
| `Resample`, `SampleDown`, `Shrink` | resolution |
| `Rotate`, `Rotate2D`, `Mirror`, `Shift` | |
| `Deskew` | light-sheet geometry |
| `OrthoView` | orthogonal views of a stack |
| `ColorCodedProjection` | depth-coded projection of a z-stack |

**Anything here that resamples or shifts invalidates the pixel↔stage relationship** the rest of this
project depends on. If a processed image is then handed to object finding, the coordinates it
produces refer to the processed geometry, not the acquired one. Convert to stage coordinates from the
original image, or not at all.

### Transformation.Topography

Height-map work on surface data.

### TimeSeries

`Kymograph`, `TimelapseAlignment`, `GlidingAverage`.

### Deconvolution

Its own area with its own settings; expensive.

### Utilities

The odd jobs, and the ones a macro reaches for most often:

| Function | Note |
|---|---|
| `CreateSubset(image, subsetString)` | a slice of the hyperstack |
| `CreateSubsetAndSplit(...)` | several at once |
| `GetSubsetString(subImage)` | the canonical way to obtain a subset string |
| `SplitScenes(image)` | one image per scene |
| `AddChannels(...)`, `CombineRgb(...)`, `SplitRgb(...)` | channel arithmetic |
| `ChangePixelType(image, ZenPixelType.Gray8)` | |
| `ExportSingleFile(...)` | TIFF, JPEG, PNG … |
| `ExportOmeTiff(...)` | |
| `ExportMovie(...)` | |
| `GenerateImagePyramid(...)` | |
| `ImageGenerator(...)` | synthetic test images |
| `MultiBlockTimeStitching(...)` | |
| `SIFTRegistration(...)` | |

### Arithmetics

Per-pixel arithmetic between images and with constants.

## Licensed extras

On a machine with the Cryo or Intellesis licence, several of these areas gain extra methods through
extension methods rather than new objects — `Filter.Smooth.RemoveStripes`,
`Segmentation.TrainableSegmentation` and so on. They are invisible until the declaring namespace is
imported; see [extension-methods.md](extension-methods.md#licensed-modules).

## In this project

The acquisition macro does essentially none of this: pixels leave ZEN as a `.czi` and all analysis
happens in World B with numpy, torch and cellpose. `Zen.Processing` is worth reaching for when
something must happen *before* the file is written — shading correction on the raw frame, a stitch of
a tile overview, an export for a human to look at — and not as a second analysis pipeline alongside
`data_processing/`.
