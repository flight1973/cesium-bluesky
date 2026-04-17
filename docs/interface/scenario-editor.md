# Scenario Editor

A text-mode editor for BlueSky `.scn` files with version
tracking. Scenarios are plain text you can edit, diff,
and commit — the editor is a convenience, not a
lock-in.

Open via **EDIT SCENARIO** in the SIM tab.

## Layout

```
┌──────────────────────────────────────────────┐
│ demo.scn                       [Load] [Save] │
│ Versions: demo, demo_v2, demo_v3             │
├──────────────────────────────────────────────┤
│   1 | 00:00:00.00>CRE KL204 B738 ...         │
│   2 | 00:00:00.00>ASAS ON                    │
│   3 | 00:00:00.00>RESO MVP                   │
│   4 |                                        │
│   5 | 00:01:00.00>HDG KL204 090              │
│     |                                        │
└──────────────────────────────────────────────┘
```

- **Filename** — top left, editable so you can "save
  as."
- **Load Into Sim** — runs `IC <filename>` on the
  current file (saves first if dirty).
- **Save** — writes to the user workdir (overwrite).
- **Save As New Version** — bumps the `_vN` suffix and
  creates a new file.
- **Versions** — horizontal list of every `.scn` file
  matching `<stem>_v*.scn`. Click to jump between
  versions.

## Text editor behavior

- Monospace font, line numbers in the gutter.
- **Tab** inserts 4 spaces (not a literal tab
  character).
- Scrolls smoothly for long files.
- Full-text editing — no linting or syntax highlighting
  yet (a future enhancement).

## Read-only vs. writable

Two classes of scenario:

| Location | Writable? |
|---|---|
| Built-in (ships with BlueSky) | **Read only** — protected to avoid corrupting shipped examples. |
| User workdir (default `~/bluesky/scenario/`) | Writable |

When you open a read-only scenario and hit **Save**, the
editor prompts to **Save As New Version** instead — which
copies to the user workdir with `_v2`. From then on
you're editing the writable copy.

## Versioning convention

- `demo.scn` — original (built-in or user-saved).
- `demo_v2.scn` — second version.
- `demo_v3.scn` — third version, and so on.

The editor's **Versions** list shows every matching
`<stem>_v*.scn` it finds. The convention is a plain file-
naming scheme — no database, no metadata. Plays
perfectly with git: each version is a tracked file, and
`git diff` works out of the box.

## Save As New Version workflow

1. Open `demo.scn`.
2. Edit.
3. Click **Save As New Version** — creates
   `demo_v2.scn`, opens it in the editor.
4. Continue editing.
5. Click **Save** — overwrites `demo_v2.scn`.

The editor auto-picks the next free `_vN` — if `_v2` and
`_v3` already exist, the next save-as goes to `_v4`.

## Loading a scenario from the editor

**Load Into Sim** issues:

```
IC <filename>
```

This resets the sim and plays the scenario from
`simt == 0`. The viewer clears trails, routes, areas;
the editor stays open on whatever you're editing.

## Under the hood

- `GET /api/scenarios/text?filename=...` loads raw text.
- `POST /api/scenarios/save-text` writes it back.
- `GET /api/scenarios/versions?filename=...` lists
  `_vN` siblings.
- `POST /api/scenarios/load` (`IC <filename>`) runs the
  scenario.

See [Scenario Files](/docs/scenario-files) for the `.scn`
format itself and
[REST Endpoints](/docs/api/rest) for the full API.

## Tips

- **Keep setup at `00:00:00.00`** — aircraft creation,
  ASAS/RESO setup. See the tips section in
  [Scenario Files](/docs/scenario-files).
- **Comment with `#`** — full-line comments are
  supported.
- **Commit each version** — since each is a separate
  file, a commit per version gives you a perfect
  replay-able history.
- **Use a real editor for big refactors** — the in-app
  editor is great for small edits and iterating during
  a session. For complex restructuring, edit the file
  on disk and reload in the browser.
