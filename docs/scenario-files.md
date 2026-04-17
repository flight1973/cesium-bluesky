# Scenario Files

A **scenario** is a plain text file (`.scn`) describing
what should happen in a simulation, over time. It's how
BlueSky reproduces experiments, tests algorithms, and
ships demos. Scenarios are human-readable,
line-oriented, and version-controllable.

## Format

Every line is either a comment or a **time-stamped
command**:

```
# Comments start with a hash
HH:MM:SS.ss>COMMAND arg1 arg2 ...
```

Time format: hours, minutes, seconds, optional
fractional seconds. `0:00:00.00>` means "at
simulation-time zero."

Examples:

```
# demo.scn — two aircraft on converging tracks
00:00:00.00>CRE KL204 B738 52.0 3.0 090 FL300 280
00:00:00.00>CRE BA815 A320 52.0 5.0 270 FL300 280
00:00:00.00>ASAS ON
00:00:00.00>RESO MVP
00:01:30.00>HDG KL204 120
00:05:00.00>HOLD
```

At `simt == 0`, both aircraft are created and ASAS/RESO
are turned on. At 1:30 KL204 gets a new heading. At 5:00
the sim is paused.

## How BlueSky plays scenarios

`IC <filename>` loads a scenario:

1. **Reset the sim** (`RESET` runs implicitly).
2. **Parse the file** into `(time, command_string)` pairs,
   sorted by time.
3. **Schedule** each pair: when the sim clock reaches
   that time, the command string is submitted via
   `bluesky.stack.stack()`.

From then on, the scheduled lines flow through the same
dispatch path as commands from the console or REST. Every
playback command shows up in the `/api/cmdlog` audit feed
just like any other.

## Built-in commands useful in scenarios

Most commands work in scenarios, but a few are
scenario-specific:

- `DT <seconds>` — set the integration step (default
  0.05).
- `FF [seconds]` — fast-forward. With no argument, runs
  as fast as possible until the next event; with a
  number, advances that many seconds of sim time.
- `DTMULT <factor>` — wall-clock multiplier.
- `HOLD` / `OP` — pause / resume the sim.
- `UTC <yyyy mm dd HH MM SS>` — anchor the simulated
  UTC clock (affects wind loaders, daylight logic).

## Where scenarios live

BlueSky has two scenario roots:

- **Built-in** — `bluesky/scenario/` (shipped with the
  sim).
- **User workdir** — typically `~/bluesky/scenario/`,
  configurable via `BlueSky` workdir setting.

Cesium-BlueSky's scenario editor writes to the user
workdir. Built-ins are read-only to avoid corrupting
shipped examples — when you "Save As New Version" a
built-in, it copies to the user workdir with `_v2`
suffix (then `_v3`, etc.).

## Versioning strategy

Scenarios are git-trackable. The convention used by our
editor:

- `demo.scn` — original
- `demo_v2.scn` — first revision
- `demo_v3.scn` — second revision, and so on

The "Versions" dropdown in the editor shows every file
matching `<stem>_v*.scn` so you can jump between them.
Diff two versions with `git diff` or any external diff
tool — the line-oriented format makes for clean diffs.

## Good practice

- **Keep setup at `0:00:00.00`** — aircraft creation,
  area definition, ASAS/RESO on. Gets the sim into a
  deterministic state before anything time-dependent
  runs.
- **Group temporal events by phase** — climb commands
  early, cruise-phase modifications middle, descents
  late. Reads better and is easier to reorder.
- **Load plugins early** — if your scenario needs SSD
  or EBY resolution, `0:00:00.00>PLUGIN LOAD SSD`
  before `RESO SSD`.
- **Seed randomness** if your scenario uses it — BlueSky
  scenarios using `TRAFGEN` or similar should set a
  seed explicitly.
- **Comment liberally** — `# what this section does`
  lines are worth writing. Future you will thank you.

## Loading from the REST API

- `GET /api/scenarios` — list scenarios categorized by
  location (built-in / user / etc.).
- `POST /api/scenarios/load` — body `{filename: "..."}`
  → runs `IC <filename>`.
- `GET /api/scenarios/text?filename=...` — raw file
  content (for the editor).
- `POST /api/scenarios/save-text` — write a full
  scenario text (user workdir only).
- `POST /api/scenarios/versions` — find every
  `<stem>_v*.scn` variant of a scenario.

See [Stack Commands](/docs/stack-commands) for how the
individual lines dispatch once a scenario is running.
