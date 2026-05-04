"""Safe extraction helpers for FEMA NFHL zip files."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from .utils import ensure_dir


LOGGER = logging.getLogger(__name__)


def extract_nfhl_zip(zip_path: str | Path, output_dir: str | Path) -> Path:
    """Safely extract a FEMA NFHL zip file and return the extraction folder."""

    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file does not exist: {zip_path}")
    destination = ensure_dir(Path(output_dir) / zip_path.stem)

    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = safe_extract_path(destination, member.filename)
            if member.is_dir():
                ensure_dir(target)
                continue
            ensure_dir(target.parent)
            with archive.open(member) as src, target.open("wb") as dst:
                dst.write(src.read())
            count += 1

    LOGGER.info("Extracted %s files to %s", count, destination)
    return destination


def safe_extract_path(destination: str | Path, member_name: str) -> Path:
    """Return a safe extraction path or raise if the member escapes destination."""

    destination = Path(destination).resolve()
    target = (destination / member_name).resolve()
    if destination != target and destination not in target.parents:
        raise ValueError(f"Unsafe zip member path detected: {member_name}")
    return target

