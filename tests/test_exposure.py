from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Polygon, box

from fema_nfhl.exposure import floodplain_area_summary, select_admin_field
from fema_nfhl.utils import safe_percent


def test_select_admin_field_prefers_known_candidates() -> None:
    field = select_admin_field(["OBJECTID", "GEOID", "NAME"], ["FIPS", "GEOID"])

    assert field == "GEOID"


def test_safe_percent_handles_zero_denominator() -> None:
    assert safe_percent(10, 0) == 0.0
    assert safe_percent(5, 20) == 25.0


@pytest.fixture
def summarize(tmp_path, monkeypatch):
    """Exercise the real overlay/CSV path with deterministic synthetic metre geometry."""

    def run(flood_rows, admin_rows=None, *, source_crs="EPSG:5070", **kwargs):
        flood = gpd.GeoDataFrame(flood_rows, columns=list(flood_rows[0]) if flood_rows else ["geometry"], crs=source_crs)
        if admin_rows is None:
            admin_rows = [{"GEOID": "001", "NAME": "Example", "geometry": box(0, 0, 200, 100)}]
        admin = gpd.GeoDataFrame(admin_rows, columns=list(admin_rows[0]) if admin_rows else ["geometry"], crs=source_crs)
        layers = {"flood.gpkg": flood, "admin.gpkg": admin}
        monkeypatch.setattr(gpd, "read_file", lambda path: layers[Path(path).name].copy())
        output = floodplain_area_summary("flood.gpkg", "admin.gpkg", tmp_path / "areas.csv", **kwargs)
        return pd.read_csv(output, dtype={"admin_id": str})

    return run


def flood_record(geometry, *, zone="X", subtype="AREA OF MINIMAL FLOOD HAZARD", **attributes):
    return {"FLD_ZONE": zone, "ZONE_SUBTY": subtype, **attributes, "geometry": geometry}


def test_disjoint_zone_reporting_and_csv_schema_are_unchanged(summarize) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 100), zone="AE", subtype=None),
        flood_record(box(100, 0, 200, 100)),
    ])

    assert list(result.columns) == [
        "admin_id", "admin_name", "fld_zone", "zone_subty",
        "flood_area_sq_km", "admin_area_sq_km", "flood_area_percent",
    ]
    assert result["fld_zone"].tolist() == ["AE", "X"]
    assert result["flood_area_sq_km"].tolist() == pytest.approx([0.01, 0.01])
    assert result["admin_area_sq_km"].tolist() == pytest.approx([0.02, 0.02])
    assert result["flood_area_percent"].tolist() == pytest.approx([50, 50])
    assert pd.isna(result.loc[0, "zone_subty"])


@pytest.mark.parametrize("second, expected", [
    (box(0, 0, 100, 100), 0.01),
    (box(50, 0, 150, 100), 0.015),
])
def test_same_category_duplicates_and_overlaps_are_unioned(summarize, second, expected) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 100), FLD_AR_ID="one"),
        flood_record(second, FLD_AR_ID="two"),
    ])

    assert len(result) == 1
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(expected)
    assert result.loc[0, "flood_area_percent"] == pytest.approx(expected / 0.02 * 100)


@pytest.mark.parametrize("second, expected_admin", [
    (box(0, 0, 100, 100), 0.01),
    (box(100, 0, 200, 100), 0.02),
    (box(50, 0, 150, 100), 0.015),
])
def test_admin_id_geometry_is_unioned_for_numerator_and_denominator(summarize, second, expected_admin) -> None:
    result = summarize(
        [flood_record(box(0, 0, 200, 100))],
        [
            {"GEOID": "001", "NAME": "Example", "geometry": box(0, 0, 100, 100)},
            {"GEOID": "001", "NAME": "Example", "geometry": second},
        ],
    )

    assert len(result) == 1
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(expected_admin)
    assert result.loc[0, "admin_area_sq_km"] == pytest.approx(expected_admin)
    assert result.loc[0, "flood_area_percent"] == pytest.approx(100)


def test_conflicting_names_for_admin_id_are_rejected(summarize) -> None:
    with pytest.raises(ValueError, match="Conflicting administrative names.*001"):
        summarize([flood_record(box(0, 0, 100, 100))], [
            {"GEOID": "001", "NAME": "First", "geometry": box(0, 0, 100, 100)},
            {"GEOID": "001", "NAME": "Second", "geometry": box(100, 0, 200, 100)},
        ])


@pytest.mark.parametrize("identifier", [None, "", "   "])
def test_missing_admin_ids_are_not_merged_as_one_unknown_unit(summarize, identifier) -> None:
    with pytest.raises(ValueError, match="Administrative IDs must be nonempty"):
        summarize([flood_record(box(0, 0, 100, 100))], [
            {"GEOID": identifier, "NAME": "Example", "geometry": box(0, 0, 100, 100)},
        ])


def test_original_fallbacks_for_missing_zone_and_admin_fields_are_retained(summarize) -> None:
    result = summarize(
        [{"geometry": box(0, 0, 100, 100)}],
        [{"geometry": box(0, 0, 200, 100)}],
    )
    assert result.loc[0, "admin_id"] == "0"
    assert str(result.loc[0, "admin_name"]) == "0"
    assert result.loc[0, "fld_zone"] == "UNKNOWN"
    assert pd.isna(result.loc[0, "zone_subty"])
    assert result.loc[0, "flood_area_percent"] == pytest.approx(50)


def test_exact_repeated_fema_id_ignores_storage_id_and_is_unioned(summarize) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 100), DFIRM_ID="county", FLD_AR_ID="one", OBJECTID=1),
        flood_record(box(0, 0, 100, 100), DFIRM_ID="county", FLD_AR_ID="one", OBJECTID=2),
    ])

    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0.01)


@pytest.mark.parametrize("change", [
    {"FLD_ZONE": "AE"},
    {"ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"},
    {"STATIC_BFE": 7.0},
    {"geometry": box(100, 0, 200, 100)},
])
def test_conflicting_repeated_fema_id_is_rejected(summarize, change) -> None:
    record = flood_record(box(0, 0, 100, 100), DFIRM_ID="county", FLD_AR_ID="one", STATIC_BFE=6.0)
    with pytest.raises(ValueError, match="Conflicting FEMA flood ID.*one"):
        summarize([record, {**record, **change}])


def test_flood_ids_are_scoped_by_dfirm_id(summarize) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 100), DFIRM_ID="county1", FLD_AR_ID="one"),
        flood_record(box(100, 0, 200, 100), DFIRM_ID="county2", FLD_AR_ID="one"),
    ])
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0.02)


@pytest.mark.parametrize("zone, subtype", [
    ("AE", None),
    ("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"),
    ("X", None),
])
def test_cross_category_overlap_is_rejected_without_precedence(summarize, zone, subtype) -> None:
    with pytest.raises(ValueError, match="Cross-category overlap.*001.*5000"):
        summarize([
            flood_record(box(0, 0, 100, 100)),
            flood_record(box(50, 0, 150, 100), zone=zone, subtype=subtype),
        ])


def test_small_positive_category_overlap_is_not_silently_removed(summarize) -> None:
    with pytest.raises(ValueError, match="Cross-category overlap"):
        summarize([
            flood_record(box(0, 0, 100, 100)),
            flood_record(box(99.999999, 0, 200, 100), zone="AE", subtype=None),
        ])


@pytest.mark.parametrize('second', [box(25, 25, 75, 75), box(0, 0, 100, 100)])
def test_cross_category_containment_and_equal_geometry_are_rejected(summarize, second) -> None:
    # The OGC overlaps predicate excludes containment and equal geometries.
    with pytest.raises(ValueError, match='Cross-category overlap'):
        summarize([
            flood_record(box(0, 0, 100, 100)),
            flood_record(second, zone='AE', subtype=None),
        ])


def test_cross_category_point_only_contact_is_allowed(summarize) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 50)),
        flood_record(box(100, 50, 200, 100), zone='AE', subtype=None),
    ])
    assert result['fld_zone'].tolist() == ['AE', 'X']
    assert result['flood_area_sq_km'].tolist() == pytest.approx([0.005, 0.005])


def test_category_overlap_outside_reported_admin_is_not_a_conflict(summarize) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 100)),
        flood_record(box(-100, 0, 0, 100), zone="AE", subtype=None),
        flood_record(box(-100, 0, 0, 100)),
    ])
    assert result["fld_zone"].tolist() == ["AE", "X"]
    assert result["flood_area_sq_km"].tolist() == pytest.approx([0, 0.01])


def test_each_administrative_unit_is_reported_independently(summarize) -> None:
    result = summarize([flood_record(box(0, 0, 200, 100))], [
        {"GEOID": "001", "NAME": "First", "geometry": box(0, 0, 100, 100)},
        {"GEOID": "002", "NAME": "Second", "geometry": box(50, 0, 150, 100)},
    ])
    assert result["admin_id"].tolist() == ["001", "002"]
    assert result["flood_area_sq_km"].tolist() == pytest.approx([0.01, 0.01])


def test_null_zone_and_subtype_group_is_preserved(summarize) -> None:
    result = summarize([
        flood_record(box(0, 0, 100, 100), zone=None, subtype=None),
        flood_record(box(0, 0, 100, 100), zone=None, subtype=None),
    ])
    assert len(result) == 1
    assert pd.isna(result.loc[0, "fld_zone"])
    assert pd.isna(result.loc[0, "zone_subty"])
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0.01)


@pytest.mark.parametrize("flood_rows, admin_rows", [
    ([], None),
    ([flood_record(box(0, 0, 100, 100))], []),
    ([flood_record(box(300, 0, 400, 100))], None),
])
def test_empty_or_no_intersection_writes_csv_headers(summarize, flood_rows, admin_rows) -> None:
    result = summarize(flood_rows, admin_rows)
    assert result.empty
    assert len(result.columns) == 7


def test_touching_boundary_preserves_zero_area_category_row(summarize) -> None:
    result = summarize([flood_record(box(200, 0, 300, 100))])
    assert len(result) == 1
    assert result.loc[0, "fld_zone"] == "X"
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0)
    assert result.loc[0, "flood_area_percent"] == pytest.approx(0)
    assert result.loc[0, "admin_area_sq_km"] == pytest.approx(0.02)


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:3857"])
def test_area_crs_must_be_projected_and_equal_area(summarize, crs) -> None:
    with pytest.raises(ValueError, match="projected equal-area CRS"):
        summarize([flood_record(box(0, 0, 100, 100))], equal_area_crs=crs)


def test_equal_area_crs_feet_are_converted_to_square_kilometres(summarize) -> None:
    feet_crs = "+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23 +lon_0=-96 +datum=NAD83 +units=us-ft +type=crs"
    result = summarize([flood_record(box(0, 0, 100, 100))], equal_area_crs=feet_crs)
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0.01)


@pytest.mark.parametrize("crs", [
    "EPSG:8857",
    "+proj=moll +datum=WGS84 +type=crs",
    "+proj=sinu +datum=WGS84 +type=crs",
])
def test_named_equal_area_projections_remain_supported(summarize, crs) -> None:
    result = summarize([flood_record(box(0, 0, 100, 100))], source_crs=crs, equal_area_crs=crs)
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0.01)


def test_missing_crs_is_rejected(summarize) -> None:
    with pytest.raises(ValueError, match="must have a CRS"):
        summarize([flood_record(box(0, 0, 100, 100))], source_crs=None)


@pytest.mark.parametrize("geometry", [
    None,
    Polygon(),
    LineString([(0, 0), (100, 100)]),
    Polygon([(0, 0), (50, 0), (100, 0), (0, 0)]),
])
def test_invalid_or_nonpolygon_geometry_is_not_silently_dropped(summarize, geometry) -> None:
    with pytest.raises(ValueError, match="valid nonempty polygon"):
        summarize([flood_record(geometry)])


def test_invalid_polygon_repair_is_explicit_and_preserves_all_polygon_parts(summarize, caplog) -> None:
    result = summarize([flood_record(
        Polygon([(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)]), FLD_AR_ID="bowtie",
    )])
    assert result.loc[0, "flood_area_sq_km"] == pytest.approx(0.005)
    assert "Repaired 1 invalid flood" in caplog.text
    assert "bowtie" in caplog.text

