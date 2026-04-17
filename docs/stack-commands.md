# Stack Commands

BlueSky is driven entirely by a line-based command
language. Every user interaction — creating an aircraft,
setting a heading, loading a scenario, enabling a feature —
is a command text string submitted to the **stack**.

```
CRE KL204 B738 52 4 180 FL350 280
HDG KL204 090
ASAS ON
RESO MVP
```

This is the same language BlueSky's Qt console uses, the
same format `.scn` files use, and the same interface our
REST API wraps. There's one authoritative entry point —
`bluesky.stack.stack(cmdline)` — and every client flows
through it.

## Anatomy

A command line is `NAME arg1 arg2 ...`, case-insensitive,
space- or comma-separated. Multiple commands on one line
are separated by semicolons.

```
HDG KL204 090; ALT KL204 FL320; SPD KL204 250
```

Argument types (`txt`, `acid`, `float`, `alt`, `spd`,
etc.) are declared by each command and parsed on the way
in — invalid arguments raise an error rather than silently
misbehaving.

## Aliases

Many commands have aliases — alternate names that resolve
to the same handler. For example:

- `ZONER` = `PZR` = `RPZ` = `PZRADIUS`
- `CDMETHOD` = `ASAS`
- `CRE` = `CREATE`

Aliases exist for historical reasons (different BlueSky
generations used different names) and for ergonomic
reasons (short vs. long forms). They all dispatch to the
same Python handler.

For the full live list of canonical names and their
aliases, see the **[live Commands reference](/docs/ref/commands)**.

## How commands are registered

Commands are Python callables decorated with
`@bluesky.stack.command`:

```python
from bluesky.stack import command

@command(name='HDG', aliases=('HEADING',))
def set_heading(acid: 'acid', hdg: float):
    '''Set the autopilot heading.'''
    bs.traf.ap.selhdg[acid] = hdg
    bs.traf.swlnav[acid] = False
    return True, f'{bs.traf.id[acid]} HDG {hdg}'
```

The decorator parses the function's type annotations to
build an argument parser, adds the command to
`Command.cmddict`, and makes it available to every
client. Plugins register commands the same way — once
`PLUGIN LOAD ...` runs, the plugin's commands appear in
the cmddict and become callable.

Handler return value is a 2-tuple `(success, message)`:

- `success=True` → command ran, `message` is echoed to
  the user.
- `success=False` → command was rejected (bad arg, unknown
  aircraft, etc.); `message` is the error.

## Dispatch flow

When `bluesky.stack.stack(cmdline)` is called:

1. **Splitting** — multi-command lines are split on `;`.
2. **Parsing** — tokenize on whitespace/commas, extract
   command name.
3. **Lookup** — find the `Command` object in
   `Command.cmddict` (aliases resolve to canonical).
4. **Argument conversion** — coerce each token to the
   declared Python type, running each argument through
   its type's registered parser (e.g., `'acid'` looks
   up an aircraft by callsign).
5. **Invocation** — call the handler, collect its
   `(success, message)`.
6. **Echo** — append the message to the output buffer
   for display.

Steps 2–6 happen in the sim thread on the next tick, not
synchronously. REST/WebSocket callers get an immediate
acknowledgement but not the command's result — that flows
back via the ECHO WebSocket topic.

## Where they run

Every command goes through the same dispatch:

| Source | Path |
|---|---|
| REST `POST /api/commands` | → `bridge.stack_command()` → `bluesky.stack.stack()` |
| WebSocket `{action: "command", ...}` | → same |
| Scenario file (`.scn`) | Lines played back by the scheduler → `bluesky.stack.stack()` |
| Console | Parsed by UI → `bluesky.stack.stack()` |
| Internal BlueSky code | Direct calls to `bluesky.stack.stack()` |

Cesium-BlueSky monkey-patches `stack()` at startup to
append every submitted command to a rolling 500-entry
audit log (`bridge._cmd_log`). That log is available at
`GET /api/cmdlog` and streamed live via the `CMDLOG`
WebSocket topic. It captures commands from **every**
source — including BlueSky's own internal dispatches —
which is invaluable for debugging why state changed.

## Scenario integration

Scenario `.scn` files are just stack commands prefixed
with a simulation time:

```
00:00:00.00>CRE KL204 B738 52 4 180 FL350 280
00:00:00.00>ASAS ON
00:01:00.00>HDG KL204 090
```

At `simt == 0:01:00`, the `HDG KL204 090` line becomes a
regular `stack()` call. From the inside, there's no
difference between a command from a scenario and one
typed by a human — they share the same dispatch path,
same logging, same error handling.

See [Scenario Files](/docs/scenario-files) for the file
format in detail.

## Tips

- **List all commands**: `GET /api/commands/list` returns
  name + brief + args for every registered command, or
  see the [live reference](/docs/ref/commands).
- **Plugin commands**: `PLUGIN LOAD EBY` (or any plugin)
  extends the cmddict immediately. The commands page
  refreshes live.
- **Canonical name wins**: If you see a command in the
  [live reference](/docs/ref/commands), that's the
  canonical name. Aliases will appear under it.
- **Debugging**: check `/api/cmdlog` to see the exact
  command string that ran, regardless of who sent it.
