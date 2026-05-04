"""Transform FEMA NFHL layers to analysis-ready vector formats."""

from __future__ import annotations

import logging
from pathlib import Path

from .catalog import IMPORTANT_LAYERS, find_layer_sources, read_layer
from .utils import ensure_dir, require_optional


LOGGER = logging.getLogger(__name__)


def transform_layers(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    output_format: str = "geoparquet",
    layers: list[str] | None = None,
) -> list[Path]:
    """Convert selected NFHL layers to GeoParquet or GeoPackage."""

    output_dir = ensure_dir(output_dir)
    selected = {layer.upper() for layer in (layers or sorted(IMPORTANT_LAYERS))}
    sources = [source for source in find_layer_sources(input_path) if source.layer_name in selected]
    written: list[Path] = []

    if output_format == "geoparquet":
        require_optional("pyarrow")

    for source in sources:
        gdf = read_layer(source)
        if gdf.crs is None:
            LOGGER.warning("%s has no CRS; output will preserve missing CRS state.", source.display_path)
        gdf = gdf.copy()
        gdf["_source_layer"] = source.layer_name
        if output_format == "geoparquet":
            out = output_dir / f"{source.layer_name}.geoparquet"
            gdf.to_parquet(out, index=False)
        elif output_format == "gpkg":
            out = output_dir / "nfhl_layers.gpkg"
            gdf.to_file(out, layer=source.layer_name, driver="GPKG")
        else:
            raise ValueError("Unsupported format. Use 'geoparquet' or 'gpkg'.")
        LOGGER.info("Wrote %s", out)
        written.append(out)
    return written

