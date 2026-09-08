"""Synthetic regressions for FEMA zone distinctions and elevation display."""

import json
import re

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from fema_nfhl.mapping import (
    build_flood_popup_rows,
    categorize_flood_hazard,
    create_interactive_map,
    format_elevation,
)


@pytest.mark.parametrize("subtype,category", [
    ("1 PCT DEPTH LESS THAN 1 FOOT", "shallow_one_percent"),
    ("1 PERCENT DRAINAGE AREA LESS THAN 1 SQUARE MILE", "small_drainage"),
    ("1-PCT DEPTH LESS THAN 1 FOOT", "shallow_one_percent"),
    (" 1%  DRAINAGE AREA LESS THAN 1 SQUARE MILE ", "small_drainage"),
    ("0.2-PCT-ANNUAL-CHANCE FLOOD HAZARD", "zero_two_percent"),
    ("0.2% ANNUAL CHANCE FLOOD HAZARD CONTAINED IN CHANNEL", "zero_two_percent"),
    ("0.2 PERCENT ANNUAL CHANCE FLOOD HAZARD IN COASTAL ZONE", "zero_two_percent"),
    ("1 PCT FUTURE CONDITIONS, FLOODWAY", "future_conditions"),
    ("1 PCT FUTURE CONDITONS, COMMUNITY ENCROACHMENT", "future_conditions"),
    ("AREA WITH REDUCED FLOOD RISK DUE TO LEVEE", "reduced_levee"),
    ("AREA WITH REDUCED FLOOD HAZARD DUE TO LEVEE SYSTEM", "reduced_levee"),
    ("AREA WITH REDUCED FLOOD HAZARD DUE TO ACCREDITED LEVEE SYSTEM", "reduced_levee"),
    ("AREA WITH REDUCED FLOOD HAZARD DUE TO PROVISIONALLY ACCREDITED LEVEE SYSTEM", "reduced_levee"),
    ("AREA OF MINIMAL FLOOD HAZARD", "minimal"),
    ("AREAS DETERMINED TO BE OUTSIDE THE 0.2 PCT ANNUAL CHANCE FLOODPLAIN", "minimal"),
])
def test_zone_x_documented_designations(subtype, category):
    assert categorize_flood_hazard("X", subtype).key == category


@pytest.mark.parametrize("subtype", [
    None, "", "  ", float("nan"), pd.NA, "<Null>", "-9999", "UNKNOWN", "SHADED",
    "UNSHADED OR SHADED", "NOT AREA OF MINIMAL FLOOD HAZARD", "NOT 0.2 PCT FLOOD HAZARD",
    "0.2 PCT ANNUAL CHANCE FLOOD HAZARD / AREA OF MINIMAL FLOOD HAZARD",
    "AREA WITH REDUCED FLOOD HAZARD DUE TO NON-ACCREDITED LEVEE SYSTEM",
    "FLOODWAY", "AREA WITH UNDETERMINED FLOOD HAZARD DUE TO NON-ACCREDITED LEVEE SYSTEM",
])
def test_zone_x_missing_ambiguous_or_unrecognized_is_explicit(subtype):
    category = categorize_flood_hazard("X", subtype)
    assert category.key == "unresolved_x"
    assert "Zone X" in category.label
    assert category.key != categorize_flood_hazard("D", None).key


@pytest.mark.parametrize("zone,subtype,category", [
    ("A", None, "one_percent"), ("AE", "FLOODWAY", "regulatory_floodway"),
    ("AH", None, "one_percent"), ("AO", None, "one_percent"),
    ("AR", None, "one_percent"), ("A99", None, "one_percent"),
    ("V", None, "coastal_high_hazard"), ("VE", None, "coastal_high_hazard"),
    ("D", None, "undetermined"), ("D", "AREA WITH FLOOD RISK DUE TO LEVEE", "levee_risk"),
    ("OPEN WATER", None, "open_water"), ("AREA NOT INCLUDED", None, "other"),
])
def test_other_existing_zone_behavior_preserved(zone, subtype, category):
    assert categorize_flood_hazard(zone, subtype).key == category


@pytest.mark.parametrize("subtype", ["1 PCT DEPTH LESS THAN 1 FOOT", None])
def test_zone_x_popup_keeps_source_sfha_and_does_not_infer_minimal(subtype):
    props = {"FLD_ZONE": "X", "ZONE_SUBTY": subtype, "SFHA_TF": "F"}
    original = props.copy()
    rows = build_flood_popup_rows(props)
    assert props == original
    assert ("Special Flood Hazard Area", "No") in rows
    assert ("Flood Hazard Category", "Minimal Flood Hazard") not in rows
    assert ("Flood Hazard Category", "0.2% Annual Chance Flood Hazard") not in rows
    if subtype is None:
        assert any(label == "Interpretation" and "subtype" in text.lower() for label, text in rows)


@pytest.mark.parametrize("value", [-9999, " -9999.0 ", -8888, "-8888.00"])
def test_elevation_display_hides_documented_codes(value):
    assert format_elevation(value, "Feet") is None


@pytest.mark.parametrize("value,expected", [(0, "0 ft"), ("0", "0 ft"), (-2.5, "-2.5 ft"), ("-12", "-12 ft")])
def test_elevation_display_preserves_valid_zero_and_negative(value, expected):
    assert format_elevation(value, "Feet") == expected


def test_map_serializes_correct_categories_and_preserves_raw_attributes(tmp_path):
    flood = gpd.GeoDataFrame({
        "FLD_ZONE": ["X"] * 4,
        "ZONE_SUBTY": ["1 PCT DEPTH LESS THAN 1 FOOT", "1 PCT DRAINAGE AREA LESS THAN 1 SQUARE MILE",
                       None, "AREA OF MINIMAL FLOOD HAZARD"],
        "SFHA_TF": ["F"] * 4,
        "STATIC_BFE": [-8888, -9999, 0, -3],
    }, geometry=[box(-122 + i * .02, 37, -121.99 + i * .02, 37.01) for i in range(4)], crs=4326)
    flood.to_file(tmp_path / "S_FLD_HAZ_AR.shp")
    output = create_interactive_map(tmp_path, tmp_path / "map.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"const floodData = (.*);", output).group(1))
    props = [feature["properties"] for feature in data["features"]]
    assert [p["_nfhl_category"] for p in props] == ["shallow_one_percent", "small_drainage", "unresolved_x", "minimal"]
    assert [p["STATIC_BFE"] for p in props] == [-8888, -9999, 0, -3]
    assert all(p["SFHA_TF"] == "F" for p in props)
    for label in ["Shallow 1% Flooding (Zone X)", "Small Drainage Area 1% Flooding (Zone X)", "Unresolved Zone X"]:
        assert f"Grouped: {label}" in output
