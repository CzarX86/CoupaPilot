from pathlib import Path

import pytest
from unittest.mock import AsyncMock

from src.engine.crawler import CoupaCrawler, SessionExpiredError


class MinimalDB:
    def __init__(self):
        self.updates = []

    def get_company_stats(self, session_id, company_code):
        return {"total": 0, "processed": 0, "errors": 0, "success": 0}

    def get_po(self, session_id, po_number):
        return {"status": "PENDING", "output_subdir": ""}

    def update_po_status(self, session_id, po_number, status, download_folder=None, attachment_count=None, error_message=None):
        self.updates.append((po_number, status, error_message))


@pytest.mark.asyncio
async def test_session_expiry_keeps_po_pending_for_hil_resume(tmp_path):
    db = MinimalDB()
    crawler = CoupaCrawler(db, 1, str(tmp_path), enable_circuit_breaker=False)
    crawler._fetch_html = AsyncMock(side_effect=SessionExpiredError("Coupa returned HTTP 401"))

    result = await crawler.process_po("PO123", "CC1")

    assert result["auth_required"] is True
    assert db.updates[-1][1] == "PENDING"
    assert db.updates[-1][2] is None
    await crawler.close()


def test_official_http_path_has_no_browser_automation_imports():
    crawler_source = (Path(__file__).parents[1] / "src" / "engine" / "crawler.py").read_text(encoding="utf-8").lower()
    process_source = (Path(__file__).parents[1] / "process_all_pos.py").read_text(encoding="utf-8").lower()

    assert "selenium" not in crawler_source
    assert "playwright" not in crawler_source
    assert "selenium" not in process_source
    assert "playwright" not in process_source
    assert "http2=true" in crawler_source
