"""Tests for county FIPS lookup helpers."""

from __future__ import annotations

from fema_nfhl.cli import main
from fema_nfhl.county_lookup import resolve_county_fips, search_counties


def test_resolve_county_fips_by_name_and_state() -> None:
    record = resolve_county_fips(state="MD", county="Montgomery")

    assert record.geoid == "24031"
    assert record.state == "MARYLAND"
    assert record.county_name == "Montgomery County"


def test_resolve_county_fips_accepts_county_suffix() -> None:
    record = resolve_county_fips(state="California", county="Alameda County")

    assert record.geoid == "06001"


def test_search_counties_shows_ambiguous_names_across_states() -> None:
    records = search_counties(county="Montgomery", limit=20)

    geoids = {record.geoid for record in records}
    assert "24031" in geoids
    assert "01101" in geoids
    assert len(records) > 1


def test_county_code_cli_value_only(capsys) -> None:
    exit_code = main(["county-code", "--state", "MARYLAND", "--county", "Montgomery", "--value-only"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "24031"
