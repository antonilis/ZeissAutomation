# Coding style

Descriptive, not aspirational: this documents how the existing code is written, so that
new code reads like the code around it. Every example below is taken from this
repository. When a rule here conflicts with a file you are editing, the file wins —
match its neighbourhood rather than reformatting it.

---

## 1. Which dialect am I writing?

Decide this first, from the file's directory:

| Directory | Dialect |
|---|---|
| `ZeissAPI/` | IronPython 2.7 + .NET, runs inside ZEN |
| everything else | CPython 3 in a venv |

Getting this wrong produces code that imports cleanly on your machine and fails at
runtime on the microscope PC, which is the worst possible failure mode here.

---

## 2. `ZeissAPI/` — IronPython dialect

### Forbidden

- f-strings — Python 2.7 syntax error
- `pathlib`
- `os.path` — use `System.IO.Path` instead
- type hints
- any pip package (numpy, pandas, cv2 …); only the stdlib and .NET are available
- dict/set comprehension features from Python 3, `nonlocal`, keyword-only args

### String formatting

Always `.format()`, positional, no index numbers:

```python
log("Loaded experiment {}".format(chosen_experiment))
log("Found {} RAW with this UUID.".format(len(matching_raws)))
final_name = "{}_{}{}".format(base_name, "_".join(parts[1:]), extenion)
```

### Paths and files

Through `System.IO`, never `os`:

```python
from System.IO import Directory, Path, File

folder = Path.Combine(base, "obj_{}".format(obj_id))

if not Directory.Exists(folder):
    Directory.CreateDirectory(folder)
```

Raw strings for Windows literals: `CONFIG_PATH = r".\config\path_config.json"`.

### Logging

There is exactly one `log()` on the ZEN side, in `runtime_config.py`. Import it:

```python
from zen_lib.runtime_config import log
```

Do not define a second one, and do not use `print` (invisible inside ZEN) or `logging`.
Its destination comes from the `log_path` key of `path_config.json` and is set when
`RuntimeConfig` is built. Everything logged before that — and everything logged when the
config does not name a `log_path` — goes to `zen_log.txt` next to the macros.

This is the one fallback in the project that is deliberately silent, and the reason is
worth knowing: the log is where a broken configuration reports itself, so it has to work
when nothing else does. It is also only a text file, so guessing wrong is cheap. Every
other setting uses `self.config["key"]` and fails loudly. Do not treat this as licence to
add fallbacks elsewhere.

Log at pipeline milestones and around every subprocess or hardware call — this file is
the only debugging channel once a run is unattended.

### Configuration

Nothing except `runtime_config.py` locates the config folder. A class that needs paths
takes the already-built `RuntimeConfig` as its first constructor argument and reads
attributes off it:

```python
class PathManager:
    """
    param RuntimeConfig config: configuration built by the macro, this class does not read it from disk itself
    """

    def __init__(self, config):

        self.config = config
        self.results = config.results
```

New path? Add a key to `path_config.example.json` (the template; the live `path_config.json` is git-ignored) and an attribute to `RuntimeConfig`. Never
`open()` a config file a second time, never write an absolute `D:\...` literal, and never
resolve a fallback path when the caller was supposed to supply one — fail loudly instead.

### Where new code goes

- A new `Zen.*` API call → a new `@staticmethod` on `ZeissApiProcessor`. Do not call
  `Zen.` directly from `AcquisitionPipeline`.
- A new output filename or directory → a new method on `PathManager`. Never build a
  path inline in the pipeline.
- Pipeline logic → a method on `AcquisitionPipeline`, private ones prefixed `_`.

### `.czmac` files are XML

The Python source lives inside `<Text>` … `</Text>` in an XML document. Consequences:

- `<`, `>` and `&` in the code must be escaped. There is a real example in
  `find_overview_positions.czmac`: the comment `"A1" -&gt; ('A', 1)`.
- Do not add an XML declaration, change `<Context>Zen26</Context>`, or reindent the
  XML shell.
- Keep the trailing `<Author>`/`<Row>`/`<Column>` block untouched.

### Section banners

Long macros are divided by banner comments. Two forms are in use; either is fine, but
be consistent within a file.

```python
###################### class for API calls ###########################################################

# ==============================================================================
# PIPELINE CLASS
# ==============================================================================
```

Inside long methods, numbered step markers:

```python
# --- 1 Do object visualization experiment, which results are used for xy-reanalysis ---
# --- 2 Reanalysis ---
```

---

## 3. `DecisionEngine/` — CPython dialect

### Imports

Absolute, rooted at `DecisionEngine/`. `execute_python.py` sets `PYTHONPATH` to that folder
(`python_project_root`), so this works both under the runner and when running a module by hand from it.

```python
import numpy as np

from IO.read_czi_file import CziFileReader
from data_processing.image_analysis.base_image_analyzer import ImageAnalysisTemplate
from data_processing.image_analysis.analysis_registry import register_class
from data_processing.image_analysis.pixel_stage_converter import z_normal
```

Order: stdlib, then third-party, then project-local. Never relative (`from .x import y`).

### Progress output

`print()`, in bracketed or plain form. The runner captures stdout and writes it to the
ZEN log, so prints are the World B equivalent of `log()`. No `logging` module anywhere
in this project.

```python
print("[INFO] Parsed arguments: {}".format(command_args))
print("Analyzing FCS")
print("Saved measurement points to:", saving_path)
```

f-strings are acceptable here and appear in a few places, but `.format()` and
comma-separated `print` are the majority. Prefer whichever the file already uses.

### Docstrings

reST field style. Class docstrings say what the class does *in the pipeline*, not just
what it is. Short helpers may document only `:return:`.

```python
class ZeissImageProcessor:
    """
    Processes Zeiss .czi files, by reading them, calling for the segmentation algorithm
    from image_analysis and saving the results as JSON files.
    """

    def save_measurement_points(self, filename):
        """
        Function responsible for saving the positions and properties of the found objects
        in the stage coordinates in the JSON file.
        :param filename: saving path of the JSON file
        :return: None
        """
```

No type hints, in either world.

### Selective kwargs forwarding

The recurring idiom for passing a config preset into an algorithm — the preset dict may
carry extra keys, so filter rather than `**self.analysis_details`:

```python
objects_df = self.image_segmentation(**{k: v for k, v in self.analysis_details.items() if
                                        k in ["objects_diameter", "circ_thr", "ecc_thr", "sol_thr"]})
```

### Analyser contract

```python
@register_class
class MyAlgorithm(ImageAnalysisTemplate):
    """
    One or two sentences: what it detects and by what method.
    """

    def get_measurement_points(self):
        """
        :return: lists of dictionaries with the founded objects properties and their positions
                 in the pixels coordinates and in the stage coordinates in um
        """
        measurement_points = [...]                    # pixel coordinates
        transformed_points = self.pixel_converter.convert_points(
            measurement_points, xy_mode='normal', z_strategy=z_normal)

        return measurement_points, transformed_points
```

Order matters: **pixels first, stage second**. `ZeissImageProcessor` swaps them on the
way out (`self.measurement_points` is the stage-coordinate list, `not_scaled_points` is
the pixel list).

### `__main__` blocks

Several modules end with a hand-run smoke test using hardcoded relative paths:

```python
if __name__ == '__main__':
    main_path = '../../Snap-10242.czi'
    ...
```

These are the project's testing method. Do not delete them, do not convert them into a
test framework unless asked, and do not "fix" their paths.

---

## 4. Formatting, both worlds

- 4 spaces, no tabs. Lines run long (up to ~120); do not reflow existing lines.
- Two blank lines between top-level definitions. Inside classes the spacing is uneven
  (one or two lines between methods) — match the file, do not normalise it.
- **Blank lines inside function bodies separate logical steps.** This is the most
  visible habit in this codebase and new code should keep it:

```python
    best_file, max_intensity = self.find_highest_intensity_file()

    pattern = r"P(\d+)"

    match = re.search(pattern, best_file)
    if match:
        p_tag = match.group()
    else:
        raise ValueError('Could not find the FCS_points.json file')

    positions = self.FCS_measurements_points[p_tag]
```

- Quotes are mixed (`'` and `"`); follow the file.
- Comments and docstrings are in **English**, sentence case, usually without a trailing
  period. A few Polish comments survive in older files — do not translate them as a
  side effect of another change, and write new ones in English.

---

## 5. Naming

- Classes: CapWords for new code. Existing exceptions (`Cellpose_algorithm`,
  `Max_intensity_Z_Scan`) are **frozen** — they are values in
  `processing_config.json`. See `CLAUDE.md`, "Do not rename these".
- Functions, methods, variables, JSON keys: `snake_case`.
- Private methods: leading underscore (`_run_experiment`, `_extract_scaling`).
- Config keys are terse and uppercase-ish shorthand (`FLGUV`, `TLGUV`,
  `z_image_analysis`); follow that when adding presets.
- Units belong in the name when a value carries one: `min_size_um`, `radius_um`,
  `scaling_um_per_pixel`, `objects_diameter`.

---

## 6. Error handling

Defensive and non-fatal by default: the pipeline runs unattended, so a single bad
object should not abort a plate. Log or print, then continue.

```python
        for raw_path in self.raw_files:
            try:
                ph_data = read_confo_cor3(raw_path)
                ...
            except Exception as e:
                print("Error reading file:", raw_path, ":", str(e))
```

Raise only where continuing would be meaningless or unsafe:

```python
raise ValueError("XY mode must be 'normal' or 'center'.")
raise ValueError("Unknown reanalysis type: {}".format(reanalysis_type))
raise ValueError("Missing '{}' in manual_points".format(r))
```

Never swallow an exception silently, and never let a failed analysis fall through to a
stage move — a wrong coordinate is worse than a skipped object.

---

## 7. Configuration

New tunable numbers go into `ZeissAPI/config/processing_config.json` as part of a
named preset, not into a function default. Presets are flat and small:

```json
{"FLGUV": {"analysis_channel": 0, "chosen_analysis": "Circles",
           "min_size_um": 2.5, "max_size_um": 60}}
```

Machine-specific absolute paths belong in `path_config.json` (template: `path_config.example.json`) and nowhere else. If you
find a hardcoded `D:\...` outside that file, it is a bug worth reporting rather than
copying.
