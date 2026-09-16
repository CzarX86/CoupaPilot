import asyncio
import json
import os
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.engine.crawler import (
    AttachmentTotalTimeoutError,
    AccessDeniedError,
    AuthError,
    CoupaCrawler,
    RateLimitError,
)
from src.engine.rate_limiter import RateLimiter
from src.auth.cookie_store import CookieStore


class MockSessionDB:
    def __init__(self):
        self.company_stats = {}
        self.po_records = {}
        self.updates = []
        self.suspended = set()
        self.access_diagnoses = {}

    def get_company_stats(self, session_id: int, company_code: str):
        return self.company_stats.get(
            (session_id, company_code),
            {"total": 0, "processed": 0, "errors": 0, "success": 0},
        )

    def suspend_company_code(self, session_id: int, company_code: str):
        self.suspended.add((session_id, company_code))

    def set_po_access_diagnosis(self, session_id: int, po_number: str, diagnosis: str):
        self.access_diagnoses[(session_id, po_number)] = diagnosis

    def get_po(self, session_id: int, po_number: str):
        return self.po_records.get((session_id, po_number))

    def update_po_status(
        self,
        session_id: int,
        po_number: str,
        status: str,
        download_folder: str | None = None,
        attachment_count: int | None = None,
        error_message: str | None = None,
    ):
        self.updates.append({
            "session_id": session_id,
            "po_number": po_number,
            "status": status,
            "download_folder": download_folder,
            "attachment_count": attachment_count,
            "error_message": error_message,
        })
        self.po_records[(session_id, po_number)] = {
            "status": status,
            "download_folder": download_folder,
            "error_message": error_message,
        }

    def set_company_stats(self, session_id: int, company_code: str, total: int, processed: int, errors: int):
        self.company_stats[(session_id, company_code)] = {
            "total": total,
            "processed": processed,
            "errors": errors,
            "success": processed - errors,
        }


@pytest.fixture
def tmp_download_dir(tmp_path):
    return str(tmp_path)


# ——— PO Processing ———


@pytest.mark.asyncio
async def test_process_po_with_pr_and_dedup(tmp_download_dir):
    db = MockSessionDB()
    db.set_company_stats(session_id=1, company_code="CC1", total=10, processed=2, errors=0)

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)

    po_html = """
    <html><body>
        <a href='/attachments/po1/download'>fileA.pdf</a>
        <a href='/requisition_headers/PR123'>PR Link</a>
    </body></html>
    """
    pr_html = """
    <html><body>
        <a href='/attachments/po1/download'>fileA.pdf</a>
        <a href='/attachments/pr2/download'>fileB.docx</a>
    </body></html>
    """

    call_count = 0

    async def mock_fetch_html(url: str, label: str = ""):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return po_html
        return pr_html

    crawler._fetch_html = mock_fetch_html
    crawler._download_attachment = AsyncMock()

    await crawler.process_po(po_number="PO123", company_code="CC1")

    assert crawler._download_attachment.call_count == 2
    downloaded = {call.args[1].split(os.sep)[-1] for call in crawler._download_attachment.call_args_list}
    assert downloaded == {"fileA.pdf", "fileB.docx"}

    po_record = db.get_po(1, "PO123")
    assert po_record["status"] == "SUCCESS"
    assert po_record["download_folder"] is not None
    await crawler.close()


@pytest.mark.asyncio
async def test_preflight_expands_denied_sample_before_blocking(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    calls = []

    async def denied_then_accessible(url: str, label: str = ""):
        calls.append(url)
        if len(calls) < 3:
            raise AccessDeniedError("denied")
        return "<html><body>PO page</body></html>"

    crawler._fetch_html = denied_then_accessible
    result = await crawler.preflight_company_access({"CC1": ["PO1", "PO2", "PO3"]})

    assert result["CC1"]["sampled"] == 3
    assert result["CC1"]["denied"] == 2
    assert result["CC1"]["accessible"] == 1
    assert result["CC1"]["confirmed"] is False
    await crawler.close()


@pytest.mark.asyncio
async def test_retry_preserves_valid_files_and_downloads_only_missing(tmp_download_dir):
    db = MockSessionDB()
    po_dir = os.path.join(tmp_download_dir, "CC1", "PO123")
    os.makedirs(po_dir, exist_ok=True)
    with open(os.path.join(po_dir, "fileA.pdf"), "wb") as stream:
        stream.write(b"%PDF-1.7 existing-valid-file")

    db.po_records[(1, "PO123")] = {
        "status": "PENDING",
        "output_subdir": "CC1",
    }
    crawler = CoupaCrawler(
        db=db,
        session_id=1,
        base_download_dir=tmp_download_dir,
        preserve_existing_files=True,
    )
    crawler._fetch_html = AsyncMock(return_value="""<html><body>
        <a href='/attachments/a/download'>fileA.pdf</a>
        <a href='/attachments/b/download'>fileB.docx</a>
    </body></html>""")
    crawler._download_attachment = AsyncMock()

    await crawler.process_po(po_number="PO123", company_code="CC1")

    assert crawler._download_attachment.call_count == 1
    assert crawler._download_attachment.call_args.args[1].endswith("fileB.docx")
    assert crawler._download_attachment.call_args.kwargs["replace_existing"] is True
    with open(os.path.join(po_dir, "fileA.pdf"), "rb") as stream:
        assert stream.read().startswith(b"%PDF-")
    await crawler.close()


@pytest.mark.asyncio
async def test_process_po_no_attachments(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(return_value="<html><body>No attachments</body></html>")
    crawler._download_attachment = AsyncMock()

    await crawler.process_po(po_number="PO001", company_code="CC1")

    assert crawler._download_attachment.call_count == 0
    po_record = db.get_po(1, "PO001")
    assert po_record["status"] == "SUCCESS"
    await crawler.close()


@pytest.mark.asyncio
async def test_process_po_uses_output_subdir_for_path(tmp_download_dir):
    db = MockSessionDB()
    db.po_records[(1, "PO777")] = {
        "status": "PENDING",
        "output_subdir": "2026/Q12026/Yellow_Wood",
    }

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(return_value="<html><body><a href='/attachments/1/download'>f.pdf</a></body></html>")
    crawler._download_attachment = AsyncMock()

    await crawler.process_po(po_number="PO777", company_code="CC1")

    assert crawler._download_attachment.call_count == 1
    dest_path = os.path.normpath(crawler._download_attachment.call_args.args[1])
    expected_subdir = os.path.join("2026", "Q12026", "Yellow_Wood", "PO777")
    assert expected_subdir in dest_path
    await crawler.close()


# ——— Circuit Breaker ———


@pytest.mark.asyncio
async def test_circuit_breaker_triggers_suspend(tmp_download_dir):
    db = MockSessionDB()
    db.set_company_stats(session_id=1, company_code="CC2", total=10, processed=3, errors=3)
    db.po_records[(1, "PO999")] = {"status": "SKIPPED_VERIFICATION_REQUIRED"}

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(return_value="<html></html>")
    crawler._download_attachment = AsyncMock()

    await crawler.process_po(po_number="PO999", company_code="CC2")

    assert (1, "CC2") in db.suspended
    assert crawler._download_attachment.call_count == 0
    await crawler.close()


@pytest.mark.asyncio
async def test_circuit_breaker_requires_min_3_processed(tmp_download_dir):
    """< 3 processed POs should NOT trigger circuit breaker, even if error rate is 100%."""
    db = MockSessionDB()
    db.set_company_stats(session_id=1, company_code="CC3", total=10, processed=2, errors=2)

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(return_value="<html><body><a href='/attachments/1/download'>f.pdf</a></body></html>")
    crawler._download_attachment = AsyncMock()

    await crawler.process_po(po_number="PO100", company_code="CC3")

    # Should NOT suspend — only 2 POs processed (< 3 minimum)
    assert (1, "CC3") not in db.suspended
    await crawler.close()


@pytest.mark.asyncio
async def test_circuit_breaker_not_triggered_below_15_percent(tmp_download_dir):
    db = MockSessionDB()
    db.set_company_stats(session_id=1, company_code="CC4", total=100, processed=10, errors=10)

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(return_value="<html></html>")

    await crawler.process_po(po_number="PO200", company_code="CC4")

    # 10/100 = 10% < 15% — should NOT suspend
    assert (1, "CC4") not in db.suspended
    await crawler.close()


@pytest.mark.asyncio
async def test_circuit_breaker_can_be_disabled(tmp_download_dir):
    db = MockSessionDB()
    db.set_company_stats(session_id=1, company_code="CCX", total=10, processed=3, errors=3)
    db.po_records[(1, "POX")] = {"status": "PENDING"}

    crawler = CoupaCrawler(
        db=db,
        session_id=1,
        base_download_dir=tmp_download_dir,
        enable_circuit_breaker=False,
    )
    crawler._fetch_html = AsyncMock(return_value="<html><body>No attachments</body></html>")

    await crawler.process_po(po_number="POX", company_code="CCX")

    assert (1, "CCX") not in db.suspended
    await crawler.close()


# ——— PO URL Resolution ———


def test_po_url_strips_prefix_for_coupa_endpoint():
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir="/tmp")
    assert crawler._po_url("PO14718345") == "https://unilever.coupahost.com/order_headers/14718345"
    assert crawler._po_url("PM12345") == "https://unilever.coupahost.com/order_headers/12345"
    assert crawler._po_url("12345") == "https://unilever.coupahost.com/order_headers/12345"


@pytest.mark.asyncio
async def test_process_po_uses_only_numeric_coupa_route(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    calls = []

    async def mock_fetch_html(url: str, label: str = ""):
        calls.append(url)
        assert url == "https://unilever.coupahost.com/order_headers/14718345"
        return "<html><body>No attachments</body></html>"

    crawler._fetch_html = mock_fetch_html
    crawler._download_attachment = AsyncMock()

    result = await crawler.process_po(po_number="PO14718345", company_code="CC1")

    assert result["success"] is True
    assert calls == ["https://unilever.coupahost.com/order_headers/14718345"]
    po_record = db.get_po(1, "PO14718345")
    assert po_record["status"] == "SUCCESS"
    await crawler.close()


def test_safe_attachment_filename_truncates_long_names():
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir="/tmp")

    long_name = "Invoice_" + ("very_long_segment_" * 30) + ".pdf"
    safe = crawler._safe_attachment_filename(long_name, "https://example.com/attachments/123/download.pdf")

    assert len(safe) <= 180
    assert safe.endswith(".pdf")
    assert " " not in safe


def test_filename_from_content_disposition_plain_filename():
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir="/tmp")

    header = 'attachment; filename="Invoice_2026_05_21.pdf"'
    assert crawler._filename_from_content_disposition(header) == "Invoice_2026_05_21.pdf"


def test_filename_from_content_disposition_filename_star():
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir="/tmp")

    header = "attachment; filename*=UTF-8''Invoice_%23ABC123.msg"
    assert crawler._filename_from_content_disposition(header) == "Invoice_#ABC123.msg"


def test_error_detail_redacts_url_query_strings():
    error = RuntimeError("GET https://example.test/attachment/1?token=secret&user=abc failed")

    assert CoupaCrawler._safe_error_detail(error) == (
        "GET https://example.test/attachment/1?[redacted] failed"
    )


# ——— Exception Handling ———


@pytest.mark.asyncio
async def test_process_po_cleans_up_on_error(tmp_download_dir):
    db = MockSessionDB()

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(
        return_value="<html><body><a href='/attachments/1/download'>f.pdf</a></body></html>"
    )
    crawler._download_attachment = AsyncMock(side_effect=RateLimitError("429"))

    result = await crawler.process_po(po_number="PO500", company_code="CC5")

    assert result["success"] is False
    assert "429" in result["error"] or "Rate" in result["error"]

    po_dir = os.path.join(tmp_download_dir, "CC5", "PO500")
    assert not os.path.exists(po_dir)
    await crawler.close()


@pytest.mark.asyncio
async def test_process_po_records_exception_type_when_message_is_empty(tmp_download_dir):
    db = MockSessionDB()

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(
        return_value="<html><body><a href='/attachments/1/download'>f.pdf</a></body></html>"
    )
    crawler._download_attachment = AsyncMock(side_effect=httpx.ReadTimeout(""))

    result = await crawler.process_po(po_number="PO501", company_code="CC5")

    assert result["error"].startswith("ReadTimeout [phase=download_attachment, po=PO501")
    assert "attachment=f.pdf" in result["error"]
    assert "timeout_s=60" in result["error"]
    assert db.updates[-1]["error_message"] == result["error"]
    assert result["diagnostic_log"].endswith("run_diagnostics.jsonl")
    with open(result["diagnostic_log"], encoding="utf-8") as stream:
        diagnostic = [json.loads(line) for line in stream]
    assert diagnostic[-1]["event"] == "po_error"
    assert diagnostic[-1]["phase"] == "download_attachment"
    assert diagnostic[-1]["error_type"] == "ReadTimeout"
    assert diagnostic[-1]["runtime"]["os"]
    assert diagnostic[-1]["runtime"]["python"]
    await crawler.close()


@pytest.mark.asyncio
async def test_process_po_records_fetch_phase_for_empty_timeout(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir, timeout=7.5)
    crawler._fetch_html = AsyncMock(side_effect=httpx.ReadTimeout(""))

    result = await crawler.process_po(po_number="PO502", company_code="CC5")

    assert "ReadTimeout [phase=fetch_po_html, po=PO502" in result["error"]
    assert "timeout_s=7.5" in result["error"]
    assert db.updates[-1]["error_message"] == result["error"]
    await crawler.close()


@pytest.mark.asyncio
async def test_download_uses_longer_read_timeout_for_large_files(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)

    class StreamResponse:
        status_code = 200
        headers = {"content-length": "6"}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size):
            assert chunk_size == 1024 * 1024
            yield b"abc"
            yield b"def"

    class StreamContext:
        async def __aenter__(self):
            return StreamResponse()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    crawler.client.stream = MagicMock(return_value=StreamContext())
    target = os.path.join(tmp_download_dir, "file.pdf")
    result = await crawler._download_attachment("https://example.test/attachment/1", target)

    timeout = crawler.client.stream.call_args.kwargs["timeout"]
    assert timeout.connect == 10.0
    assert timeout.read == 60.0
    assert result["bytes"] == 6
    assert result["content_length"] == 6
    assert result["attempt"] == 1
    with open(target, "rb") as stream:
        assert stream.read() == b"abcdef"
    await crawler.close()


@pytest.mark.asyncio
async def test_download_retries_transient_timeout_and_records_attempt(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._download_attachment_once = AsyncMock(
        side_effect=[
            httpx.ReadTimeout(""),
            {"bytes": 6, "content_length": 6, "duration_ms": 12},
        ]
    )

    result = await crawler._download_attachment(
        "https://example.test/attachment/1",
        os.path.join(tmp_download_dir, "file.pdf"),
    )

    assert result["attempt"] == 2
    assert crawler._download_attachment_once.await_count == 2
    with open(crawler.diagnostic_log_path, encoding="utf-8") as stream:
        diagnostic = [json.loads(line) for line in stream]
    assert diagnostic[-1]["event"] == "download_retry"
    assert diagnostic[-1]["attempt"] == 1
    await crawler.close()


@pytest.mark.asyncio
async def test_download_enforces_total_timeout_separately(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(
        db=db,
        session_id=1,
        base_download_dir=tmp_download_dir,
        download_attempts=1,
        download_total_timeout=0.01,
    )

    async def slow_download(*args, **kwargs):
        await asyncio.sleep(0.2)

    crawler._download_attachment_once = slow_download

    with pytest.raises(AttachmentTotalTimeoutError, match="exceeded 0.1s"):
        await crawler._download_attachment(
            "https://example.test/attachment/1",
            os.path.join(tmp_download_dir, "file.pdf"),
        )
    await crawler.close()


@pytest.mark.asyncio
async def test_process_po_records_attachment_parser_phase(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    crawler._fetch_html = AsyncMock(return_value="<html></html>")

    with patch("src.engine.crawler.CoupaParser.extract_attachments", side_effect=ValueError("")):
        result = await crawler.process_po(po_number="PO504", company_code="CC5")

    assert "ValueError [phase=extract_po_attachments, po=PO504" in result["error"]
    with open(crawler.diagnostic_log_path, encoding="utf-8") as stream:
        diagnostic = [json.loads(line) for line in stream]
    assert diagnostic[-1]["phase"] == "extract_po_attachments"
    assert diagnostic[-1]["error_type"] == "ValueError"
    await crawler.close()


@pytest.mark.asyncio
async def test_process_po_persists_pr_error_without_hiding_it(tmp_download_dir):
    db = MockSessionDB()
    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir)
    calls = 0

    async def fetch(url: str, label: str = ""):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "<a href='/requisition_headers/PR123'>PR</a>"
        raise httpx.ReadTimeout("")

    crawler._fetch_html = fetch
    result = await crawler.process_po(po_number="PO503", company_code="CC5")

    assert result["success"] is True
    with open(crawler.diagnostic_log_path, encoding="utf-8") as stream:
        diagnostic = [json.loads(line) for line in stream]
    assert diagnostic[-1]["event"] == "pr_error"
    assert diagnostic[-1]["phase"] == "fetch_pr_html"
    assert diagnostic[-1]["error_type"] == "ReadTimeout"
    assert "timeout_s=10" in diagnostic[-1]["formatted_error"]
    await crawler.close()


# ——— Concurrent Batch ———


@pytest.mark.asyncio
async def test_process_batch_concurrent(tmp_download_dir):
    db = MockSessionDB()
    po_html = "<html><body>No attachments</body></html>"

    crawler = CoupaCrawler(db=db, session_id=1, base_download_dir=tmp_download_dir, concurrency=5)
    crawler._fetch_html = AsyncMock(return_value=po_html)

    batch = [("PO001", "CC-A"), ("PO002", "CC-A"), ("PO003", "CC-B")]
    results = await crawler.process_batch(batch)

    assert len(results) == 3
    assert all(r["success"] for r in results)
    await crawler.close()


@pytest.mark.asyncio
async def test_close_persists_cookie_refreshed_during_download(tmp_path):
    store = CookieStore(tmp_path / "cookies.json", tmp_path / "auth_cache.db")
    crawler = CoupaCrawler(
        db=MockSessionDB(),
        session_id=1,
        base_download_dir=str(tmp_path),
        cookies={"_coupa_session": "cached"},
        cookie_store=store,
    )
    current = next(iter(crawler.client.cookies.jar))
    crawler.client.cookies.set("_coupa_session", "refreshed", domain=current.domain, path="/")

    await crawler.close()

    assert store.load()["_coupa_session"] == "refreshed"
