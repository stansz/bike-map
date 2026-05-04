# Cycling Routes — Stats Canada Can-BICS Network

Cycling infrastructure data from the [Canadian Cycling Network Database](https://www150.statcan.gc.ca/n1/pub/23-26-0004/232600042024001-eng.htm) (Stats Canada, 2024). Covers 75 municipalities nationwide, classified using Can-BICS (Canadian Bikeway Comfort and Safety) standards.

## Data

| File | Size | Source |
|---|---|---|
| `data/cycle_network_2024.gpkg` | 46MB | Stats Canada (GeoPackage, spatially indexed) |
| `data/canadian_cycling_network_database.zip` | 23MB | Original download archive |

**Table:** `canbics_2024` — 82,115 rows (10,994 in BC)

### Key Columns

| Column | Type | Description |
|---|---|---|
| `geom` | MULTILINESTRING | Route geometry |
| `province_territory` | TEXT | 'bc', 'on', 'qc', etc. |
| `municipality` | TEXT | City name |
| `canbics_class` | TEXT | Can-BICS classification |
| `source_class` | TEXT | Original municipal classification |
| `surface_type` | TEXT | Paved, gravel, etc. |
| `length_km` | REAL | Segment length |
| `csdname` | TEXT | Census subdivision |

### Can-BICS Classes

| Class | Comfort | Color | Description |
|---|---|---|---|
| `cycle_track` | High | Green | Protected bike lane, physical separation |
| `bike_path` | High | Green | Off-road dedicated path |
| `multi_use_path` | High | Teal | Shared path (peds + bikes) |
| `painted_bike_lane` | Medium | Yellow | Painted lane on road |
| `local_street_bikeway` | Medium | Blue | Traffic-calmed residential street |
| `shared_roadway` | Low | Orange | Shared with cars, no separation |
| `major_shared_roadway` | Low | Red | Shared on arterial road |
| `gravel_trail` | Unpaved | Brown | Gravel/dirt trail |

### BC Coverage

| Municipality | Segments | km |
|---|---|---|
| Surrey | 1,427 | 594.6 |
| Kelowna | 1,859 | 422.5 |
| Vancouver | 3,571 | 333.0 |
| North Vancouver | 700 | 161.4 |
| Coquitlam | 188 | 80.5 |
| Burnaby | 414 | 79.5 |
| Victoria | 425 | 60.8 |
| + 14 more cities | | |
| **Total BC** | **10,994** | **2,919** |

## Geo-API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/cycling/routes` | Routes near lat/lon, filtered by class/municipality |
| `GET /api/cycling/bbox` | Routes in bounding box (map rendering) |
| `GET /api/cycling/stats` | Summary: km per municipality, per class |
| `GET /api/cycling/municipalities` | List available BC municipalities |

Returns GeoJSON FeatureCollection with LineString features.

## Data Flow

```
cycle_network_2024.gpkg (GeoPackage/SQLite)
  ↑ queried directly, no import needed
  |
geo-api.py (/api/cycling/*)
  ↑
transit.ogsapps.cc / elevation.ogsapps.cc / sea.ogsapps.cc (Leaflet map)
```

## Frontend Integration (Phase 2)

- Toggle cycling layer on map (like trails/ferries on sea chart)
- Color by Can-BICS comfort level
- Filter by municipality, class
- Click segment for details (class, surface, length, municipality)

## Data Refresh

- Stats Canada published Jan 2025 (data collected Nov 2023–Feb 2024)
- Check for updates annually at: https://www150.statcan.gc.ca/n1/pub/23-26-0004/232600042024001-eng.htm
- Replace `cycle_network_2024.gpkg` — no rebuild/import needed

## Gotchas

- GPKG uses lowercase province codes: `'bc'` not `'British Columbia'`
- `length_km` can be NULL on some records — use COALESCE
- GPKG has rtree spatial index tables — use them for bbox queries
- No import needed — geo-api queries the GPKG file directly
- Data is under Open Government License - Canada (free to use)
