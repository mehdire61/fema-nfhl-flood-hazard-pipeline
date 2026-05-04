from __future__ import annotations

import pandas as pd

from fema_nfhl.validate import check_required_layers, validate_bfe_values


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

