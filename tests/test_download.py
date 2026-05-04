from __future__ import annotations

from fema_nfhl.download import NfhlDownloadLink, download_one, infer_file_name, parse_nfhl_download_links
from fema_nfhl.extract import safe_extract_path


def test_parse_nfhl_download_links_filters_state() -> None:
    html = """
    <a href="/femaportal/ProductsDownLoadServlet?state=CALIFORNIA&fileName=06001C_20240101.zip">Download</a>
    <a href="/femaportal/ProductsDownLoadServlet?state=MARYLAND&fileName=24001C_20240101.zip">Download</a>
    """

    links = parse_nfhl_download_links(html, base_url="https://hazards.fema.gov/femaportal/NFHL/searchResult", state="CALIFORNIA")

    assert len(links) == 1
    assert links[0].state == "CALIFORNIA"
    assert links[0].file_name == "06001C_20240101.zip"


def test_infer_file_name_uses_fema_query_parameter() -> None:
    url = "https://hazards.fema.gov/femaportal/ProductsDownLoadServlet?fileName=06001C-NFHL.zip"

    assert infer_file_name(url) == "06001C-NFHL.zip"


def test_download_one_writes_catalog_record(tmp_path) -> None:
    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"abc"

    class FakeSession:
        def get(self, url, stream, timeout):
            return FakeResponse()

    record = download_one(
        NfhlDownloadLink(state="CALIFORNIA", file_name="test.zip", url="https://example.com/test.zip"),
        tmp_path,
        session=FakeSession(),
        skip_existing=False,
    )

    assert record.status == "downloaded"
    assert record.file_size_bytes == 3
    assert (tmp_path / "CALIFORNIA" / "test.zip").read_bytes() == b"abc"


def test_safe_extract_path_rejects_path_traversal(tmp_path) -> None:
    try:
        safe_extract_path(tmp_path, "../escape.txt")
    except ValueError as exc:
        assert "Unsafe zip member" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected unsafe path to raise")

