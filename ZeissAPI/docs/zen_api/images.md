# ZenImage — the image object

Everything `Zen.Acquisition` returns, everything `Zen.Processing` takes and returns, and everything
`Zen.Analyzing` measures is a `ZenImage`.

## Properties

| Member | Type | Note |
|---|---|---|
| `Bounds` | `ZenBounds` | the dimensions — see below |
| `Metadata` | `ZenImageMetadata` | scaling, stage position, channel info |
| `Scaling` | `ZenScaling` | `.X`, `.Y`, `.Z` in micrometres per pixel |
| `Title` | `str` | shown in the GUI tab |
| `Comment`, `Description`, `Keywords`, `Rating` | | free-text annotation stored in the `.czi` |
| `DisplaySetting` | `ZenDisplaySetting` | contrast/LUT, display only — never changes pixels |
| `Graphics` | `ZenGraphics` | overlay shapes |
| `GraphicLayers` | `ZenGraphicLayers` | the layers those shapes live on |
| `ImageAttachements` | | attached label/overview images (spelling is Zeiss's) |
| `HasPyramid` | `bool` | |
| `Core` | `ImageDocument` | the internal object |

`ZenImage` is a `ZenDocumentBase`, so `Save`, `SaveAs`, `Close`, `SetActive`, `Rename` and
`IsModified` work as described in the [README](README.md#rules-that-hold-across-the-whole-api).

## Dimensions — ZenBounds

A `.czi` is up to eleven-dimensional. `image.Bounds` gives `Start*` and `Size*` for each:

| Letter | Meaning |
|---|---|
| `X`, `Y`, `Z` | pixels, pixels, focus planes |
| `C` | channel |
| `T` | time point |
| `S` | scene |
| `M` | tile within a mosaic |
| `R` | region |
| `B` | block |
| `H` | phase |
| `I` | illumination |
| `V` | view |

So `image.Bounds.SizeX`, `image.Bounds.StartZ`, and so on. Convenience flags save the arithmetic:
`IsTiles`, `IsZStack`, `IsTimeLapse`, `IsMultiChannel`, `IsMultiScene`, plus `Dimensionality` and a
human-readable `InfoText`.

A macro that assumes a single plane should check rather than hope:

```python
if image.Bounds.IsZStack:
    log("z-stack with {} planes".format(image.Bounds.SizeZ))
```

## Subsets

A subset string selects part of the hyperstack, e.g. `"C(1)|Z(3)"` or `"T(1-10)"`.

```python
plane = image.CreateSubImage("C(1)|Z(3)")
```

`CreateSubImage(subsetString[, keepTiles])` returns a new `ZenImage`; the original is untouched, and
the copy has to be closed too. The syntax is easy to get subtly wrong, so rather than composing it by
hand, make the selection once in the GUI and ask ZEN what it was:

```python
subset_string = Zen.Processing.Utilities.GetSubsetString(sub_image)
```

`Zen.Processing.Utilities.CreateSubset(...)` and `CreateSubsetAndSplit(...)` do the same job from the
processing side — see [processing.md](processing.md).

## Metadata

`image.Metadata` is where acquisition facts live. The ones that matter for closed-loop work:

| Member | Note |
|---|---|
| `ScalingMicron` | `ZenScaling`, **micrometres** per pixel |
| `StagePositionMicron` | stage position of the image |
| `FocusPositionMicron` | z |
| `AcquisitionDateTime` | |
| `GetChannelName(i)`, `GetChannelColor(i)`, `GetChannelDyeName(i)` | |
| `GetChannelExposureTime(i)` | |
| `GetChannelSectionThickness(i)`, `GetChannelDepthOfFocus(i)` | confocal |
| `GetMetadataWithPath(path)` / `GetMetadataStringWithPath(path)` | arbitrary XML node by path |
| `Xml` | the whole metadata XML as a string |
| `SaveAsXml(fileName)` | |

**Units, again.** `ScalingMicron` is micrometres per pixel. The raw `.czi` XML that World B parses
stores the same quantity in **metres** — that is the reason for the `* 1e6` factors in
`data_processing/`. When a number is off by exactly a million, this is why.

`GetMetadataWithPath` is the escape hatch for anything Zeiss did not expose as a property. Find the
path by dumping `image.Metadata.Xml` once and reading it.

## Pixels

| Call | Returns | Note |
|---|---|---|
| `CopyPixelsToArray(pixelType)` | `Array[Byte]` | the whole image, as raw bytes |
| `CopyPixelsToArray(subsetString, pixelType)` | `Array[Byte]` | a subset; the string format is not verified yet |
| `CopyPixelsFromArray(array)` | | and back in |

**There is no overload without arguments**, whatever the dump's member list suggests: it raises
`CopyPixelsToArray() takes at least 1 argument`, and handing it a preallocated array raises
`expected ZenPixelType`. The overloads above are the method's own `__doc__`, read on the instrument
(ZEN 3.28). `pixelType` is a `ZenPixelType`: `Gray8`, `Gray16`, `Gray32Float`, `Gray64ComplexFloat`,
`Bgr24`, `Bgr48`, `Bgr96Float`, `Bgra32`, `Bgr192ComplexFloat`.

The bytes are raw. For `Gray16` every pixel is two of them, **low byte first**, so a 1633 x 1633
LSM frame comes back as 5 333 378 bytes:

```python
image = Zen.Acquisition.AcquireImage(experiment)
data = image.CopyPixelsToArray(ZenPixelType.Gray16)
image.Close()

# every 16th pixel is plenty for a median; the loop is IronPython and not fast
values = sorted(data[i] + 256 * data[i + 1] for i in xrange(0, data.Length - 1, 2 * 16))
median = values[len(values) // 2]
p99 = values[int(len(values) * 0.99)]
```

Measured on a 1633 x 1633 frame: copy, decode and sort of every 16th pixel take **0.3 s**, so a
median per field of view costs nothing next to the acquisition. The image never has to be saved or
looked at - it is read straight from memory and closed. `adaptive/smart_SLB_imaging.py` chooses the
laser power this way.

For anything beyond a few statistics the pixels still go to World B through the `.czi` file, which
gives numpy - see the contract section of the project `CLAUDE.md`.

## Saving and closing

```python
image.Save(saving_path)
image.Close()
```

| Call | Note |
|---|---|
| `Save(fileName)` / `Save()` | `.czi` |
| `SaveWithOptions(fileName, ZenImageSavingOptions)` | compression, 8-bit conversion, display mappings |
| `Close()` | frees the memory |
| `Close(deleteFile)` | `True` also deletes what was saved |

Closing is not optional in a long run. Every acquired and every derived image stays in memory until
closed, and processing functions return *new* images — a per-field pipeline of four steps leaks four
images per field unless each is closed.

For exporting to formats other than `.czi` (TIFF, OME-TIFF, movies), use
`Zen.Processing.Utilities.ExportSingleFile` / `ExportOmeTiff` / `ExportMovie`.

## Building images up

| Call | Note |
|---|---|
| `AddChannel(...)`, `AddScene(...)`, `AddSubset(...)`, `AddSubImage(...)` | assemble a multi-dimensional image |
| `MakeSpace(...)` | reserve dimensions before filling them |
| `Clone()` | |
| `SetChannelName(i, name)`, `SetChannelColor(i, color)` | |
| `SetDisplaySetting(setting)` | |
| `CopyRois(source)` | carry analysis ROIs across |
| `AddCustomAttachment(...)` | |
| `AttachImageLabel(...)` | |
| `BurnInGraphics()` | render the overlay into the pixels — destructive |
| `InsertDefaultScaleBarGraphic()` | |

`BurnInGraphics` is the one to be careful with: it is how you get an annotated export, and it is also
how you permanently damage measurement data. Burn in on a clone, not on the original.

## Graphics overlay

Shapes drawn on an image without touching its pixels. Useful for marking detected objects inside ZEN
— this project draws its overlay in World B with matplotlib instead, but if the mark has to appear in
the ZEN document, this is the route.

`image.Graphics`:

| Member | Note |
|---|---|
| `Add(ZenGraphicCategory)` | returns the new `ZenGraphic` |
| `GetById(id)`, `GetFirstByName(name)`, `Count`, `[i]` | |
| `Merge(...)`, `Load(...)`, `SaveAs(...)` | overlays are separately storable |
| `ShowGrid` | |

`ZenGraphic`:

| Member | Note |
|---|---|
| `SetBounds(left, top, width, height)` | |
| `SetActualSubsetBounds(...)` | which plane/channel the shape belongs to |
| `FillColor`, `StrokeColor`, `TextColor`, `Thickness`, `FontSize`, `RotationAngle` | |

Categories come from the `ZenGraphicCategory` enum (rectangle, ellipse, line, polygon, text, and so
on); enumerate it with `dir(ZenGraphicCategory)` rather than guessing a member name. Colours are
`ZenColor.FromRgb(r, g, b)` or `ZenColor.FromName("Red")` — note that the *experiment region*
extension methods in [acquisition.md](acquisition.md) want a `System.Windows.Media.Color` instead,
which is an easy mix-up.

`ZenScaleBarGraphic` is the specialised one behind `InsertDefaultScaleBarGraphic`.

`image.GraphicLayers` groups shapes into layers that can be shown and hidden together.
