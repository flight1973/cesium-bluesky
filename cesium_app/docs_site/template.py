"""HTML template for the docs site.

The layout is a two-pane design: fixed-width sidebar with
the navigation tree on the left, main content area on the
right.  Styling matches the simulator's dark console look.
"""
from pygments.formatters import HtmlFormatter

from cesium_app.docs_site.nav import NAV, Leaf

# Pygments syntax-highlight CSS.  Injected once at module
# load to avoid rebuilding per request.
_PYGMENTS_CSS = HtmlFormatter(style="monokai").get_style_defs(
    ".highlight",
)


CSS = (
    """
:root {
  color-scheme: dark;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: #0d0d0d;
  color: #d0d0d0;
  font-family: -apple-system, BlinkMacSystemFont,
    'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px;
  line-height: 1.55;
}
a { color: #66d9ef; text-decoration: none; }
a:hover { text-decoration: underline; }

.layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: 100vh;
}

/* ── Sidebar ── */
.sidebar {
  background: #161616;
  border-right: 1px solid #2a2a2a;
  padding: 16px 18px;
  overflow-y: auto;
  position: sticky;
  top: 0;
  max-height: 100vh;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12.5px;
}
.sidebar h1 {
  font-size: 15px;
  color: #00ff00;
  margin: 0 0 14px 0;
  letter-spacing: 0.5px;
}
.sidebar .group {
  margin-bottom: 16px;
}
.sidebar .group-title {
  color: #888;
  text-transform: uppercase;
  font-size: 10px;
  letter-spacing: 1px;
  margin: 6px 0 4px 0;
}
.sidebar a {
  display: block;
  padding: 2px 6px;
  color: #bbb;
  border-radius: 3px;
}
.sidebar a.active {
  background: #222;
  color: #00ff00;
  border-left: 2px solid #00ff00;
  padding-left: 8px;
}
.sidebar a:hover { color: #00ff00; background: #1a1a1a;
  text-decoration: none; }

/* ── Content ── */
.content {
  padding: 28px 40px 60px 40px;
  max-width: 900px;
}
.content h1 { font-size: 28px; margin: 0 0 8px 0;
  color: #fff; }
.content h2 { font-size: 20px; margin: 28px 0 8px 0;
  color: #fff; border-bottom: 1px solid #2a2a2a;
  padding-bottom: 4px; }
.content h3 { font-size: 16px; margin: 20px 0 6px 0;
  color: #ddd; }
.content h4 { font-size: 14px; margin: 14px 0 4px 0;
  color: #bbb; }
.content p { margin: 8px 0 12px 0; }
.content strong { color: #fff; }
.content em { color: #ccc; }
.content ul, .content ol {
  margin: 8px 0 14px 0;
  padding-left: 22px;
}
.content li { margin: 3px 0; }
.content blockquote {
  border-left: 3px solid #444;
  margin: 12px 0;
  padding: 4px 14px;
  color: #aaa;
}
.content code {
  background: #1e1e1e;
  color: #66d9ef;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12.5px;
}
.content pre {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 10px 14px;
  overflow-x: auto;
  margin: 10px 0;
}
.content pre code {
  background: transparent;
  padding: 0;
  color: #d0d0d0;
  font-size: 12px;
  line-height: 1.5;
}
.content table {
  border-collapse: collapse;
  margin: 12px 0;
  width: 100%;
}
.content th, .content td {
  border: 1px solid #2a2a2a;
  padding: 6px 10px;
  text-align: left;
}
.content th { background: #1a1a1a; color: #fff; }
.content .headerlink {
  color: #444;
  text-decoration: none;
  margin-left: 6px;
  font-size: 0.8em;
}
.content h1:hover .headerlink,
.content h2:hover .headerlink,
.content h3:hover .headerlink { color: #00ff00; }

/* Breadcrumbs / back link */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid #2a2a2a;
  font-size: 12px;
  color: #888;
}
.topbar a { color: #888; }
.topbar a:hover { color: #00ff00; }

/* ── Pygments (injected) ── */
"""
    + _PYGMENTS_CSS
)


def _render_sidebar(
    nodes: list[Leaf],
    active_slug: str,
) -> str:
    """Render the nav tree as nested HTML."""
    out: list[str] = []
    for node in nodes:
        children = node.get("children")
        if children:
            out.append('<div class="group">')
            out.append(
                '<div class="group-title">'
                f'{node["title"]}</div>'
            )
            out.append(_render_sidebar(children, active_slug))
            out.append("</div>")
        else:
            slug = node["slug"]
            cls = "active" if slug == active_slug else ""
            out.append(
                f'<a href="/docs/{slug}" class="{cls}">'
                f'{node["title"]}</a>'
            )
    return "\n".join(out)


def render_page(
    title: str,
    body_html: str,
    active_slug: str,
) -> str:
    """Wrap rendered content in the full docs page layout."""
    sidebar = _render_sidebar(NAV, active_slug)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title} — BlueSky Docs</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
  <nav class="sidebar">
    <h1>BlueSky Docs</h1>
    {sidebar}
  </nav>
  <main class="content">
    <div class="topbar">
      <div><a href="/">← Back to sim</a></div>
      <div><a href="/docs/">All topics</a></div>
    </div>
    {body_html}
  </main>
</div>
</body>
</html>
"""
