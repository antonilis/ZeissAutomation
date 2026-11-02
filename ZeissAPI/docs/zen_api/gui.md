# Zen.Windows and Zen.Application — dialogs, files, macros

## Building a dialog

`Zen.Windows.CreateWindow()` returns a `ZenWindow`. Add controls, call `Show()`, read the answers out
of the `ZenResult`.

```python
window = Zen.Windows.CreateWindow()
window.AddLabel("Choose the analysis preset")
window.AddDropDown("preset", "Preset", presets, 0)
window.AddCheckbox("find_objects", "Find objects", True)

result = window.Show()

if result.HasCanceled:
    raise Exception("cancelled by the user")

preset = result.GetValue("preset")
```

`HasCanceled` is the first thing to check every time. Skipping it means the macro runs with default
values after the user pressed Cancel, which in an acquisition macro means the stage moves.

### Controls

| Call | Note |
|---|---|
| `AddLabel(text)` | |
| `AddTextBlock(text)` | multi-line static text |
| `AddTextBox(id, label, value)` | |
| `AddMultiLineTextBox(id, label, value)` | |
| `AddCheckbox(id, label, value)` | |
| `AddDropDown(id, label, items, selectedIndex)` | `items` is a list of strings |
| `AddIntegerRange(id, label, value, min, max)` | |
| `AddDoubleRange(id, label, value, min, max)` | |
| `AddFolderBrowser(id, label, path)` | |
| `AddImage2dView(id, image)` | show an image inside the dialog |
| `AddDimension(...)` | a dimension selector |
| `ClearContent()`, `RemoveContent(id)` | rebuild a dialog between shows |
| `SetFocus(id)` | |

The first argument is always the **id** used to read the value back; the second is the visible label.
Getting them the wrong way round produces a dialog that looks right and returns nothing under the
name you expect.

`ZenResult` has `HasCanceled`, `GetValue(id)` and `Contains(id)`. `Contains` matters when the dialog
was built conditionally — asking for a control that was never added throws.

Dropdown values come back as the **string that was displayed**, not the index. That is why the
macros in this project map a display name back to a key rather than to a position.

### One-shot dialogs

For a single question there is no need to build a window:

| Call | Note |
|---|---|
| `Zen.Windows.ShowTextBox(text[, title])` | |
| `Zen.Windows.ShowDropDown(items[, title])` | |
| `Zen.Windows.ShowImage2d(image)` | |
| `Zen.Windows.Show(window)` | equivalent to `window.Show()` |

## Zen.Application

`Zen.Application` is a `ZenBlueApplication` — documents, folders, and control of ZEN itself.

| Member | Note |
|---|---|
| `Documents` | the open document collection: `Count`, `[i]`, `GetByName`, `Add`, `Remove`, `RemoveAll` |
| `ActiveDocument` | |
| `LoadImage(fileName[, addToDocuments])` | → `ZenImage` |
| `Save(document)`, `SaveAs(...)` | |
| `RunMacro(name)` | chain macros |
| `Pause(message)` | shows a message and waits for the user — **blocks** |
| `Wait(milliseconds)` | |
| `ProgressInfo(...)` | progress bar for a long macro |
| `ShowWindow(...)`, `ShowWizard(...)` | |
| `ReadDirectoryPath(...)` | folder picker |
| `LeftToolArea` | the tool panel; `ZenToolTab` selects a tab |
| `Environment` | below |

### Folders

```python
documents = Zen.Application.Environment.GetFolderPath(ZenSpecialFolder.UserDocuments)
```

`ZenSpecialFolder` names ZEN's configured locations — user documents, images, experiments, analysis
settings, and so on. Enumerate the enum with `dir(ZenSpecialFolder)` on the machine rather than
assuming a member name, since the set differs slightly between versions.

This is the ZEN-blessed way to find a folder, but note that **this project does not use it**: all
result paths come from `ZeissAPI/config/path_config.json` through `RuntimeConfig`, so that the same
macro runs on a machine with different drive letters. Do not reintroduce a `GetFolderPath` call to
locate something the config already knows about.

### Blocking calls

`Pause`, `AnalyzeInteractive`, any processing call with `interactive=True`, and `Close(True)` all wait
for a human. In an overnight acquisition each of them is a stall that ends the run without an error
message. The rule of thumb: if a call can put a window on screen, it does not belong in the part of a
macro that runs unattended.

## Logging, not printing

In World A, `print` output goes to ZEN's macro console, which is not open during an unattended run
and is not saved. Use the project's own logger instead:

```python
from zen_lib.runtime_config import log

log("acquired {}".format(name))
```

`log()` writes to the file named by the `log_path` key of `path_config.json`, falling back to
`zen_log.txt` next to the macros. Never define a second `log()`; see the project `CLAUDE.md`.
