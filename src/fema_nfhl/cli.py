"""Command-line interface for the FEMA NFHL flood hazard pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .utils import configure_logging


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""

    parser = argparse.ArgumentParser(
        prog="python -m fema_nfhl.cli",
        description="FEMA NFHL data ingestion, validation, transformation, mapping, and exposure analysis.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _download_parser(subparsers)
    _county_code_parser(subparsers)
    _quickstart_parser(subparsers)
    _extract_parser(subparsers)
    _catalog_parser(subparsers)
    _clip_parser(subparsers)
    _validate_parser(subparsers)
    _transform_parser(subparsers)
    _map_parser(subparsers)
    _export_map_image_parser(subparsers)
    _exposure_parser(subparsers)
    _plot_exposure_parser(subparsers)
    return parser


def _download_parser(subparsers) -> None:
    parser = subparsers.add_parser("download", help="Download FEMA NFHL zip files.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--state", help="State name to download, for example CALIFORNIA.")
    scope.add_argument("--all-states", action="store_true", help="Download all discovered state/community files.")
    parser.add_argument("--output", required=True, type=Path, help="Output directory for raw downloads.")
    parser.add_argument("--skip-existing", action="store_true", default=False, help="Skip non-empty files already present.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Number of retry attempts for transient HTTP failures.")
    parser.add_argument("--catalog-csv", type=Path, help="Path for the download catalog CSV.")
    parser.add_argument("--source-url", default=None, help="Optional FEMA search result URL override.")
    parser.set_defaults(func=_cmd_download)


def _county_code_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "county-code",
        help="Look up Census/FEMA county FIPS prefixes used in county NFHL zip names.",
    )
    parser.add_argument("--state", help="State name, postal abbreviation, or two-digit state FIPS, for example MD.")
    parser.add_argument("--county", help="County name, with or without suffix, for example Montgomery.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum matches to display. Default: 20.")
    parser.add_argument("--value-only", action="store_true", help="Print only the five-digit county GEOID/FIPS.")
    parser.set_defaults(func=_cmd_county_code)


def _quickstart_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "quickstart",
        help="Run a county NFHL smoke test: extract, catalog, validate, and create an HTML map.",
    )
    parser.add_argument("--zip", required=True, type=Path, dest="zip_path", help="County/community NFHL zip file.")
    parser.add_argument("--extracted-root", type=Path, default=Path("data/extracted"), help="Extraction root directory.")
    parser.add_argument("--outputs", type=Path, default=Path("outputs"), help="Output directory for CSV reports and HTML map.")
    parser.add_argument("--overwrite-extract", action="store_true", help="Extract again even if the target folder already exists.")
    parser.set_defaults(func=_cmd_quickstart)


def _extract_parser(subparsers) -> None:
    parser = subparsers.add_parser("extract", help="Safely extract an NFHL zip file.")
    parser.add_argument("--zip", required=True, type=Path, dest="zip_path", help="NFHL zip file.")
    parser.add_argument("--output", required=True, type=Path, help="Extraction root directory.")
    parser.set_defaults(func=_cmd_extract)


def _catalog_parser(subparsers) -> None:
    parser = subparsers.add_parser("catalog", help="Catalog extracted NFHL layers.")
    parser.add_argument("--input", required=True, type=Path, help="Extracted NFHL directory.")
    parser.add_argument("--output", required=True, type=Path, help="Output catalog CSV.")
    parser.set_defaults(func=_cmd_catalog)


def _clip_parser(subparsers) -> None:
    parser = subparsers.add_parser("clip", help="Prepare a county- or bbox-scale NFHL case-study folder.")
    parser.add_argument("--input", required=True, type=Path, help="Extracted NFHL directory, often from a larger package.")
    parser.add_argument("--output", required=True, type=Path, help="Output directory for clipped case-study layers.")
    clip_area = parser.add_mutually_exclusive_group(required=True)
    clip_area.add_argument("--boundary", type=Path, help="County or study-area boundary vector layer.")
    clip_area.add_argument("--bbox", nargs=4, metavar=("MINX", "MINY", "MAXX", "MAXY"), help="Bounding box to clip to.")
    parser.add_argument("--boundary-id-field", help="Optional boundary field to filter, for example GEOID.")
    parser.add_argument("--boundary-id-value", help="Optional boundary value to filter, for example 06001.")
    parser.add_argument("--bbox-crs", help="CRS for --bbox. Defaults to each NFHL layer CRS if omitted.")
    parser.add_argument("--layers", nargs="*", help="Optional NFHL layer names to clip.")
    parser.add_argument(
        "--format",
        choices=["shapefile", "gpkg", "geoparquet"],
        default="shapefile",
        help="Output format for clipped layers. Default: shapefile.",
    )
    parser.add_argument("--keep-empty", action="store_true", help="Write empty clipped layers instead of skipping them.")
    parser.set_defaults(func=_cmd_clip)


def _validate_parser(subparsers) -> None:
    parser = subparsers.add_parser("validate", help="Validate extracted NFHL layers.")
    parser.add_argument("--input", required=True, type=Path, help="Extracted NFHL directory.")
    parser.add_argument("--output", required=True, type=Path, help="Output validation report CSV.")
    parser.set_defaults(func=_cmd_validate)


def _transform_parser(subparsers) -> None:
    parser = subparsers.add_parser("transform", help="Convert selected NFHL layers to GeoParquet or GeoPackage.")
    parser.add_argument("--input", required=True, type=Path, help="Extracted NFHL directory.")
    parser.add_argument("--output", required=True, type=Path, help="Processed data output directory.")
    parser.add_argument("--format", choices=["geoparquet", "gpkg"], default="geoparquet", help="Output vector format.")
    parser.add_argument("--layers", nargs="*", help="Optional layer names to transform.")
    parser.set_defaults(func=_cmd_transform)


def _map_parser(subparsers) -> None:
    parser = subparsers.add_parser("map", help="Create a Folium flood hazard map.")
    parser.add_argument("--input", required=True, type=Path, help="Extracted NFHL directory.")
    parser.add_argument("--output", required=True, type=Path, help="Output HTML map.")
    _image_export_arguments(parser, html_required=False)
    parser.set_defaults(func=_cmd_map)


def _export_map_image_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "export-map-image",
        help="Export an interactive HTML map to a high-resolution PNG or JPEG.",
    )
    _image_export_arguments(parser, html_required=True)
    parser.set_defaults(func=_cmd_export_map_image)


def _image_export_arguments(parser, *, html_required: bool) -> None:
    if html_required:
        parser.add_argument("--html", required=True, type=Path, help="Input HTML map.")
    parser.add_argument(
        "--image-output",
        required=html_required,
        type=Path,
        help="PNG/JPEG screenshot output path." if html_required else "Optional PNG/JPEG screenshot output path.",
    )
    parser.add_argument("--image-width", type=int, default=2200, help="Browser viewport width for image export.")
    parser.add_argument("--image-height", type=int, default=1400, help="Browser viewport height for image export.")
    parser.add_argument("--image-scale", type=float, default=2.0, help="Device scale factor for high-resolution export.")
    parser.add_argument("--image-wait", type=float, default=5.0, help="Seconds to wait for map tiles before capture.")
    parser.add_argument("--image-quality", type=int, default=95, help="JPEG quality, 1-100. PNG ignores this.")
    parser.add_argument("--browser-path", type=Path, help="Optional Chrome/Edge/Chromium executable path.")


def _exposure_parser(subparsers) -> None:
    parser = subparsers.add_parser("exposure", help="Summarize floodplain area by administrative unit.")
    parser.add_argument("--flood-layer", required=True, type=Path, help="Path to S_FLD_HAZ_AR.")
    parser.add_argument("--admin-boundaries", required=True, type=Path, help="Administrative boundary vector layer.")
    parser.add_argument("--output", required=True, type=Path, help="Output area summary CSV.")
    parser.add_argument("--admin-id-field", help="Administrative identifier field.")
    parser.add_argument("--admin-name-field", help="Administrative name field.")
    parser.add_argument("--equal-area-crs", default="EPSG:5070", help="CRS for area calculations. Default: EPSG:5070.")
    parser.set_defaults(func=_cmd_exposure)


def _plot_exposure_parser(subparsers) -> None:
    parser = subparsers.add_parser("plot-exposure", help="Create a static exposure summary chart.")
    parser.add_argument("--summary-csv", required=True, type=Path, help="Floodplain area summary CSV.")
    parser.add_argument("--output", required=True, type=Path, help="Output PNG chart.")
    parser.add_argument("--title", default="Floodplain Area By FEMA Flood Zone", help="Chart title.")
    parser.set_defaults(func=_cmd_plot_exposure)


def _cmd_download(args) -> None:
    from .download import DEFAULT_NFHL_SEARCH_URL, download_nfhl, write_download_catalog

    records = download_nfhl(
        output_dir=args.output,
        state=args.state,
        all_states=args.all_states,
        skip_existing=args.skip_existing,
        timeout=args.timeout,
        retries=args.retries,
        catalog_csv=args.catalog_csv,
        source_url=args.source_url or DEFAULT_NFHL_SEARCH_URL,
    )
    if not args.catalog_csv:
        write_download_catalog(records, args.output / "nfhl_download_catalog.csv")


def _cmd_county_code(args) -> None:
    from .county_lookup import COUNTY_LOOKUP_SOURCE, records_to_csv, resolve_county_fips, search_counties

    if not args.state and not args.county:
        raise ValueError("Provide --state, --county, or both. Example: --state MD --county Montgomery.")
    if args.value_only:
        if not args.state or not args.county:
            raise ValueError("--value-only requires both --state and --county.")
        print(resolve_county_fips(state=args.state, county=args.county).geoid)
        return

    matches = search_counties(state=args.state, county=args.county, limit=args.limit)
    if not matches:
        raise ValueError("No county FIPS matches found.")
    print(records_to_csv(matches))
    print(f"\nSource: {COUNTY_LOOKUP_SOURCE}", file=sys.stderr)


def _cmd_quickstart(args) -> None:
    from .workflow import run_county_quickstart

    run_county_quickstart(
        zip_path=args.zip_path,
        extracted_root=args.extracted_root,
        outputs_dir=args.outputs,
        overwrite_extract=args.overwrite_extract,
    )


def _cmd_extract(args) -> None:
    from .extract import extract_nfhl_zip

    extract_nfhl_zip(args.zip_path, args.output)


def _cmd_catalog(args) -> None:
    from .catalog import catalog_extracted_layers

    catalog_extracted_layers(args.input, args.output)


def _cmd_clip(args) -> None:
    from .case_study import prepare_county_case_study

    prepare_county_case_study(
        args.input,
        args.output,
        boundary_path=args.boundary,
        boundary_id_field=args.boundary_id_field,
        boundary_id_value=args.boundary_id_value,
        bbox=args.bbox,
        bbox_crs=args.bbox_crs,
        layers=args.layers,
        output_format=args.format,
        keep_empty=args.keep_empty,
    )


def _cmd_validate(args) -> None:
    from .validate import validate_layers

    validate_layers(args.input, output_csv=args.output)


def _cmd_transform(args) -> None:
    from .transform import transform_layers

    transform_layers(args.input, args.output, output_format=args.format, layers=args.layers)


def _cmd_map(args) -> None:
    from .mapping import create_interactive_map

    output_html = create_interactive_map(args.input, args.output)
    if args.image_output:
        from .map_export import export_html_map_image

        export_html_map_image(
            output_html,
            args.image_output,
            width=args.image_width,
            height=args.image_height,
            scale=args.image_scale,
            wait_seconds=args.image_wait,
            quality=args.image_quality,
            browser_path=args.browser_path,
        )


def _cmd_export_map_image(args) -> None:
    from .map_export import export_html_map_image

    if not args.image_output:
        raise ValueError("Provide --image-output ending in .png, .jpg, or .jpeg.")
    export_html_map_image(
        args.html,
        args.image_output,
        width=args.image_width,
        height=args.image_height,
        scale=args.image_scale,
        wait_seconds=args.image_wait,
        quality=args.image_quality,
        browser_path=args.browser_path,
    )


def _cmd_exposure(args) -> None:
    from .exposure import floodplain_area_summary

    floodplain_area_summary(
        args.flood_layer,
        args.admin_boundaries,
        args.output,
        admin_id_field=args.admin_id_field,
        admin_name_field=args.admin_name_field,
        equal_area_crs=args.equal_area_crs,
    )


def _cmd_plot_exposure(args) -> None:
    from .visualize import create_exposure_bar_chart

    create_exposure_bar_chart(args.summary_csv, args.output, title=args.title)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    try:
        args.func(args)
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
