from __future__ import annotations

from fema_nfhl.visualize import create_exposure_bar_chart


def test_create_exposure_bar_chart_from_sample_csv(tmp_path) -> None:
    output = create_exposure_bar_chart(
        "outputs/sample/floodplain_area_summary_sample.csv",
        tmp_path / "chart.png",
        title="Alameda County Floodplain Area",
    )

    assert output.exists()
    assert output.stat().st_size > 0
