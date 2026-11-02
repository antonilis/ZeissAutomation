# Zen.Devices — hardware

`Zen.Devices` is a `ZenDevicesLM`.

| Member | Type |
|---|---|
| `Stage` | `ZenStage` |
| `Focus` | `ZenFocus` |
| `ObjectiveChanger` | `ZenObjectiveChanger` |
| `Optovar` | `ZenOptovarChanger` |
| `Reflector` | `ZenReflectorChanger` |
| `Lamp` | `ZenLamp` |
| `Immersion` | `ZenImmersion` |
| `HardwareSettings` | `ZenHardwareSettings` |
| `IsMicroscopeInitialized` | `bool` |
| `Core` | the internal `IMicroscope` |

| Method | Note |
|---|---|
| `GetLampByName(lampName)` | systems with several lamps |
| `ReadHardwareSetting()` | snapshot of the whole stand → `ZenHardwareSetting` |
| `ApplyHardwareSetting(setting)` | push a snapshot back |

`IsMicroscopeInitialized` is worth checking once at the top of an acquisition macro. On a stand that
has not finished initialising, position reads return values that look plausible and are wrong.

## Stage and focus

Both follow the same two-step pattern, and both also offer a one-shot `MoveTo`:

```python
Zen.Devices.Stage.TargetPositionX = x
Zen.Devices.Stage.TargetPositionY = y
Zen.Devices.Stage.Apply()

Zen.Devices.Focus.TargetPosition = z
Zen.Devices.Focus.Apply()
```

or

```python
Zen.Devices.Stage.MoveTo(x, y)
Zen.Devices.Focus.MoveTo(z)
```

The two-step form lets you stage several changes and commit them together; `MoveTo` is clearer when
there is only one. Whether either blocks until the stage has physically arrived is **not settled by
the dump** — if a subsequent acquisition ever looks smeared, that is the first thing to test.

| `ZenStage` | `ZenFocus` |
|---|---|
| `ActualPositionX`, `ActualPositionY` | `ActualPosition` |
| `TargetPositionX`, `TargetPositionY` | `TargetPosition` |
| `MoveTo(x, y)` | `MoveTo(z)` |
| `Apply()`, `Home()`, `Load()`, `Work()`, `SetZero()` | same |

All values are micrometres. `Actual*` is where the hardware reports it is; `Target*` is where it has
been told to go — after a manual move at the joystick these differ until the next `Apply()`.

`Load()` and `Work()` drive to the configured load and work positions. `SetZero()` redefines the
current position as the origin, which silently invalidates every coordinate recorded earlier —
never call it from a macro that also drives to stored positions.

## Changers (objective, optovar, reflector)

All three derive from `ZenChanger`:

| Member | Note |
|---|---|
| `ActualPosition` / `TargetPosition` | `int`, counted from 1 |
| `ActualPositionName` | e.g. the objective label |
| `ItemsCount` | how many slots |
| `GetNameByPosition(position)` | |
| `Apply()` | commit `TargetPosition` |

`ZenObjectiveChanger` and `ZenOptovarChanger` add:

| Member | Note |
|---|---|
| `Magnification` | of the current position |
| `GetMagnificationByPosition(position)` | without switching to it |

```python
Zen.Devices.ObjectiveChanger.TargetPosition = 3
Zen.Devices.ObjectiveChanger.Apply()
magnification = Zen.Devices.ObjectiveChanger.Magnification
```

Changing an objective changes the pixel size, so anything cached from the previous objective —
a scaling, a pixel-to-stage conversion, an overview ROI in pixels — is stale from that moment.

## Lamp

| Member | Note |
|---|---|
| `ActualIntensity` / `TargetIntensity` | |
| `ActualMode` / `TargetMode` | `ZenLampMode`: `Undefined`, `Manual`, `Set3200K`, `Standby` |
| `Apply()` | |

## Immersion

Automatic water immersion. Blocking and non-blocking variants of each operation:

| Blocking | Fire-and-forget |
|---|---|
| `CreateImmersion()` | `StartCreateImmersion()` |
| `RemoveImmersion()` | `StartRemoveImmersion()` |
| `RenewImmersion([enforce])` | `StartRenewImmersion([enforce])` |

State to check before and after: `IsImmersionAvailable`, `IsImmersionApplied`, `IsImmersionInWork`,
`ImmersionWorkingState` (`ZenImmersionFunktionCompletionStatus`: `Undefined`, `NotAvailable`,
`InWork`, `Created`, `Removed`, `Done`, `Error`, `Cancelled`), `WaterLevelAvailable`,
`WaterLevelForImmersion`, `WaterLevelLowForImmersion`, `WasteWaterLevelAfterImmersion`,
`WasteWaterLevelHighAfterImmersion`, and `LastError`.

Every operation returns `bool`. A long unattended run should check it and `ImmersionWorkingState`
rather than assume the water arrived.

## Camera

`Zen.Acquisition.ActiveCamera` is a `ZenCamera`:

| Member | Note |
|---|---|
| `Name` | |
| `ExposureTime` | |
| `Binning` | `str`, e.g. `"1,1"` |
| `Frame` | `str`, the ROI |
| `GetAllParameterNames()` | `str[]` — the discovery route for everything else |
| `ReadCameraSetting()` | → `ZenCameraSetting` |
| `ApplyCameraSetting(setting)` | |
| `SetDefaultSetting()` | |

`Binning` and `Frame` being strings rather than numbers is a genuine API quirk, not a dump artefact.

### ZenCameraSetting

| Member | Note |
|---|---|
| `GetParameter(name)` / `SetParameter(name, value)` | |
| `GetParameterFromSlaveCamera(name)` / `SetParameterForSlaveCamera(name, value)` | dual-camera systems |
| `HasParameter(name)` | check before reading |
| `Load(fileName[, ZenSettingDirectory])`, `Save()`, `SaveAs(...)`, `Rename(...)`, `Delete()` | |
| `Name`, `FullName`, `IsModified` | |
| `Core` | internal `IInitializationSettings` |

Parameter names are camera-specific; get them from `GetAllParameterNames()` on the camera rather
than hardcoding a list that only works on one stand.

## ZenHardwareSetting

A snapshot of the whole light path — reflectors, filters, lamp, camera — addressed by component id.

| Member | Note |
|---|---|
| `GetAllComponentIds()` | `str[]`, start here |
| `GetAllParameterNames(componentId)` | `str[]` |
| `GetParameter(componentId, parameterName)` | `object` |
| `SetParameter(componentId, parameterName, value)` | overloads for `bool`, `int`, `long`, `float`, `str` |
| `IsActivated(componentId)` | only activated components are applied |
| `SetComponentActive(id)` / `SetComponentInactive(id)` | |
| `SetAllComponentActive()` / `SetAllComponentInactive()` | |
| `Clear()` | |
| `LoadFromImage(image)` | recover the light path an image was taken with |
| `Clone()` | |

The activation flags decide what `ApplyHardwareSetting` actually touches. A setting loaded from a
file usually has everything active; if a macro should change only the reflector, deactivate the rest
first rather than trusting the file.

```python
setting = Zen.Devices.ReadHardwareSetting()

for component_id in setting.GetAllComponentIds():
    log("{}: {}".format(component_id, setting.IsActivated(component_id)))
```

Saved hardware settings live in `Zen.Devices.HardwareSettings` (a collection with `GetByName`,
`GetByFileName`, `Contains`, `Delete`, `ActiveHardwareSetting`).

**Not for the laser power of an LSM experiment.** The stand's setting lists
`MTBLKM980LaserLine639.Intensity` and friends, but an experiment applies its own track's laser
settings when it runs, and `experiment.GetDetectorSettings(0)` contains only `MTBLSMImagingDevice`.
The route that works goes through `experiment.Core` - see
[acquisition.md](acquisition.md#laser-power).
