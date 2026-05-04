from __future__ import annotations

from fema_nfhl.exposure import select_admin_field
from fema_nfhl.utils import safe_percent


def test_select_admin_field_prefers_known_candidates() -> None:
    field = select_admin_field(["OBJECTID", "GEOID", "NAME"], ["FIPS", "GEOID"])

    assert field == "GEOID"


def test_safe_percent_handles_zero_denominator() -> None:
    assert safe_percent(10, 0) == 0.0
    assert safe_percent(5, 20) == 25.0

