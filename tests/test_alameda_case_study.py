from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_example_config_uses_alameda_california_case_study() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "config" / "example_config.yaml").read_text(encoding="utf-8"))

    assert config["project"]["case_study"] == "Alameda County, California"
    assert config["paths"]["case_study_data"] == "data/case_study/alameda"
    assert config["case_study"]["county_fips"] == "06001"
    assert config["case_study"]["boundary_id_field"] == "GEOID"
    assert config["case_study"]["boundary_id_value"] == "06001"
    assert config["case_study"]["clip_output"] == "data/case_study/alameda"
    assert config["download"]["state"] == "CALIFORNIA"
    assert config["scientific_assumptions"]["flood_depth_modeling_included"] is False
    assert config["scientific_assumptions"]["not_for_official_use"] is True


def test_demo_notebook_keeps_one_alameda_case_study() -> None:
    notebook = json.loads((PROJECT_ROOT / "notebooks" / "01_demo_nfhl_pipeline.ipynb").read_text(encoding="utf-8"))
    text = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )

    assert "Alameda County, California" in text
    assert "prepare_county_case_study" in text
    assert "case_study_nfhl" in text
    assert "alameda" in text
    assert "Los Angeles" not in text
    assert "San Francisco" not in text
    assert "Maryland" not in text
    assert "flood_hazard_map.html" in text


def test_sample_exposure_output_contains_alameda_county_only() -> None:
    sample = PROJECT_ROOT / "outputs" / "sample" / "floodplain_area_summary_sample.csv"
    with sample.open(newline="", encoding="utf-8") as src:
        rows = list(csv.DictReader(src))

    assert rows
    assert {row["admin_name"] for row in rows} == {"Alameda County"}
    assert {row["admin_id"] for row in rows} == {"06001"}


def test_sample_catalog_points_to_alameda_case_study_folder() -> None:
    sample = PROJECT_ROOT / "outputs" / "sample" / "nfhl_catalog_sample.csv"
    with sample.open(newline="", encoding="utf-8") as src:
        rows = list(csv.DictReader(src))

    assert rows
    assert all(row["file_path"].startswith("data/case_study/alameda/") for row in rows)
