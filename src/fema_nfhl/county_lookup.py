"""County FIPS/GEOID lookup helpers for FEMA NFHL package selection."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable


COUNTY_LOOKUP_SOURCE = (
    "U.S. Census Bureau 2025 County Adjacency File: "
    "https://www2.census.gov/geo/docs/reference/county_adjacency/county_adjacency2025.txt"
)

COUNTY_SUFFIX_PATTERN = re.compile(
    r"\b(county|parish|borough|census area|city and borough|municipio|municipality|planning region|district)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class CountyRecord:
    """A county or county-equivalent FIPS lookup record."""

    state: str
    state_abbr: str
    state_fips: str
    county_name: str
    county_fips: str
    geoid: str
    census_name: str
    source_year: str


def _data_path() -> Path:
    """Return the packaged county lookup CSV path."""

    return Path(str(resources.files("fema_nfhl").joinpath("data", "county_fips_2025.csv")))


def normalize_lookup_text(value: str) -> str:
    """Normalize a state or county string for forgiving lookup."""

    normalized = re.sub(r"[^A-Za-z0-9]+", " ", value or "").strip().upper()
    return re.sub(r"\s+", " ", normalized)


def simplify_county_name(value: str) -> str:
    """Normalize county names while allowing users to omit common suffixes."""

    without_suffix = COUNTY_SUFFIX_PATTERN.sub(" ", value or "")
    return normalize_lookup_text(without_suffix)


def load_counties(path: Path | None = None) -> list[CountyRecord]:
    """Load the packaged county FIPS lookup table."""

    lookup_path = path or _data_path()
    with lookup_path.open(newline="", encoding="utf-8") as handle:
        return [CountyRecord(**row) for row in csv.DictReader(handle)]


def _state_matches(record: CountyRecord, state: str | None) -> bool:
    if not state:
        return True
    state_key = normalize_lookup_text(state)
    return state_key in {
        normalize_lookup_text(record.state),
        normalize_lookup_text(record.state_abbr),
        normalize_lookup_text(record.state_fips),
    }


def _county_score(record: CountyRecord, county: str | None) -> int | None:
    if not county:
        return 0
    county_key = simplify_county_name(county)
    record_key = simplify_county_name(record.county_name)
    record_full = normalize_lookup_text(record.county_name)
    if county_key == record_key or normalize_lookup_text(county) == record_full:
        return 0
    if record_key.startswith(county_key):
        return 1
    if county_key in record_key:
        return 2
    return None


def search_counties(
    *,
    state: str | None = None,
    county: str | None = None,
    records: Iterable[CountyRecord] | None = None,
    limit: int = 20,
) -> list[CountyRecord]:
    """Search county records by state and/or county name."""

    source = list(records) if records is not None else load_counties()
    scored: list[tuple[int, CountyRecord]] = []
    for record in source:
        if not _state_matches(record, state):
            continue
        score = _county_score(record, county)
        if score is not None:
            scored.append((score, record))
    scored.sort(key=lambda item: (item[0], item[1].state, item[1].county_name, item[1].geoid))
    return [record for _, record in scored[:limit]]


def resolve_county_fips(
    *,
    state: str,
    county: str,
    records: Iterable[CountyRecord] | None = None,
) -> CountyRecord:
    """Resolve a single county to its five-digit Census/FEMA county GEOID."""

    source = list(records) if records is not None else load_counties()
    matches = search_counties(state=state, county=county, records=source, limit=50)
    exact_matches = [
        record
        for record in matches
        if simplify_county_name(record.county_name) == simplify_county_name(county)
        or normalize_lookup_text(record.county_name) == normalize_lookup_text(county)
    ]
    candidates = exact_matches or matches
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        examples = search_counties(state=state, records=source, limit=5)
        suffix = _format_suggestions(examples)
        raise ValueError(f"No county FIPS match found for county={county!r}, state={state!r}.{suffix}")
    suffix = _format_suggestions(candidates[:10])
    raise ValueError(f"County lookup was ambiguous for county={county!r}, state={state!r}.{suffix}")


def _format_suggestions(records: Iterable[CountyRecord]) -> str:
    suggestions = [f"{record.county_name}, {record.state_abbr} -> {record.geoid}" for record in records]
    if not suggestions:
        return ""
    return " Candidates: " + "; ".join(suggestions)


def records_to_csv(records: Iterable[CountyRecord]) -> str:
    """Format county records as CSV text."""

    rows = ["state,state_abbr,county_name,geoid,fema_zip_prefix"]
    rows.extend(
        f"{record.state},{record.state_abbr},{record.county_name},{record.geoid},{record.geoid}" for record in records
    )
    return "\n".join(rows)
