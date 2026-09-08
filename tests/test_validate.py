from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from fema_nfhl.validate import check_required_layers, validate_bfe_values, validate_geodataframe


def test_check_required_layers_flags_missing_bfe() -> None:
    findings = check_required_layers(["S_FLD_HAZ_AR"])

    by_layer = {(finding.layer, finding.check): finding for finding in findings}
    assert by_layer[("S_FLD_HAZ_AR", "required_layer_present")].status == "pass"
    assert by_layer[("S_BFE", "recommended_layer_present")].status == "warning"


def test_validate_bfe_values_counts_bad_values() -> None:
    findings = validate_bfe_values(pd.Series([10, "bad", None, 0]), field_name="ELEV")

    by_check = {finding.check: finding for finding in findings}
    assert by_check["bfe_null_values"].message.endswith(": 1")
    assert by_check["bfe_non_numeric_values"].message.endswith(": 1")
    assert by_check["bfe_zero_values"].message.endswith(": 1")


def test_bfe_sentinels_are_missing_with_distinct_meanings_and_source_preserved() -> None:
    values = pd.Series([-9999, " -9999.0 ", -8888, "-8.888e3", None, "", "  ", "<null>", "bad"])
    original = values.copy(deep=True)

    by_check = {finding.check: finding for finding in validate_bfe_values(values)}

    assert by_check["bfe_not_applicable_values"].message.endswith(": 2")
    assert by_check["bfe_not_populated_values"].message.endswith(": 2")
    assert by_check["bfe_null_values"].message.endswith(": 4")
    assert by_check["bfe_non_numeric_values"].message.endswith(": 1")
    assert by_check["bfe_not_applicable_values"].status == "warning"
    assert by_check["bfe_not_populated_values"].status == "warning"
    pd.testing.assert_series_equal(values, original)


def test_zero_and_nonsentinel_negative_bfe_are_valid_elevations() -> None:
    by_check = {
        finding.check: finding
        for finding in validate_bfe_values(pd.Series([0, "0.0", -1.25, "-20", 12.5]))
    }

    assert by_check["bfe_zero_values"].message.endswith(": 2")
    assert all(finding.status == "pass" for finding in by_check.values())
    assert all(finding.severity == "info" for finding in by_check.values())


def test_bfe_nonfinite_values_are_distinct_from_null_and_invalid_text() -> None:
    values = pd.Series([float("inf"), float("-inf"), "inf", "-Infinity", pd.NA, float("nan"), "nan", "invalid"])

    by_check = {finding.check: finding for finding in validate_bfe_values(values)}

    assert by_check["bfe_non_finite_values"].message.endswith(": 4")
    assert by_check["bfe_null_values"].message.endswith(": 3")
    assert by_check["bfe_non_numeric_values"].message.endswith(": 1")
    assert by_check["bfe_non_finite_values"].severity == "error"


def test_static_bfe_validates_sentinels_without_requiring_an_optional_elevation() -> None:
    flood = gpd.GeoDataFrame(
        {
            "FLD_ZONE": ["X", "X", "AE", "AE"],
            "ZONE_SUBTY": ["AREA OF MINIMAL FLOOD HAZARD", "AREA OF MINIMAL FLOOD HAZARD", None, None],
            "static_bfe": [-9999, None, -8888, -2.5],
        },
        geometry=[box(index, 0, index + 1, 1) for index in range(4)],
        crs="EPSG:5070",
    )
    original = flood.copy(deep=True)

    by_check = {finding.check: finding for finding in validate_geodataframe(flood, "S_FLD_HAZ_AR")}

    assert by_check["bfe_not_applicable_values"].message.endswith(": 1")
    assert by_check["bfe_not_applicable_values"].severity == "info"
    assert by_check["bfe_not_applicable_values"].status == "pass"
    assert by_check["bfe_null_values"].status == "pass"
    assert by_check["bfe_not_populated_values"].status == "warning"
    assert by_check["bfe_not_populated_values"].value == "static_bfe"
    pd.testing.assert_frame_equal(flood, original)

