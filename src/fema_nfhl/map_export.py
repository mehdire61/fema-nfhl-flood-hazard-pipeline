"""Export interactive HTML maps to static presentation images."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .utils import ensure_dir


LOGGER = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def export_html_map_image(
    html_path: str | Path,
    output_image: str | Path,
    *,
    width: int = 2200,
    height: int = 1400,
    scale: float = 2.0,
    wait_seconds: float = 5.0,
    quality: int = 95,
    browser_path: str | Path | None = None,
) -> Path:
    """Render a Folium/Leaflet HTML map to a high-resolution PNG or JPEG.

    This is a presentation export. It captures the visible browser rendering,
    including basemap tiles, the legend, and active layers. It is not a
    geospatial raster product.
    """

    html_path = Path(html_path).resolve()
    output_image = Path(output_image).resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"HTML map does not exist: {html_path}")
    if output_image.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError("Output image must end with .png, .jpg, or .jpeg.")
    if width <= 0 or height <= 0:
        raise ValueError("Image width and height must be positive.")
    if scale <= 0:
        raise ValueError("Image scale must be positive.")
    if not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be between 1 and 100.")

    ensure_dir(output_image.parent)
    resolved_browser_path = find_browser_executable(browser_path)
    try:
        return _export_with_playwright(
            html_path,
            output_image,
            width=width,
            height=height,
            scale=scale,
            wait_seconds=wait_seconds,
            quality=quality,
            browser_path=resolved_browser_path,
        )
    except Exception as exc:
        LOGGER.debug("Playwright map export unavailable; trying browser CLI fallback: %s", exc)

    return _export_with_browser_cli(
        html_path,
        output_image,
        width=width,
        height=height,
        scale=scale,
        wait_seconds=wait_seconds,
        quality=quality,
        browser_path=resolved_browser_path,
    )


def find_browser_executable(browser_path: str | Path | None = None) -> Path | None:
    """Find a Chrome/Edge/Chromium executable for headless screenshot export."""

    if browser_path:
        candidate = Path(browser_path)
        return candidate if candidate.exists() else None
    env_path = os.getenv("FEMA_NFHL_BROWSER")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    for name in ["chrome", "google-chrome", "chromium", "chromium-browser", "msedge", "microsoft-edge"]:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)

    common_paths = [
        Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LocalAppData", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for candidate in common_paths:
        if candidate.exists():
            return candidate
    return None


def _export_with_playwright(
    html_path: Path,
    output_image: Path,
    *,
    width: int,
    height: int,
    scale: float,
    wait_seconds: float,
    quality: int,
    browser_path: Path | None,
) -> Path:
    from playwright.sync_api import sync_playwright

    image_type = "jpeg" if output_image.suffix.lower() in {".jpg", ".jpeg"} else "png"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(browser_path) if browser_path else None,
            headless=True,
            args=["--allow-file-access-from-files"],
        )
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            )
            page.goto(html_path.as_uri(), wait_until="networkidle", timeout=max(15_000, int((wait_seconds + 15) * 1000)))
            if wait_seconds > 0:
                page.wait_for_timeout(int(wait_seconds * 1000))
            kwargs = {"path": str(output_image), "type": image_type, "full_page": False}
            if image_type == "jpeg":
                kwargs["quality"] = quality
            page.screenshot(**kwargs)
        finally:
            browser.close()
    LOGGER.info("Wrote static map image %s", output_image)
    return output_image


def _export_with_browser_cli(
    html_path: Path,
    output_image: Path,
    *,
    width: int,
    height: int,
    scale: float,
    wait_seconds: float,
    quality: int,
    browser_path: Path | None,
) -> Path:
    browser = find_browser_executable(browser_path)
    if browser is None:
        raise RuntimeError(
            "Static map image export requires Playwright or a local Chrome/Edge/Chromium executable. "
            "Install the optional export dependency or set FEMA_NFHL_BROWSER to the browser executable path."
        )

    target_path = output_image
    temp_png: Path | None = None
    if output_image.suffix.lower() in {".jpg", ".jpeg"}:
        temp_handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_handle.close()
        temp_png = Path(temp_handle.name)
        target_path = temp_png

    with tempfile.TemporaryDirectory(prefix="fema_nfhl_browser_") as profile_dir:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile_dir}",
            f"--window-size={width},{height}",
            f"--force-device-scale-factor={scale}",
            f"--virtual-time-budget={max(0, int(wait_seconds * 1000))}",
            f"--screenshot={target_path}",
            html_path.as_uri(),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30, int(wait_seconds + 30)),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Browser screenshot export failed: "
                f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
            )

    if temp_png is not None:
        try:
            from PIL import Image

            with Image.open(temp_png) as image:
                image.convert("RGB").save(output_image, quality=quality)
        finally:
            temp_png.unlink(missing_ok=True)

    if not output_image.exists():
        raise RuntimeError(f"Browser screenshot did not create expected output: {output_image}")
    LOGGER.info("Wrote static map image %s", output_image)
    return output_image
