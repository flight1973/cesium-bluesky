# Data Integration Plan

Phased plan to integrate external aviation data sources
into cesium-bluesky.  Each phase builds on the previous;
sources within a phase can be parallelized.  All
credential-gated sources follow the modular-feeds
directive (opt-in, vault-stored, graceful degradation).

---

## Currently Integrated (Baseline)

| Source | Data | Protocol | Status |
|---|---|---|---|
| FAA ArcGIS FeatureServer | Class B/C/D/E airspace, SUA, chart tiles (VFR/TAC/IFR) | ArcGIS REST | ✅ Live |
| FAA CIFP (aeronav.faa.gov) | 52K procedures, 1.5K airways, 100K navfixes | ARINC-424 text | ✅ Cached in SQLite + Neo4j |
| FAA Preferred Routes (fly.faa.gov) | 13K preferred routes | CSV | ✅ Cached |
| FAA TFR GeoServer | Active TFRs | WFS GeoJSON | ✅ Live |
| FAA SUA GeoServer | Special Use Airspace | WFS GeoJSON | ✅ Live |
| AWC (aviationweather.gov) | METARs, TAFs, PIREPs, SIGMETs, AIRMETs, G-AIRMETs, CWAs, ISIGMETs, TCF, MIS, stations | GeoJSON / JSON | ✅ Live |
| NWS mapservices | MRMS radar, SPC outlooks, W/W/A, NDFD temp, snow, smoke | ArcGIS REST | ✅ Tile overlays |
| IEM (Iowa State) | NEXRAD radar (XYZ tiles + WMS), GOES visible (WMS) | WMS / XYZ | ✅ Tile overlays |
| NASA GIBS | GOES-East IR satellite | WMTS | ✅ Tile overlay |
| EGM2008 geoid | MSL↔HAE conversion | PROJ vgridshift | ✅ Baked into image |
| Neo4j | Airway graph + route builder | Bolt | ✅ Running |

---

## Phase 1 — Surveillance + Identity (Weeks 1-2)

**Goal**: Live aircraft on the globe from real-world feeds.

| # | Source | Data | Auth | Adapter | Effort |
|---|---|---|---|---|---|
| 1a | **OpenSky Network** (live API) | ADS-B positions, global | Optional (higher rate) 🔑 | `surveillance/opensky.py` | 1 day |
| 1b | **FAA SWIM STDDS + SFDPS** | Surface surveillance + filed flight plans, US | SWIM creds 🔑 | `surveillance/swim.py` | 2 days |
| 1c | **FAA Aircraft Registration DB** | 280K N-numbers → Mode S hex → make/model/operator | None (public ZIP) | `ingest/faa_registration.py` | 1 day |
| 1d | **OpenSky Aircraft Database** | 460K global aircraft frames (supplements FAA for non-US) | None | `ingest/opensky_aircraft.py` | 0.5 day |
| 1e | **Comm-B Capability DB** (GitHub) | Mode S transponder capabilities per aircraft | None | Merge into registration tables | 0.5 day |

**Depends on**: Credential vault (✅ shipped).
**Unlocks**: Hybrid live+sim mode, position fusion, active-runway inference.

---

## Phase 2 — Worldwide Navdata (Weeks 2-4)

**Goal**: Route builder works globally, not just US.

| # | Source | Data | Auth | Adapter | Effort |
|---|---|---|---|---|---|
| 2a | **EUROCONTROL DDR2** | EU airways, waypoints, airports, airspace | OneSky login 🔑 | `ingest/ddr2/` (scaffolded) | 2 days (parser tuning) |
| 2b | **EUROCONTROL ADRR** | EU filed+actual flight trajectories (historic) | OneSky login 🔑 | `ingest/adrr/` | 2 days |
| 2c | **OpenAIP** | Global airports, airspace, navaids | Optional API key 🔑 | `ingest/openaip.py` | 1 day |
| 2d | **OurAirports** | Global airport list (CSV, public domain) | None | `ingest/ourairports.py` | 0.5 day |
| 2e | **EAD Basic** (European AIS) | EU aeronautical information pubs | Registration 🔑 | Reference only (manual) | — |
| 2f | **Virtual Radar Standing Data** (GitHub) | Non-US aircraft registration cross-ref | None | Merge into registration tables | 0.5 day |

**Conflict rule**: FAA > EUROCONTROL > OpenAIP > OurAirports (per feature, not per region).
**Depends on**: Phase 1c (registration DB as the identity backbone).
**Unlocks**: KDFW→EGLL routing, EU procedure visualization, worldwide traffic generation.

---

## Phase 3 — Performance + Schedules (Weeks 3-5)

**Goal**: Realistic aircraft performance + schedule-driven traffic.

| # | Source | Data | Auth | Adapter | Effort |
|---|---|---|---|---|---|
| 3a | **BADA 4** (GitHub) | Aircraft performance polynomials (thrust/drag/fuel) | EUPL (open) | `bluesky/traffic/performance/bada4/` | 3 days |
| 3b | **OPDI** (opdi.aero) | Flight phases + events from ADS-B (validation data) | None | Analysis scripts, not runtime | 1 day |
| 3c | **BTS T-100 + On-Time** | US airline schedules, delays, capacity | None (public CSV) | `ingest/bts_schedules.py` | 1 day |
| 3d | **Airline cargo schedules** (AA, LH, SQ, United CSVs) | Carrier-specific schedule downloads | None | `ingest/airline_schedules.py` | 1 day |
| 3e | **FAA Aircraft Characteristics DB** | BADA profiles, dimensions, wake category (Excel) | None | Merge into `aircraft_model` table | 0.5 day |
| 3f | **Boeing / Airbus planning docs** | Gate dimensions, runway requirements | None (PDFs) | Manual → `gate` table | Reference |
| 3g | **ICAO Engine Emissions DB** (EASA) | Engine emission data per type | None | `ingest/emissions.py` | 0.5 day |

**Depends on**: Phase 1c (aircraft identity for type→performance mapping).
**Unlocks**: Realistic climb/descent profiles, fuel-aware routing, traffic generation from real schedules, BADA 4 validation via OPDI.

---

## Phase 4 — Weather Depth + 3D Atmosphere (Weeks 4-6)

**Goal**: Volumetric weather, 3D wind fields, model-driven clouds.

| # | Source | Data | Auth | Adapter | Effort |
|---|---|---|---|---|---|
| 4a | **ERA5 / ECMWF CDS** | 3D wind/temp/humidity grids (hourly, global, 31 km) | Registration 🔑 | `weather/era5.py` | 2 days |
| 4b | **NOAA WAFS / WIFS** | Icing, turbulence, CB forecasts (gridded GRIB2) | Registration 🔑 | `weather/wafs.py` | 2 days |
| 4c | **Ogimet** | Historical METAR archive | None | Analysis/validation only | 0.5 day |
| 4d | **SACS Volcanic Ash** | Volcanic ash polygons | None | `weather/volcanic_ash.py` | 0.5 day |

**Depends on**: AWC baseline (✅ shipped), EGM2008 (✅ shipped).
**Unlocks**: 3D cloud rendering (Phase 1-4 from `project_3d_clouds.md`), volumetric turbulence/icing overlays, wind particle animation with real 3D wind data.

---

## Phase 5 — Airport Operations (Weeks 5-7)

**Goal**: Ground-level realism — gate assignments, runway configs, capacity.

| # | Source | Data | Auth | Adapter | Effort |
|---|---|---|---|---|---|
| 5a | **OSM Overpass API** | Airport gate positions, taxiway geometry, parking stands | None | `ingest/osm_airports.py` | 1 day |
| 5b | **EUROCONTROL Airport Corner** | Runway capacities, configurations per airport | Limited access 🔑 | `ingest/airport_capacity.py` | 1 day |
| 5c | **Airport APIs** (Schiphol, Finavia, Avinor, etc.) | Live departure/arrival boards, gate assignments | Per-API key 🔑 | `surveillance/airport_apis/` | 2 days (per airport) |
| 5d | **Helicopter chart GeoPDFs** (FAA aeronav) | Helo route chart tiles | None | `ingest/helo_charts.py` + GDAL (scaffolded) | 1 day |
| 5e | **Noise databases** (EANS, BruitParif, Explane) | Airport noise measurements | None | Future: noise layer | Reference |

**Depends on**: Phase 2 (worldwide airports), Phase 3 (schedules for demand).
**Unlocks**: Gate assignment in flow engine, realistic TRACON sequencing, ground movement, international active-runway tracking.

---

## Phase 6 — International Schedule Depth (Weeks 6-8)

**Goal**: Non-US schedule data for global traffic generation.

| # | Source | Data | Auth | Adapter | Effort |
|---|---|---|---|---|---|
| 6a | **ANAC Brazil** | Brazilian flight data since 2000 | None | `ingest/anac_brazil.py` | 0.5 day |
| 6b | **BITRE Australia** | Australian aviation statistics | None | `ingest/bitre_australia.py` | 0.5 day |
| 6c | **Hong Kong Airport** | Flight schedule + status | None (JSON API) | `ingest/hk_airport.py` | 0.5 day |
| 6d | **CARATS Japan** | Japanese trajectory data (2012-2016) | None | Research / validation | 0.5 day |
| 6e | **Indian flight schedule** (data.gov.in) | Indian scheduled flights | None | `ingest/india_schedule.py` | 0.5 day |
| 6f | **EUROCONTROL STATFOR** | EU traffic forecasts + network stats | Registration 🔑 | Analysis / scenario authoring | Reference |
| 6g | **Eurostat** | EU-wide transport statistics | None | Analysis | Reference |

**Depends on**: Phase 2 (worldwide navdata for airport resolution).
**Unlocks**: Global traffic generation beyond US + EU.

---

## Integration Architecture

Every source follows the same pattern:

```
Source endpoint
    │
    ▼
cesium_app/ingest/<source>.py     ← adapter (download + parse)
    │
    ├──▶ SQLite (canonical store, source-tagged)
    │
    ├──▶ Neo4j (derived graph, rebuilt from SQLite)
    │
    └──▶ bs.navdb (runtime, rebuilt on startup)
```

All adapters:
- Are self-contained (one file per source)
- Call `get_secret()` for credentials (vault-gated)
- Degrade to no-op if credentials missing
- Tag rows with `source='<SOURCE_NAME>'`
- Respect the conflict-resolution hierarchy (FAA > EUROCONTROL > OpenAIP > OurAirports)

CLI:
```bash
python -m cesium_app.ingest <source>       # individual
python -m cesium_app.ingest all            # everything
python -m cesium_app.ingest status         # freshness dashboard
```

---

## Effort Summary

| Phase | Scope | Estimated days | Key deliverable |
|---|---|---|---|
| 1 | Surveillance + Identity | 5 | Live aircraft on globe |
| 2 | Worldwide Navdata | 6 | Global route building |
| 3 | Performance + Schedules | 7 | BADA 4 + traffic generation |
| 4 | Weather Depth | 5 | 3D atmosphere |
| 5 | Airport Operations | 5 | Ground-level realism |
| 6 | International Schedules | 3 | Global traffic beyond US+EU |
| **Total** | | **~31 days** | |

Phases 1-3 are the critical path (18 days).
Phases 4-6 can be parallelized or deferred.

---

## Dependencies

```
Phase 1 (Surveillance)
    │
    ├──▶ Phase 2 (Worldwide Navdata)
    │       │
    │       └──▶ Phase 6 (Int'l Schedules)
    │
    └──▶ Phase 3 (Performance + Schedules)
            │
            └──▶ Phase 5 (Airport Ops)

Phase 4 (Weather) ← independent, can start anytime
```

---

## Data Volume Estimates

| Source | Raw size | In our DB | Refresh |
|---|---|---|---|
| FAA CIFP | 53 MB | 700 MB (compiled) | 28 days |
| FAA Registration | 40 MB | 30 MB | Weekly |
| OpenSky Aircraft DB | 50 MB | 40 MB | Monthly |
| DDR2 navdata | 200 MB | 100 MB | 28 days |
| ADRR trajectories | 5 GB/month | Analysis only | Quarterly |
| BTS schedules | 100 MB/year | 50 MB | Monthly |
| ERA5 weather grids | 2 GB/day | 500 MB (subset) | Hourly |
| OSM airport geometry | 10 MB/airport | 50 MB | Monthly |
| Live ADS-B | streaming | In-memory | Real-time |
| SQLite total (Phase 1-3) | | ~1 GB | |
| Neo4j total (Phase 1-3) | | ~500 MB | |
