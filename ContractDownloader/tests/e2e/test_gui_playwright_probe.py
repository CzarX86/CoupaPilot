from pathlib import Path

from scripts.gui_playwright_debug import run_probe


def _assert_common_report(report: dict) -> None:
    assert report["page_error_count"] == 0
    assert "loaded-index" in report["steps"]
    assert "progress-visible" in report["steps"]
    assert "history-loaded" in report["steps"]
    assert "modal-opened" in report["steps"]
    assert "po-edge-link-clicked" in report["steps"]
    assert "export-clicked" in report["steps"]
    assert "manual-update-check" in report["steps"]
    assert "start-over-clicked" in report["steps"]
    assert "re-selected-after-start-over" in report["steps"]

    dom_state = report["dom_state"]
    assert dom_state["history_rows"] >= 1
    assert dom_state["console_ui_lines"] >= 1
    assert dom_state["modal_po_rows"] >= 1
    assert dom_state["status_filter_inputs"] == 5
    assert dom_state["sidebar_controls_visible"] is True
    sidebar = dom_state["sidebar_metrics"]
    assert sidebar["overflowY"] == "hidden"
    assert sidebar["scrollHeight"] <= sidebar["clientHeight"]
    assert sidebar["bottom"] <= sidebar["viewportHeight"] + 1
    settings_save = dom_state["settings_save_metrics"]
    assert settings_save["fullyVisible"] is True
    assert settings_save["bottom"] <= settings_save["viewportHeight"]


def test_gui_playwright_probe_mock(tmp_path: Path) -> None:
    result = run_probe(mode="mock", timeout_ms=20000, output_root=tmp_path)

    _assert_common_report(result.report)
    assert result.report["mode"] == "mock"
    assert result.report["dom_state"]["progress_text"].startswith("0%") is False
    assert "pause-clicked" in result.report["steps"]
    assert "clicked-stop" in result.report["steps"]

    expected_screens = [
        "01_loaded.png",
        "02_file_selected.png",
        "03_progress.png",
        "04_history.png",
        "05_modal.png",
        "06_done.png",
        "07_settings_scrolled.png",
    ]
    for screen in expected_screens:
        assert (result.run_dir / screen).exists(), f"Missing screenshot: {screen}"


def test_gui_playwright_probe_real_backend(tmp_path: Path) -> None:
    result = run_probe(mode="real", timeout_ms=25000, output_root=tmp_path)

    _assert_common_report(result.report)
    assert result.report["mode"] == "real"

    # In real mode, import creates one real session and history should show it.
    assert result.report["dom_state"]["history_rows"] >= 1
    assert (result.run_dir / "probe.db").exists()


def test_gui_playwright_probe_start_without_file(tmp_path: Path) -> None:
    result = run_probe(mode="mock", timeout_ms=20000, output_root=tmp_path)

    # The journey starts with a disabled continuation control until an input
    # file is selected, so starting is impossible at this stage.
    assert "checked-next-without-file" in result.report["steps"]
    assert "clicked-start" in result.report["steps"]


def test_gui_playwright_probe_stop_during_execution(tmp_path: Path) -> None:
    result = run_probe(mode="mock", timeout_ms=20000, output_root=tmp_path)

    # Stopping during execution must be exercised by the probe, not simulated
    # in the test report after the fact.
    assert "clicked-stop" in result.report["steps"]
    assert "Stop requested. Waiting current operation to end..." in result.report["console_logs"]
