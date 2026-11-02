# Zen.Analyzing and Zen.Measurement — image analysis inside ZEN

ZEN has its own object-finding and measurement engine. This project does not use it — object finding
lives in World B (`data_processing/image_analysis/`) — but it is worth knowing what is here, because
for a simple threshold-and-measure job it is a lot less machinery, and because `ZenRegion` is the
natural bridge if anything ever needs to come back the other way.

## Zen.Analyzing

`Zen.Analyzing` is a `ZenAnalyzer`. The work is always described by a saved **image analysis
setting** (`.czias`), authored in the ZEN wizard, and the macro just runs it.

| Call | Returns / note |
|---|---|
| `Analyze(image, setting)` | runs the setting on the image |
| `AnalyzeInteractive(image, setting)` | opens the dialog — **blocks** |
| `AnalyzeToImage(image, setting)` | result as an image |
| `AnalyzeToFile(image, setting, fileName)` | result straight to disk |
| `AnalyzeBatch(...)`, `AnalyzeToImageBatch(...)`, `AnalyzeToFileBatch(...)` | over several images |
| `Measure(...)` | measurement without the full analysis setting |
| `Segment(...)` | segmentation stage only |
| `LabelImage(...)` | labelled image of the found objects |
| `DefineRegionsMask(...)` | restrict analysis to a mask |
| `CutOutRegions(...)` | crop each found object out into its own image |
| `GetRegions(image, className)` | → the found objects, as `ZenRegion`s |
| `GetImageAnalysisSetting(name)` | load a `.czias` by name |
| `StartAnalysisSettingWizard()` | opens the GUI editor |
| `ResetAnalysisResult(image)` | clear previous results from the image |
| `ExtractObjectStore(...)` / `ImportObjectStore(...)` | move results between images |

Result tables:

| Call | Note |
|---|---|
| `CreateRegionTable(...)` / `CreateRegionsTable(...)` | single object / all objects |
| `CreateHeatmapTable(...)` | |
| `FillRegionTable(...)` / `FillRegionsTable(...)` / `FillTables(...)` | into an existing `ZenTable` |

```python
setting = Zen.Analyzing.GetImageAnalysisSetting("guv_count.czias")
Zen.Analyzing.Analyze(image, setting)

table = Zen.Analyzing.CreateRegionsTable(image)
table.Save(table_path)
```

`ZenImageAnalysisSetting` is a `ZenCategorisedDocument` (`Load`, `SaveAs`, `SetActive`, …). Its
internal .NET object is exposed as **`.Ias`, not `.Core`** — the one place in the API that breaks the
`.Core` convention.

## ZenRegion

One found object. This is the closest ZEN equivalent of what `ImageAnalysisTemplate` produces in
World B:

| Call | Note |
|---|---|
| `Area()` | |
| `BoundLeft()`, `BoundTop()`, `BoundRight()`, `BoundBottom()` | bounding box |
| `BoundWidth()`, `BoundHeight()` | |
| `GetPolygon()` | outline |
| `GetBoundingPolygon()` | |
| `GetPolygonHighDetails()` | finer outline |

Note they are **methods, not properties** — `region.Area()`, not `region.Area`.

These coordinates are in **pixels**. Driving the stage to an object found this way still needs the
same pixel→stage conversion as everything else, which in this project lives in
`data_processing/image_analysis/pixel_stage_converter.py` and is treated as safety-critical. There is
no ZEN-side shortcut that makes that step unnecessary.

## ZenTable

The result table document. A `ZenCategorisedDocument`, plus row/column access, `GetValue`,
`SetValue`, `Save`/`SaveAs` (CSV and ZEN's own format) and `Core` → `TableDocument`.

One extension method lives here: `ZenTableExtensions.GetBoundsColumnInfoFromImageAnalysis(...)`,
which identifies which columns of an analysis table hold the bounding-box coordinates. Subject to the
import rule in [extension-methods.md](extension-methods.md).

## Zen.Measurement

`Zen.Measurement` is the interactive measurement tool — the one a human uses to draw a line on an
image and read its length. From a macro it mainly offers the **feature sets**
(`ZenFeatureSet`, which features are measured and reported) and measurement sequence settings, both
`ZenCategorisedDocument`s.

For unattended work `Zen.Analyzing` is the right entry point; `Zen.Measurement` is for preparing what
a human will do afterwards.

## When to prefer World B

The split in this project is deliberate: ZEN acquires, CPython analyses. Reasons to keep it that way
even though `Zen.Analyzing` exists —

- the analysers need numpy, torch and cellpose, none of which IronPython 2.7 can load;
- an analysis setting is a binary `.czias` authored in a GUI, which does not diff or review;
- analysis failures must not take the acquisition down with them, and a subprocess boundary gives
  that for free.

`Zen.Analyzing` is the better choice for a quick count on a single image, or when the result has to
appear in the ZEN document for a human to look at.
