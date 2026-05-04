"""Prepare small county- or bbox-scale NFHL case-study datasets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .catalog import IMPORTANT_LAYERS, find_layer_sources, read_layer
from .utils import ensure_dir, parse_bbox, require_optional


LOGGER = logging.getLogger(__name__)
DEFAULT_CASE_STUDY_LAYERS = tuple(sorted(IMPORTANT_LAYERS))


@dataclass(frozen=True)
class CaseStudyClipResult:
    """Summary for one clipped layer."""

    layer_name: str
    source_path: str
    output_path: str
    input_feature_count: int
    output_feature_count: int
    clip_method: str


def prepare_county_case_study(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    boundary_path: str | Path | None = None,
    boundary_id_field: str | None = None,
    boundary_id_value: str | None = None,
    bbox: Iterable[str | float] | None = None,
    bbox_crs: str | None = None,
    layers: Iterable[str] | None = None,
    output_format: str = "shapefile",
    keep_empty: bool = False,
) -> list[CaseStudyClipResult]:
    """Clip selected NFHL layers to a county boundary or bounding box.

    Use a county boundary when available. A bbox is useful for quick case-study
    smoke tests, but it should be expressed in the CRS declared by ``bbox_crs``
    or in each source layer CRS when ``bbox_crs`` is omitted.
    """

    if boundary_path is None and bbox is None:
        raise ValueError("Provide either a county boundary with --boundary or a bounding box with --bbox.")
    if boundary_path is not None and bbox is not None:
        raise ValueError("Use either --boundary or --bbox, not both.")
    if output_format not in {"shapefile", "gpkg", "geoparquet"}:
        raise ValueError("output_format must be 'shapefile', 'gpkg', or 'geoparquet'.")
    if output_format == "geoparquet":
        require_optional("pyarrow")

    gpd = require_optional("geopandas")
    shapely_geometry = require_optional("shapely.geometry", "shapely.geometry")
    output_dir = ensure_dir(output_dir)
    selected_layers = {layer.upper() for layer in (layers or DEFAULT_CASE_STUDY_LAYERS)}
    sources = [source for source in find_layer_sources(input_path) if source.layer_name in selected_layers]
    if not sources:
        raise FileNotFoundError("No requested NFHL layers were found to clip.")

    boundary = None
    bbox_tuple = parse_bbox(tuple(bbox)) if bbox is not None else None
    if boundary_path is not None:
        boundary = _load_boundary(
            gpd,
            boundary_path,
            boundary_id_field=boundary_id_field,
            boundary_id_value=boundary_id_value,
        )

    results: list[CaseStudyClipResult] = []
    for source in sources:
        gdf = read_layer(source)
        if gdf.crs is None:
            raise ValueError(f"{source.display_path} has no CRS; cannot clip safely.")

        if boundary is not None:
            clip_geometry = boundary.to_crs(gdf.crs)
            clip_method = "boundary"
        else:
            clip_geometry = _bbox_to_geodataframe(gpd, shapely_geometry, bbox_tuple, source_crs=gdf.crs, bbox_crs=bbox_crs)
            clip_method = "bbox"

        clipped = _clip_geodataframe(gdf, clip_geometry)
        if clipped.empty and not keep_empty:
            LOGGER.info("Skipping %s because no features intersected the case-study area.", source.layer_name)
            continue

        output_path = _write_case_study_layer(clipped, output_dir, source.layer_name, output_format)
        results.append(
            CaseStudyClipResult(
                layer_name=source.layer_name,
                source_path=source.display_path,
                output_path=str(output_path),
                input_feature_count=int(len(gdf)),
                output_feature_count=int(len(clipped)),
                clip_method=clip_method,
            )
        )
        LOGGER.info("Clipped %s from %s to %s features.", source.layer_name, len(gdf), len(clipped))
    return results


def _load_boundary(gpd, boundary_path, *, boundary_id_field: str | None, boundary_id_value: str | None):
    boundary = gpd.read_file(boundary_path)
    if boundary.crs is None:
        raise ValueError(f"Boundary layer has no CRS: {boundary_path}")
    if boundary_id_field and boundary_id_value is not None:
        if boundary_id_field not in boundary.columns:
            raise ValueError(f"Boundary field not found: {boundary_id_field}")
        boundary = boundary[boundary[boundary_id_field].astype(str) == str(boundary_id_value)]
        if boundary.empty:
            raise ValueError(f"No boundary records matched {boundary_id_field}={boundary_id_value}.")
    if boundary.empty:
        raise ValueError("Boundary layer is empty.")
    return boundary


def _bbox_to_geodataframe(gpd, shapely_geometry, bbox, *, source_crs, bbox_crs: str | None):
    if bbox is None:
        raise ValueError("bbox cannot be None here.")
    minx, miny, maxx, maxy = bbox
    bbox_gdf = gpd.GeoDataFrame(geometry=[shapely_geometry.box(minx, miny, maxx, maxy)], crs=bbox_crs or source_crs)
    if bbox_gdf.crs != source_crs:
        bbox_gdf = bbox_gdf.to_crs(source_crs)
    return bbox_gdf


def _clip_geodataframe(gdf, clip_geometry):
    try:
        clipped = gdf.clip(clip_geometry)
    except Exception:
        geometry = clip_geometry.union_all() if hasattr(clip_geometry, "union_all") else clip_geometry.unary_union
        clipped = gdf[gdf.intersects(geometry)].copy()
        clipped["geometry"] = clipped.geometry.intersection(geometry)
    return clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()


def _write_case_study_layer(gdf, output_dir: Path, layer_name: str, output_format: str) -> Path:
    if output_format == "shapefile":
        path = output_dir / f"{layer_name}.shp"
        gdf.to_file(path)
        return path
    if output_format == "gpkg":
        path = output_dir / "nfhl_case_study.gpkg"
        gdf.to_file(path, layer=layer_name, driver="GPKG")
        return path
    path = output_dir / f"{layer_name}.geoparquet"
    gdf.to_parquet(path, index=False)
    return path

