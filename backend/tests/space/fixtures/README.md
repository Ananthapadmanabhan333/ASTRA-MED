# Test fixtures: real NASA open data excerpts

Trimmed from live responses retrieved on 2026-11-12. NASA open data; see docs/NASA_DATA_SOURCES.md
for licensing and citation.

| File | Source |
| --- | --- |
| donki_*.json | CCMC DONKI web service, https://ccmc.gsfc.nasa.gov/DONKI/WS/get/{type} (GST and SEP from May-June 2024; others 2026-10-13..2026-11-12) |
| eda_missions.json, eda_radiation_RR-1.json | OSDR Environmental Data App API, https://visualization.osdr.nasa.gov/eda/api/missions/ |
| eda_telemetry_RR-1.json | EDA telemetry_data for RR-1, first 300 records. Three records are deliberately corrupted for the quality tests: index 10 temperature_iss = 999, index 11 humidity_iss = null, and a duplicate of index 20 appended at the end. |
| osdr_search.json | OSDR search API, term "rodent research", first 3 hits |
