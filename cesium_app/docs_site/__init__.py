"""In-app documentation system for BlueSky.

Renders markdown files under ``docs/`` as HTML, plus a set
of auto-generated reference pages pulled live from the
running BlueSky instance (command list, resolvers,
detectors, loaded plugins).

The FastAPI router is in :mod:`cesium_app.api.docs`; the
rendering internals, navigation tree, and generators live
in this package.
"""
