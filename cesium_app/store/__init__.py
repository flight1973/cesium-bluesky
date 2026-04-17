"""Persistent data store for slow-changing FAA data.

SQLite-based cache with R-tree virtual tables for
bbox queries.  Avoids SpatiaLite because the R-tree
module ships with SQLite's core library — zero extra
system dependencies.

Data lifecycle:

* :mod:`cesium_app.ingest` populates the DB from the
  live FAA endpoints on an AIRAC-cycle cadence.
* Airspace adapters (``airspace/classes.py``,
  ``suas.py``) read from the DB when populated and
  fall back to the existing live fetch when empty.
* TFRs bypass this cache entirely — they change on
  the order of minutes and stay in-memory.
"""
