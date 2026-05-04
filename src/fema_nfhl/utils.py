"""Shared utilities for the FEMA NFHL workflow."""

from __future__ import annotations

import csv
import importlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


LOGGER_NAME = "fema_nfhl"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package logger."""

    return logging.getLogger(name or LOGGER_NAME)


def configure_logging(verbose: bool = False) -> None:
    """Configure simple console logging for CLI runs."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def require_optional(package: str, import_name: str | None = None):
    """Import an optional dependency with a clear installation error."""

    module_name = import_name or package
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        message = (
            f"Missing optional dependency '{package}'. Install project dependencies with "
            "`pip install -e .` or `pip install -r requirements.txt`."
        )
        raise ImportError(message) from exc


def ensure_dir(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""

    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def utc_now_iso() -> str:
    """Return an ISO 8601 UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_csv(
    rows: Iterable[Mapping[str, object]],
    output: str | Path,
    fieldnames: Sequence[str] | None = None,
) -> Path:
    """Write dictionaries to CSV, creating parent directories."""

    output_path = Path(output)
    ensure_dir(output_path.parent)
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with output_path.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def json_text(value: object) -> str:
    """Serialize a compact JSON value for CSV fields."""

    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def normalize_layer_name(name: str) -> str:
    """Normalize a layer or file stem for NFHL layer comparisons."""

    return Path(name).stem.upper()


def parse_bbox(values: Sequence[str] | Sequence[float] | None) -> tuple[float, float, float, float] | None:
    """Parse a four-value bounding box."""

    if values is None:
        return None
    if len(values) != 4:
        raise ValueError("--bbox requires exactly four values: minx miny maxx maxy")
    minx, miny, maxx, maxy = (float(v) for v in values)
    if minx >= maxx or miny >= maxy:
        raise ValueError("Invalid bbox: expected minx < maxx and miny < maxy")
    return minx, miny, maxx, maxy


def safe_percent(numerator: float, denominator: float) -> float:
    """Return percentage while avoiding divide-by-zero."""

    if denominator == 0:
        return 0.0
    return (numerator / denominator) * 100.0

