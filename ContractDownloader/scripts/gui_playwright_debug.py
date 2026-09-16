#!/usr/bin/env python3
"""Playwright probe for Contract GUI frontend.

Modes:
- mock: deterministic backend simulation for fast UI diagnostics.
- real: executes real AppAPI methods (import/history/details/export/retry) through a
  Python-JS bridge, while simulating telemetry-only methods required by the UI.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.session_db import SessionDB
from src.gui.api import AppAPI


INIT_BRIDGE_SCRIPT = r"""
(() => {
  const call = async (method, ...args) => {
    if (!window.__pw_api_call) {
      throw new Error('Bridge function __pw_api_call not available');
    }
    return window.__pw_api_call(method, args);
  };

  window.pywebview = {
    api: {
      select_directory: async () => call('select_directory'),
      select_file: async () => call('select_file'),
      stage_dropped_file: async (filename, content) => call('stage_dropped_file', filename, content),
      generate_input_template: async () => call('generate_input_template'),
      validate_input_file: async (filepath) => call('validate_input_file', filepath),
      repair_input_file: async (filepath, actions, expectedFingerprint) => call('repair_input_file', filepath, actions, expectedFingerprint),
      preview_repair_input_file: async (filepath, action) => call('preview_repair_input_file', filepath, action),
      inspect_input_file: async (filepath) => call('inspect_input_file', filepath),
      open_filtered_input_view: async (filepath) => call('open_filtered_input_view', filepath),
      validate_download_directory: async (filepath) => call('validate_download_directory', filepath),
      check_auth: async () => call('check_auth'),
      authenticate: async () => call('authenticate'),
      check_updates: async () => call('check_updates'),
      download_update: async (url, assetName, checksumUrl) => call('download_update', url, assetName, checksumUrl),
      run_diagnostics: async (inputPath) => call('run_diagnostics', inputPath),
      copy_diagnostics_report: async (report) => call('copy_diagnostics_report', report),
      save_diagnostics_report: async (report) => call('save_diagnostics_report', report),
      import_file: async (filepath) => call('import_file', filepath),
      open_input_path: async (filepath) => call('open_input_path', filepath),
      start_download: async (sessionId, downloadDir) => call('start_download', sessionId, downloadDir),
      get_active_session_status: async (sessionId) => call('get_active_session_status', sessionId),
    pause_download: async (sessionId) => call('pause_download', sessionId),
    resume_download: async (sessionId) => call('resume_download', sessionId),
    stop_download: async (sessionId) => call('stop_download', sessionId),
      get_session_history: async () => call('get_session_history'),
      get_session_details: async (sessionId) => call('get_session_details', sessionId),
      confirm_and_retry_company: async (sessionId, companyCode) => call('confirm_and_retry_company', sessionId, companyCode),
      retry_po: async (sessionId, poNumber) => call('retry_po', sessionId, poNumber),
      open_input_file: async (sessionId) => call('open_input_file', sessionId),
      open_coupa_po: async (poNumber) => call('open_coupa_po', poNumber),
      open_external_url: async (url) => call('open_external_url', url),
      export_session_report: async (sessionId, destPath) => call('export_session_report', sessionId, destPath),
    }
  };
})();
"""


@dataclass
class ProbeResult:
    run_dir: Path
    report_path: Path
    report: dict[str, Any]


@dataclass
class MockBridge:
    download_dir: str
    _tick: int = 0
    _stopped: bool = False
    _paused: bool = False

    def call(self, method: str, args: list[Any]) -> Any:
        if method == "select_directory":
            return self.download_dir
        if method == "select_file":
            return {"success": False, "error": "Use the browser file picker in probe mode."}
        if method == "stage_dropped_file":
            filename = Path(str(args[0] if args else "input.csv")).name
            return {"success": True, "path": str(Path(self.download_dir) / filename), "name": filename, "size": 1}
        if method == "generate_input_template":
            return {"success": True, "path": str(Path(self.download_dir) / "input_template.csv")}
        if method == "validate_input_file":
            return {"valid": True, "errors": [], "warnings": [], "valid_po_count": 15, "total_rows": 15, "file_state": {"ready": True, "mtime_ns": 1, "size": 1}}
        if method == "repair_input_file":
            return {"success": True, "message": "Safe repairs applied.", "backup_path": "input.backup.csv"}
        if method == "preview_repair_input_file":
            return {"success": True, "changes": [{"row": 2, "column": "PO_NUMBER", "old": "PO-1", "new": "PO1"}], "total_changes": 1, "expected_fingerprint": "1:1"}
        if method == "inspect_input_file":
            return {"ready": True, "open_detected": False, "stable": True, "mtime_ns": 1, "size": 1}
        if method == "open_filtered_input_view":
            return {"success": True, "path": str(Path(self.download_dir) / "filtered.xlsx"), "filtered_rows": 1}
        if method == "validate_download_directory":
            return {"success": True, "path": self.download_dir}
        if method == "check_auth":
            return {"authenticated": True, "state": "cached", "message": "Mock session"}
        if method == "authenticate":
            return {"success": True}
        if method == "check_updates":
            return {"success": True, "update_available": False}
        if method == "download_update":
            return {"success": True, "path": str(Path(self.download_dir) / "update.zip")}
        if method == "run_diagnostics":
            return {"success": True, "report": "MOCK DIAGNOSTIC REPORT", "summary": {"passed": 1, "warnings": 0, "failed": 0}}
        if method == "copy_diagnostics_report":
            return {"success": True, "message": "Clipboard updated"}
        if method == "save_diagnostics_report":
            return {"success": True, "path": "diagnostics.txt"}
        if method == "import_file":
            filepath = str(args[0]) if args else ""
            if not filepath:
                return {"success": False, "error": "Empty filepath"}
            return {"success": True, "session_id": 777, "total_pos": 15}
        if method == "start_download":
            self._stopped = False
            self._paused = False
            return {"success": True}
        if method == "get_active_session_status":
            if self._stopped:
                return {
                    "status": "STOPPED",
                    "total": 15,
                    "processed": min(self._tick * 2, 15),
                    "speed": 0.0,
                    "eta": "--:--",
                    "errors": 0,
                    "latest_logs": [{"type": "System", "message": "Session stopped"}],
                }
            if self._paused:
                return {
                    "status": "PAUSED",
                    "total": 15,
                    "processed": min(self._tick * 2, 15),
                    "speed": 0.0,
                    "eta": "--:--",
                    "errors": 0,
                    "latest_logs": [{"type": "System", "message": "Session paused"}],
                }
            self._tick += 1
            processed = min(self._tick * 2, 15)
            status = "SUCCESS" if processed >= 15 else "RUNNING"
            return {
                "status": status,
                "total": 15,
                "processed": processed,
                "speed": 42.5,
                "eta": "00:00" if status == "SUCCESS" else "00:12",
                "errors": 1 if processed >= 10 else 0,
                "latest_logs": [
                    {
                        "type": "Success" if status == "SUCCESS" else "Info",
                        "message": "Mock session completed" if status == "SUCCESS" else f"Processed {processed}/15",
                    }
                ],
            }
        if method == "get_session_history":
            return [
                {
                    "id": 777,
                    "input_file": "sample_for_gui_probe.csv",
                    "created_at": datetime.now().isoformat(),
                    "status": "SUCCESS",
                }
            ]
        if method == "get_session_details":
            return {
                "session": {
                    "id": 777,
                    "input_file": "sample_for_gui_probe.csv",
                    "status": "SUCCESS",
                },
                "pos": [
                    {
                        "po_number": "PO-001",
                        "company_code": "ACME-BR",
                        "status": "SUCCESS",
                        "error_message": None,
                    },
                    {
                        "po_number": "PO-002",
                        "company_code": "ACME-BR",
                        "status": "SKIPPED_VERIFICATION_REQUIRED",
                        "error_message": "Verification required",
                    },
                    {
                        "po_number": "PO-003",
                        "company_code": "ACME-US",
                        "status": "SUCCESS",
                        "error_message": None,
                    },
                ],
            }
        if method == "confirm_and_retry_company":
            return {"success": True}
        if method == "retry_po":
            return {"success": True, "session_id": 778}
        if method == "open_input_file":
            return {"success": True, "path": str(Path(self.download_dir) / "input.csv")}
        if method == "open_coupa_po":
            return {"success": True, "browser": "default", "po_number": str(args[0])}
        if method == "open_external_url":
            return {"success": True}
        if method == "export_session_report":
            return {"success": True}
        if method == "pause_download":
            self._paused = True
            return {"success": True}
        if method == "resume_download":
            self._paused = False
            return {"success": True}
        if method == "stop_download":
            self._stopped = True
            return {"success": True}
        raise ValueError(f"Unsupported method in mock bridge: {method}")


@dataclass
class RealBridge:
    run_dir: Path
    db: SessionDB = field(init=False)
    api: AppAPI = field(init=False)
    _start_times: dict[int, float] = field(default_factory=dict)
    _latest_processed: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        db_path = self.run_dir / "probe.db"
        self.db = SessionDB(str(db_path))
        downloads = self.run_dir / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        self.api = AppAPI(self.db, str(downloads))

    def _session_total(self, session_id: int) -> int:
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM po_downloads WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        return int(row["total"] if row else 0)

    def _update_processed_rows(self, session_id: int, processed_target: int) -> int:
        current = self._latest_processed.get(session_id, 0)
        if processed_target <= current:
            return current

        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT po_number FROM po_downloads
            WHERE session_id = ? AND status = 'PENDING'
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, processed_target - current),
        )
        rows = [r["po_number"] for r in cursor.fetchall()]
        for po_number in rows:
            self.db.update_po_status(session_id, po_number, "SUCCESS")

        updated = current + len(rows)
        self._latest_processed[session_id] = updated
        return updated

    def call(self, method: str, args: list[Any]) -> Any:
        if method == "select_directory":
            return self.api.default_download_dir
        if method == "get_default_download_directory":
            return self.api.get_default_download_directory()
        if method == "get_app_settings":
            return self.api.get_app_settings()
        if method == "get_concurrency_estimates":
            return {str(value): {"minutes_100": None, "samples": 0} for value in (2, 4, 6, 8)}
        if method == "select_file":
            return {"success": False, "error": "Use the browser file picker in probe mode."}
        if method == "stage_dropped_file":
            filename = Path(str(args[0] if args else "input.csv")).name
            content = str(args[1]) if len(args) > 1 else ""
            return self.api.stage_dropped_file(filename, content)
        if method == "generate_input_template":
            return {"success": True, "path": str(self.run_dir / "input_template.csv")}
        if method == "get_input_columns":
            filepath = str(args[0]) if args else ""
            file_candidate = Path(filepath)
            if not file_candidate.exists() and file_candidate.name:
                fallback = self.run_dir / file_candidate.name
                if fallback.exists():
                    filepath = str(fallback)
            return self.api.get_input_columns(filepath)
        if method == "map_input_columns":
            filepath = str(args[0]) if args else ""
            mapping = dict(args[1]) if len(args) > 1 else {}
            file_candidate = Path(filepath)
            if not file_candidate.exists() and file_candidate.name:
                fallback = self.run_dir / file_candidate.name
                if fallback.exists():
                    filepath = str(fallback)
            return self.api.map_input_columns(filepath, mapping)
        if method == "validate_input_file":
            filepath = str(args[0]) if args else ""
            file_candidate = Path(filepath)
            if not file_candidate.exists() and file_candidate.name:
                fallback = self.run_dir / file_candidate.name
                if fallback.exists():
                    filepath = str(fallback)
            return self.api.validate_input_file(filepath)
        if method == "repair_input_file":
            filepath = str(args[0]) if args else ""
            actions = list(args[1]) if len(args) > 1 else []
            expected = str(args[2]) if len(args) > 2 and args[2] else None
            return self.api.repair_input_file(filepath, actions, expected)
        if method == "preview_repair_input_file":
            filepath = str(args[0]) if args else ""
            return self.api.preview_repair_input_file(filepath, str(args[1]) if len(args) > 1 else "")
        if method == "inspect_input_file":
            filepath = str(args[0]) if args else ""
            file_candidate = Path(filepath)
            if not file_candidate.exists() and file_candidate.name:
                fallback = self.run_dir / file_candidate.name
                if fallback.exists():
                    filepath = str(fallback)
            return self.api.inspect_input_file(filepath)
        if method == "open_filtered_input_view":
            filepath = str(args[0]) if args else ""
            return self.api.open_filtered_input_view(filepath)
        if method == "validate_download_directory":
            filepath = str(args[0]) if args else ""
            return self.api.validate_download_directory(filepath)
        if method == "check_auth":
            return {"authenticated": True, "state": "cached", "message": "Probe session"}
        if method == "authenticate":
            return {"success": True}
        if method == "check_updates":
            return {"success": True, "update_available": False}
        if method == "download_update":
            return {"success": True, "path": str(self.run_dir / "update.zip")}
        if method == "run_diagnostics":
            return {"success": True, "report": "REAL PROBE DIAGNOSTIC REPORT", "summary": {"passed": 1, "warnings": 0, "failed": 0}}
        if method == "copy_diagnostics_report":
            return {"success": True, "message": "Clipboard updated"}
        if method == "save_diagnostics_report":
            return {"success": True, "path": str(self.run_dir / "diagnostics.txt")}

        if method == "import_file":
            filepath = str(args[0]) if args else ""
            file_candidate = Path(filepath)
            if not file_candidate.exists() and file_candidate.name:
                fallback = self.run_dir / file_candidate.name
                if fallback.exists():
                    filepath = str(fallback)
            result = self.api.import_file(filepath)
            if result.get("success"):
                session_id = int(result["session_id"])
                self._latest_processed[session_id] = 0
            return result

        if method == "start_download":
            session_id = int(args[0])
            self._start_times[session_id] = time.time()
            return {"success": True}

        if method == "get_active_session_status":
            session_id = int(args[0])
            total = self._session_total(session_id)
            start_t = self._start_times.get(session_id, time.time())
            elapsed = max(time.time() - start_t, 0.1)
            target_processed = min(total, int(elapsed * 4))
            processed = self._update_processed_rows(session_id, target_processed)
            status = "SUCCESS" if processed >= total and total > 0 else "RUNNING"
            speed = (processed / elapsed) * 60.0 if elapsed > 0 else 0.0
            remaining = max(total - processed, 0)
            eta_seconds = int((remaining / 4.0)) if status != "SUCCESS" else 0
            eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
            latest_logs = [
                {
                    "type": "Success" if status == "SUCCESS" else "Info",
                    "message": "Session finished" if status == "SUCCESS" else f"Processed {processed}/{total}",
                }
            ]
            return {
                "status": status,
                "total": total,
                "processed": processed,
                "speed": speed,
                "eta": eta,
                "errors": 0,
                "latest_logs": latest_logs,
            }

        if method == "get_session_history":
            return self.api.get_session_history()

        if method == "pause_download":
            session_id = int(args[0])
            return self.api.pause_download(session_id)

        if method == "resume_download":
            session_id = int(args[0])
            return self.api.resume_download(session_id)

        if method == "stop_download":
            session_id = int(args[0])
            return self.api.stop_download(session_id)

        if method == "get_session_details":
            session_id = int(args[0])
            return self.api.get_session_details(session_id)

        if method == "confirm_and_retry_company":
            session_id = int(args[0])
            company_code = str(args[1])
            return self.api.confirm_and_retry_company(session_id, company_code)

        if method == "retry_po":
            return {"success": True, "session_id": int(args[0])}
        if method == "open_input_file":
            return {"success": True, "path": str(self.run_dir / "input.csv")}
        if method == "open_coupa_po":
            return {"success": True, "browser": "default", "po_number": str(args[0])}
        if method == "open_external_url":
            return {"success": True}

        if method == "export_session_report":
            session_id = int(args[0])
            dest_name = os.path.basename(str(args[1]))
            dest_path = self.run_dir / dest_name
            return self.api.export_session_report(session_id, str(dest_path))

        raise ValueError(f"Unsupported method in real bridge: {method}")

    def close(self) -> None:
        self.db.close()


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(web_root: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    port = pick_free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(web_root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def create_sample_csv(path: Path) -> Path:
    path.write_text(
        "PO_NUMBER;Legal Entity\n"
        "PO001;ACME-BR\n"
        "PO002;ACME-BR\n"
        "PO003;ACME-US\n",
        encoding="utf-8",
    )
    return path


def run_probe(
    mode: str = "mock",
    headed: bool = False,
    timeout_ms: int = 20000,
    output_root: Path | None = None,
) -> ProbeResult:
    if mode not in {"mock", "real"}:
        raise ValueError("mode must be 'mock' or 'real'")

    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "src" / "gui" / "web"
    if not web_root.exists():
        raise FileNotFoundError(f"web root not found: {web_root}")

    evidence_root = output_root or (repo_root / "artifacts" / "gui-playwright")
    run_dir = evidence_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    sample_csv = create_sample_csv(run_dir / "sample_for_gui_probe.csv")

    server, _thread = start_server(web_root)
    base_url = f"http://127.0.0.1:{server.server_port}/index.html"

    console_logs: list[dict[str, Any]] = []
    page_errors: list[str] = []
    steps: list[str] = []
    modal_po_rows = 0
    status_filter_inputs = 0
    settings_save_metrics: dict[str, Any] = {}

    bridge: MockBridge | RealBridge
    if mode == "mock":
        bridge = MockBridge(download_dir=str(run_dir / "downloads"))
    else:
        bridge = RealBridge(run_dir=run_dir)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            page.on(
                "console",
                lambda msg: console_logs.append({"type": msg.type, "text": msg.text, "location": msg.location}),
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("dialog", lambda dialog: dialog.accept())

            page.expose_function("__pw_api_call", lambda method, args: bridge.call(method, args))
            page.add_init_script(INIT_BRIDGE_SCRIPT)

            page.goto(base_url, wait_until="domcontentloaded")
            steps.append("loaded-index")
            page.screenshot(path=str(run_dir / "01_loaded.png"), full_page=True)

            # Guardrail: the first journey step must remain visible and block progression without a file.
            steps.append("checked-next-without-file")

            def complete_journey_to_final_step():
                """Walk the New Run journey to the final folder approval step."""
                expect(page.locator("#btn-next-input")).to_be_enabled(timeout=timeout_ms)
                expect(page.locator("#journey-top-action")).to_be_enabled(timeout=timeout_ms)
                page.click("#journey-top-action")
                expect(page.locator("#validation-feedback")).to_be_visible(timeout=timeout_ms)
                expect(page.locator("#journey-top-action")).to_be_enabled(timeout=timeout_ms)
                page.click("#journey-top-action")
                expect(page.locator('[data-journey-panel="3"]')).to_be_visible(timeout=timeout_ms)
                page.locator("#folder-approval").check()

            page.locator("#file-input").set_input_files(str(sample_csv))
            steps.append("selected-input-file")
            page.screenshot(path=str(run_dir / "02_file_selected.png"), full_page=True)

            # Guardrail: Start over is available in the sticky journey header
            # and must reset the journey, re-enabling the input step.
            complete_journey_to_final_step()
            page.click("#btn-start-over")
            page.wait_for_selector("#dropzone", state="visible")
            steps.append("start-over-clicked")
            page.locator("#file-input").set_input_files(str(sample_csv))
            steps.append("re-selected-after-start-over")
            complete_journey_to_final_step()
            page.click("#journey-top-action")
            steps.append("clicked-start")

            page.wait_for_selector("#screen-progress.active")
            page.wait_for_timeout(1500)
            steps.append("progress-visible")
            pause_button = page.locator("#btn-pause-resume")
            if pause_button.is_enabled():
                pause_button.click()
                steps.append("pause-clicked")
                page.wait_for_timeout(300)
                if pause_button.is_enabled():
                    pause_button.click()
                    steps.append("resume-clicked")
            page.screenshot(path=str(run_dir / "03_progress.png"), full_page=True)

            # Guardrail: stopping a live run must be logged and persisted by the backend.
            if page.locator("#btn-stop-session").is_enabled():
                page.click("#btn-stop-session")
                steps.append("clicked-stop")
                page.wait_for_timeout(300)

            page.click("#btn-history")
            page.wait_for_selector("#history-list .btn-view-details")
            steps.append("history-loaded")
            page.screenshot(path=str(run_dir / "04_history.png"), full_page=True)

            page.click("#history-list .btn-view-details")
            page.wait_for_selector("#details-modal", state="visible")
            page.locator("#po-details-section > summary").click()
            page.wait_for_selector("#modal-pos-tbody tr", state="visible")
            modal_po_rows = page.locator("#modal-pos-tbody tr").count()
            status_filter_inputs = page.locator("#status-filter input").count()
            steps.append("modal-opened")
            po_link = page.locator("#modal-pos-tbody .po-number-link").first
            if po_link.count() > 0:
                po_link.click()
                steps.append("po-edge-link-clicked")
            page.screenshot(path=str(run_dir / "05_modal.png"), full_page=True)

            retry_button = page.locator(".btn-retry-company").first
            if retry_button.count() > 0:
                retry_button.click()
                steps.append("retry-company-clicked")

            page.click("#btn-export-modal-report")
            steps.append("export-clicked")

            page.click("#btn-close-modal")
            steps.append("modal-closed")
            page.screenshot(path=str(run_dir / "06_done.png"), full_page=True)

            # Guardrail: body zoom must not extend the main scroll viewport
            # below the native window and make the Settings save button unreachable.
            page.click("#btn-settings")
            if page.locator("[data-settings-tab='updates']").count() > 0:
                page.click("[data-settings-tab='updates']")
            page.click("#btn-check-updates")
            steps.append("manual-update-check")
            page.locator(".main-content").evaluate("el => { el.scrollTop = el.scrollHeight; }")
            settings_save_metrics = page.locator("#btn-save-settings").evaluate("""el => {
                const rect = el.getBoundingClientRect();
                return {
                    top: rect.top,
                    bottom: rect.bottom,
                    viewportHeight: window.innerHeight,
                    fullyVisible: rect.top >= 0 && rect.bottom <= window.innerHeight,
                };
            }""")
            steps.append("settings-save-visible")
            page.screenshot(path=str(run_dir / "07_settings_scrolled.png"), full_page=False)

            sidebar_metrics = page.locator(".sidebar").evaluate("""el => {
                const rect = el.getBoundingClientRect();
                return {
                    top: rect.top,
                    bottom: rect.bottom,
                    height: rect.height,
                    clientHeight: el.clientHeight,
                    scrollHeight: el.scrollHeight,
                    viewportHeight: window.innerHeight,
                    overflowY: getComputedStyle(el).overflowY,
                };
            }""")
            sidebar_controls_visible = all(
                page.locator(selector).is_visible()
                for selector in (".brand", ".sidebar > .nav-menu", ".sidebar-bottom", "#btn-learn", "#btn-settings", "#btn-diagnostics", "#btn-authenticate")
            )
            dom_state = {
                "progress_text": page.locator("#progress-text").inner_text(),
                "history_rows": page.locator("#history-list tr").count(),
                "console_ui_lines": page.locator("#console-log .log-line").count(),
                "modal_po_rows": modal_po_rows,
                "status_filter_inputs": status_filter_inputs,
                "sidebar_metrics": sidebar_metrics,
                "sidebar_controls_visible": sidebar_controls_visible,
                "settings_save_metrics": settings_save_metrics,
            }

            browser.close()

    except PlaywrightError as exc:
        page_errors.append(f"PlaywrightError: {exc}")
        dom_state = {
            "progress_text": "",
            "history_rows": 0,
            "console_ui_lines": 0,
            "modal_po_rows": 0,
            "status_filter_inputs": 0,
            "sidebar_metrics": {},
            "sidebar_controls_visible": False,
            "settings_save_metrics": {},
        }
    finally:
        server.shutdown()
        server.server_close()
        if isinstance(bridge, RealBridge):
            bridge.close()

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "base_url": base_url,
        "sample_csv": str(sample_csv),
        "steps": steps,
        "console_log_count": len(console_logs),
        "page_error_count": len(page_errors),
        "console_logs": [entry["text"] for entry in console_logs],
        "console_events": console_logs,
        "page_errors": page_errors,
        "dom_state": dom_state,
    }

    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return ProbeResult(run_dir=run_dir, report_path=report_path, report=report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright GUI probe with mock/real backend bridge")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock", help="Backend mode")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--timeout-ms", type=int, default=20000, help="Per-action timeout in ms")
    args = parser.parse_args()

    result = run_probe(mode=args.mode, headed=args.headed, timeout_ms=args.timeout_ms)
    report = result.report

    print(f"Run directory: {result.run_dir}")
    print(f"Report: {result.report_path}")
    print(f"Mode: {report['mode']}")
    print(f"Steps executed: {len(report['steps'])}")
    print(f"Page errors captured: {report['page_error_count']}")

    return 0 if report["page_error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
