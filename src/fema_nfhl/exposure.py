"""Floodplain exposure and area summaries."""

from __future__ import annotations

import logging
from pathlib import Path

from .utils import ensure_dir, require_optional, safe_percent


LOGGER = logging.getLogger(__name__)
DEFAULT_EQUAL_AREA_CRS = "EPSG:5070"


def floodplain_area_summary(
    flood_layer: str | Path,
    admin_boundaries: str | Path,
    output_csv: str | Path,
    *,
    admin_id_field: str | None = None,
    admin_name_field: str | None = None,
    equal_area_crs: str = DEFAULT_EQUAL_AREA_CRS,
) -> Path:
    """Calculate flood hazard area by administrative unit and FEMA zone."""

    gpd = require_optional("geopandas")
    flood = gpd.read_file(flood_layer)
    admin = gpd.read_file(admin_boundaries)
    if flood.crs is None or admin.crs is None:
        raise ValueError("Both flood and admin layers must have a CRS for area calculations.")

    flood = flood.to_crs(equal_area_crs)
    admin = admin.to_crs(equal_area_crs)
    admin_id_field = admin_id_field or select_admin_field(admin.columns, ["GEOID", "GEOID20", "FIPS", "ID"])
    admin_name_field = admin_name_field or select_admin_field(admin.columns, ["NAME", "NAMELSAD", "COUNTY", "ADMIN_NAME"])

    if admin_id_field is None:
        admin["_admin_id"] = admin.index.astype(str)
        admin_id_field = "_admin_id"
    if admin_name_field is None:
        admin["_admin_name"] = admin[admin_id_field].astype(str)
        admin_name_field = "_admin_name"

    admin = admin.copy()
    admin["_admin_area_sq_km"] = admin.geometry.area / 1_000_000

    flood_zone = _actual_column(flood.columns, "FLD_ZONE")
    zone_subty = _actual_column(flood.columns, "ZONE_SUBTY")
    if flood_zone is None:
        flood["FLD_ZONE"] = "UNKNOWN"
        flood_zone = "FLD_ZONE"
    if zone_subty is None:
        flood["ZONE_SUBTY"] = ""
        zone_subty = "ZONE_SUBTY"

    LOGGER.warning("Large vector overlays can be slow; clip inputs to the study area where practical.")
    intersection = gpd.overlay(
        admin[[admin_id_field, admin_name_field, "_admin_area_sq_km", "geometry"]],
        flood[[flood_zone, zone_subty, "geometry"]],
        how="intersection",
        keep_geom_type=False,
    )
    if intersection.empty:
        rows = []
    else:
        intersection["_flood_area_sq_km"] = intersection.geometry.area / 1_000_000
        grouped = (
            intersection.groupby([admin_id_field, admin_name_field, flood_zone, zone_subty], dropna=False)
            .agg(flood_area_sq_km=("_flood_area_sq_km", "sum"), admin_area_sq_km=("_admin_area_sq_km", "first"))
            .reset_index()
        )
        grouped["flood_area_percent"] = [
            safe_percent(flood_area, admin_area)
            for flood_area, admin_area in zip(grouped["flood_area_sq_km"], grouped["admin_area_sq_km"])
        ]
        grouped = grouped.rename(
            columns={
                admin_id_field: "admin_id",
                admin_name_field: "admin_name",
                flood_zone: "fld_zone",
                zone_subty: "zone_subty",
            }
        )
        rows = grouped[
            [
                "admin_id",
                "admin_name",
                "fld_zone",
                "zone_subty",
                "flood_area_sq_km",
                "admin_area_sq_km",
                "flood_area_percent",
            ]
        ]

    output_csv = Path(output_csv)
    ensure_dir(output_csv.parent)
    if hasattr(rows, "to_csv"):
        rows.to_csv(output_csv, index=False)
    else:
        import pandas as pd

        pd.DataFrame(
            rows,
            columns=[
                "admin_id",
                "admin_name",
                "fld_zone",
                "zone_subty",
                "flood_area_sq_km",
                "admin_area_sq_km",
                "flood_area_percent",
            ],
        ).to_csv(output_csv, index=False)
    return output_csv


def select_admin_field(columns, candidates: list[str]) -> str | None:
    """Select a likely administrative identifier/name field."""

    lookup = {str(column).upper(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.upper() in lookup:
            return lookup[candidate.upper()]
    return None


def _actual_column(columns, wanted: str) -> str | None:
    lookup = {str(column).upper(): str(column) for column in columns}
    return lookup.get(wanted.upper())

