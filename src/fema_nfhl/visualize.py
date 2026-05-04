"""Small static visualizations for portfolio outputs."""

from __future__ import annotations

from pathlib import Path

from .utils import ensure_dir, require_optional


def create_exposure_bar_chart(
    summary_csv: str | Path,
    output_png: str | Path,
    *,
    title: str = "Floodplain Area By FEMA Flood Zone",
) -> Path:
    """Create a compact exposure summary bar chart from an exposure CSV."""

    pandas = require_optional("pandas")
    pyplot = require_optional("matplotlib", "matplotlib.pyplot")

    summary = pandas.read_csv(summary_csv)
    required = {"fld_zone", "zone_subty", "flood_area_sq_km", "flood_area_percent"}
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"Exposure summary is missing required columns: {sorted(missing)}")
    if summary.empty:
        raise ValueError("Exposure summary is empty.")

    plot_data = summary.copy()
    plot_data["zone_label"] = plot_data.apply(_zone_label, axis=1)
    plot_data = plot_data.sort_values("flood_area_sq_km", ascending=True)

    fig_height = max(3.2, 0.55 * len(plot_data) + 1.6)
    fig, ax = pyplot.subplots(figsize=(8, fig_height))
    colors = ["#1f77b4" if str(zone).upper() != "X" else "#f28e2b" for zone in plot_data["fld_zone"]]
    bars = ax.barh(plot_data["zone_label"], plot_data["flood_area_sq_km"], color=colors)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold")
    ax.set_xlabel("Flood hazard area (sq km)")
    ax.set_ylabel("")
    ax.grid(axis="x", color="#d1d5db", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)

    for bar, percent in zip(bars, plot_data["flood_area_percent"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f" {bar.get_width():.2f} sq km ({percent:.2f}%)",
            va="center",
            ha="left",
            fontsize=9,
        )

    fig.tight_layout()
    output_png = Path(output_png)
    ensure_dir(output_png.parent)
    fig.savefig(output_png, dpi=160, bbox_inches="tight")
    pyplot.close(fig)
    return output_png


def _zone_label(row) -> str:
    zone = str(row["fld_zone"])
    subtype = "" if pandas_is_missing(row["zone_subty"]) else str(row["zone_subty"])
    return f"{zone} - {subtype}" if subtype else zone


def pandas_is_missing(value) -> bool:
    pandas = require_optional("pandas")
    return bool(pandas.isna(value)) or str(value).strip() == ""
