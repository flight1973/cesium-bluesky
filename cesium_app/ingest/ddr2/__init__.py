"""EUROCONTROL DDR2 (Demand Data Repository v2)
ingest.

Source: ``ddr.eurocontrol.int`` — free with
researcher registration.  See
``data/ddr2/README.md`` for the manual download
flow (DDR2 doesn't have a programmatic API
suitable for re-download every AIRAC cycle).

DDR2 ships AIRAC datasets as ``airac_dataset_<cycle>.zip``
containing ALLFT+ /  CFMU  / NEST format files.
For navdata ingest, the relevant files are:

- ``points.csv`` — significant points (waypoints,
  navaids) with WGS-84 coordinates.
- ``routes.csv`` — airway segments with route
  identifier + sequence + fix references.
- ``airports.csv`` — airport reference points.
- ``airspaces.csv`` — sector / FIR boundaries.

This module's adapters parse those files and
load into our ``navfix`` / ``airway`` /
``airway_fix`` tables tagged
``source='EUROCONTROL'``.

Conflict resolution at insert time: skip when an
existing row from FAA already covers the same
``(id, region)`` — the FAA-wins-where-it-has-data
rule from ``project_worldwide_navdata.md``.
"""
from __future__ import annotations

SOURCE_TAG = "EUROCONTROL"
