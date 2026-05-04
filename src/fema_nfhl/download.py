"""Download FEMA NFHL data with retries, timeouts, and a catalog."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from .utils import ensure_dir, utc_now_iso, write_csv


DEFAULT_NFHL_SEARCH_URL = "https://hazards.fema.gov/femaportal/NFHL/searchResult"
CATALOG_COLUMNS = [
    "state",
    "file_name",
    "url",
    "local_path",
    "status",
    "http_status",
    "file_size_bytes",
    "downloaded_at",
    "error_message",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NfhlDownloadLink:
    """A discovered NFHL download link."""

    state: str
    file_name: str
    url: str


@dataclass
class DownloadRecord:
    """A row in the download catalog."""

    state: str
    file_name: str
    url: str
    local_path: str
    status: str
    http_status: int | None
    file_size_bytes: int | None
    downloaded_at: str
    error_message: str

    def to_dict(self) -> dict[str, object]:
        """Return a CSV-friendly dictionary."""

        return asdict(self)


def build_retry_session(retries: int = 3):
    """Build a requests session with retry behavior for transient failures."""

    requests = _requests()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def discover_nfhl_downloads(
    state: str | None = None,
    *,
    source_url: str = DEFAULT_NFHL_SEARCH_URL,
    timeout: int = 30,
    retries: int = 3,
    session=None,
) -> list[NfhlDownloadLink]:
    """Discover FEMA NFHL download links from the FEMA search results page."""

    session = session or build_retry_session(retries)
    response = session.get(source_url, timeout=timeout)
    response.raise_for_status()
    return parse_nfhl_download_links(response.text, base_url=source_url, state=state)


def parse_nfhl_download_links(
    html: str,
    *,
    base_url: str = DEFAULT_NFHL_SEARCH_URL,
    state: str | None = None,
) -> list[NfhlDownloadLink]:
    """Parse NFHL zip download links from FEMA search result HTML."""

    target_state = state.upper() if state else None
    hrefs = _extract_hrefs(html)
    links: list[NfhlDownloadLink] = []
    seen: set[str] = set()
    for href in hrefs:
        decoded_href = unquote(href)
        if "ProductsDownLoadServlet" not in decoded_href and ".zip" not in decoded_href.lower():
            continue
        url = urljoin(base_url, href.replace(" ", "%20"))
        file_name = infer_file_name(url)
        link_state = infer_state_from_url_or_text(url, decoded_href)
        if target_state and target_state not in link_state.upper() and target_state not in decoded_href.upper():
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(NfhlDownloadLink(state=link_state or state or "UNKNOWN", file_name=file_name, url=url))
    return links


def infer_file_name(url: str) -> str:
    """Infer a local filename from a FEMA download URL."""

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("fileName", "filename", "file"):
        if query.get(key):
            return Path(unquote(query[key][0])).name
    name = Path(unquote(parsed.path)).name
    return name if name else "nfhl_download.zip"


def infer_state_from_url_or_text(url: str, text: str = "") -> str:
    """Infer the state name from a URL query string or nearby text."""

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("state"):
        return unquote(query["state"][0]).strip().upper()
    match = re.search(r"state=([^&\"'>]+)", text, flags=re.IGNORECASE)
    if match:
        return unquote(match.group(1)).strip().upper()
    return "UNKNOWN"


def download_nfhl(
    *,
    output_dir: str | Path,
    state: str | None = None,
    all_states: bool = False,
    skip_existing: bool = True,
    timeout: int = 60,
    retries: int = 3,
    catalog_csv: str | Path | None = None,
    source_url: str = DEFAULT_NFHL_SEARCH_URL,
) -> list[DownloadRecord]:
    """Download NFHL zip files and return catalog records."""

    if not state and not all_states:
        raise ValueError("Provide --state or --all-states.")
    if state and all_states:
        raise ValueError("Use either --state or --all-states, not both.")

    output_dir = ensure_dir(output_dir)
    session = build_retry_session(retries)
    links = discover_nfhl_downloads(
        None if all_states else state,
        source_url=source_url,
        timeout=timeout,
        retries=retries,
        session=session,
    )
    if not links:
        LOGGER.warning("No NFHL download links were discovered for the requested scope.")

    records: list[DownloadRecord] = []
    for link in links:
        record = download_one(link, output_dir, session=session, skip_existing=skip_existing, timeout=timeout)
        records.append(record)

    if catalog_csv:
        write_download_catalog(records, catalog_csv)
    return records


def download_one(
    link: NfhlDownloadLink,
    output_dir: str | Path,
    *,
    session=None,
    skip_existing: bool = True,
    timeout: int = 60,
) -> DownloadRecord:
    """Download a single NFHL link."""

    requests = _requests()
    session = session or requests.Session()
    state_dir = ensure_dir(Path(output_dir) / _safe_folder_name(link.state))
    local_path = state_dir / link.file_name
    timestamp = utc_now_iso()

    if skip_existing and local_path.exists() and local_path.stat().st_size > 0:
        return DownloadRecord(
            state=link.state,
            file_name=link.file_name,
            url=link.url,
            local_path=str(local_path),
            status="skipped_existing",
            http_status=None,
            file_size_bytes=local_path.stat().st_size,
            downloaded_at=timestamp,
            error_message="",
        )

    try:
        with session.get(link.url, stream=True, timeout=timeout) as response:
            http_status = response.status_code
            response.raise_for_status()
            with local_path.open("wb") as dst:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        dst.write(chunk)
        size = local_path.stat().st_size if local_path.exists() else 0
        status = "downloaded" if size > 0 else "failed"
        error = "" if size > 0 else "Downloaded file is empty."
        LOGGER.info("%s %s (%s bytes)", status, local_path, size)
        return DownloadRecord(link.state, link.file_name, link.url, str(local_path), status, http_status, size, timestamp, error)
    except Exception as exc:  # pragma: no cover - exercised via mocked failures in tests
        LOGGER.error("Failed to download %s: %s", link.url, exc)
        return DownloadRecord(link.state, link.file_name, link.url, str(local_path), "failed", None, None, timestamp, str(exc))


def write_download_catalog(records: Iterable[DownloadRecord], output: str | Path) -> Path:
    """Write download records to CSV."""

    return write_csv((record.to_dict() for record in records), output, CATALOG_COLUMNS)


def _extract_hrefs(html: str) -> list[str]:
    """Extract href values using BeautifulSoup when available, regex otherwise."""

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    soup = BeautifulSoup(html, "html.parser")
    return [anchor.get("href", "") for anchor in soup.find_all("a")]


def _safe_folder_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip() or "UNKNOWN")


def _requests():
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Missing dependency 'requests'. Install with `pip install -r requirements.txt`.") from exc
    return requests

