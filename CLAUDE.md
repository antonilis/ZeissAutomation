# Automated ZEISS acquisition pipeline

Closed-loop microscopy automation: ZEN drives the microscope, a separate Python
process analyses each acquired image and returns coordinates, ZEN moves there and
acquires again. Targets GUVs, fluorescent hexagonal meshes and FCS point measurements.

## The two-runtime rule — read this before touching anything

This repository holds **two programs in two different Python interpreters**. They never
import each other. They communicate only through the filesystem and one subprocess call.

| | World A — ZEN | World B — analysis |
|---|---|---|
| Interpreter | IronPython 2.7 (.NET), inside ZEN | CPython 3 in a venv |
| Code | `ZeissAPI/` | `data_processing/`, `IO/`, `utils.py`, `result_processing/` |
| Marker | `from System.IO import ...`, `Zen.*` | numpy, torch, f-strings, pathlib |
| Entry point | `main_macro.czmac` (run from ZEN's macro editor) | `main_processor.py` (run via CLI) |

**Never add an import that crosses the table.** World A cannot use numpy, pathlib,
f-strings or anything pip-installed. World B cannot use `Zen`, `System.*` or `.czmac`.
If you are unsure which world a file belongs to, check its imports before editing.

## The contract between the two worlds

`ZeissAPI/zen_lib/execute_python.py` starts World B as a subprocess and passes six flags:

```
python.exe main_processor.py --type="..." --file_path="..." --saving_path="..."
                             --analysis_arguments="..." --is_FCS="..."
                             --processing_config="..." --selection_config="..."
                             [--selection_arguments="..."]
```

- `type` — one of `overview`, `reanalysis_xy`, `reanalysis_z`. It selects behaviour on the
  analysis side: `reanalysis_xy` reduces several detections to the one nearest the current
  stage position, and `reanalysis_z` suppresses the PNG overlay.
- `analysis_arguments` — a **key** in `processing_config.json`
- `selection_arguments` — a **key** in `selection_config.json`, naming the optional object
  selection. It is the one flag that may be absent: `_make_args` drops arguments whose value
  is `None`, so choosing "None" in the GUI produces exactly the command line that existed
  before the second stage did, and World B runs no selection.
- `is_FCS` — arrives as the string `"True"` / `"False"`, not a bool
- `processing_config` — full path to `processing_config.json`, added automatically
  by `PythonAnalysisRunner.run()`. **Required**: World B raises if it is missing rather
  than resolving a path itself, so that there is only one source of truth.
- `selection_config` — full path to `selection_config.json`, added the same way. Required
  only when `selection_arguments` is present, so that a hand-run without any selection stays
  as short as it was.

Values are quoted, because result folders are named after the sample and may contain
spaces. `utils.parse_args_to_dict` strips the quotes on the way in.

World B writes a JSON file at `saving_path` and exits. World A reads that file back.
stdout/stderr are logged only, never parsed. **This is the whole interface** — if you
change the flags, the JSON shape, or the config keys, you must change both sides.

JSON shape returned by World B: `{ "<uuid>": { "position": [x, y, z], "selected": true, ... } }`,
where `position` is in stage micrometres and the key is the object's `id`. `selected` is
always written — `true` when no object selection ran — and the macro drives only to the
objects where it is true. `radius`, `intensity`, `source`, `timestamp` and
algorithm-specific fields may also be present.

## Where paths come from

**`path_config.json` is per machine.** The repository holds only its template,
`path_config.example.json`; each microscope PC keeps its own git-ignored copy (made by hand or
by `install.bat`), because the paths differ between machines. A missing `path_config.json` stops
the macro with a message naming the template. A new key goes into the **template** (and into
each local copy). `processing_config.json` and `selection_config.json` are shared and tracked
as they are.

The config folder belongs to the ZEN runtime: it sits in `ZeissAPI/config/`, next to the
macros. `ZeissAPI/zen_lib/runtime_config.py` is the **only** place that knows how to find it — it
resolves `./config/` relative to its own `__file__`, so nothing depends on ZEN's working
directory and no absolute `D:\...` literal appears anywhere in the code.

Each macro builds one `RuntimeConfig()` at the top and passes that object down:
`PathManager`, `PythonAnalysisRunner`, `AcquisitionPipeline` and `AcquisitionGrid` all
take it as their first argument and none of them reads configuration from disk. World B
receives the one path it needs on the command line. `log()` also lives in
`runtime_config`. Its destination is the `log_path` key of `path_config.json`; when that
key is absent — or when something logs before the config has been read — it falls back to
`zen_log.txt` next to the macros, so logging never depends on a hardcoded drive letter
and never fails just because the configuration is broken.

The `adaptive/` folder is found the same way the config folder is — relative to
`runtime_config.__file__`, surfaced as `RuntimeConfig.adaptive_path` — because it is ZEN code
and never leaves World A. It is deliberately not a `path_config.json` key: the plugins have to
sit next to the macro that runs them.

The `last_setup_path` key follows the same rule: `main_macro` writes the settings it was run
with there once the summary has been confirmed, and offers to start from them next time. A
missing key falls back to `last_setup.json` next to the macros, and a failure to write is
logged and ignored, because recording the settings must never cost an acquisition.

If you need a new path, add a key to `path_config.example.json` (and to the local copies) and surface it as an attribute on
`RuntimeConfig`. Do not read the JSON again somewhere else, and do not hardcode a path.

## Layout

- `ZeissAPI/main_macro.czmac` — the acquisition pipeline + its ZEN GUI. The main program.
- `ZeissAPI/find_overview_positions.czmac` — run once beforehand, writes `temp/points_for_overview.json`.
  In manual mode the wells are named by a selection like `A1-C4` or `A1-H1, A4-H4, E5`, parsed by
  `parse_well_list`: comma-separated items, each a single well or a rectangle between two corners.
  A bare `A1-C4` is exactly what the old `start`/`end` fields meant. Every well is placed relative
  to the **first well of the selection**, which is where the stage has to be standing.
  `expand_with_subgrid` then optionally replaces every point with a grid centred on it, which is
  how one gets several fields of view inside a single well. It runs on the output of both modes.

  Point names end up in result folder and file names, and they have to stay unique: within one run
  the overview image and the measurement JSON of two points are told apart by the name alone,
  because `overview_id` is minted once per pipeline. Avoid names matching `P<digits>` — the FCS
  processor searches the whole path for that pattern.
- `ZeissAPI/adaptive/` — adaptive experiment plugins, one function per file (see below).
- `ZeissAPI/zen_lib/` — the ZEN side helper modules, imported by **both** macros as
  `zen_lib.<module>`. They are machinery; `config/` and `adaptive/` stay at the top level
  because they are content, edited by hand. The package resolves because ZEN already has
  `ZeissAPI/` on `sys.path` — that is what made the old flat `from runtime_config import ...`
  work in the first place.

  Both macros drop `zen_lib` from `sys.modules` before importing it. ZEN keeps its Python engine
  alive between runs, so without that an edited helper would keep running its old version until
  ZEN itself was restarted — which is not only slow to work with, it is how a half finished copy
  of the folder ends up looking like a bug in the code. **Nothing in this project now needs a ZEN
  restart**: the macros are read from their XML each run, `RuntimeConfig` re-reads the JSON each
  run, and `zen_lib` and the `adaptive` package are re-imported each run.
- `ZeissAPI/zen_lib/runtime_config.py` — config location, `RuntimeConfig`, and the shared `log()`.
  Note that it now sits one level below the macros, so `macro_directory()` takes the parent of
  its own folder.
- `ZeissAPI/zen_lib/path_manager_main_macro.py` — every result path and filename is built here. Do not build paths inline.
- `ZeissAPI/zen_lib/execute_python.py` — the subprocess bridge.
- `ZeissAPI/config/` — machine paths (`path_config.json`, git-ignored; template `path_config.example.json`), named analysis presets
  (`processing_config.json`) and named object selection presets (`selection_config.json`).
- `data_processing/main_processor.py` — World B entry point.
- `data_processing/image_analysis/` — pluggable analysers, auto-registered (see below).
- `data_processing/object_selection/` — pluggable second stage that rejects found objects,
  same registry pattern.
- `data_processing/image_analysis/pixel_stage_converter.py` — pixels → stage micrometres.
- `IO/` — `.czi` reader (pylibCZIrw + XML metadata) and ConfoCor3 `.raw` reader.
- `result_processing/` — offline post-hoc analysis. Currently broken, see below.

## Adding an image-analysis algorithm

1. New file in `data_processing/image_analysis/`.
2. Subclass `ImageAnalysisTemplate`, decorate with `@register_class`.
3. Implement `get_measurement_points()` returning `(pixel_points, stage_points)` —
   two lists of dicts, each with a `"position"` and an `"id"` from `self.new_object_id()`.
4. Convert with `self.pixel_converter.convert_points(points, xy_mode=..., z_strategy=...)`.
   It deep-copies the dicts and replaces only `position`, so ids and properties come along.
5. Add an entry to `processing_config.json` whose `chosen_analysis` value is the
   **exact class name**. It is then selectable in the ZEN dropdown. No other wiring.

To let the analyser be combined with an object selection, set `provides_object_rois = True`
and implement `get_object_rois()`, returning `{id: {x_start, x_stop, y_start, y_stop, mask}}`
— the filled outline of each object, cropped to its bounding box. `Circles` draws it from
the contour it already has, `Cellpose_algorithm` cuts it out of the labelled image with
`labels_image == label`. Analysers that only produce coordinates, like `HexagonalMesh` and
`Max_intensity_Z_Scan`, leave the flag at `False`; combining one with a selection is refused
before the file is even opened.

Positions are `[x, y]` where `x` is a **column**, while numpy is indexed `[row, column]`.
Getting this backwards measures a different part of the image and reports no error.

`data_processing/image_analysis/__init__.py` imports the package tree automatically,
so registration happens on import — nothing to add to a list.

## Adding an adaptive experiment

An adaptive experiment is a function that rewrites a ZEN experiment just before it runs, using
the properties of the object it is about to run on — `fcs_zscan` centres an FCS z-scan on the
top of a GUV, using the radius the analysis measured.

1. New file in `ZeissAPI/adaptive/`, one function per file.
2. Decorate it with `@register_adaptive`, imported from `zen_lib.adaptive_loader`. The function's
   own name is what the ZEN dropdown offers, the same way a class name is on the analysis side.
3. The function takes one argument, an `AdaptiveContext`: `ctx.zen_api`, `ctx.experiment` (the
   name of the experiment about to run), `ctx.obj`, `ctx.obj_id`, `ctx.stage`, `ctx.name` and
   `ctx.result_dir()` for the plugin's own files. **`ctx.obj` is `None` whenever object finding is
   switched off** — there is no object then, the macro is only visiting overview points — so a
   plugin must handle both. `fcs_zscan` falls back to a radius of zero and centres its scan on the
   current focus. Keywords after `ctx` are for other plugins only: `smart_SLB_imaging` imports
   `smart_focus` and calls it with `use_surface=True`.

**A plugin is an ordinary module and touches the microscope only through `ctx.zen_api`.** It
never calls `Zen` — it could not, an imported module does not see the names ZEN injects into a
macro — and it never calls an experiment editing method itself. When a plugin needs a ZEN call
that `ZenApi` does not have yet, add a method to `ZenApi` rather than reaching around it.

**This is how adaptive experiments are developed: grow `ZenApi`, then compose.** A new adaptive
experiment should be mostly a combination of existing `ZenApi` methods — `smart_SLB_imaging` is
`find_surface` + `autofocus` + `set_laser_power` + `frame_statistics` with a few lines of
arithmetic between them. When a new idea needs something the microscope can do but `ZenApi` cannot
yet, the work is in two steps:

1. Add **one small method per ZEN operation** to `ZenApi` — one call, or one tightly bound group
   such as clear-then-add positions — named after what it does to the microscope, not after the
   plugin that first needed it. Verify it on the instrument once (a probe, or the first run that
   uses it) and say in its docstring what was measured. An unverified call does not go into
   `ZenApi`.
2. Write the plugin as a composition of those methods plus the decision logic, which is the only
   thing that is new.

The payoff is that a verified method is reused by every later plugin without another trip to the
microscope, and the internal `.Core` paths that ZEN can change in an update sit in one file.

That last rule is load-bearing, because **the experiment editing API is .NET extension methods.**
`ClearExperimentRegionsAndPositions`, `ClearTileRegionsAndPositions`, `AddSinglePosition`,
`GetTileRegionInfos` and about twenty more are not members of `ZenExperiment` at all: they are
extension methods declared in `Zeiss.Micro.LM.Scripting.ZenExperimentExtensions`. IronPython
surfaces extension methods only in a compilation unit that imported their namespace, and every
`.py` file is its own compilation unit. `zen_api.py` does that import at its top
(`clr.ImportExtensions(Zeiss.Micro.LM.Scripting)`); measured on the instrument, a module sees 71
members on a `ZenExperiment` without it and 95 with it, where the macro sees 96. Keeping every
edit inside `ZenApi` keeps that import in one file.

Things that sound like the cause and are **not**, all tested back when the plugins were `exec`d
into the macro: the namespace the code runs in (a copy versus the macro's real `globals()`), the
code object's `co_filename`, activating the experiment with `SetActive()` first, and `exec` as a
statement versus `execfile`. None of them affects which extensions the compilation unit imported.

`load_adaptive_functions` drops the `adaptive` package from `sys.modules` and imports every file
in the folder, so an edited plugin is what runs, and any state a plugin keeps at module level
starts empty at every macro run. It logs the file each plugin
was loaded from and warns if that is not `RuntimeConfig.adaptive_path`. A file that raises while
being imported is logged and skipped — one broken plugin must not stop an acquisition that does
not use it; a plugin that imports a broken one fails with it. Files whose name starts with an
underscore, `__init__.py` included, are treated as helpers and skipped.

A run can pair **several** functions with several experiments. A checkbox in window 2 (default
off) decides whether the pairing window appears at all, so a run without adaptive experiments
costs no extra clicks. That window works like the post-analysis one — two dropdowns plus
Add another / Done / Clear all — and it comes **after** the post-analysis window on purpose: its
"Applies to" list offers only the experiments this run will actually execute, because pairing a
function with an experiment that never runs does nothing and reports nothing.

`AcquisitionPipeline` takes `adaptive_experiments`, a dict of experiment name to function. It is
keyed by the experiment because two functions rewriting one experiment would fight over it and
the second would quietly win; `build_adaptive_experiments` refuses that pairing by name. The
saved setup stores `adaptive_pairs`, a list of `[function name, experiment name]` — **names,
never functions**.

## Adding an object-selection algorithm

The second stage. It runs after an analyser has found the objects and decides which of
them are worth driving to. It is deliberately symmetric to the first stage:

1. New file in `data_processing/object_selection/`.
2. Subclass `ObjectSelectionTemplate`, decorate with `@register_class` (the one from
   `object_selection.selection_registry`, not the analysis one).
3. Implement `get_kept_ids()` — no arguments — returning the ids of the objects to keep.
4. If it needs a channel the objects were not detected on, override the classmethod
   `required_channels(**selection_details)`. The `.czi` is read in a single pass and
   closed, so the list must be known before the file is opened.
5. Add a preset to `selection_config.json`. It is **flat**, exactly like an analysis preset:
   `chosen_selection` is the **exact class name** and every other key is handed to the class
   as one of its `selection_details`. The preset is then selectable in the ZEN dropdown.

The two stages are configured independently, in two files, and are chosen from two dropdowns.
An analysis preset does not name a selection and never did after this split; combining them is
the user's choice at run time. Choosing "None" means no selection runs, and then nothing about
the analysis side differs from a run made before the second stage existed. A `selection_config.json`
that is missing altogether is not an error either — `RuntimeConfig.selection_config()` logs it and
returns `{}`, so the dropdown offers "None" alone.

**A selection sees pixels and nothing else.** `self.values_of(object_id, channel)` returns
a 1D array of the pixels inside that object, on that channel. No metadata, no scaling, no
image coordinates — all of that stays on the analysis side, where the pixel converter
already lives. This is the whole reason the ROI is built by the analyser.

`values_of` is boolean indexing, not a multiplication by the mask. Multiplying would turn
the background inside the bounding box into zeros and drag every statistic towards zero by
however much of the box that object happens not to fill — 28% for a circle, and a
different figure for every shape.

**Nothing is deleted.** A rejected object stays in the results with whatever was measured
on it, and only its `selected` flag turns false. `capture_objects` skips it, the PNG
overlay draws it as a red cross, and the record still shows what was found.

## Object identity

Every analyser gives each object an `id` from `ImageAnalysisTemplate.new_object_id()` at
the moment it is created. That same id keys the ROIs, is what a selection returns from
`get_kept_ids()`, and becomes the object's key in the saved JSON. Nothing anywhere matches
objects up by their position in a list — `ZeissImageProcessor` keeps the pixel and stage
lists separately and copies properties between them by id.

An analyser that returns a point without an `id` is rejected immediately, with a message
naming the class.

## Do not rename these

Analyser class names are a public contract: they appear as `chosen_analysis` values in
`processing_config.json` and, indirectly, in the ZEN GUI dropdown. `Cellpose_algorithm`
and `Max_intensity_Z_Scan` do not follow CapWords, and that is fine — renaming them
silently breaks saved configurations. The same applies to JSON keys and to the CLI flag
names in `execute_python.py`.

## Coordinates and units — the easy way to break a microscope

- `.czi` metadata scaling is in **metres per pixel** despite the key being named
  `scaling_um_per_pixel`. Hence the `* 1e6` / `* 10 ** (6)` factors everywhere.
- Stage coordinates are in **micrometres**. Object radii are in micrometres.
- All pixel→stage conversion lives in `PixelStageConverter`. A mistake there sends the
  stage to the wrong place with no error. Treat it as safety-critical: change it only
  when asked, and say explicitly what you changed.

## Known-broken, do not trust

- `result_processing/results_analyzer.py` imports a package that does not exist
  (`data_processing.preprocessors...`) and requests an analyser name that is not
  registered (`FluorescentGUV`). It cannot run. Do not use it as a reference for how
  the rest of the code works.
- `FluorescentGUV` is also the stale default of `ZeissImageProcessor.__init__`.
- `ZeissAPI/zen_lib/path_manager_main_macro.py` starts with a UTF-8 BOM. Harmless at runtime but
  confuses tooling.
- `PixelStageConverter.convert_xy` centres `px[0]` (a column index, so X) on `H/2` and
  `px[1]` on `W/2`. Invisible on square images, an offset of `(W - H) / 2` px on others;
  every image the pipeline has taken so far is square. Pinned down by
  `test_rectangular_image_x_uses_width` (xfail) next to the frozen current behaviour; it
  moves the stage, so fix it only when asked.

## Style

Follow `CODING_STYLE.md`. The short version:

- World A: no f-strings, no pathlib, no os.path — `"{}".format()` and `System.IO`.
  Log with `from runtime_config import log`, never `print`, and never define a second
  `log()`.
- World B: `print()` for progress (the runner captures it), absolute imports from the
  project root, reST docstrings (`:param x:` / `:return:`), no type hints.
- Match the surrounding blank-line rhythm; this code separates logical steps inside
  functions with blank lines and uses `####`/`====` banner comments between sections.
- `if __name__ == '__main__':` blocks are hand-run smoke tests with hardcoded paths.
  They are intentional. Leave them.

## Running

World B, standalone, from the project root (needs no `path_config.json`):

```
python data_processing/main_processor.py --type=overview --file_path=<abs .czi> \
       --saving_path=<abs .json> --analysis_arguments=FLGUV --is_FCS=False \
       --processing_config=ZeissAPI/config/processing_config.json
```

With an object selection, two more flags:

```
       --selection_config=ZeissAPI/config/selection_config.json \
       --selection_arguments=green_membrane
```

World A cannot be run outside ZEN. `.czmac` files are XML wrappers — the Python source
sits inside `<Text>` and must be XML-escaped (`&gt;`, `&lt;`, `&amp;`).

## Tests

```
python3 -m venv .venv
.venv/bin/pip install torch==2.8.0+cpu --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest                                    # everything that needs no data
ZEISS_TEST_DATA=/media/dysk/MPI .venv/bin/python -m pytest    # also the .czi files outside the repo
```

Without cellpose, torch and skimage the analysis tests are skipped, not failed. Cellpose downloads
its model on the first run.

`tests/world_a/` runs ZeissAPI/zen_lib in CPython against fakes of `System.*`, `clr` and `Zeiss.*`
(`tests/support/zen_fakes.py`); `tests/contract/` checks the command line between the worlds and
the two-runtime rule; `tests/world_b/` the analysis side on one real, scrubbed overview image,
`tests/fixtures/guv_overview.czi` (metadata, pixels, the Cellpose preset, `main_processor.py` end to
end; see `tests/fixtures/README.md`). Tests marked `data` read acquisitions that are not in the
repository and run only with `ZEISS_TEST_DATA`. What only ZEN can show — real .NET paths, the real
interpreter — is for the autotest inside ZEN.

Rules:

- Run `pytest` before every commit that changes code.
- Changing an existing test — an assertion, an expected value, removing a test, adding an
  `xfail` — is a commit of its own, with the reason in the commit message. Never in the same
  commit as a change to production code.
- A known bug is an `xfail(strict=True)` whose `reason` names the file, the line and the bug, often
  next to a test freezing the current behaviour. When the xfail starts passing (strict turns that
  into a failure), remove the xfail marker and the frozen counterpart, in a commit of their own.
