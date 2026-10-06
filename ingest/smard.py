"""Pull SMARD generation data for one day and land it raw in Bronze.

Bronze rule: whatever the API returned, written untouched. No parsing, no
filtering, no type casting. That all happens in Silver. If the API shape
changes later, the raw file is the only thing that lets you reprocess.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.smard.de/app/chart_data"
REGION = "DE"
RESOLUTION = "hour"

# SMARD generation filter IDs. These are widely used but verify them on the
# first run with the sanity check in the README before trusting them.
FILTERS = {
    4068: "photovoltaik",
    4067: "wind_onshore",
    1225: "wind_offshore",
}

BRONZE = Path("data/bronze/smard")

log = logging.getLogger("ingest.smard")


def week_index(filter_id: int) -> list[int]:
    """SMARD publishes each series as weekly files.

    The index endpoint returns the start timestamp of every available week,
    in Unix milliseconds. You cannot request an arbitrary day directly: you
    pick the week that contains it, then fetch that file.
    """
    url = f"{BASE}/{filter_id}/{REGION}/index_{RESOLUTION}.json"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()["timestamps"]


def week_containing(timestamps: list[int], target: datetime) -> int:
    """Return the newest week start that is not after the target day."""
    target_ms = int(target.timestamp() * 1000)
    candidates = [t for t in timestamps if t <= target_ms]
    if not candidates:
        raise ValueError(f"SMARD has no week covering {target.date()}")
    return max(candidates)


def fetch_week(filter_id: int, week_start_ms: int) -> dict:
    """Fetch one weekly series file.

    Note the filter and region appear twice in the path, once as the folder
    and once inside the filename. The API rejects the request if they differ.
    """
    url = (
        f"{BASE}/{filter_id}/{REGION}/"
        f"{filter_id}_{REGION}_{RESOLUTION}_{week_start_ms}.json"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def land(payload: dict, filter_id: int, load_date: str) -> Path:
    """Write the response to the Bronze partition for this load date.

    Writing rather than appending is what makes the load idempotent: running
    the same date twice leaves you with the same file, not duplicate rows.
    """
    out_dir = BRONZE / f"load_date={load_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{FILTERS[filter_id]}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    # One hardcoded day on purpose. Date ranges and CLI arguments come later,
    # once a single day works end to end.
    day = datetime(2026, 9, 15, tzinfo=timezone.utc)
    load_date = day.date().isoformat()

    for filter_id in FILTERS:
        index = week_index(filter_id)
        week_start = week_containing(index, day)
        payload = fetch_week(filter_id, week_start)
        path = land(payload, filter_id, load_date)
        log.info(
            "landed %-14s points=%-4d -> %s",
            FILTERS[filter_id],
            len(payload.get("series", [])),
            path,
        )


if __name__ == "__main__":
    main()
