# NASA data sources: documentation report

Generated 2026-11-12 18:53 UTC from the ASTRA-MED store (`postgresql`). All figures are computed from stored records and synchronisation logs.

> ASTRA-MED is an independent research prototype. It is not affiliated with or endorsed by NASA. Crew data in ASTRA-MED are simulated; only the sources below are real.

## Data categories

| Category | Meaning |
| --- | --- |
| `measured` | Measured |
| `indicator` | Environmental indicator |
| `model` | Model output |
| `estimate` | Estimate |
| `simulated` | Simulated |
| `metadata` | Catalogue metadata |

## DONKI: Space Weather Database Of Notifications, Knowledge, Information

- **Provider:** NASA Community Coordinated Modeling Center (CCMC) and the Moon to Mars Space Weather Analysis Office
- **Homepage:** https://ccmc.gsfc.nasa.gov/tools/DONKI/
- **Endpoints (tried in order):** `https://api.nasa.gov/DONKI` (API key, server side); `https://ccmc.gsfc.nasa.gov/DONKI/WS/get`
- **Format:** JSON arrays, one object per event; UTC timestamps as YYYY-MM-DDTHH:MMZ
- **Categories:** indicator, model
- **Update frequency:** Event-driven, typically within hours of an event; polled every few hours
- **Units:** flare class: GOES 1-8 Å X-ray class (A/B/C/M/X); CME speed: km/s; Kp: planetary K index (0-9)
- **Licence / use:** NASA open data, provided by CCMC as a courtesy to the community, "as is" without warranty. (https://ccmc.gsfc.nasa.gov/tools/DONKI/)
- **Citation:** Data courtesy of the CCMC DONKI system (https://ccmc.gsfc.nasa.gov/tools/DONKI/). See the CCMC publication policy for acknowledgement wording.
- **Synchronisation:** 216 runs (ok 216); last run 2026-11-12 18:53 UTC (ok).
- **Records received / invalid / duplicates skipped:** 3,672 / 0 / 138
- **Successful runs by endpoint:** ccmc 216
- **Scientific limitations:**
  - CCMC states that real-time space weather information and simulations in DONKI should be considered prototyping quality and used in a research context.
  - NOAA's Space Weather Prediction Center is the official U.S. Government source for space weather forecasts and warnings; DONKI notifications are experimental.
  - Events are observed from near Earth (GOES, ACE, SOHO, SDO, STEREO). Their relevance to a spacecraft elsewhere in the solar system depends on its position.
  - DONKI records carry no particle flux, so solar energetic particle events cannot be given a NOAA S-scale level here.
  - An environmental event is never a dose: no astronaut dose is derived from DONKI records.

Stored: **3,289 events** (2014-09-17 to 2026-11-12) and **239 notifications**.

| Type | Events | First | Last | Classified (scale or class) | Unit of magnitude |
| --- | --- | --- | --- | --- | --- |
| FLR (Solar flare) | 640 | 2014-09-18 | 2026-11-11 | 640 | W/m² |
| CME (Coronal mass ejection) | 2,014 | 2014-09-17 | 2026-11-12 | 2,001 | km/s |
| SEP (Solar energetic particle event) | 59 | 2014-09-25 | 2026-09-05 | 0 | — |
| GST (Geomagnetic storm) | 36 | 2016-05-02 | 2026-10-31 | 36 | Kp |
| RBE (Radiation belt enhancement) | 79 | 2014-10-22 | 2026-11-08 | 0 | — |
| IPS (Interplanetary shock) | 63 | 2026-05-17 | 2026-10-25 | 0 | — |
| HSS (High-speed solar wind stream) | 35 | 2026-05-20 | 2026-11-11 | 0 | — |
| MPC (Magnetopause crossing) | 7 | 2026-06-11 | 2026-10-10 | 0 | — |
| WSA (WSA-ENLIL solar wind simulation) | 356 | 2026-07-11 | 2026-11-12 | 0 | Kp (modelled) |

Severity distribution (NOAA R for flares, NOAA G for storms, DONKI speed class for CMEs):

| Type | Level | Events |
| --- | --- | --- |
| CME | unclassified | 13 |
| CME | class 1 (minor) | 1,234 |
| CME | class 2 (moderate) | 678 |
| CME | class 3 (strong) | 85 |
| CME | class 4 (severe) | 4 |
| FLR | below scale | 147 |
| FLR | R1 (minor) | 423 |
| FLR | R2 (moderate) | 46 |
| FLR | R3 (strong) | 24 |
| GST | G1 (minor) | 1 |
| GST | G2 (moderate) | 23 |
| GST | G3 (strong) | 9 |
| GST | G4 (severe) | 3 |

Records by serving endpoint: ccmc 3,289.

## Environmental Data App (EDA): ISS cabin telemetry and radiation dosimetry

- **Provider:** NASA Open Science Data Repository (OSDR), Ames Research Center
- **Homepage:** https://visualization.osdr.nasa.gov/eda/
- **Endpoints (tried in order):** `https://visualization.osdr.nasa.gov/eda/api`
- **Format:** JSON arrays; telemetry at about 5-minute resolution, radiation as daily values; UTC ISO 8601 timestamps
- **Categories:** measured
- **Update frequency:** Historical releases per mission; changes rarely
- **Units:** temperature: °C; relative humidity: %; CO2: ppm; GCR / SAA / total dose: mGy/day (absorbed dose in water)
- **Licence / use:** Distributed under NASA's open access policy (NASA Science Mission Directorate Science Information Policy); a bibliographic citation is requested. (https://www.nasa.gov/reference/osdr-help-terms-and-conditions/)
- **Citation:** ISS environmental data courtesy of the NASA Open Science Data Repository Environmental Data App (https://visualization.osdr.nasa.gov/eda/).
- **Synchronisation:** 102 runs (ok 100, partial 2); last run 2026-11-12 18:53 UTC (ok).
- **Records received / invalid / duplicates skipped:** 8,287,902 / 2,868 / 870,370
- **Successful runs by endpoint:** eda-api 102
- **Scientific limitations:**
  - Historical measurements from specific Rodent Research and other ISS missions (2014 onward). This is not current ISS telemetry.
  - Radiation values are absorbed dose in water at the experiment location, from a preliminary analysis of ISS instruments by NASA-JSC's Space Radiation Analysis Group. They are not any astronaut's dose.
  - Days on the launch vehicle before transfer to the ISS are approximated from US Lab averages, not measured; they are flagged as approximate.
  - Telemetry sensors sit in the ISS cabin and in ground-control habitats near the rodent hardware; values describe those locations only.

Stored: **80,226 aggregated measurements** from 17 of 24 listed missions.

Unit check (one unit per quantity expected): co2_ppm → ppm; dose_gcr_mgy_day → mGy/day; dose_saa_mgy_day → mGy/day; dose_total_mgy_day → mGy/day; humidity_pct → %; temperature_c → °C.

Completeness is per distinct timestamp after merging rows that EDA splits across two records. Out-of-range values (for example relative humidity above 100 %) are excluded and counted.

| Mission | Period | ISS temperature | ISS humidity | ISS CO₂ | Out of range | Split rows merged | Conflicts | Gaps > 3× sampling | Dose days (approx.) | GCR+SAA = total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RR-1 | 2014-09-20 to 2014-11-01 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 6 | 39 (5) | ok |
| RR-3 | 2016-04-08 to 2016-05-28 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 6 | 43 (5) | ok |
| RR-4 | 2017-02-24 to 2017-03-14 | not recorded | not recorded | not recorded | 0 | 0 | 0 | 0 | 19 (1) | ok |
| RR-5 | 2017-06-01 to 2017-08-08 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 12 | — | — |
| RR-9 | 2017-08-18 to 2018-09-18 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 0 | 32 (1) | ok |
| RR-6 | 2017-12-06 to 2018-02-06 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 3 | 49 (5) | ok |
| RR-7 | 2018-06-29 to 2018-09-18 | 100.0% | 100.0% | 100.0% | 0 | 21,949 | 0 | 51 | 76 (6) | ok |
| RR-8 | 2018-12-05 to 2019-01-13 | not recorded | not recorded | not recorded | 0 | 0 | 0 | 0 | 40 (6) | ok |
| RR-12 | 2019-04-17 to 2019-05-28 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 3 | 37 (5) | ok |
| RR-17 | 2019-07-25 to 2019-09-20 | not recorded | not recorded | not recorded | 0 | 0 | 0 | 0 | 58 (5) | ok |
| RR-19 | 2019-12-03 to 2020-01-08 | 100.0% | 100.0% | 100.0% | 0 | 0 | 0 | 3 | 35 (5) | ok |
| RR-10 | 2020-12-04 to 2021-01-03 | 100.0% | 100.0% | 88.4% | 0 | 43,103 | 0 | 8 | — | — |
| RR-23 | 2020-12-06 to 2021-01-15 | 91.9% | 91.9% | 82.7% | 0 | 0 | 0 | 1,540 | 39 (4) | ok |
| RR-18 | 2021-12-20 to 2022-02-28 | 100.0% | 98.6% | all null | 1,434 | 46,663 | 0 | 28 | — | — |
| RR-25 | 2022-11-29 to 2023-02-02 | 88.5% | all null | all null | 0 | 0 | 0 | 1,045 | — | — |
| RR-20 | 2023-11-21 to 2024-01-07 | 77.4% | all null | all null | 0 | 3 | 2 | 1,144 | — | — |
| RR-28 | 2024-03-24 to 2024-05-06 | 90.4% | all null | all null | 0 | 7 | 0 | 216 | — | — |
| VEG-01A | no usable values: all 51,270 published readings are null | — | — | — | — | — | — | — | — | — |
| APEX-03-1 | no usable values: all 16,302 published readings are null | — | — | — | — | — | — | — | — | — |
| APEX-03-2 | no usable values: all 14,580 published readings are null | — | — | — | — | — | — | — | — | — |
| VEG-01C | no usable values: all 482,328 published readings are null | — | — | — | — | — | — | — | — | — |
| APEX-04 | no usable values: all 21,240 published readings are null | — | — | — | — | — | — | — | — | — |
| RR-22 | no telemetry or dosimetry published | — | — | — | — | — | — | — | — | — |
| VEG-01B | no telemetry or dosimetry published | — | — | — | — | — | — | — | — | — |

## Open Science Data Repository (OSDR) study catalogue

- **Provider:** NASA Open Science Data Repository, Ames Research Center
- **Homepage:** https://osdr.nasa.gov/bio/repo/
- **Endpoints (tried in order):** `https://osdr.nasa.gov/osdr/data/search`
- **Format:** JSON search results (one record per study)
- **Categories:** metadata
- **Update frequency:** New studies are released continuously; catalogue refreshed daily
- **Licence / use:** Distributed under NASA's open access policy; cite each study using the citation in its OSDR record. (https://www.nasa.gov/reference/osdr-help-terms-and-conditions/)
- **Citation:** Study metadata courtesy of the NASA Open Science Data Repository (https://osdr.nasa.gov/bio/repo/). Cite individual studies with their OSDR citation.
- **Synchronisation:** 25 runs (ok 25); last run 2026-11-12 18:53 UTC (ok).
- **Records received / invalid / duplicates skipped:** 1,140 / 0 / 0
- **Successful runs by endpoint:** osdr-search 25
- **Scientific limitations:**
  - Only study metadata is ingested (titles, organisms, missions, assays); no study data files are downloaded.
  - Most studies concern cells, plants or rodents, or ground radiation exposures. They inform context, not crew physiology.

Stored: **188 studies** (metadata only).

| Topic preset | OSDR search term | Studies stored |
| --- | --- | --- |
| Radiation-related biological studies | `radiation` | 50 |
| Rodent research | `rodent research` | 50 |
| Spaceflight biological experiments | `spaceflight` | 50 |
| Physiological research | `cardiovascular` | 28 |
| Environmental monitoring | `environmental monitoring` | 50 |

Project types: Spaceflight Study 125, Ground Study 61, Suborbital Flight Study 1, Spaceflight 1.
Studies linked to EDA missions: APEX-03-1 1, APEX-04 2, APEX-08 1, RR-1 11, RR-12 1, RR-17 4, RR-18 4, RR-19 1, RR-23 4, RR-3 4, RR-4 1, RR-5 3, RR-6 5, RR-7 1, RR-8 21, RR-9 8, VEG-05 1.

## Timestamp checks

All timestamps are stored and served as UTC (timezone-aware columns; DONKI and EDA document UTC). The dashboard converts to the selected display zone only when rendering.

| Table | Earliest | Latest | Rows |
| --- | --- | --- | --- |
| `space_weather_events.start_time` | 2014-09-17 15:25 | 2026-11-12 02:24 | 3,289 |
| `space_notifications.issue_time` | 2026-07-11 17:44 | 2026-11-11 21:02 | 239 |
| `env_measurements.ts` | 2014-09-20 03:00 | 2024-05-06 13:00 | 80,226 |
| `osdr_studies.release_date` | 2007-11-01 07:00 | 2026-10-28 00:00 | 188 |

Events dated in the future (should be none except model predictions): 0.

## Evaluated but not integrated

- **RadLab Portal and Data API** (https://visualization.osdr.nasa.gov/radlab/): Not integrated: the portal returned HTTP 500 on 2026-11-12, and the API needs detector-specific query parameters.
- **OSDR Biological Data API** (https://visualization.osdr.nasa.gov/biodata/api/): Reachable. Serves per-study sample and assay data; not needed beyond the catalogue for this phase.
- **Other NASA Open APIs (APOD, NeoWs, EONET, EPIC, Mars rover photos)** (https://api.nasa.gov/): Not relevant to crew radiation or space weather; not integrated.
- **NASA Life Sciences Data Archive (LSDA)** (https://nlsp.nasa.gov/explore/lsdahome): Crew physiology archives are restricted and need a data request; not used.

