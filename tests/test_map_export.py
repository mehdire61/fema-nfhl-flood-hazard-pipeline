"""Tests for static map image export helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from fema_nfhl import map_export
from fema_nfhl.cli import main


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_export_html_map_image_uses_browser_cli_fallback(tmp_path, monkeypatch) -> None:
    html_path = tmp_path / "map.html"
    html_path.write_text("<html><body>map</body></html>", encoding="utf-8")
    output_path = tmp_path / "map.png"
    fake_browser = tmp_path / "chrome.exe"
    fake_browser.write_text("", encoding="utf-8")
    commands: list[list[str]] = []

    def fail_playwright(*args, **kwargs):
        raise RuntimeError("playwright unavailable")

    def fake_run(command, **kwargs):
        commands.append(command)
        screenshot_arg = next(arg for arg in command if str(arg).startswith("--screenshot="))
        Path(str(screenshot_arg).split("=", 1)[1]).write_bytes(PNG_BYTES)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(map_export, "_export_with_playwright", fail_playwright)
    monkeypatch.setattr(map_export, "find_browser_executable", lambda browser_path=None: fake_browser)
    monkeypatch.setattr(map_export.subprocess, "run", fake_run)

    result = map_export.export_html_map_image(html_path, output_path, width=1200, height=800, scale=1.5, wait_seconds=0)

    assert result == output_path
    assert output_path.exists()
    assert any("--window-size=1200,800" in arg for arg in commands[0])
    assert any("--force-device-scale-factor=1.5" in arg for arg in commands[0])


def test_export_html_map_image_rejects_unsupported_extension(tmp_path) -> None:
    html_path = tmp_path / "map.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    with pytest.raises(ValueError, match="must end with"):
        map_export.export_html_map_image(html_path, tmp_path / "map.pdf")


def test_find_browser_executable_uses_env_path(tmp_path, monkeypatch) -> None:
    browser = tmp_path / "browser.exe"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setenv("FEMA_NFHL_BROWSER", str(browser))

    assert map_export.find_browser_executable() == browser


def test_export_map_image_cli_calls_exporter(tmp_path, monkeypatch) -> None:
    html_path = tmp_path / "map.html"
    output_path = tmp_path / "map.png"
    html_path.write_text("<html></html>", encoding="utf-8")
    calls = []

    def fake_export(*args, **kwargs):
        calls.append((args, kwargs))
        output_path.write_bytes(PNG_BYTES)
        return output_path

    monkeypatch.setattr(map_export, "export_html_map_image", fake_export)

    exit_code = main(
        [
            "export-map-image",
            "--html",
            str(html_path),
            "--image-output",
            str(output_path),
            "--image-width",
            "1600",
        ]
    )

    assert exit_code == 0
    assert calls
    assert calls[0][1]["width"] == 1600
