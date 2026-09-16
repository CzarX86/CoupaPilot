from collections import deque
from io import StringIO
from pathlib import Path

import pytest

from src.gui.cli_supervisor import CliProcessSupervisor


def test_recent_progress_metrics_use_rolling_completion_window():
    supervisor = CliProcessSupervisor()
    supervisor.started_at = 1_000.0
    supervisor._progress_samples = deque([(1_000.0, 0)], maxlen=180)
    supervisor._last_processed = 0
    supervisor._last_progress_at = 1_000.0

    speed, eta, stalled = supervisor._recent_progress_metrics(10, 40, now=1_030.0)

    assert speed == pytest.approx(20.0)
    assert eta == "01:30"
    assert stalled == 0

    speed, eta, stalled = supervisor._recent_progress_metrics(10, 40, now=1_100.0)

    assert speed == 0.0
    assert eta == "--:--"
    assert stalled == 70


def test_eta_format_does_not_wrap_after_one_hour():
    assert CliProcessSupervisor._format_eta(65) == "01:05"
    assert CliProcessSupervisor._format_eta(3_661) == "1h 01m"


def test_actionable_logs_keep_progress_and_drop_timing_noise():
    assert CliProcessSupervisor._actionable_log_entry(
        "[TIMING] _fetch_html po: total=25ms http=20ms"
    ) is None

    entry = CliProcessSupervisor._actionable_log_entry(
        "[  25/100] ok=23 err=2 files=41  speed=50/min  eta=1m30s"
    )

    assert entry == {
        "type": "Warning",
        "message": "Progress: 25/100 POs · 23 succeeded · 2 failed · 41 attachments",
    }

    error = CliProcessSupervisor._actionable_log_entry(
        "[ERROR][PO PO17907374] ReadTimeout [phase=download_attachment, po=PO17907374] "
        "[diagnostic_log=C:\\Users\\A\\Downloads\\run_diagnostics.jsonl]"
    )
    assert error == {
        "type": "Error",
        "message": "Error: [PO PO17907374] ReadTimeout [phase=download_attachment, po=PO17907374] "
        "[diagnostic_log=C:\\Users\\A\\Downloads\\run_diagnostics.jsonl]",
    }


def test_supervisor_reports_resumable_pause_as_safe_completion():
    class FinishedProcess:
        stdout = StringIO("[INFO] Run paused safely; pending POs remain queued for resume.\\n")

        @staticmethod
        def wait():
            return 0

    supervisor = CliProcessSupervisor()
    supervisor.stop_requested = True
    supervisor._read_output(FinishedProcess())

    assert supervisor._logs[-1] == {
        "type": "System",
        "message": "Download pipeline paused safely; pending POs remain queued for resume.",
    }


def test_sidebar_owns_viewport_and_main_content_owns_scroll():
    css = (Path(__file__).parents[1] / "src" / "gui" / "web" / "style.css").read_text(encoding="utf-8")

    assert "height: 100vh" in css
    assert "overflow: hidden" in css
    assert ".main-content" in css and "overflow-y: auto" in css
    assert "zoom: calc(1 / var(--font-scale))" in css


def test_pythonw_gui_uses_console_python_for_cli_worker(monkeypatch, tmp_path):
    import src.gui.cli_supervisor as supervisor_module

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    pythonw = runtime / "pythonw.exe"
    python = runtime / "python.exe"
    pythonw.touch()
    python.touch()
    supervisor = CliProcessSupervisor()
    monkeypatch.setattr(supervisor_module.sys, "executable", str(pythonw))
    monkeypatch.setattr(supervisor_module.sys, "platform", "win32")

    command = supervisor._command(concurrency=4)

    assert command[0] == str(python)
    assert command[1].endswith("process_all_pos.py")


def test_supplier_retry_command_targets_existing_session():
    supervisor = CliProcessSupervisor()
    command = supervisor._command(
        retry_in_place_supplier="Supplier A",
        source_session_id=17,
        run_dir="/tmp/run-17",
        concurrency=11,
    )
    assert "--retry-in-place-supplier" in command
    assert command[command.index("--retry-in-place-supplier") + 1] == "Supplier A"
    assert command[command.index("--retry-session-id") + 1] == "17"


def test_windows_cli_worker_does_not_create_a_console_window(monkeypatch):
    import src.gui.cli_supervisor as supervisor_module

    monkeypatch.setattr(supervisor_module.os, "name", "nt")

    flags = CliProcessSupervisor._process_creationflags()

    assert flags & 0x08000000


def test_retry_file_update_replaces_po_and_adds_remark(tmp_path):
    from openpyxl import Workbook, load_workbook

    path = tmp_path / "input.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Input"
    sheet.append(["PO_NUMBER", "SUPPLIER"])
    sheet.append(["12345678", "ACME"])
    workbook.save(path)

    CliProcessSupervisor._replace_po_in_file(
        path,
        "12345678",
        "1234567",
        "Corrected from 12345678 to 1234567; retry succeeded.",
    )

    row = list(load_workbook(path, read_only=True).active.iter_rows(values_only=True))[1]
    assert row == ("1234567", "ACME", "Corrected from 12345678 to 1234567; retry succeeded.")

    # Existing archived values may have a PO prefix or numeric Excel formatting.
    assert CliProcessSupervisor._po_values_equal("168012998", "PO168012998")
    assert CliProcessSupervisor._po_values_equal("168012998.0", "PO168012998")


def test_history_status_translation_preserves_filter_inputs():
    web_root = Path(__file__).parents[1] / "src" / "gui" / "web"
    html = (web_root / "index.html").read_text(encoding="utf-8")
    javascript = (web_root / "app.js").read_text(encoding="utf-8")

    assert 'data-status="SUCCESS" checked><span>Success</span>' in html
    assert '"#status-filter legend, #status-filter label span"' in javascript
    assert '"#status-filter legend, #status-filter label"' not in javascript
    assert 'class="coupa-column"' not in html
    assert 'class="coupa-link po-number-link"' in javascript
    assert 'id="btn-check-updates"' in html
    assert 'id="btn-start-over"' in html
    assert 'accept=".xlsx,.xls,.xlsm,.csv"' in html
    assert 'id="destination-feedback"' in html
    assert 'reset_new_run' in javascript
    assert 'get_authentication_status' in javascript
    assert 'await initializeAuth()' in javascript
    assert 'renderAffectedValues' in javascript
    assert 'open_filtered_input_view' in javascript
    assert 'btn-open-filtered-view' in javascript
    assert 'validateDestinationPath' in javascript
    assert 'hierarchyColumnsLoaded' in javascript
    assert 'Action required' in javascript
    assert 'checkForUpdates(true)' in javascript
    assert '$("#modal-pos-tbody").addEventListener("click"' in javascript
    assert 'retry_po_with_edit' in javascript
    assert 'save_retry_attempt' in javascript
    assert 'discard_retry_attempt' in javascript
    assert 'id="retry-result-modal"' in html
    assert 'id="btn-save-retry-result"' in html
    assert 'id="btn-discard-retry-result"' in html
    assert 'id="run-complete-card"' in html
    assert 'id="btn-open-complete-report"' in html
    assert 'id="btn-open-complete-folder"' in html
    assert 'open_run_report' in javascript
    assert 'open_run_folder' in javascript
    assert 'btn-open-run-folder' not in javascript
    assert 'formatHistoryDate' in javascript
    assert 'id="modal-input-link"' in html
    assert 'id="modal-run-folder"' in html
    assert 'id="btn-delete-detail"' in html
    assert 'run-summary-entity-tabs' in html
    assert '<th>Input</th>' not in html
    assert '<th>Description</th>' not in html
    assert 'setButtonBusy' in javascript
    assert 'aria-busy' in javascript
    assert '.btn.is-busy' in (web_root / "style.css").read_text(encoding="utf-8")
    assert '#retry-edit-modal, #retry-result-modal' in (web_root / "style.css").read_text(encoding="utf-8")


def test_run_artifact_actions_open_the_session_folder_and_report(tmp_path, monkeypatch):
    from src.db.session_db import SessionDB
    import src.gui.cli_supervisor as supervisor_module

    db_path = tmp_path / "sessions.db"
    SessionDB(str(db_path)).close()
    run_dir = tmp_path / "run_20260804"
    run_dir.mkdir()
    input_path = run_dir / "input_source_1.xlsx"
    input_path.write_bytes(b"input")
    report_path = run_dir / "report_session_1.xlsx"
    report_path.write_bytes(b"report")

    supervisor = CliProcessSupervisor()
    supervisor.db_path = db_path
    supervisor._session_metadata.clear()
    with supervisor._connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, input_file, input_file_path, status) VALUES (1, 'input.xlsx', ?, 'SUCCESS')",
            (str(input_path),),
        )

    opened = []
    monkeypatch.setattr(supervisor_module.sys, "platform", "darwin")
    monkeypatch.setattr(supervisor_module.subprocess, "Popen", lambda command: opened.append(command))

    folder_result = supervisor.open_run_folder(1)
    report_result = supervisor.open_run_report(1)

    assert folder_result == {"success": True, "path": str(run_dir)}
    assert report_result == {"success": True, "path": str(report_path)}
    assert opened == [["open", str(run_dir)], ["open", str(report_path)]]


# ── Run description and archived-input protection ────────────────────────


def test_set_run_description_updates_session(tmp_path):
    from src.gui.cli_supervisor import CliProcessSupervisor
    from src.db.session_db import SessionDB
    SessionDB(str(tmp_path / "sessions.db")).close()
    supervisor = CliProcessSupervisor()
    supervisor.db_path = tmp_path / "sessions.db"
    with supervisor._connect() as conn:
        conn.execute("INSERT INTO sessions (input_file, status) VALUES ('input.csv', 'SUCCESS')")
        session_id = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()["id"]

    result = supervisor.set_run_description(session_id, "Análise para auditoria")
    assert result["success"] is True
    with supervisor._connect() as conn:
        row = conn.execute("SELECT description FROM sessions WHERE id = ?", (session_id,)).fetchone()
    assert row["description"] == "Análise para auditoria"


def test_archived_input_becomes_read_only_after_run(tmp_path):
    from src.gui.cli_supervisor import CliProcessSupervisor
    from src.db.session_db import SessionDB
    SessionDB(str(tmp_path / "sessions.db")).close()
    supervisor = CliProcessSupervisor()
    supervisor.db_path = tmp_path / "sessions.db"
    archive = tmp_path / "run_1" / "input_source_1.csv"
    archive.parent.mkdir()
    archive.write_text("PO_NUMBER;SUPPLIER\nPO1;CompA\n", encoding="utf-8")
    with supervisor._connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, input_file, input_file_path, status) VALUES (1, 'input.csv', ?, 'SUCCESS')",
            (str(archive),),
        )
    supervisor.session_id = 1

    supervisor._protect_archived_inputs()

    import stat
    mode = stat.S_IMODE(archive.stat().st_mode)
    assert mode == 0o444

    # An explicit retry temporarily lifts the protection and re-applies it.
    supervisor._set_file_readonly(archive, False)
    archive.write_text("PO_NUMBER;SUPPLIER\nPO1;CompA\nPO2;CompB\n", encoding="utf-8")
    supervisor._set_file_readonly(archive, True)
    assert stat.S_IMODE(archive.stat().st_mode) == 0o444
