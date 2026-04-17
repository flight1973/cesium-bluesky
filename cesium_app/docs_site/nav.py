"""Navigation tree for the docs site.

Each leaf has either a ``file`` (path relative to the
``docs/`` directory) or a ``generator`` key (name of an
auto-generator in :mod:`cesium_app.docs_site.generators`).
"""
from typing import TypedDict


class Leaf(TypedDict, total=False):
    """One entry in the sidebar."""

    title: str
    slug: str        # URL slug (path after /docs/)
    file: str        # markdown file path (docs/-relative)
    generator: str   # generator name (auto content)
    children: list["Leaf"]


NAV: list[Leaf] = [
    {
        "title": "Introduction",
        "slug": "index",
        "file": "index.md",
    },
    {
        "title": "Using the interface",
        "children": [
            {
                "title": "Getting Started",
                "slug": "interface/getting-started",
                "file": "interface/getting-started.md",
            },
            {
                "title": "Viewer & 3D Globe",
                "slug": "interface/viewer",
                "file": "interface/viewer.md",
            },
            {
                "title": "Toolbar & Tabs",
                "slug": "interface/toolbar",
                "file": "interface/toolbar.md",
            },
            {
                "title": "Aircraft Panel",
                "slug": "interface/aircraft-panel",
                "file": "interface/aircraft-panel.md",
            },
            {
                "title": "Scenario Editor",
                "slug": "interface/scenario-editor",
                "file": "interface/scenario-editor.md",
            },
            {
                "title": "Area Tools",
                "slug": "interface/area-tools",
                "file": "interface/area-tools.md",
            },
            {
                "title": "Camera Modes",
                "slug": "interface/camera-modes",
                "file": "interface/camera-modes.md",
            },
            {
                "title": "Layers",
                "slug": "interface/layers",
                "file": "interface/layers.md",
            },
            {
                "title": "Settings & Units",
                "slug": "interface/settings",
                "file": "interface/settings.md",
            },
            {
                "title": "Visual Conventions",
                "slug": "interface/visual-conventions",
                "file": "interface/visual-conventions.md",
            },
        ],
    },
    {
        "title": "BlueSky concepts",
        "children": [
            {
                "title": "Simulation Overview",
                "slug": "simulation-overview",
                "file": "simulation-overview.md",
            },
            {
                "title": "Stack Commands",
                "slug": "stack-commands",
                "file": "stack-commands.md",
            },
            {
                "title": "Scenario Files",
                "slug": "scenario-files",
                "file": "scenario-files.md",
            },
        ],
    },
    {
        "title": "BlueSky systems",
        "children": [
            {
                "title": "Autopilot & FMS",
                "slug": "autopilot",
                "file": "autopilot.md",
            },
            {
                "title": "Conflict Detection & Resolution",
                "slug": "asas",
                "file": "asas.md",
            },
            {
                "title": "Resolution Methods",
                "slug": "reso-methods",
                "file": "reso-methods.md",
            },
            {
                "title": "Wind",
                "slug": "wind",
                "file": "wind.md",
            },
        ],
    },
    {
        "title": "API reference",
        "children": [
            {
                "title": "REST Endpoints",
                "slug": "api/rest",
                "file": "api/rest.md",
            },
            {
                "title": "WebSocket Protocol",
                "slug": "api/websocket",
                "file": "api/websocket.md",
            },
        ],
    },
    {
        "title": "Reference (live)",
        "children": [
            {
                "title": "Commands",
                "slug": "ref/commands",
                "generator": "commands",
            },
            {
                "title": "Resolution Methods",
                "slug": "ref/resolvers",
                "generator": "resolvers",
            },
            {
                "title": "Detection Methods",
                "slug": "ref/detectors",
                "generator": "detectors",
            },
            {
                "title": "Plugins",
                "slug": "ref/plugins",
                "generator": "plugins",
            },
        ],
    },
    {
        "title": "Plans & design notes",
        "children": [
            {
                "title": "Smooth Banking",
                "slug": "plans/smooth-banking",
                "file": "smooth-banking-plan.md",
            },
            {
                "title": "Wind Control",
                "slug": "plans/wind-control",
                "file": "wind-control-plan.md",
            },
            {
                "title": "Terrain Strategy",
                "slug": "plans/terrain-strategy",
                "file": "terrain-strategy.md",
            },
        ],
    },
]


def iter_leaves(nodes: list[Leaf] | None = None):
    """Depth-first traversal yielding every content leaf."""
    if nodes is None:
        nodes = NAV
    for node in nodes:
        if node.get("children"):
            yield from iter_leaves(node["children"])
        if "slug" in node:
            yield node


def find_by_slug(slug: str) -> Leaf | None:
    """Locate a leaf by its URL slug."""
    for leaf in iter_leaves():
        if leaf.get("slug") == slug:
            return leaf
    return None
