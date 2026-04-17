"""Auto-generated documentation pages.

Each generator returns a markdown string.  They are invoked
at request time so they always reflect the current sim
state (e.g., plugins loaded this session).
"""
import inspect
from typing import Callable


def _safe_doc(obj: object) -> str:
    """Return a trimmed docstring, or '' if none."""
    doc = inspect.getdoc(obj)
    return doc.strip() if doc else ""


def commands() -> str:
    """Every registered stack command, grouped alphabetically."""
    from bluesky.stack.cmdparser import Command

    lines: list[str] = [
        "# Commands Reference",
        "",
        "Every stack command currently registered with "
        "BlueSky, including commands added by loaded "
        "plugins.  Regenerated on each page view, so "
        "loading a plugin via ``PLUGIN LOAD ...`` will "
        "make its commands appear here on refresh.",
        "",
    ]

    # Build canonical → entry mapping so aliases don't
    # duplicate rows.
    canonical: dict[str, Command] = {}
    aliases: dict[str, list[str]] = {}
    for name, cmd in Command.cmddict.items():
        cname = cmd.name
        if cname not in canonical:
            canonical[cname] = cmd
            aliases[cname] = []
        if name != cname:
            aliases[cname].append(name)

    cmds_sorted = sorted(canonical.items())

    # Alphabetic index.
    lines.append("## Index")
    lines.append("")
    for name, _ in cmds_sorted:
        lines.append(f"- [`{name}`](#{name.lower()})")
    lines.append("")

    # Per-command sections.
    for name, cmd in cmds_sorted:
        lines.append(f"## `{name}`")
        lines.append("")
        if aliases.get(name):
            alias_str = ", ".join(
                f"`{a}`" for a in sorted(aliases[name])
            )
            lines.append(f"**Aliases:** {alias_str}")
            lines.append("")
        brief = (cmd.brief or "").strip()
        if brief:
            lines.append(f"**Usage:** `{brief}`")
            lines.append("")
        if cmd.annotations:
            lines.append("**Arguments:**")
            lines.append("")
            for ann in cmd.annotations:
                parts = str(ann).split(":")
                lines.append(f"- `{parts[0]}`" + (
                    f" — *{parts[1].strip()}*"
                    if len(parts) > 1 else ""
                ))
            lines.append("")
        doc = (cmd.help or "").strip()
        if doc:
            lines.append(doc)
            lines.append("")
        lines.append("")

    return "\n".join(lines)


def _document_class_tree(
    base_cls: type,
    title: str,
    intro: str,
) -> str:
    """Render all subclasses of ``base_cls`` as markdown.

    Used for ConflictResolution / ConflictDetection which
    both expose a ``.derived()`` dict of registered
    subclasses.
    """
    lines: list[str] = [f"# {title}", "", intro, ""]
    methods = base_cls.derived()
    lines.append(
        f"**Active:** `{base_cls.selected().__name__}`"
    )
    lines.append("")
    lines.append(f"**Registered ({len(methods)}):**")
    lines.append("")
    for name in sorted(methods):
        cls = methods[name]
        lines.append(f"## `{cls.__name__}`")
        lines.append("")
        module = cls.__module__
        lines.append(f"**Module:** `{module}`")
        lines.append("")
        doc = _safe_doc(cls)
        if doc:
            lines.append(doc)
            lines.append("")
    return "\n".join(lines)


def resolvers() -> str:
    """Registered ConflictResolution subclasses."""
    from bluesky.traffic.asas.resolution import (
        ConflictResolution,
    )
    return _document_class_tree(
        ConflictResolution,
        "Resolution Methods (RESO)",
        "Every Conflict Resolution implementation "
        "currently registered.  Base class sentinel "
        "(``ConflictResolution`` itself) means "
        "resolution is **OFF**.  See also "
        "[the reso-methods guide](/docs/reso-methods).",
    )


def detectors() -> str:
    """Registered ConflictDetection subclasses."""
    from bluesky.traffic.asas.detection import (
        ConflictDetection,
    )
    return _document_class_tree(
        ConflictDetection,
        "Conflict Detection Methods (CDMETHOD / ASAS)",
        "Every Conflict Detection implementation "
        "currently registered.  Base class sentinel "
        "means detection is **OFF**.",
    )


def plugins() -> str:
    """Loaded vs. available plugins."""
    from bluesky.core.plugin import Plugin

    lines: list[str] = [
        "# Plugins",
        "",
        "BlueSky plugins extend the sim at runtime — "
        "adding commands, resolvers, detectors, data "
        "sources, and more.  Load via "
        "``PLUGIN LOAD <NAME>`` from the console.",
        "",
    ]

    loaded = dict(Plugin.loaded_plugins)
    available = {
        k: v for k, v in Plugin.plugins.items()
        if k not in loaded
    }

    def section(
        title: str, plugs: dict, empty: str,
    ) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not plugs:
            lines.append(f"*{empty}*")
            lines.append("")
            return
        for name in sorted(plugs):
            p = plugs[name]
            lines.append(f"### `{name}`")
            lines.append("")
            doc = (p.plugin_doc or "").strip()
            if doc:
                lines.append(doc)
                lines.append("")
            if getattr(p, "plugin_stack", None):
                lines.append("**Commands added:**")
                lines.append("")
                for cmd_name, cmd_doc in p.plugin_stack:
                    lines.append(
                        f"- `{cmd_name}` — "
                        f"{cmd_doc.strip().splitlines()[0]}"
                        if cmd_doc.strip() else f"- `{cmd_name}`"
                    )
                lines.append("")
        lines.append("")

    section(
        "Loaded",
        loaded,
        "No plugins currently loaded.",
    )
    section(
        "Available",
        available,
        "No additional plugins available.",
    )

    return "\n".join(lines)


GENERATORS: dict[str, Callable[[], str]] = {
    "commands": commands,
    "resolvers": resolvers,
    "detectors": detectors,
    "plugins": plugins,
}
