"""REST endpoints for scenario management."""
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

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
