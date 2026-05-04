"""Catalog extracted FEMA NFHL layers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .utils import json_text, normalize_layer_name, require_optional, write_csv


IMPORTANT_LAYERS = {
    "S_FLD_HAZ_AR",
    "S_BFE",
    "S_XS",
    "S_WTR_LN",
    "S_LOMR",
    "L_COMMUNITY_INFO",
}

CATALOG_COLUMNS = [
    "layer_name",
    "file_path",
    "geometry_type",
    "feature_count",
    "crs",
    "bounds",
    "fields",
    "has_fld_zone",
    "has_zone_subty",
    "has_elev",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayerSource:
    """A file/layer pair that can be read by GeoPandas."""

    layer_name: str
    file_path: Path
    layer: str | None = None

    @property
    def display_path(self) -> str:
        """Return a stable path string for reports."""

        if self.layer:
            return f"{self.file_path}::{self.layer}"
        return str(self.file_path)


def find_layer_sources(input_path: str | Path) -> list[LayerSource]:
    """Find shapefiles and geodatabase feature classes under an extracted folder."""

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    sources: list[LayerSource] = []
    for shp in input_path.rglob("*.shp"):
        sources.append(LayerSource(normalize_layer_name(shp.stem), shp))

    for gdb in input_path.rglob("*.gdb"):
        sources.extend(_multi_layer_sources(gdb))

    for gpkg in input_path.rglob("*.gpkg"):
        sources.extend(_multi_layer_sources(gpkg))

    for geoparquet in input_path.rglob("*.geoparquet"):
        sources.append(LayerSource(normalize_layer_name(geoparquet.stem), geoparquet))

    sources.sort(key=lambda src: (src.layer_name, src.display_path))
    return sources


def catalog_extracted_layers(input_path: str | Path, output_csv: str | Path | None = None) -> list[dict[str, object]]:
    """Create a CSV-friendly catalog of extracted NFHL layers."""

    rows: list[dict[str, object]] = []
    for source in find_layer_sources(input_path):
        try:
            rows.append(catalog_layer(source))
        except Exception as exc:
            LOGGER.warning("Could not catalog %s: %s", source.display_path, exc)
            rows.append(
                {
                    "layer_name": source.layer_name,
                    "file_path": source.display_path,
                    "geometry_type": "",
                    "feature_count": "",
                    "crs": "",
                    "bounds": "",
                    "fields": "",
                    "has_fld_zone": False,
                    "has_zone_subty": False,
                    "has_elev": False,
                }
            )

    if output_csv:
        write_csv(rows, output_csv, CATALOG_COLUMNS)
    return rows


def catalog_layer(source: LayerSource) -> dict[str, object]:
    """Catalog one vector layer."""

    gpd = require_optional("geopandas")
    gdf = _read_source(gpd, source)
    columns = list(gdf.columns)
    geometry_types = sorted(str(value) for value in gdf.geometry.geom_type.dropna().unique()) if len(gdf) else []
    return {
        "layer_name": source.layer_name,
        "file_path": source.display_path,
        "geometry_type": ";".join(geometry_types),
        "feature_count": int(len(gdf)),
        "crs": str(gdf.crs) if gdf.crs else "",
        "bounds": json_text([float(v) for v in gdf.total_bounds]) if len(gdf) else "",
        "fields": json_text(columns),
        "has_fld_zone": _has_field(columns, "FLD_ZONE"),
        "has_zone_subty": _has_field(columns, "ZONE_SUBTY"),
        "has_elev": _has_field(columns, "ELEV") or _has_field(columns, "STATIC_BFE"),
    }


def find_source_by_layer(input_path: str | Path, layer_names: Iterable[str]) -> LayerSource | None:
    """Find the first source matching any requested NFHL layer name."""

    wanted = {normalize_layer_name(layer) for layer in layer_names}
    for source in find_layer_sources(input_path):
        if source.layer_name in wanted:
            return source
    return None


def read_layer(source: LayerSource):
    """Read a layer source as a GeoDataFrame."""

    gpd = require_optional("geopandas")
    return _read_source(gpd, source)


def _read_source(gpd, source: LayerSource):
    if source.layer:
        return gpd.read_file(source.file_path, layer=source.layer)
    return gpd.read_file(source.file_path)


def _multi_layer_sources(path: Path) -> list[LayerSource]:
    fiona = require_optional("fiona")
    try:
        layers = fiona.listlayers(path)
    except Exception as exc:
        LOGGER.warning("Could not list layers in %s: %s", path, exc)
        return []
    return [LayerSource(normalize_layer_name(layer), path, layer=layer) for layer in layers]


def _has_field(columns: list[str], field: str) -> bool:
    return field.upper() in {column.upper() for column in columns}
