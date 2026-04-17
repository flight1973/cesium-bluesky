# EUROCONTROL DDR2 Data Drop

DDR2 datasets aren't programmatically downloadable
on a schedule (the portal needs an interactive
login).  Drop downloaded files in this directory
and run the ingest CLI.

## Where to get the files

1. Register at <https://ddr.eurocontrol.int/>
   (free for researchers).
2. Once approved, log in and navigate to:
   - **Reference Data → AIRAC datasets**
3. Download the current AIRAC's
   `airac_dataset_<cycle>.zip` and unzip into
   this directory.  Expected files:

```
data/ddr2/
├── points.csv      ← significant points / waypoints
├── routes.csv      ← airway segments
├── airports.csv    ← airport reference points
└── airspaces.csv   ← FIR / sector boundaries
```

Filename casing varies by DDR2 release; the
ingest CLI is case-insensitive and tolerates
common variants (`Points.csv`, `point.csv`,
`POINTS.txt`, etc.).

## Run the ingest

```
python -m cesium_app.ingest ddr2
```

This walks `data/ddr2/`, parses each known file,
and writes rows into the SQLite cache tagged
`source='EUROCONTROL'`.  Rows that conflict with
existing FAA data are skipped (FAA wins per the
project's
[worldwide-navdata convention](../../../.claude/projects/-Users-cmartin-git-cesium-bluesky/memory/project_worldwide_navdata.md)).

After ingest, regenerate the Neo4j graph:

```
python -m cesium_app.ingest graph
```

## Refresh cadence

DDR2 publishes monthly on the AIRAC cycle
(28 days).  Re-download when the cycle rolls
over; the ingest CLI replaces the old DDR2 rows
with the new ones (FAA rows untouched).

## Privacy note

Files in this directory are gitignored.  Don't
commit them — your DDR2 license likely doesn't
permit redistribution.
