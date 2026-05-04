param(
    [string]$State,
    [string]$CountyFips,
    [string]$County,
    [string]$Slug,
    [string]$RawDir = "data/raw",
    [string]$ExtractedDir = "data/extracted",
    [string]$OutputsDir = "outputs",
    [int]$Timeout = 60,
    [int]$Retries = 3,
    [switch]$ForceExtract,
    [switch]$SkipImage,
    [ValidateSet("png", "jpg", "jpeg")]
    [string]$ImageFormat = "png",
    [int]$ImageWidth = 2200,
    [int]$ImageHeight = 1400,
    [double]$ImageScale = 2.0,
    [double]$ImageWait = 5.0,
    [int]$ImageQuality = 95,
    [string]$BrowserPath,
    [string]$Python = "python",
    [switch]$Help
)

function Show-Help {
    @"
Run the FEMA NFHL county map workflow:
  download state packages -> find county FIPS zip -> extract -> catalog -> validate -> map

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/run_county_nfhl_map.ps1 -State MARYLAND -County "Montgomery" -Slug montgomery_md
  powershell -ExecutionPolicy Bypass -File scripts/run_county_nfhl_map.ps1 -State MARYLAND -CountyFips 24031 -Slug montgomery_md

Options:
  -State STATE_NAME       FEMA state name, e.g. MARYLAND or CALIFORNIA. Required.
  -County COUNTY_NAME     County name; script resolves the five-digit Census/FEMA county FIPS.
  -CountyFips FIPS       Five-digit county FIPS prefix used in FEMA package names.
  -Slug NAME             Output filename slug. Default: <state>_<county-fips>.
  -RawDir PATH           Raw download directory. Default: data/raw.
  -ExtractedDir PATH     Extracted data directory. Default: data/extracted.
  -OutputsDir PATH       Output directory. Default: outputs.
  -Timeout SECONDS       Request timeout for downloads. Default: 60.
  -Retries COUNT         Download retries. Default: 3.
  -ForceExtract          Re-extract even when extracted folder already exists.
  -SkipImage             Do not attempt static PNG/JPEG export.
  -ImageFormat FORMAT    Static image format: png, jpg, or jpeg. Default: png.
  -ImageWidth PX         Static image browser viewport width. Default: 2200.
  -ImageHeight PX        Static image browser viewport height. Default: 1400.
  -ImageScale VALUE      Static image device scale factor. Default: 2.
  -ImageWait SECONDS     Wait time for basemap tiles before capture. Default: 5.
  -ImageQuality 1-100    JPEG quality. PNG ignores this. Default: 95.
  -BrowserPath PATH      Optional Chrome/Edge/Chromium executable path for image export.
  -Python PATH_OR_NAME   Python executable. Default: python.
  -Help                  Show this help.

Notes:
  - Run from the repository root after installing the package with: python -m pip install -e .
  - This script creates catalog, validation, HTML map, and best-effort static image outputs.
  - Exposure summaries still require an admin boundary layer and should be run separately.
"@
}

if ($Help) {
    Show-Help
    exit 0
}

if ([string]::IsNullOrWhiteSpace($State) -or ([string]::IsNullOrWhiteSpace($CountyFips) -and [string]::IsNullOrWhiteSpace($County))) {
    Write-Error "State and either County or CountyFips are required."
    Show-Help
    exit 2
}

if ([string]::IsNullOrWhiteSpace($CountyFips) -and -not [string]::IsNullOrWhiteSpace($County)) {
    Write-Host "==> Resolving county FIPS for $County, $State"
    $CountyFips = (& $Python -m fema_nfhl.cli county-code --state $State --county $County --value-only).Trim()
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "==> County FIPS/GEOID: $CountyFips"
}

if ($CountyFips -notmatch '^\d{5}$') {
    Write-Error "CountyFips must be a five-digit county FIPS code."
    exit 2
}

$StateUpper = $State.ToUpperInvariant()
if ([string]::IsNullOrWhiteSpace($Slug)) {
    $StateSlug = $StateUpper.ToLowerInvariant().Replace(" ", "_")
    $Slug = "${StateSlug}_${CountyFips}"
}

New-Item -ItemType Directory -Force -Path $RawDir, $ExtractedDir, $OutputsDir | Out-Null

$DownloadCatalog = Join-Path $OutputsDir "${Slug}_download_catalog.csv"
$CatalogCsv = Join-Path $OutputsDir "${Slug}_nfhl_catalog.csv"
$ValidationCsv = Join-Path $OutputsDir "${Slug}_validation_report.csv"
$MapHtml = Join-Path $OutputsDir "${Slug}_flood_hazard_map.html"
$ImageExt = $ImageFormat.ToLowerInvariant()
if ($ImageExt -eq "jpeg") { $ImageExt = "jpg" }
$MapImage = Join-Path $OutputsDir "${Slug}_flood_hazard_map.${ImageExt}"

Write-Host "==> Downloading FEMA NFHL packages for $StateUpper"
& $Python -m fema_nfhl.cli download `
    --state $StateUpper `
    --output $RawDir `
    --skip-existing `
    --timeout $Timeout `
    --retries $Retries `
    --catalog-csv $DownloadCatalog
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$StateRawDir = Join-Path $RawDir $StateUpper
$zip = Get-ChildItem -Path $StateRawDir -Filter "${CountyFips}*.zip" -File -ErrorAction SilentlyContinue |
    Sort-Object Name |
    Select-Object -Last 1

if ($null -eq $zip) {
    Write-Error "No downloaded NFHL zip found for county FIPS $CountyFips in $StateRawDir. Check $DownloadCatalog for downloaded file names and FEMA availability."
    exit 1
}

$ZipPath = $zip.FullName
$ZipStem = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
$ExtractedPath = Join-Path $ExtractedDir $ZipStem

if ($ForceExtract -or -not (Test-Path -LiteralPath $ExtractedPath)) {
    Write-Host "==> Extracting $ZipPath"
    & $Python -m fema_nfhl.cli extract --zip $ZipPath --output $ExtractedDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "==> Reusing existing extracted folder: $ExtractedPath"
}

Write-Host "==> Cataloging NFHL layers"
& $Python -m fema_nfhl.cli catalog --input $ExtractedPath --output $CatalogCsv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Validating NFHL layers"
& $Python -m fema_nfhl.cli validate --input $ExtractedPath --output $ValidationCsv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Creating interactive HTML map"
& $Python -m fema_nfhl.cli map --input $ExtractedPath --output $MapHtml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipImage) {
    Write-Host "==> Exporting static map image"
    $ImageArgs = @(
        "-m", "fema_nfhl.cli", "export-map-image",
        "--html", $MapHtml,
        "--image-output", $MapImage,
        "--image-width", $ImageWidth,
        "--image-height", $ImageHeight,
        "--image-scale", $ImageScale,
        "--image-wait", $ImageWait,
        "--image-quality", $ImageQuality
    )
    if (-not [string]::IsNullOrWhiteSpace($BrowserPath)) {
        $ImageArgs += @("--browser-path", $BrowserPath)
    }
    & $Python @ImageArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Static map image export failed. The interactive HTML map is still available."
    }
}

@"

Done.
County NFHL zip:      $ZipPath
Extracted folder:     $ExtractedPath
Download catalog:     $DownloadCatalog
Layer catalog:        $CatalogCsv
Validation report:    $ValidationCsv
Interactive map HTML: $MapHtml
Static map image:     $(if ($SkipImage) { "skipped" } else { $MapImage })

Open the HTML map in a browser:
  $MapHtml
"@
