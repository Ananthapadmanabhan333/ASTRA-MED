"""Data categories and the registry of external sources.

Every value the space module serves carries one category so measurements, indicators, model
output, estimates and simulations are never mixed:

* ``measured``  - an instrument reading (for example ISS dosimetry or cabin telemetry).
* ``indicator`` - an environmental event or index (a solar flare, a geomagnetic storm). It says
  something about the environment, never about any person's dose.
* ``model``     - output of a space-weather model run (WSA-ENLIL), not an observation.
* ``estimate``  - a value derived from published measurements for a hypothetical situation.
* ``simulated`` - produced by the ASTRA-MED simulator.
* ``metadata``  - catalogue records (study descriptions), not measurements.

The usage notes below paraphrase the providers' own pages as read on 2026-11-12; the linked
pages are authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal["measured", "indicator", "model", "estimate", "simulated", "metadata"]

CATEGORY_LABELS: dict[str, str] = {
    "measured": "Measured",
    "indicator": "Environmental indicator",
    "model": "Model output",
    "estimate": "Estimate",
    "simulated": "Simulated",
    "metadata": "Catalogue metadata",
}


@dataclass(frozen=True)
class Endpoint:
    name: str
    base_url: str
    needs_key: bool = False
    note: str = ""


@dataclass(frozen=True)
class SourceInfo:
    id: str
    name: str
    provider: str
    homepage: str
    endpoints: tuple[Endpoint, ...]
    data_format: str
    categories: tuple[Category, ...]
    update_frequency: str
    units: dict[str, str]
    license: str
    license_url: str
    citation: str
    caveats: tuple[str, ...] = field(default_factory=tuple)


DONKI = SourceInfo(
    id="donki",
    name="DONKI: Space Weather Database Of Notifications, Knowledge, Information",
    provider="NASA Community Coordinated Modeling Center (CCMC) and the Moon to Mars Space Weather Analysis Office",
    homepage="https://ccmc.gsfc.nasa.gov/tools/DONKI/",
    endpoints=(
        Endpoint("api.nasa.gov", "https://api.nasa.gov/DONKI", needs_key=True,
                 note="NASA Open APIs gateway; requires an API key (DEMO_KEY is heavily rate limited)."),
        Endpoint("ccmc", "https://ccmc.gsfc.nasa.gov/DONKI/WS/get", needs_key=False,
                 note="Official CCMC web service. DONKI moved here on 2026-09-30 (previously kauai.ccmc.gsfc.nasa.gov)."),
    ),
    data_format="JSON arrays, one object per event; UTC timestamps as YYYY-MM-DDTHH:MMZ",
    categories=("indicator", "model"),
    update_frequency="Event-driven, typically within hours of an event; polled every few hours",
    units={"flare class": "GOES 1-8 Å X-ray class (A/B/C/M/X)", "CME speed": "km/s", "Kp": "planetary K index (0-9)"},
    license="NASA open data, provided by CCMC as a courtesy to the community, \"as is\" without warranty.",
    license_url="https://ccmc.gsfc.nasa.gov/tools/DONKI/",
    citation="Data courtesy of the CCMC DONKI system (https://ccmc.gsfc.nasa.gov/tools/DONKI/). See the CCMC publication policy for acknowledgement wording.",
    caveats=(
        "CCMC states that real-time space weather information and simulations in DONKI should be considered prototyping quality and used in a research context.",
        "NOAA's Space Weather Prediction Center is the official U.S. Government source for space weather forecasts and warnings; DONKI notifications are experimental.",
        "Events are observed from near Earth (GOES, ACE, SOHO, SDO, STEREO). Their relevance to a spacecraft elsewhere in the solar system depends on its position.",
        "DONKI records carry no particle flux, so solar energetic particle events cannot be given a NOAA S-scale level here.",
        "An environmental event is never a dose: no astronaut dose is derived from DONKI records.",
    ),
)

EDA = SourceInfo(
    id="eda",
    name="Environmental Data App (EDA): ISS cabin telemetry and radiation dosimetry",
    provider="NASA Open Science Data Repository (OSDR), Ames Research Center",
    homepage="https://visualization.osdr.nasa.gov/eda/",
    endpoints=(Endpoint("eda-api", "https://visualization.osdr.nasa.gov/eda/api"),),
    data_format="JSON arrays; telemetry at about 5-minute resolution, radiation as daily values; UTC ISO 8601 timestamps",
    categories=("measured",),
    update_frequency="Historical releases per mission; changes rarely",
    units={
        "temperature": "°C", "relative humidity": "%", "CO2": "ppm",
        "GCR / SAA / total dose": "mGy/day (absorbed dose in water)",
    },
    license="Distributed under NASA's open access policy (NASA Science Mission Directorate Science Information Policy); a bibliographic citation is requested.",
    license_url="https://www.nasa.gov/reference/osdr-help-terms-and-conditions/",
    citation="ISS environmental data courtesy of the NASA Open Science Data Repository Environmental Data App (https://visualization.osdr.nasa.gov/eda/).",
    caveats=(
        "Historical measurements from specific Rodent Research and other ISS missions (2014 onward). This is not current ISS telemetry.",
        "Radiation values are absorbed dose in water at the experiment location, from a preliminary analysis of ISS instruments by NASA-JSC's Space Radiation Analysis Group. They are not any astronaut's dose.",
        "Days on the launch vehicle before transfer to the ISS are approximated from US Lab averages, not measured; they are flagged as approximate.",
        "Telemetry sensors sit in the ISS cabin and in ground-control habitats near the rodent hardware; values describe those locations only.",
    ),
)

OSDR = SourceInfo(
    id="osdr",
    name="Open Science Data Repository (OSDR) study catalogue",
    provider="NASA Open Science Data Repository, Ames Research Center",
    homepage="https://osdr.nasa.gov/bio/repo/",
    endpoints=(Endpoint("osdr-search", "https://osdr.nasa.gov/osdr/data/search"),),
    data_format="JSON search results (one record per study)",
    categories=("metadata",),
    update_frequency="New studies are released continuously; catalogue refreshed daily",
    units={},
    license="Distributed under NASA's open access policy; cite each study using the citation in its OSDR record.",
    license_url="https://www.nasa.gov/reference/osdr-help-terms-and-conditions/",
    citation="Study metadata courtesy of the NASA Open Science Data Repository (https://osdr.nasa.gov/bio/repo/). Cite individual studies with their OSDR citation.",
    caveats=(
        "Only study metadata is ingested (titles, organisms, missions, assays); no study data files are downloaded.",
        "Most studies concern cells, plants or rodents, or ground radiation exposures. They inform context, not crew physiology.",
    ),
)

SOURCES: dict[str, SourceInfo] = {s.id: s for s in (DONKI, EDA, OSDR)}

# Evaluated but not integrated (recorded so the inventory is complete).
EVALUATED_SOURCES: list[dict[str, str]] = [
    {
        "name": "RadLab Portal and Data API",
        "url": "https://visualization.osdr.nasa.gov/radlab/",
        "status": "Not integrated: the portal returned HTTP 500 on 2026-11-12, and the API needs detector-specific query parameters.",
    },
    {
        "name": "OSDR Biological Data API",
        "url": "https://visualization.osdr.nasa.gov/biodata/api/",
        "status": "Reachable. Serves per-study sample and assay data; not needed beyond the catalogue for this phase.",
    },
    {
        "name": "Other NASA Open APIs (APOD, NeoWs, EONET, EPIC, Mars rover photos)",
        "url": "https://api.nasa.gov/",
        "status": "Not relevant to crew radiation or space weather; not integrated.",
    },
    {
        "name": "NASA Life Sciences Data Archive (LSDA)",
        "url": "https://nlsp.nasa.gov/explore/lsdahome",
        "status": "Crew physiology archives are restricted and need a data request; not used.",
    },
]
