"""Pull Open-Meteo hourly history for a few German locations into Bronze.

Same Bronze rules as the SMARD loader: land the response untouched, one file
per location, overwrite rather than append so a re-run is safe.

Two deliberate choices worth knowing about:

  1. Timezone. Open-Meteo will return timestamps in whatever timezone you ask
     for. We ask for UTC. SMARD gives epoch milliseconds, which are already
     absolute. Both sides therefore land as unambiguous instants and the join
     in Silver is a straight equality rather than a guess.

  2. Date range. We pull a day either side of the SMARD week rather than
     trimming to it. Bronze overfetches; Silver decides what counts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

BASE = "https://archive-api.open-meteo.com/v1/archive"

# Spread north to south. Hamburg is wind country, Munich is the solar end,
# Leipzig sits between them.
LOCATIONS = {
    "hamburg": (53.5511, 9.9937),
    "leipzig": (51.3397, 12.3731),
    "muenchen": (48.1374, 11.5755),
}

# shortwave_radiation drives photovoltaic output, wind_speed_100m is near
# turbine hub height, and cloud_cover gives you something readable on a chart.
HOURLY = [
    "temperature_2m",
    "cloud_cover",
    "shortwave_radiation",
    "wind_speed_100m",
]

START_DATE = "2026-09-13"
END_DATE = "2026-09-21"

BRONZE = Path("data/bronze/weather")

log = logging.getLogger("ingest.weather")


def fetch_location(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": ",".join(HOURLY),
        "timezone": "UTC",
    }
    response = requests.get(BASE, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def land(payload: dict, name: str, load_date: str) -> Path:
    out_dir = BRONZE / f"load_date={load_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    # Matches the SMARD load so the two land in the same partition.
    load_date = "2026-09-15"

    for name, (lat, lon) in LOCATIONS.items():
        payload = fetch_location(lat, lon)
        path = land(payload, name, load_date)
        hours = len(payload.get("hourly", {}).get("time", []))
        log.info("landed %-10s hours=%-5d -> %s", name, hours, path)


if __name__ == "__main__":
    main()
