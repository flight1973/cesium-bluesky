"""REST endpoints for scenario management."""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import bluesky as bs
from bluesky import settings

from cesium_app.sim.bridge import SimBridge

router = APIRouter(
    prefix="/api/scenarios",
    tags=["scenarios"],
)

# Map directory names to human-readable categories.
# Directories not listed here use their name as-is.
_CATEGORY_LABELS: dict[str, str] = {
    ".": "General",
    "ASAS": "Conflict Detection & Resolution",
    "Contest": "Contest / Competition",
    "DEMO": "Demos",
    "EHAM": "Amsterdam Schiphol (EHAM)",
    "Florent": "Research (Florent)",
    "LNAV_VNAV": "Navigation (LNAV/VNAV)",
    "Loggers": "Data Logging",
    "Malik": "Research (Malik)",
    "MOV": "Movement / Maneuvers",
    "old": "Legacy / Archive",
    "Sectors": "Airspace Sectors",
    "SSD": "State Space Diagram",
    "synthetics": "Synthetic Traffic",
    "testscenarios": "Test Scenarios",
    "TRAFGEN": "Traffic Generation",
}


class ScenarioLoad(BaseModel):
    """Request body for loading a scenario file.

    Attributes:
        filename: Scenario filename relative to scenario dir.
    """

    filename: str


class ScenarioEntry(BaseModel):
    """One line in a scenario file.

    Attributes:
        time: Time in seconds from sim start (0+).
        command: The stack command to execute.
    """

    time: float = 0.0
    command: str


class ScenarioSave(BaseModel):
    """Request body for saving a scenario file.

    Attributes:
        filename: Target filename (.scn will be added if
            missing).
        entries: Ordered list of time+command entries.
        overwrite: If false, fail when file exists.
    """

    filename: str
    entries: list[ScenarioEntry] = Field(default_factory=list)
    overwrite: bool = True


class ScenarioTextSave(BaseModel):
    """Request body for saving a scenario as raw text.

    Bypasses the structured entries format — use this to
    preserve comments, blank lines, and original formatting.

    Attributes:
        filename: Target filename.
        text: Full .scn file content.
        overwrite: If false, fail when file exists.
    """

    filename: str
    text: str
    overwrite: bool = True


def _user_scenario_dir() -> Path:
    """User-writable directory for saving scenarios.

    Uses the first resource path (BlueSky workdir's scenario
    folder).  Built-in package scenarios are never modified.
    """
    scen_res = bs.resource(settings.scenario_path)
    if hasattr(scen_res, '_paths'):
        return Path(scen_res._paths[0])
    return Path(scen_res)


def _resolve_scenario_file(filename: str) -> Path | None:
    """Locate a scenario file across resource paths."""
    scen_res = bs.resource(settings.scenario_path)
    if hasattr(scen_res, '_paths'):
        bases = scen_res._paths
    else:
        bases = [Path(scen_res)]
    for base in bases:
        p = Path(base) / filename
        if p.is_file():
            return p
    return None


def _parse_scenario_line(
    line: str,
) -> tuple[float, str] | None:
    """Parse one line of a .scn file.

    Lines look like:
        HH:MM:SS.hh>COMMAND
        HH:MM:SS>COMMAND
    Or may be blank / comments (start with #).

    Returns (time_in_seconds, command) or None.
    """
    line = line.rstrip("\r\n")
    if not line or line.lstrip().startswith("#"):
        return None
    match = re.match(
        r"\s*(\d+):(\d+):(\d+)(?:\.(\d+))?>(.*)",
        line,
    )
    if not match:
        return None
    h, m, s, frac, cmd = match.groups()
    seconds = (
        int(h) * 3600 + int(m) * 60 + int(s)
    )
    if frac:
        seconds += float(f"0.{frac}")
    return seconds, cmd.strip()


def _format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.hh."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s_float = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s_float:05.2f}"


def _safe_filename(name: str) -> str:
    """Sanitize a scenario filename.

    Keeps alphanumerics, dashes, underscores, and slashes
    (for subdirectories).  Strips .. to prevent path
    traversal.
    """
    cleaned = re.sub(r"[^\w./-]", "_", name)
    cleaned = cleaned.replace("..", "_")
    if not cleaned.lower().endswith((".scn", ".SCN")):
        cleaned = cleaned + ".scn"
    return cleaned


def _bridge(request: Request) -> SimBridge:
    """Extract the SimBridge from app state."""
    return request.app.state.bridge


@router.get("")
async def list_scenarios(
    request: Request,
) -> dict:
    """List scenario files organized by category.

    Returns a dict mapping category names to lists of
    scenarios, sorted alphabetically within each category.
    """
    scen_res = bs.resource(settings.scenario_path)

    if hasattr(scen_res, '_paths'):
        bases = scen_res._paths
    else:
        bases = [Path(scen_res)]

    categories: dict[str, list[dict]] = {}
    seen: set[str] = set()

    for base in bases:
        if not base.exists():
            continue
        for f in base.rglob("*.[sS][cC][nN]"):
            key = f.name.lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                rel = f.relative_to(base)
            except ValueError:
                continue

            # Determine category from parent directory.
            parts = rel.parts
            if len(parts) == 1:
                cat_key = "."
            else:
                cat_key = parts[0]

            cat_label = _CATEGORY_LABELS.get(
                cat_key, cat_key,
            )

            if cat_label not in categories:
                categories[cat_label] = []

            categories[cat_label].append({
                "filename": str(rel),
                "name": f.stem,
                "size": f.stat().st_size,
            })

    # Sort scenarios within each category.
    for cat in categories:
        categories[cat].sort(
            key=lambda s: s["name"].lower(),
        )

    # Return with categories in sorted order.
    return dict(sorted(categories.items()))


@router.post("/load")
async def load_scenario(
    request: Request,
    body: ScenarioLoad,
) -> dict:
    """Load a scenario file (IC command)."""
    cmd = f"IC {body.filename}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.get("/content")
async def get_scenario_content(
    request: Request,
    filename: str,
) -> dict:
    """Return the parsed contents of a scenario file.

    Args:
        filename: Path relative to scenario dir.

    Returns:
        Dict with filename, entries (list of time+command),
        and writable flag (user-dir files are writable;
        package-built-ins are read-only).
    """
    path = _resolve_scenario_file(filename)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario {filename} not found",
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Read failed: {exc}",
        ) from exc

    entries: list[dict] = []
    for line in raw.splitlines():
        parsed = _parse_scenario_line(line)
        if parsed is None:
            continue
        t, cmd = parsed
        entries.append({"time": t, "command": cmd})

    user_dir = _user_scenario_dir().resolve()
    try:
        path_resolved = path.resolve()
        writable = str(path_resolved).startswith(
            str(user_dir),
        )
    except Exception:  # pylint: disable=broad-except
        writable = False

    return {
        "filename": filename,
        "entries": entries,
        "writable": writable,
    }


@router.get("/text")
async def get_scenario_text(
    request: Request,
    filename: str,
) -> dict:
    """Return the raw text of a scenario file.

    Preserves comments and blank lines.
    """
    path = _resolve_scenario_file(filename)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario {filename} not found",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Read failed: {exc}",
        ) from exc

    user_dir = _user_scenario_dir().resolve()
    writable = str(path.resolve()).startswith(
        str(user_dir),
    )
    return {
        "filename": filename,
        "text": text,
        "writable": writable,
    }


@router.post("/save-text")
async def save_scenario_text(
    request: Request,
    body: ScenarioTextSave,
) -> dict:
    """Save raw text as a scenario file.

    Preserves comments and whitespace exactly as provided.
    Use this when editing in text mode.
    """
    fname = _safe_filename(body.filename)
    target = _user_scenario_dir() / fname
    if target.exists() and not body.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"Scenario {fname} already exists",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(body.text, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Write failed: {exc}",
        ) from exc
    return {
        "status": "ok",
        "filename": str(
            target.relative_to(_user_scenario_dir())
        ),
        "size": target.stat().st_size,
    }


@router.post("/save")
async def save_scenario(
    request: Request,
    body: ScenarioSave,
) -> dict:
    """Save a scenario file to the user scenario dir.

    Only writes under the user workdir — package-built-in
    scenarios cannot be overwritten.
    """
    fname = _safe_filename(body.filename)
    target = _user_scenario_dir() / fname
    if target.exists() and not body.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"Scenario {fname} already exists",
        )

    # Build file contents.
    lines = [f"# Scenario: {fname}", ""]
    for e in sorted(body.entries, key=lambda x: x.time):
        ts = _format_time(e.time)
        lines.append(f"{ts}>{e.command}")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(
            "\n".join(lines) + "\n", encoding="utf-8",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Write failed: {exc}",
        ) from exc

    return {
        "status": "ok",
        "filename": str(
            target.relative_to(_user_scenario_dir())
        ),
        "size": target.stat().st_size,
    }


@router.post("/versions")
async def save_new_version(
    request: Request,
    body: ScenarioSave,
) -> dict:
    """Save a new version of a scenario with an auto suffix.

    If the requested filename exists, appends ``_v2``,
    ``_v3``, etc. until a free name is found.
    """
    fname = _safe_filename(body.filename)
    target = _user_scenario_dir() / fname

    if target.exists():
        stem = target.stem
        # Strip any existing _vN suffix to start fresh.
        base_match = re.match(
            r"^(.*?)_v(\d+)$", stem,
        )
        if base_match:
            base_stem = base_match.group(1)
            next_v = int(base_match.group(2)) + 1
        else:
            base_stem = stem
            next_v = 2
        while True:
            candidate = (
                _user_scenario_dir()
                / f"{base_stem}_v{next_v}.scn"
            )
            if not candidate.exists():
                target = candidate
                break
            next_v += 1

    lines = [f"# Scenario: {target.name}", ""]
    for e in sorted(body.entries, key=lambda x: x.time):
        ts = _format_time(e.time)
        lines.append(f"{ts}>{e.command}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )
    return {
        "status": "ok",
        "filename": str(
            target.relative_to(_user_scenario_dir())
        ),
    }


@router.delete("/{filename:path}")
async def delete_scenario(
    request: Request,
    filename: str,
) -> dict:
    """Delete a user scenario file.

    Only files in the user scenario directory can be
    deleted; package-built-in scenarios are protected.
    """
    target = _user_scenario_dir() / _safe_filename(filename)
    if not target.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Scenario {filename} not found",
        )
    user_dir = _user_scenario_dir().resolve()
    if not str(target.resolve()).startswith(str(user_dir)):
        raise HTTPException(
            status_code=403,
            detail="Cannot delete built-in scenarios",
        )
    try:
        target.unlink()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {exc}",
        ) from exc
    return {"status": "ok", "filename": filename}


@router.get("/versions")
async def list_versions(
    request: Request,
    stem: str,
) -> list[dict]:
    """List all versions of a scenario by name stem.

    Finds files matching ``{stem}.scn`` and ``{stem}_vN.scn``
    in all scenario resource paths, sorted by version.
    """
    safe_stem = re.sub(r"[^\w-]", "", stem)
    scen_res = bs.resource(settings.scenario_path)
    if hasattr(scen_res, '_paths'):
        bases = scen_res._paths
    else:
        bases = [Path(scen_res)]

    user_dir = _user_scenario_dir().resolve()
    results: list[dict] = []
    seen: set[str] = set()
    for base in bases:
        if not Path(base).exists():
            continue
        patterns = [f"{safe_stem}.scn", f"{safe_stem}.SCN",
                    f"{safe_stem}_v*.scn"]
        for pat in patterns:
            for f in Path(base).glob(pat):
                if f.name in seen:
                    continue
                seen.add(f.name)
                writable = str(f.resolve()).startswith(
                    str(user_dir),
                )
                results.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "writable": writable,
                })

    def version_key(entry: dict) -> int:
        m = re.match(
            r".*_v(\d+)\.scn$", entry["filename"],
        )
        return int(m.group(1)) if m else 1

    return sorted(results, key=version_key)
