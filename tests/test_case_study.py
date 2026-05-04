from __future__ import annotations

from pathlib import Path

from fema_nfhl.case_study import DEFAULT_CASE_STUDY_LAYERS, prepare_county_case_study
from fema_nfhl.catalog import find_layer_sources
from fema_nfhl.cli import build_parser


def test_default_case_study_layers_include_core_nfhl_layers() -> None:
    assert "S_FLD_HAZ_AR" in DEFAULT_CASE_STUDY_LAYERS
    assert "S_BFE" in DEFAULT_CASE_STUDY_LAYERS


def test_prepare_case_study_requires_boundary_or_bbox(tmp_path) -> None:
    try:
        prepare_county_case_study(tmp_path, tmp_path / "out")
    except ValueError as exc:
        assert "Provide either" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected missing clip area to raise")


def test_clip_cli_parses_alameda_boundary_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "clip",
            "--input",
            "data/extracted",
            "--boundary",
            "data/boundaries/alameda_county.shp",
            "--boundary-id-field",
            "GEOID",
            "--boundary-id-value",
            "06001",
            "--output",
            "data/case_study/alameda",
        ]
    )

    assert args.command == "clip"
    assert args.input == Path("data/extracted")
    assert args.boundary == Path("data/boundaries/alameda_county.shp")
    assert args.boundary_id_field == "GEOID"
    assert args.boundary_id_value == "06001"
    assert args.output == Path("data/case_study/alameda")


def test_quickstart_cli_parses_alameda_zip() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "quickstart",
            "--zip",
            "data/raw/CALIFORNIA/06001C_20260428.zip",
            "--extracted-root",
            "data/extracted",
            "--outputs",
            "outputs",
        ]
    )

    assert args.command == "quickstart"
    assert args.zip_path == Path("data/raw/CALIFORNIA/06001C_20260428.zip")
    assert args.extracted_root == Path("data/extracted")
    assert args.outputs == Path("outputs")


def test_plot_exposure_cli_parses_output_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "plot-exposure",
            "--summary-csv",
            "outputs/sample/floodplain_area_summary_sample.csv",
            "--output",
            "outputs/sample/floodplain_area_summary_sample.png",
            "--title",
            "Alameda County Floodplain Area",
        ]
    )

    assert args.command == "plot-exposure"
    assert args.summary_csv == Path("outputs/sample/floodplain_area_summary_sample.csv")
    assert args.output == Path("outputs/sample/floodplain_area_summary_sample.png")
    assert args.title == "Alameda County Floodplain Area"


def test_find_layer_sources_discovers_geoparquet_layers(tmp_path) -> None:
    layer = tmp_path / "S_FLD_HAZ_AR.geoparquet"
    layer.write_bytes(b"placeholder")

    sources = find_layer_sources(tmp_path)

    assert len(sources) == 1
    assert sources[0].layer_name == "S_FLD_HAZ_AR"
