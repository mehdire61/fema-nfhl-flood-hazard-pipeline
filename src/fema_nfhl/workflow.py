"""High-level workflows for common NFHL project runs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .catalog import catalog_extracted_layers
from .extract import extract_nfhl_zip
from .mapping import create_interactive_map
from .utils import ensure_dir
from .validate import validate_layers


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuickstartResult:
    """Output paths from a quickstart county NFHL run."""

    extracted_dir: Path
    catalog_csv: Path
    validation_csv: Path
    map_html: Path


def run_county_quickstart(
    *,
    zip_path: str | Path,
    extracted_root: str | Path = "data/extracted",
    outputs_dir: str | Path = "outputs",
    overwrite_extract: bool = False,
) -> QuickstartResult:
    """Run the lightweight county NFHL workflow: extract, catalog, validate, and map.

    This workflow is intended for county/community NFHL packages such as Alameda
    County's ``06001C_*.zip``. It intentionally does not require a county
    boundary file because the package is already scoped to the quick-check area.
    """

    zip_path = Path(zip_path)
    extracted_root = ensure_dir(extracted_root)
    outputs_dir = ensure_dir(outputs_dir)
    expected_extract_dir = extracted_root / zip_path.stem

    if expected_extract_dir.exists() and not overwrite_extract:
        extracted_dir = expected_extract_dir
        LOGGER.info("Using existing extracted folder %s", extracted_dir)
    else:
        extracted_dir = extract_nfhl_zip(zip_path, extracted_root)

    catalog_csv = outputs_dir / "nfhl_catalog.csv"
    validation_csv = outputs_dir / "validation_report.csv"
    map_html = outputs_dir / "flood_hazard_map.html"

    catalog_extracted_layers(extracted_dir, catalog_csv)
    validate_layers(extracted_dir, output_csv=validation_csv)
    create_interactive_map(extracted_dir, map_html)

    LOGGER.info("Quickstart complete. Map: %s", map_html)
    return QuickstartResult(
        extracted_dir=extracted_dir,
        catalog_csv=catalog_csv,
        validation_csv=validation_csv,
        map_html=map_html,
    )

