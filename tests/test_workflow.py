from __future__ import annotations

from pathlib import Path

import fema_nfhl.workflow as workflow


def test_run_county_quickstart_orchestrates_outputs(tmp_path, monkeypatch) -> None:
    zip_path = tmp_path / "06001C_20260428.zip"
    zip_path.write_bytes(b"fake")
    extracted_root = tmp_path / "data" / "extracted"
    outputs = tmp_path / "outputs"
    extracted_dir = extracted_root / "06001C_20260428"

    calls: list[tuple[str, Path]] = []

    def fake_extract(path, output):
        calls.append(("extract", Path(path)))
        extracted_dir.mkdir(parents=True)
        return extracted_dir

    def fake_catalog(input_path, output_csv):
        calls.append(("catalog", Path(input_path)))
        Path(output_csv).write_text("layer_name\nS_FLD_HAZ_AR\n", encoding="utf-8")

    def fake_validate(input_path, *, output_csv=None):
        calls.append(("validate", Path(input_path)))
        Path(output_csv).write_text("check,status\ncrs_present,pass\n", encoding="utf-8")
        return []

    def fake_map(input_path, output_html):
        calls.append(("map", Path(input_path)))
        Path(output_html).write_text("<html></html>", encoding="utf-8")
        return Path(output_html)

    monkeypatch.setattr(workflow, "extract_nfhl_zip", fake_extract)
    monkeypatch.setattr(workflow, "catalog_extracted_layers", fake_catalog)
    monkeypatch.setattr(workflow, "validate_layers", fake_validate)
    monkeypatch.setattr(workflow, "create_interactive_map", fake_map)

    result = workflow.run_county_quickstart(zip_path=zip_path, extracted_root=extracted_root, outputs_dir=outputs)

    assert result.extracted_dir == extracted_dir
    assert result.catalog_csv == outputs / "nfhl_catalog.csv"
    assert result.validation_csv == outputs / "validation_report.csv"
    assert result.map_html == outputs / "flood_hazard_map.html"
    assert result.map_html.exists()
    assert calls == [
        ("extract", zip_path),
        ("catalog", extracted_dir),
        ("validate", extracted_dir),
        ("map", extracted_dir),
    ]
