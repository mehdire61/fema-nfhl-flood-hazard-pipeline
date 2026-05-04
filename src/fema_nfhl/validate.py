"""Validation checks for FEMA NFHL vector layers."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .catalog import IMPORTANT_LAYERS, find_layer_sources, read_layer
from .utils import write_csv


VALIDATION_COLUMNS = ["check", "severity", "layer", "status", "message", "value"]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationFinding:
    """One validation report row."""

    check: str
    severity: str
    layer: str
    status: str
    message: str
    value: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return a CSV-friendly dictionary."""

        return asdict(self)


def validate_layers(
    input_path: str | Path,
    *,
    output_csv: str | Path | None = None,
) -> list[ValidationFinding]:
    """Validate extracted NFHL layers."""

    sources = find_layer_sources(input_path)
    findings: list[ValidationFinding] = []
    findings.extend(check_required_layers(source.layer_name for source in sources))
    for source in sources:
        if source.layer_name not in IMPORTANT_LAYERS:
            continue
        try:
            gdf = read_layer(source)
        except Exception as exc:
            findings.append(
                ValidationFinding("layer_readable", "error", source.layer_name, "fail", f"Could not read layer: {exc}")
            )
            continue
        findings.extend(validate_geodataframe(gdf, source.layer_name))

    if output_csv:
        write_validation_report(findings, output_csv)
    return findings


def check_required_layers(layer_names: Iterable[str]) -> list[ValidationFinding]:
    """Check for required or strongly expected NFHL layers."""

    present = {name.upper() for name in layer_names}
    findings: list[ValidationFinding] = []
    required = {"S_FLD_HAZ_AR"}
    recommended = {"S_BFE"}
    for layer in sorted(required):
        status = "pass" if layer in present else "fail"
        severity = "info" if status == "pass" else "error"
        message = f"Required layer {layer} is present." if status == "pass" else f"Required layer {layer} is missing."
        findings.append(ValidationFinding("required_layer_present", severity, layer, status, message))
    for layer in sorted(recommended):
        status = "pass" if layer in present else "warning"
        severity = "info" if status == "pass" else "warning"
        message = (
            f"Recommended layer {layer} is present."
            if status == "pass"
            else f"Recommended layer {layer} is missing; BFE lines will be absent from the interactive map."
        )
        findings.append(ValidationFinding("recommended_layer_present", severity, layer, status, message))
    return findings


def validate_geodataframe(gdf, layer_name: str) -> list[ValidationFinding]:
    """Run layer-level vector validation checks."""

    findings: list[ValidationFinding] = []
    crs_status = "pass" if gdf.crs else "fail"
    findings.append(
        ValidationFinding(
            "crs_present",
            "info" if gdf.crs else "error",
            layer_name,
            crs_status,
            "CRS is present." if gdf.crs else "CRS is missing.",
            str(gdf.crs or ""),
        )
    )

    empty_count = int(gdf.geometry.is_empty.sum()) if "geometry" in gdf else 0
    findings.append(_count_finding("empty_geometries", "warning", layer_name, empty_count))

    invalid_count = int((~gdf.geometry.is_valid).sum()) if "geometry" in gdf else 0
    findings.append(_count_finding("invalid_geometries", "warning", layer_name, invalid_count))

    field_names = {column.upper(): column for column in gdf.columns}
    if layer_name == "S_FLD_HAZ_AR":
        findings.extend(_field_check(gdf, layer_name, "FLD_ZONE", expected=True))
        findings.extend(_field_check(gdf, layer_name, "ZONE_SUBTY", expected=True))
    if layer_name == "S_BFE":
        elev_field = field_names.get("ELEV") or field_names.get("STATIC_BFE")
        if elev_field:
            findings.extend(validate_bfe_values(gdf[elev_field], layer_name, elev_field))
        else:
            findings.append(ValidationFinding("bfe_elevation_field", "error", layer_name, "fail", "Missing ELEV or STATIC_BFE."))
    return findings


def validate_bfe_values(values, layer_name: str = "S_BFE", field_name: str = "ELEV") -> list[ValidationFinding]:
    """Validate BFE elevation values for null, zero, and non-numeric records."""

    numeric = pd.to_numeric(values, errors="coerce")
    null_count = int(values.isna().sum())
    non_numeric = int(numeric.isna().sum() - null_count)
    zero_count = int((numeric == 0).sum())
    return [
        _count_finding("bfe_null_values", "error", layer_name, null_count, field_name),
        _count_finding("bfe_non_numeric_values", "error", layer_name, non_numeric, field_name),
        _count_finding("bfe_zero_values", "warning", layer_name, zero_count, field_name),
    ]


def write_validation_report(findings: Iterable[ValidationFinding], output: str | Path) -> Path:
    """Write validation findings to CSV."""

    return write_csv((finding.to_dict() for finding in findings), output, VALIDATION_COLUMNS)


def _field_check(gdf, layer_name: str, field_name: str, *, expected: bool) -> list[ValidationFinding]:
    columns = {column.upper(): column for column in gdf.columns}
    if field_name not in columns:
        severity = "error" if expected else "warning"
        return [ValidationFinding(f"{field_name.lower()}_present", severity, layer_name, "fail", f"Missing {field_name}.")]
    null_count = int(gdf[columns[field_name]].isna().sum())
    return [_count_finding(f"{field_name.lower()}_missing_values", "warning", layer_name, null_count)]


def _count_finding(
    check: str,
    severity_if_nonzero: str,
    layer: str,
    count: int,
    value: str | None = None,
) -> ValidationFinding:
    status = "pass" if count == 0 else "warning"
    severity = "info" if count == 0 else severity_if_nonzero
    message = f"{check.replace('_', ' ').capitalize()}: {count}"
    return ValidationFinding(check, severity, layer, status, message, str(count if value is None else value))


