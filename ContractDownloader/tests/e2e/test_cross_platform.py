"""Cross-platform and environment-aware E2E tests.

These tests validate behaviors that differ between macOS and Windows without
requiring a running browser — they exercise the same code paths the GUI uses
at runtime.
"""

import json
import os
import sys
from pathlib import Path

import pytest
from process_all_pos import _clean_folder_part, _detect_csv_encoding, read_input_dataframe
from src.engine.tls import system_ssl_context


# ── Input encoding (CP1252, UTF-8, UTF-8-SIG) ───────────────────────────


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"PO_NUMBER;SUPPLIER\nPO-1;Companhia S\xe3o Paulo\n", "cp1252"),
        (b"PO_NUMBER;SUPPLIER\nPO-1;Cia\n", "utf-8-sig"),  # pure ASCII: utf-8-sig tried first
        (b"\xef\xbb\xbfPO_NUMBER;SUPPLIER\nPO-1;Cia\n", "utf-8-sig"),
    ],
)
def test_detect_csv_encoding(data: bytes, expected: str, tmp_path: Path) -> None:
    csv = tmp_path / "input.csv"
    csv.write_bytes(data)
    assert _detect_csv_encoding(str(csv)) == expected


def test_read_input_dataframe_xlsx_preserves_unicode(tmp_path: Path) -> None:
    import pandas as pd

    xlsx = tmp_path / "input.xlsx"
    pd.DataFrame({"PO_NUMBER": ["PO-1"], "SUPPLIER": ["Companhia São Paulo"]}).to_excel(xlsx, index=False)
    frame = read_input_dataframe(str(xlsx))
    assert frame.iloc[0]["SUPPLIER"] == "Companhia São Paulo"


def test_read_input_dataframe_xlsm_is_treated_as_excel(tmp_path: Path) -> None:
    import pandas as pd

    xlsm = tmp_path / "input.xlsm"
    pd.DataFrame({"PO_NUMBER": ["PO-1"], "SUPPLIER": ["ACME"]}).to_excel(xlsm, index=False)
    frame = read_input_dataframe(str(xlsm))
    assert list(frame["PO_NUMBER"]) == ["PO-1"]


# ── Folder path sanitization (cross-filesystem safe) ────────────────────


def test_clean_folder_part_replaces_slashes_and_whitespace() -> None:
    assert _clean_folder_part("Foo/Bar") == "Foo_Bar"
    assert _clean_folder_part("Foo\\Bar") == "Foo_Bar"
    assert _clean_folder_part("  Leading Trailing  ") == "Leading_Trailing"
    assert _clean_folder_part(r"Integrated\_Advertising\_\_\_Creative\_-\_Agency\_Fees") == "Integrated_Advertising_Creative_-_Agency_Fees"
    assert _clean_folder_part("TV___Cinema_including_Buyouts_excluding_celebrity_costs") == "TV_Cinema_including_Buyouts_excluding_celebrity_costs"
    assert _clean_folder_part("") == "Unknown"
    assert _clean_folder_part(".") == "Unknown"
    assert _clean_folder_part("nan") == "Unknown"
    assert _clean_folder_part("None") == "Unknown"


# ── TLS / SSL context (truststore vs default) ───────────────────────────


def test_system_ssl_context_returns_valid_context() -> None:
    ctx = system_ssl_context()
    # On macOS truststore may not be installed but default SSLContext must be valid.
    assert ctx.check_hostname is True


def test_system_ssl_context_is_ssl_context() -> None:
    import ssl

    ctx = system_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)


# ── Portable-runtime Windows guardrails ─────────────────────────────────


def test_python_portable_env_var_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COUPA_PYTHON_PORTABLE", "1")
    from src.gui.api import AppAPI

    assert AppAPI._is_python_portable() is True


def test_python_portable_not_detected_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COUPA_PYTHON_PORTABLE", raising=False)
    from src.gui.api import AppAPI

    assert AppAPI._is_python_portable() is False


# ── Windows path normalization via output_subdir ────────────────────────


def test_output_subdir_uses_posix_separators_regardless_of_platform() -> None:
    """output_subdir must always use POSIX separators so sessions are portable."""
    import pandas as pd
    from process_all_pos import _build_output_subdir

    row = pd.Series({"Year": "2026", "Quarter": "Q1", "BU": "Americas"})
    subdir = _build_output_subdir(row, "Supplier", ["Year", "Quarter", "BU"], has_hierarchy_data=True)
    assert "\\" not in subdir
    assert subdir == "Supplier/2026/Q1/Americas"


# ── Settings JSON survives round-trip on both platforms ─────────────────


def test_settings_json_roundtrip_preserves_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.gui.api.Path.home", lambda: tmp_path)
    from src.db.session_db import SessionDB
    from src.gui.api import AppAPI

    db = SessionDB(str(tmp_path / "settings.db"))
    api = AppAPI(db, "Downloads/CoupaAttachments")

    result = api.set_app_settings({
        "language": "pt-BR",
        "concurrency": 6,
        "font_scale": 1.2,
    })
    assert result["success"] is True

    settings = AppAPI(db, "Downloads/CoupaAttachments").get_app_settings()
    assert settings["language"] == "pt-BR"
    assert settings["concurrency"] == 6
    assert settings["font_scale"] == 1.2


# ── Startup-update flag honours portable default ────────────────────────


def test_python_portable_defaults_auto_updates_to_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COUPA_PYTHON_PORTABLE", "1")
    monkeypatch.setattr("src.gui.api.Path.home", lambda: tmp_path)
    from src.db.session_db import SessionDB
    from src.gui.api import AppAPI

    db = SessionDB(str(tmp_path / "settings.db"))
    api = AppAPI(db, "Downloads/CoupaAttachments")

    settings = api.get_app_settings()
    assert settings["python_portable"] is True
    assert settings["auto_updates"] is False


# ── Diagnostics report is platform-aware ────────────────────────────────


def test_diagnostics_includes_os_and_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.gui.api.Path.home", lambda: tmp_path)
    from src.db.session_db import SessionDB
    from src.gui.api import AppAPI

    db = SessionDB(str(tmp_path / "settings.db"))
    api = AppAPI(db, "Downloads/CoupaAttachments")

    report = api.run_diagnostics("")
    assert report["success"] is True
    assert "Operating system" in report["report"]
    assert sys.platform in report["report"].lower() or "Windows" in report["report"] or "Darwin" in report["report"] or "Linux" in report["report"]
    assert "Python runtime" in report["report"]
    assert "Edge profile" in report["report"]
    assert "Coupa session" in report["report"]
    assert report["summary"]["passed"] >= 2


def test_diagnostics_includes_edge_profile_on_this_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge profile check must succeed or warn — never fail — on any machine."""
    monkeypatch.setattr("src.gui.api.Path.home", lambda: tmp_path)
    from src.db.session_db import SessionDB
    from src.gui.api import AppAPI

    db = SessionDB(str(tmp_path / "settings.db"))
    api = AppAPI(db, "Downloads/CoupaAttachments")

    report = api.run_diagnostics("")
    assert report["success"] is True

    profile_checks = [c for c in report["checks"] if c["name"] == "Edge profile"]
    assert len(profile_checks) == 1
    assert profile_checks[0]["status"] in {"PASS", "WARN"}
    assert profile_checks[0]["status"] != "FAIL"


def test_diagnostics_includes_coupa_session_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Coupa session check must be present and never crash the report."""
    monkeypatch.setattr("src.gui.api.Path.home", lambda: tmp_path)
    from src.db.session_db import SessionDB
    from src.gui.api import AppAPI

    db = SessionDB(str(tmp_path / "settings.db"))
    api = AppAPI(db, "Downloads/CoupaAttachments")

    report = api.run_diagnostics("")
    assert report["success"] is True

    session_checks = [c for c in report["checks"] if c["name"] == "Coupa session"]
    assert len(session_checks) == 1
    assert session_checks[0]["status"] in {"PASS", "WARN"}
    assert session_checks[0]["status"] != "FAIL"
