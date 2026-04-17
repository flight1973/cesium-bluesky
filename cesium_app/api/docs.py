"""FastAPI router for the in-app documentation site.

Serves markdown files from ``docs/`` and auto-generated
reference pages at ``/docs/...``.  Hot-reload friendly —
file contents are re-read on every request so edits to
markdown show up on refresh without a restart.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from cesium_app.docs_site import generators, nav, render
from cesium_app.docs_site.template import render_page

router = APIRouter(tags=["docs"])

# Project root: cesium_app/ → parent is the project root,
# which holds docs/.
_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


@router.get("/docs", response_class=HTMLResponse)
@router.get("/docs/", response_class=HTMLResponse)
async def docs_index() -> HTMLResponse:
    """Landing page for the docs site."""
    return await docs_page("index")


@router.get("/docs/{slug:path}", response_class=HTMLResponse)
async def docs_page(slug: str) -> HTMLResponse:
    """Render the documentation page for ``slug``."""
    # Normalize: strip trailing slash and index.
    slug = slug.rstrip("/")
    if not slug:
        slug = "index"

    leaf = nav.find_by_slug(slug)
    if leaf is None:
        raise HTTPException(
            status_code=404,
            detail=f"No docs page for {slug!r}",
        )

    # Build the markdown body.
    if "generator" in leaf:
        gen_name = leaf["generator"]
        gen = generators.GENERATORS.get(gen_name)
        if gen is None:
            raise HTTPException(
                status_code=500,
                detail=f"Unknown generator {gen_name!r}",
            )
        try:
            md_text = gen()
        except Exception as exc:  # pylint: disable=broad-except
            md_text = (
                f"# {leaf['title']}\n\n"
                f"Error generating this page:\n\n"
                f"```\n{exc!r}\n```"
            )
    elif "file" in leaf:
        try:
            md_text = render.load_markdown_file(
                _DOCS_DIR, leaf["file"],
            )
        except FileNotFoundError:
            md_text = (
                f"# {leaf['title']}\n\n"
                f"*This page hasn't been written yet.*\n\n"
                f"The referenced file "
                f"`docs/{leaf['file']}` was not found. "
                f"Drop a markdown file there and it will "
                f"render automatically on refresh."
            )
    else:
        raise HTTPException(
            status_code=500,
            detail="Malformed nav entry: no file or generator",
        )

    body = render.render_markdown(md_text)
    html = render_page(
        title=leaf["title"],
        body_html=body,
        active_slug=slug,
    )
    return HTMLResponse(content=html)
