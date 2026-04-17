"""Markdown-to-HTML rendering for the docs site.

Wraps the standard ``markdown`` library with the extensions
we want for good technical writing: fenced code, syntax
highlighting, tables, and auto-generated TOC.
"""
from pathlib import Path

import markdown


_EXTENSIONS = [
    "fenced_code",
    "codehilite",
    "tables",
    "sane_lists",
    "toc",
    "attr_list",
    "md_in_html",
]

_EXTENSION_CONFIGS = {
    "codehilite": {
        "css_class": "highlight",
        "guess_lang": False,
        "use_pygments": True,
    },
    "toc": {
        "toc_depth": "2-4",
        "permalink": "¶",
    },
}


def render_markdown(text: str) -> str:
    """Convert markdown to HTML with our standard config."""
    md = markdown.Markdown(
        extensions=_EXTENSIONS,
        extension_configs=_EXTENSION_CONFIGS,
        output_format="html5",
    )
    return md.convert(text)


def load_markdown_file(docs_dir: Path, rel_path: str) -> str:
    """Load a markdown file from ``docs_dir``.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    path = (docs_dir / rel_path).resolve()
    # Guard against path traversal — the resolved path must
    # live inside docs_dir.
    docs_dir_r = docs_dir.resolve()
    if docs_dir_r not in path.parents and path != docs_dir_r:
        raise FileNotFoundError(rel_path)
    return path.read_text(encoding="utf-8")
