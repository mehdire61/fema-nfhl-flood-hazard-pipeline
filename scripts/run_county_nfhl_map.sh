#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Run the FEMA NFHL county map workflow:
  download state packages -> find county FIPS zip -> extract -> catalog -> validate -> map

Usage:
  scripts/run_county_nfhl_map.sh --state MARYLAND --county Montgomery --slug montgomery_md
  scripts/run_county_nfhl_map.sh --state MARYLAND --county-fips 24031 --slug montgomery_md

Options:
  --state STATE_NAME       FEMA state name, e.g. MARYLAND or CALIFORNIA. Required.
  --county COUNTY_NAME     County name; script resolves the five-digit Census/FEMA county FIPS.
  --county-fips FIPS      Five-digit county FIPS prefix used in FEMA package names.
  --slug NAME             Output filename slug. Default: <state>_<county-fips>.
  --raw-dir PATH          Raw download directory. Default: data/raw.
  --extracted-dir PATH    Extracted data directory. Default: data/extracted.
  --outputs-dir PATH      Output directory. Default: outputs.
  --timeout SECONDS       Request timeout for downloads. Default: 60.
  --retries COUNT         Download retries. Default: 3.
  --force-extract         Re-extract even when extracted folder already exists.
  --skip-image            Do not attempt static PNG/JPEG export.
  --image-format FORMAT   Static image format: png, jpg, or jpeg. Default: png.
  --image-width PX        Static image browser viewport width. Default: 2200.
  --image-height PX       Static image browser viewport height. Default: 1400.
  --image-scale VALUE     Static image device scale factor. Default: 2.
  --image-wait SECONDS    Wait time for basemap tiles before capture. Default: 5.
  --image-quality 1-100   JPEG quality. PNG ignores this. Default: 95.
  --browser-path PATH     Optional Chrome/Edge/Chromium executable path for image export.
  -h, --help              Show this help.

Notes:
  - Run from the repository root after installing the package with: python -m pip install -e .
  - This script creates catalog, validation, HTML map, and best-effort static image outputs.
  - Exposure summaries still require an admin boundary layer and should be run separately.
EOF
}

STATE=""
COUNTY_FIPS=""
COUNTY=""
SLUG=""
RAW_DIR="data/raw"
EXTRACTED_DIR="data/extracted"
OUTPUTS_DIR="outputs"
TIMEOUT="60"
RETRIES="3"
FORCE_EXTRACT="false"
SKIP_IMAGE="false"
IMAGE_FORMAT="png"
IMAGE_WIDTH="2200"
IMAGE_HEIGHT="1400"
IMAGE_SCALE="2"
IMAGE_WAIT="5"
IMAGE_QUALITY="95"
BROWSER_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --state)
      STATE="${2:-}"
      shift 2
      ;;
    --county-fips)
      COUNTY_FIPS="${2:-}"
      shift 2
      ;;
    --county)
      COUNTY="${2:-}"
      shift 2
      ;;
    --slug)
      SLUG="${2:-}"
      shift 2
      ;;
    --raw-dir)
      RAW_DIR="${2:-}"
      shift 2
      ;;
    --extracted-dir)
      EXTRACTED_DIR="${2:-}"
      shift 2
      ;;
    --outputs-dir)
      OUTPUTS_DIR="${2:-}"
      shift 2
      ;;
    --timeout)
      TIMEOUT="${2:-}"
      shift 2
      ;;
    --retries)
      RETRIES="${2:-}"
      shift 2
      ;;
    --force-extract)
      FORCE_EXTRACT="true"
      shift
      ;;
    --skip-image)
      SKIP_IMAGE="true"
      shift
      ;;
    --image-format)
      IMAGE_FORMAT="${2:-}"
      shift 2
      ;;
    --image-width)
      IMAGE_WIDTH="${2:-}"
      shift 2
      ;;
    --image-height)
      IMAGE_HEIGHT="${2:-}"
      shift 2
      ;;
    --image-scale)
      IMAGE_SCALE="${2:-}"
      shift 2
      ;;
    --image-wait)
      IMAGE_WAIT="${2:-}"
      shift 2
      ;;
    --image-quality)
      IMAGE_QUALITY="${2:-}"
      shift 2
      ;;
    --browser-path)
      BROWSER_PATH="${2:-}"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      show_help >&2
      exit 2
      ;;
  esac
done

if [[ -z "$STATE" || ( -z "$COUNTY_FIPS" && -z "$COUNTY" ) ]]; then
  echo "ERROR: --state and either --county or --county-fips are required." >&2
  show_help >&2
  exit 2
fi

if [[ -z "$COUNTY_FIPS" && -n "$COUNTY" ]]; then
  echo "==> Resolving county FIPS for $COUNTY, $STATE"
  COUNTY_FIPS="$(python -m fema_nfhl.cli county-code --state "$STATE" --county "$COUNTY" --value-only)"
  echo "==> County FIPS/GEOID: $COUNTY_FIPS"
fi

if [[ ! "$COUNTY_FIPS" =~ ^[0-9]{5}$ ]]; then
  echo "ERROR: --county-fips must be a five-digit county FIPS code." >&2
  exit 2
fi

STATE_UPPER="$(printf '%s' "$STATE" | tr '[:lower:]' '[:upper:]')"
if [[ -z "$SLUG" ]]; then
  STATE_SLUG="$(printf '%s' "$STATE_UPPER" | tr '[:upper:] ' '[:lower:]_')"
  SLUG="${STATE_SLUG}_${COUNTY_FIPS}"
fi

mkdir -p "$RAW_DIR" "$EXTRACTED_DIR" "$OUTPUTS_DIR"

DOWNLOAD_CATALOG="$OUTPUTS_DIR/${SLUG}_download_catalog.csv"
CATALOG_CSV="$OUTPUTS_DIR/${SLUG}_nfhl_catalog.csv"
VALIDATION_CSV="$OUTPUTS_DIR/${SLUG}_validation_report.csv"
MAP_HTML="$OUTPUTS_DIR/${SLUG}_flood_hazard_map.html"
IMAGE_EXT="$(printf '%s' "$IMAGE_FORMAT" | tr '[:upper:]' '[:lower:]')"
if [[ "$IMAGE_EXT" == "jpeg" ]]; then
  IMAGE_EXT="jpg"
fi
if [[ "$IMAGE_EXT" != "png" && "$IMAGE_EXT" != "jpg" ]]; then
  echo "ERROR: --image-format must be png, jpg, or jpeg." >&2
  exit 2
fi
MAP_IMAGE="$OUTPUTS_DIR/${SLUG}_flood_hazard_map.${IMAGE_EXT}"

echo "==> Downloading FEMA NFHL packages for $STATE_UPPER"
python -m fema_nfhl.cli download \
  --state "$STATE_UPPER" \
  --output "$RAW_DIR" \
  --skip-existing \
  --timeout "$TIMEOUT" \
  --retries "$RETRIES" \
  --catalog-csv "$DOWNLOAD_CATALOG"

STATE_RAW_DIR="$RAW_DIR/$STATE_UPPER"
ZIP_PATH="$(find "$STATE_RAW_DIR" -maxdepth 1 -type f -name "${COUNTY_FIPS}*.zip" | sort | tail -n 1 || true)"
if [[ -z "$ZIP_PATH" ]]; then
  echo "ERROR: No downloaded NFHL zip found for county FIPS $COUNTY_FIPS in $STATE_RAW_DIR." >&2
  echo "Check $DOWNLOAD_CATALOG for downloaded file names and FEMA availability." >&2
  exit 1
fi

ZIP_STEM="$(basename "$ZIP_PATH" .zip)"
EXTRACTED_PATH="$EXTRACTED_DIR/$ZIP_STEM"

if [[ "$FORCE_EXTRACT" == "true" || ! -d "$EXTRACTED_PATH" ]]; then
  echo "==> Extracting $ZIP_PATH"
  python -m fema_nfhl.cli extract --zip "$ZIP_PATH" --output "$EXTRACTED_DIR"
else
  echo "==> Reusing existing extracted folder: $EXTRACTED_PATH"
fi

echo "==> Cataloging NFHL layers"
python -m fema_nfhl.cli catalog --input "$EXTRACTED_PATH" --output "$CATALOG_CSV"

echo "==> Validating NFHL layers"
python -m fema_nfhl.cli validate --input "$EXTRACTED_PATH" --output "$VALIDATION_CSV"

echo "==> Creating interactive HTML map"
python -m fema_nfhl.cli map --input "$EXTRACTED_PATH" --output "$MAP_HTML"

if [[ "$SKIP_IMAGE" != "true" ]]; then
  echo "==> Exporting static map image"
  IMAGE_ARGS=(
    -m fema_nfhl.cli export-map-image
    --html "$MAP_HTML"
    --image-output "$MAP_IMAGE"
    --image-width "$IMAGE_WIDTH"
    --image-height "$IMAGE_HEIGHT"
    --image-scale "$IMAGE_SCALE"
    --image-wait "$IMAGE_WAIT"
    --image-quality "$IMAGE_QUALITY"
  )
  if [[ -n "$BROWSER_PATH" ]]; then
    IMAGE_ARGS+=(--browser-path "$BROWSER_PATH")
  fi
  if ! python "${IMAGE_ARGS[@]}"; then
    echo "WARNING: Static map image export failed. The interactive HTML map is still available." >&2
  fi
fi

cat <<EOF

Done.
County NFHL zip:      $ZIP_PATH
Extracted folder:     $EXTRACTED_PATH
Download catalog:     $DOWNLOAD_CATALOG
Layer catalog:        $CATALOG_CSV
Validation report:    $VALIDATION_CSV
Interactive map HTML: $MAP_HTML
Static map image:     $(if [[ "$SKIP_IMAGE" == "true" ]]; then printf 'skipped'; else printf '%s' "$MAP_IMAGE"; fi)

Open the HTML map in a browser:
  $MAP_HTML
EOF
