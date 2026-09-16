from __future__ import annotations

import os
import sys
import time
import asyncio
import subprocess
import threading
import shutil
import socket
import traceback
import datetime
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from src.db.session_db import SessionDB
from src.gui.api import AppAPI
from src.gui.cli_supervisor import CliProcessSupervisor
from src.auth import AuthService, AuthState, AuthenticationActionRequired
from src.engine.benchmarker import benchmark
from src.powerbi_provider import POWERBI_DOWNLOAD_FOLDER_COLUMNS
from src.engine.updater import (
    apply_update_and_restart,
    check_for_update,
    download_update as fetch_update,
    prepare_update,
)



async def get_coupa_cookies(*args, **kwargs):
    """Compatibility injection point; the official path uses ``AuthService``.

    Keeping this symbol lets an embedding integration replace the historical
    function-level hook without importing the legacy root project or the old
    authenticator module into the official bundle.
    """
    raise RuntimeError("Use AuthService for Contract Downloader authentication.")


_DEFAULT_GET_COUPA_COOKIES = get_coupa_cookies
_POWERBI_PO_COLUMNS_CACHE_MAX_AGE = datetime.timedelta(days=30)


class SingleInstanceGuard:
    """Keep one desktop window per user session.

    The loopback socket is released automatically when the process exits, so a
    crashed instance does not leave a stale lock file behind.
    """

    _HOST = "127.0.0.1"
    _PORT = 47631

    def __init__(self) -> None:
        self._socket: socket.socket | None = None

    def acquire(self) -> bool:
        if self._socket is not None:
            return True
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            candidate.bind((self._HOST, self._PORT))
            candidate.listen(1)
        except OSError:
            candidate.close()
            return False
        self._socket = candidate
        return True

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None


def _show_startup_message(title: str, message: str) -> None:
    """Show a native message even when the Windows app has no console."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
        return
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
            return
        except Exception:
            pass
    print(f"{title}: {message}", file=sys.stderr)


def _initialize_desktop_api() -> tuple[SessionDB, TurboAPI]:
    db = SessionDB(get_database_path())
    try:
        return db, TurboAPI(db, default_download_dir=os.path.expanduser("~/Downloads/CoupaAttachments"))
    except Exception:
        db.close()
        raise


def _initialize_with_windows_splash() -> tuple[SessionDB, TurboAPI]:
    """Show immediate startup feedback while the desktop bridge initializes."""
    try:
        import tkinter as tk
    except Exception:
        return _initialize_desktop_api()

    result: dict[str, Any] = {}
    done = threading.Event()

    def initialize() -> None:
        try:
            result["value"] = _initialize_desktop_api()
        except Exception as exc:
            result["error"] = exc
        finally:
            done.set()

    try:
        splash = tk.Tk()
        splash.overrideredirect(True)
        splash.configure(background="#162f43")
        width, height = 390, 150
        splash.update_idletasks()
        x = max(0, (splash.winfo_screenwidth() - width) // 2)
        y = max(0, (splash.winfo_screenheight() - height) // 2)
        splash.geometry(f"{width}x{height}+{x}+{y}")
        splash.attributes("-topmost", True)
        tk.Label(
            splash,
            text="Contract Downloader",
            font=("Segoe UI", 18, "bold"),
            foreground="#ffffff",
            background="#162f43",
        ).pack(pady=(34, 4))
        tk.Label(
            splash,
            text="Loading workspace and Coupa session…",
            font=("Segoe UI", 10),
            foreground="#b9d5e2",
            background="#162f43",
        ).pack()
        splash.update()
    except Exception:
        return _initialize_desktop_api()

    threading.Thread(target=initialize, name="desktop-startup", daemon=True).start()
    try:
        while not done.is_set():
            splash.update_idletasks()
            splash.update()
            time.sleep(0.03)
    finally:
        splash.destroy()
    if "error" in result:
        raise result["error"]
    return result["value"]


def resolve_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        bundle_root = Path(sys._MEIPASS)
        candidates = [
            bundle_root.parent / "Resources" / relative_path,
            bundle_root / relative_path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        # Preserve a useful path in the error shown by pywebview if an asset is
        # missing from a malformed package.
        return str(candidates[-1])
    base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_database_path() -> str:
    user_home = os.path.expanduser("~")
    app_data_dir = os.path.join(user_home, ".contract_downloader")
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "sessions.db")


class TurboAPI(AppAPI):
    """GUI bridge backed by the canonical process_all_pos.py pipeline."""

    def __init__(self, db: SessionDB, default_download_dir: str):
        super().__init__(db, default_download_dir)
        from src.powerbi_provider import PowerBIProvider
        from src.timesheet_provider import TimesheetProvider

        self.powerbi = PowerBIProvider()
        self.timesheets = TimesheetProvider()
        self.cli_backend = CliProcessSupervisor()
        self._pending_input_path: str | None = None
        self._fresh_auth_requested = False
        self._auth_lock = threading.Lock()
        self._auth_thread: threading.Thread | None = None
        self._auth_status: dict[str, str] = {"state": "idle", "message": ""}

    # ------------------------------------------------------------------
    # Isolated Power BI tab API. It does not participate in the Coupa run.
    # ------------------------------------------------------------------
    def get_powerbi_status(self) -> dict:
        return self.powerbi.auth_status()

    def start_powerbi_login(self) -> dict:
        try:
            return {"success": True, **self.powerbi.start_login()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def cancel_powerbi_query(self) -> dict:
        """Abort the in-flight Power BI query (preview, GRIR, FX, hierarchy)."""
        try:
            self.powerbi.cancel_query()
            return {"success": True, "cancelled": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _get_lab_relationship_powerbi(self, po_numbers: list[str]) -> dict | None:
        if not po_numbers:
            return None
        return self.powerbi.relationship_data(po_numbers)

    def get_powerbi_supplier_cache(self) -> dict:
        try:
            return {"success": True, "suppliers": self.powerbi.get_supplier_cache()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def search_powerbi_suppliers(self, term: str) -> dict:
        try:
            return {"success": True, "suppliers": self.powerbi.search_suppliers(term)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def save_powerbi_suppliers(self, suppliers: list[dict]) -> dict:
        try:
            return {"success": True, "suppliers": self.powerbi.save_suppliers(suppliers)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def delete_powerbi_supplier(self, uu: str) -> dict:
        try:
            return {"success": True, "suppliers": self.powerbi.delete_supplier(uu)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def validate_powerbi_supplier_cache(self) -> dict:
        try:
            return {"success": True, **self.powerbi.validate_supplier_cache()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_powerbi_management_hierarchy(self) -> dict:
        try:
            cached = self.db.save_powerbi_management_hierarchy(self.powerbi.management_hierarchy())
            return {"success": True, **cached}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_powerbi_management_hierarchy_cache(self) -> dict:
        try:
            return {"success": True, **self.db.get_powerbi_management_hierarchy()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def refresh_powerbi_po_date_range(self) -> dict:
        try:
            cached = self.db.save_powerbi_po_date_range(self.powerbi.po_creation_date_range())
            return {"success": True, **cached, "refreshed": True, "source": "provider"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_powerbi_po_date_range(self) -> dict:
        try:
            cached = self.db.get_powerbi_po_date_range()
            stale = not cached.get("min_date") or not cached.get("max_date") or self._powerbi_po_columns_cache_is_stale(cached.get("updated_at"))
            if stale:
                cached = self.db.save_powerbi_po_date_range(self.powerbi.po_creation_date_range())
            return {"success": True, **cached, "refreshed": stale, "source": "provider" if stale else "cache"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _powerbi_po_columns_cache_is_stale(updated_at: str | None) -> bool:
        if not updated_at:
            return True
        try:
            cached_at = datetime.datetime.fromisoformat(str(updated_at))
        except ValueError:
            return True
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=datetime.timezone.utc)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - _POWERBI_PO_COLUMNS_CACHE_MAX_AGE
        return cached_at < cutoff

    def refresh_powerbi_po_columns(self) -> dict:
        try:
            previous = self.db.get_powerbi_po_columns()
            discovered = self.powerbi.discover_po_columns()
            if self.powerbi.po_columns_source() == "provider-fallback" and previous["columns"]:
                self.powerbi.set_po_columns(previous["columns"])
                return {
                    "success": True,
                    **previous,
                    "columns": self.powerbi.active_po_columns(),
                    "refreshed": False,
                    "source": "cache",
                    "catalog_source": "provider-fallback",
                    "warning": "Power BI metadata was unavailable; the previous catalog was retained.",
                }
            cached = self.db.save_powerbi_po_columns(discovered)
            self.powerbi.set_po_columns(cached["columns"])
            return {
                "success": True,
                **cached,
                "columns": self.powerbi.active_po_columns(),
                "refreshed": True,
                "source": "provider",
                "catalog_source": self.powerbi.po_columns_source(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_powerbi_po_columns(self) -> dict:
        try:
            cached = self.db.get_powerbi_po_columns()
            stale = not cached["columns"] or self._powerbi_po_columns_cache_is_stale(cached.get("updated_at"))
            if stale:
                discovered = self.powerbi.discover_po_columns()
                if self.powerbi.po_columns_source() == "provider-fallback" and cached["columns"]:
                    self.powerbi.set_po_columns(cached["columns"])
                    return {
                        "success": True,
                        **cached,
                        "columns": self.powerbi.active_po_columns(),
                        "refreshed": False,
                        "source": "cache",
                        "catalog_source": "provider-fallback",
                        "warning": "Power BI metadata was unavailable; the previous catalog was retained.",
                    }
                cached = self.db.save_powerbi_po_columns(discovered)
                self.powerbi.set_po_columns(cached["columns"])
            else:
                self.powerbi.set_po_columns(cached["columns"])
            return {
                "success": True,
                **cached,
                "columns": self.powerbi.active_po_columns(),
                "refreshed": stale,
                "source": "provider" if stale else "cache",
                "catalog_source": self.powerbi.po_columns_source(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_powerbi_po_column_selection(self) -> dict:
        try:
            return {"success": True, **self.db.get_powerbi_po_column_selection()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def save_powerbi_po_column_selection(self, columns: list[str]) -> dict:
        try:
            return {"success": True, **self.db.save_powerbi_po_column_selection(columns)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_powerbi_purchase_families(self) -> dict:
        """Distinct Purchase Family / Commodity values for the filter dropdown."""
        try:
            return {
                "success": True,
                **self.powerbi.purchase_families(),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": "provider",
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def preview_powerbi_pos(
        self,
        year: str,
        uu_codes: list[str],
        management_paths: list[dict] | None = None,
        columns: list[str] | None = None,
        date_periods: list[str] | None = None,
        family_names: list[str] | None = None,
    ) -> dict:
        try:
            rows = self.powerbi.preview_pos(year, uu_codes, management_paths, columns, date_periods, family_names)
            selected_columns = columns if columns is not None else [
                item["key"] for item in self.powerbi.active_po_columns() if item.get("default") or item.get("required")
            ]
            return {
                "success": True,
                "rows": rows,
                "columns": selected_columns,
                "unique_pos": len({row.get("po_number") for row in rows if row.get("po_number")}),
                "records": len(rows),
                "query_diagnostics": self.powerbi.last_preview_diagnostics(),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "query_diagnostics": self.powerbi.last_preview_diagnostics(),
            }

    @staticmethod
    def _powerbi_number(value: Any) -> float:
        try:
            if value is None or str(value).strip() == "":
                return 0.0
            text = str(value).replace("€", "").replace(" ", "").replace(",", "")
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _powerbi_values(group: dict[str, Any], field: str) -> list[str]:
        values = sorted({str(row.get(field) or "").strip() for row in group["rows"] if str(row.get(field) or "").strip()})
        if field == "supplier_uu" and values:
            return [min(values, key=lambda value: (len(value), value.casefold()))]
        return values

    def _powerbi_selected_specs(self, selected_columns: list[str] | None) -> list[dict[str, Any]]:
        if not selected_columns:
            return []
        specs = {str(item.get("key")): item for item in self.powerbi.active_po_columns() if item.get("key")}
        selected = []
        seen = set()
        for raw_key in selected_columns:
            key = str(raw_key or "").strip()
            if key in seen or key not in specs:
                continue
            seen.add(key)
            selected.append(specs[key])
        return selected

    @staticmethod
    def _powerbi_input_header(spec: dict[str, Any], reserved: set[str]) -> str:
        label = str(spec.get("label") or spec.get("key") or "Power BI field").strip()
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").upper() or "POWERBI_FIELD"
        if normalized in reserved:
            normalized = f"POWERBI_{normalized}"
        return normalized

    def _powerbi_selected_value(
        self,
        group: dict[str, Any],
        spec: dict[str, Any],
        ordered_units: list[str],
    ) -> Any:
        key = str(spec.get("key") or "")
        if key == "management_unit_l3":
            return " | ".join(ordered_units)
        if key == "year":
            values = self._powerbi_values(group, key)
            if not values:
                values = sorted({str(row.get("po_creation_date") or "")[:4] for row in group["rows"] if row.get("po_creation_date")})
            return " | ".join(values)
        if key in {"commitment_value_eur", "goods_received_value_eur", "po_document_amount", "po_reporting_eur"}:
            return sum(self._powerbi_number(row.get(key)) for row in group["rows"])
        values = self._powerbi_values(group, key)
        if spec.get("type") == "currency" and values:
            return sum(self._powerbi_number(value) for value in values)
        return " | ".join(values)

    def _build_powerbi_input_rows(
        self,
        rows: list[dict],
        selected_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            po_number = str(row.get("po_number") or "").strip()
            if not po_number:
                continue
            grouped.setdefault(po_number, {"po_number": po_number, "rows": []})["rows"].append(row)
        output: list[dict[str, Any]] = []
        for po_number, group in grouped.items():
            allocation: dict[str, float] = {}
            for row in group["rows"]:
                management_unit = str(row.get("management_unit_l3") or row.get("management_unit") or "").strip()
                if management_unit:
                    allocation[management_unit] = allocation.get(management_unit, 0.0) + self._powerbi_number(row.get("commitment_value_eur"))
            ordered_units = sorted(allocation, key=lambda value: (-allocation[value], value.upper()))
            suppliers = self._powerbi_values(group, "supplier_uu")
            company_codes = self._powerbi_values(group, "company_code")
            legal_codes = self._powerbi_values(group, "legal_entity_code")
            legal_names = self._powerbi_values(group, "legal_entity_name")
            creation_dates = self._powerbi_values(group, "po_creation_date")
            commitment = sum(self._powerbi_number(row.get("commitment_value_eur")) for row in group["rows"])
            goods_received = sum(self._powerbi_number(row.get("goods_received_value_eur")) for row in group["rows"])
            output_row = {
                "PO_NUMBER": po_number,
                "SUPPLIER": " | ".join(suppliers),
                "COMPANY_CODE": " | ".join(company_codes),
                "LEGAL_ENTITY_CODE": " | ".join(legal_codes),
                "LEGAL_ENTITY_NAME": " | ".join(legal_names),
                "PO_CREATION_DATE": creation_dates[0] if creation_dates else "",
                "COMMITMENT_VALUE_EUR": commitment,
                "GOODS_RECEIVED_VALUE_EUR": goods_received,
                "POWERBI_SOURCE": "Power BI PO Mass Download Dataset",
            }
            selected_specs = self._powerbi_selected_specs(selected_columns)
            selected_keys = {str(spec.get("key") or "") for spec in selected_specs}
            for key in POWERBI_DOWNLOAD_FOLDER_COLUMNS:
                if key not in selected_keys and key in self.powerbi._po_column_by_key:
                    selected_specs.append(self.powerbi._po_column_by_key[key])
            reserved_headers = set(output_row) | {"<|>", "MANAGEMENT_UNIT"}
            supplier_metadata: dict[str, Any] = {}
            folder_metadata: dict[str, Any] = {}
            for spec in selected_specs:
                key = str(spec.get("key") or "")
                # Supplier and PO are fixed levels in the download workflow;
                # L3 is already represented by the commitment-ranked MU path.
                if key in {"po_number", "supplier_uu", "management_unit_l3"}:
                    continue
                header = self._powerbi_input_header(spec, reserved_headers)
                value = self._powerbi_selected_value(group, spec, ordered_units)
                if key.startswith("supplier_"):
                    supplier_metadata[header] = value
                else:
                    folder_metadata[header] = value
                reserved_headers.add(header)
            output_row.update(supplier_metadata)
            output_row["<|>"] = ""
            output_row["MANAGEMENT_UNIT"] = " | ".join(ordered_units)
            output_row.update(folder_metadata)
            output.append(output_row)
        return sorted(output, key=lambda item: item["PO_NUMBER"])

    def prepare_powerbi_input(
        self,
        rows: list[dict],
        filters: dict | None = None,
        selected_columns: list[str] | None = None,
    ) -> dict:
        """Create an internal one-row-per-PO snapshot for the New run."""
        import csv

        input_rows = self._build_powerbi_input_rows(rows, selected_columns)
        if not input_rows:
            return {"success": False, "error": "There are no selected POs to use in the New run."}
        destination = Path.home() / ".contract_downloader" / "working"
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"powerbi_po_input_{time.strftime('%Y%m%d-%H%M%S')}_{os.getpid()}.csv"
        columns = list(input_rows[0])
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
            writer.writeheader()
            writer.writerows(input_rows)
        metadata = {
            "source": "Power BI PO Mass Download Dataset",
            "filters": filters or {},
            "found_pos": len({str(row.get("po_number") or "").strip() for row in rows if row.get("po_number")}),
            "selected_pos": len(input_rows),
            "chunk_count": (filters or {}).get("chunk_count", 1),
            "selected_columns": list(selected_columns or []),
        }
        return {"success": True, "path": str(path), "unique_pos": len(input_rows), "source_metadata": metadata}

    def analyze_powerbi_grir(self, po_numbers: list[str]) -> dict:
        try:
            rows = self.powerbi.analyze_grir(po_numbers)
            return {"success": True, "rows": rows}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def analyze_powerbi_grir_fx(self, po_numbers: list[str]) -> dict:
        try:
            rows = self.powerbi.analyze_grir_fx(po_numbers)
            return {"success": True, "rows": rows}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Isolated Timesheet Analysis tab API. It does not participate in the
    # Coupa run or Power BI queries.
    # ------------------------------------------------------------------
    def select_timesheet_file(self) -> dict:
        try:
            window = self._native_window()
            if window is None:
                return {"success": False, "error": "Native file dialog is unavailable."}
            import webview

            paths = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Timesheet files (*.xlsb;*.xlsx;*.xlsm;*.csv)",),
            )
            path = paths[0] if paths else ""
            return {"success": bool(path), "path": path}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _timesheet_view(analysis: dict, updated_at: str | None = None) -> dict:
        result = dict(analysis)
        source = dict(result.get("source") or {})
        if updated_at:
            source["cache_updated_at"] = updated_at
        result["source"] = source
        return result

    def load_timesheet_file(self, path: str) -> dict:
        try:
            analysis = self.timesheets.load(path)
            full_analysis = self.timesheets.last_analysis or analysis
            saved = self.db.save_timesheet_analysis(full_analysis)
            return {"success": True, "analysis": self._timesheet_view(analysis, saved["updated_at"])}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_timesheet_analysis_cache(self) -> dict:
        try:
            cached = self.db.get_timesheet_analysis_cache()
            analysis = cached.get("analysis")
            if not analysis:
                return {"success": True, "analysis": None, "updated_at": cached.get("updated_at")}
            return {
                "success": True,
                "analysis": self._timesheet_view(self.timesheets.filter(analysis), cached.get("updated_at")),
                "updated_at": cached.get("updated_at"),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def filter_timesheet_analysis(self, supplier: str = "", scope: str = "tm") -> dict:
        try:
            cached = self.db.get_timesheet_analysis_cache()
            analysis = cached.get("analysis")
            if not analysis:
                return {"success": False, "error": "Load a timesheet workbook first."}
            view = self.timesheets.filter(analysis, supplier, scope)
            return {"success": True, "analysis": self._timesheet_view(view, cached.get("updated_at"))}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def export_powerbi_preview(self, rows: list[dict]) -> dict:
        """Write a reviewable, one-row-per-PO CSV outside the Coupa run flow."""
        import csv

        input_rows = self._build_powerbi_input_rows(rows)
        if not input_rows:
            return {"success": False, "error": "There are no selected POs to export."}
        destination = Path.home() / "Downloads" / "ContractDownloader" / "PowerBI"
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"powerbi_po_input_{time.strftime('%Y%m%d-%H%M%S')}.csv"
        columns = list(input_rows[0])
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
            writer.writeheader()
            writer.writerows(input_rows)
        return {"success": True, "path": str(path), "unique_pos": len(input_rows)}

    def _set_auth_status(self, state: str, message: str) -> None:
        with self._auth_lock:
            self._auth_status = {"state": state, "message": message}

    def _authenticate_worker(self, fresh: bool) -> None:
        try:
            browser = self.get_app_settings().get("auth_browser", "auto")
            auth_message = "Coupa session captured and validated."
            if get_coupa_cookies is _DEFAULT_GET_COUPA_COOKIES:
                result = asyncio.run(self.auth_service.authenticate(
                    browser_preference=browser,
                    fresh=fresh,
                    status_callback=self._set_auth_status,
                    # Startup already performed the shared cache check. Avoid
                    # a duplicate Coupa request before opening the dedicated
                    # browser profile.
                    _skip_cache_check=True,
                ))
                if not result.cookies or result.state not in {AuthState.VALID, AuthState.UNAVAILABLE}:
                    raise RuntimeError(result.message or "Coupa authentication did not produce a usable session.")
                cookies = dict(result.cookies)
                auth_message = result.message
            else:
                # Compatibility seam for integrations that replaced the
                # historical function-level entry point.
                try:
                    cookies = asyncio.run(get_coupa_cookies(
                        load_from_file=not fresh,
                        fresh=fresh,
                        status_callback=self._set_auth_status,
                        browser=browser,
                    ))
                except TypeError as exc:
                    if "browser" not in str(exc):
                        raise
                    cookies = asyncio.run(get_coupa_cookies(
                        load_from_file=not fresh,
                        fresh=fresh,
                        status_callback=self._set_auth_status,
                    ))
            self.set_auth_cookies(cookies)
            self._set_auth_status("success", auth_message)
        except AuthenticationActionRequired as exc:
            self._set_auth_status("action_required", str(exc))
        except Exception as exc:
            self._set_auth_status("error", str(exc))
        finally:
            with self._auth_lock:
                self._auth_thread = None

    def get_authentication_status(self) -> dict:
        with self._auth_lock:
            return dict(self._auth_status)

    def reset_authentication(self) -> dict:
        """Clear app authentication without touching downloads or input files."""
        with self._auth_lock:
            if self._auth_thread and self._auth_thread.is_alive():
                return {"success": False, "error": "Wait for the current Coupa sign-in attempt to finish."}
        result = self.auth_service.reset()
        if result.get("success") or "cookies" in result.get("removed", []):
            self._cookies = None
            self._fresh_auth_requested = True
            self._set_auth_status("idle", "Sign-in state reset.")
        return result

    def authenticate(self) -> dict:
        """Start Coupa authentication and expose progress through polling."""
        with self._auth_lock:
            if self._auth_thread and self._auth_thread.is_alive():
                return {"success": True, "started": False, "message": "Authentication is already in progress."}
            fresh = self._fresh_auth_requested
            self._fresh_auth_requested = False
            self._auth_status = {"state": "starting", "message": "Preparing Coupa sign-in…"}
            worker = threading.Thread(
                target=self._authenticate_worker,
                args=(fresh,),
                name="coupa-authentication",
                daemon=True,
            )
            self._auth_thread = worker
            worker.start()
        return {"success": True, "started": True}

    def run_benchmark(self, urls: list[str], base_url: str = "https://unilever.coupahost.com") -> dict:
        """Run network benchmark against sample URLs, return optimal params."""
        try:
            browser = self.get_app_settings().get("auth_browser", "auto")
            auth_result = asyncio.run(self.auth_service.ensure_session(interactive=True, browser_preference=browser))
            if not auth_result.cookies or auth_result.state not in {AuthState.VALID, AuthState.UNAVAILABLE}:
                raise RuntimeError(auth_result.message or "Coupa authentication is required before benchmarking.")
            result = asyncio.run(benchmark(urls, cookies=dict(auth_result.cookies), base_url=base_url))
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_updates(self) -> dict:
        """Check GitHub Releases for newer version."""
        try:
            update_info = asyncio.run(check_for_update())
            if update_info:
                return {"success": True, "update_available": True, **update_info}
            return {"success": True, "update_available": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_update(self, download_url: str, asset_name: str = "update.zip", checksum_url: str | None = None) -> dict:
        """Download a verified release asset to the local update cache."""
        try:
            from pathlib import Path
            update_dir = Path.home() / ".contract_downloader" / "updates"
            path = asyncio.run(fetch_update(download_url, str(update_dir), asset_name, checksum_url))
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def install_update(self, package_path: str) -> dict:
        """Install a downloaded update and restart the application."""
        try:
            payload = prepare_update(package_path)
            apply_update_and_restart(payload)
            # The detached updater waits for this process to exit before
            # replacing the executable or .app bundle.
            threading.Timer(0.7, lambda: os._exit(0)).start()
            return {"success": True, "restarting": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reset_new_run(self, filepath: str = "") -> dict:
        result = super().reset_new_run(filepath)
        if result.get("success"):
            self._pending_input_path = None
        return result

    def get_input_columns(self, filepath: str) -> dict:
        return super().get_input_columns(filepath)

    def map_input_columns(self, filepath: str, mapping: dict) -> dict:
        return super().map_input_columns(filepath, mapping)

    def _working_copy_for(self, filepath: str) -> tuple[str, bool]:
        """Return (path, copied) for a selected input.

        When the user picks an input that is the archived snapshot of another
        run, that snapshot must stay immutable (audit evidence). The new run
        works on a private copy instead.
        """
        selected = str(Path(filepath).expanduser().resolve())
        try:
            with self.cli_backend._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE input_file_path = ? ORDER BY id DESC LIMIT 1",
                    (selected,),
                ).fetchone()
        except Exception:
            row = None
        if not row:
            return selected, False
        work_dir = Path.home() / ".contract_downloader" / "working"
        work_dir.mkdir(parents=True, exist_ok=True)
        source = Path(selected)
        target = work_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}_{source.name}"
        shutil.copy2(source, target)
        return str(target), True

    def import_file(self, filepath: str, hierarchy_order: list[str] | None = None) -> dict:
        """Validate and stage the input; the CLI creates the real session."""
        # ``hierarchy_order`` is accepted for parity with AppAPI. The CLI
        # backend applies the selected order when start_download is called.
        working_path, copied = self._working_copy_for(filepath)
        validation = self.validate_input_file(working_path)
        if not validation.get("valid"):
            return {
                "success": False,
                "error": "Input validation failed.",
                "validation": validation,
            }
        self._pending_input_path = working_path
        return {
            "success": True,
            "session_id": 0,
            "total_pos": validation.get("valid_po_count", 0),
            "backend": "cli",
            "working_copy": copied,
        }

    def start_download(
        self,
        session_id: int,
        download_dir: str,
        concurrency: int = 11,
        hierarchy_order: list[str] | None = None,
        retry_attempts: int | None = None,
        description: str | None = None,
        source_metadata: dict | None = None,
    ) -> dict:
        if not self._pending_input_path:
            return {"success": False, "error": "No validated input file is staged."}
        settings = self.get_app_settings()
        selected_dir = str(download_dir or self.get_default_download_directory()).strip()
        effective_concurrency = int(settings.get("concurrency", concurrency))
        effective_retry_attempts = int(retry_attempts or settings.get("retry_attempts", 1))
        msg_processing = str(settings.get("msg_processing", "convert_extract"))
        deduplicate_files = bool(settings.get("deduplicate_files", True))
        selected_path = Path(self._absolute_user_path(selected_dir))
        persistent_root = selected_path.parent if selected_path.name.startswith("run_") else selected_path
        self._persist_download_root(str(persistent_root))
        mapping = self._mapping_for(self._pending_input_path) or None
        return self.cli_backend.start(
            self._pending_input_path,
            str(selected_path),
            effective_concurrency,
            run_dir=str(selected_path),
            hierarchy_order=hierarchy_order,
            retry_attempts=effective_retry_attempts,
            msg_processing=msg_processing,
            deduplicate_files=deduplicate_files,
            description=description,
            source_metadata=source_metadata,
            column_mapping=mapping,
            auth_browser=str(settings.get("auth_browser", "auto")),
        )

    def set_run_description(self, session_id: int, description: str) -> dict:
        return self.cli_backend.set_run_description(int(session_id), description)

    def get_active_session_status(self, session_id: int) -> dict:
        return self.cli_backend.get_status(session_id)

    def pause_download(self, session_id: int) -> dict:
        return self.cli_backend.pause()

    def resume_download(self, session_id: int) -> dict:
        # Re-authentication is an explicit GUI action. Resume never starts a
        # child browser; it only proceeds after the shared secure cache is
        # valid (or temporarily unavailable with usable cached cookies).
        auth = self.check_auth()
        if not auth.get("authenticated") and not auth.get("has_cached_session"):
            return {
                "success": False,
                "requires_auth": True,
                "error": auth.get("message") or "Authenticate with Coupa before resuming this run.",
            }
        return self.cli_backend.resume()

    def stop_download(self, session_id: int) -> dict:
        return self.cli_backend.stop()

    def retry_errors(self, session_id: int) -> dict:
        return self.cli_backend.retry_errors(int(session_id))

    def retry_supplier(self, session_id: int, supplier: str) -> dict:
        return self.cli_backend.retry_supplier(int(session_id), supplier)

    def retry_po(self, session_id: int, po_number: str) -> dict:
        return self.cli_backend.retry_po(int(session_id), po_number)

    def retry_po_with_edit(self, session_id: int, original_po: str, edited_po: str) -> dict:
        return self.cli_backend.retry_po_with_edit(int(session_id), original_po, edited_po)

    def get_retry_attempt_status(self, attempt_id: int) -> dict:
        return self.cli_backend.get_retry_attempt_status(int(attempt_id))

    def save_retry_attempt(self, attempt_id: int) -> dict:
        committed = self.cli_backend.commit_retry_attempt(int(attempt_id))
        if not committed.get("success"):
            return committed
        persisted = self.cli_backend.persist_retry_files(int(attempt_id))
        if not persisted.get("success"):
            return persisted
        return {**committed, **persisted}

    def discard_retry_attempt(self, attempt_id: int) -> dict:
        return self.cli_backend.discard_retry_attempt(int(attempt_id))

    def open_input_file(self, session_id: int) -> dict:
        return self.cli_backend.open_input_file(int(session_id))

    def open_run_folder(self, session_id: int) -> dict:
        return self.cli_backend.open_run_folder(int(session_id))

    def open_run_report(self, session_id: int) -> dict:
        return self.cli_backend.open_run_report(int(session_id))

    def open_coupa_po(self, po_number: str) -> dict:
        value = str(po_number or "").strip()
        order_number = value[2:] if value.upper().startswith(("PO", "PM")) else value
        if not order_number:
            return {"success": False, "error": "PO number is missing."}
        target = f"https://unilever.coupahost.com/order_headers/{quote(order_number, safe='')}"
        return self.open_external_url(target)

    def open_external_url(self, url: str) -> dict:
        target = str(url).strip()
        parsed = urlparse(target)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not (
            hostname == "unilever.coupahost.com" or hostname.endswith(".coupahost.com")
        ):
            return {"success": False, "error": "Only Coupa URLs can be opened."}
        try:
            # Use the OS launcher synchronously so failures are observable. A
            # detached Popen can report success even when macOS rejects it.
            if sys.platform == "darwin":
                # Keep browser selection outside the app. On macOS the default
                # URL handler (including Finicky) chooses the browser.
                subprocess.run(["/usr/bin/open", target], check=True, timeout=10)
            elif os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", target], check=True, timeout=10)
            return {"success": True, "url": target, "external_browser": True}
        except (OSError, subprocess.SubprocessError) as exc:
            try:
                import webbrowser
                if webbrowser.open_new_tab(target):
                    return {"success": True, "url": target, "external_browser": True, "fallback": True}
            except Exception:
                pass
            return {"success": False, "error": f"Could not open the external browser: {exc}"}

    def get_concurrency_estimates(self) -> dict:
        return self.cli_backend.concurrency_estimates()

    def get_session_history(self) -> list[dict]:
        return self.cli_backend.history()

    def get_session_details(self, session_id: int) -> dict:
        return self.cli_backend.details(int(session_id))

    def delete_session(self, session_id: int) -> dict:
        return self.cli_backend.delete_session(int(session_id))

    def clear_all_sessions(self) -> dict:
        return self.cli_backend.clear_all_sessions()

    def reset_application_state(self) -> dict:
        """Reset sign-in and local run records while preserving user files."""
        auth = self.reset_authentication()
        if not auth.get("success"):
            return auth
        local = self.cli_backend.reset_local_state_preserving_files()
        if not local.get("success"):
            return local
        try:
            self.db.conn.execute("DELETE FROM retry_events")
            self.db.conn.execute("DELETE FROM retry_attempts")
            self.db.conn.execute("DELETE FROM po_downloads")
            self.db.conn.execute("DELETE FROM sessions")
            self.db.conn.commit()
        except Exception as exc:
            return {"success": False, "error": f"Could not reset GUI run state: {exc}"}
        self._pending_input_path = None
        return {"success": True, "files_preserved": True}

    def export_session_report(self, session_id: int, dest_filepath: str) -> dict:
        return self.cli_backend.export_report(int(session_id), dest_filepath)

    def confirm_and_retry_company(self, session_id: int, company_code: str) -> dict:
        return {"success": False, "error": "Supplier-specific retry is not implemented; use Retry failed POs."}


def _activate_macos_window() -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
    except Exception:
        # Window activation is best-effort and must not prevent startup.
        pass


def calculate_window_geometry(screen_width: int, screen_height: int, screen_x: int = 0, screen_y: int = 0) -> dict[str, int]:
    """Size the window to 88% of the screen width and center it.

    The larger default (minimum 1080px) gives the title, the authentication
    card, and the translated strings enough room so nothing is compressed.
    """
    width = max(1080, round(screen_width * 0.88))
    height = min(840, max(720, round(screen_height * 0.88)))
    return {
        "width": width,
        "height": height,
        "x": round(screen_x + (screen_width - width) / 2),
        "y": round(screen_y + (screen_height - height) / 2),
    }


def _run_cli_pipeline() -> None:
    """Run the canonical worker and treat GUI pause cancellation as expected."""
    import process_all_pos

    try:
        asyncio.run(process_all_pos.main())
    except asyncio.CancelledError:
        # The GUI sends SIGINT for pause/stop. In the frozen entrypoint,
        # asyncio.run lives here (not under process_all_pos.__main__), so this
        # boundary must also consume CancelledError to avoid PyInstaller's
        # unhandled-exception report and exit code 1.
        print("\\n[INFO] Run interrupted safely; pending POs remain queued for resume.", flush=True)
    except KeyboardInterrupt:
        print("\\n[INFO] Run interrupted by the user (Ctrl+C).", flush=True)


def main():
    # The packaged GUI can also host the canonical CLI pipeline in a child
    # process, avoiding a second crawler implementation.
    if "--cli-pipeline" in sys.argv:
        sys.argv = [arg for arg in sys.argv if arg != "--cli-pipeline"]
        _run_cli_pipeline()
        return

    instance = SingleInstanceGuard()
    if not instance.acquire():
        _show_startup_message(
            "Contract Downloader",
            "Contract Downloader is already running. Close the existing window before starting another one.",
        )
        return

    db: SessionDB | None = None
    try:
        if sys.platform == "win32":
            db, api = _initialize_with_windows_splash()
        else:
            db, api = _initialize_desktop_api()
        import webview

        html_file = resolve_path(os.path.join("gui", "web", "index.html"))
        icon_file = resolve_path(os.path.join("gui", "web", "favicon.ico"))

        primary_screen = webview.screens[0] if getattr(webview, "screens", None) else None
        geometry = calculate_window_geometry(
            int(primary_screen.width) if primary_screen else 1600,
            int(primary_screen.height) if primary_screen else 900,
            int(primary_screen.x) if primary_screen else 0,
            int(primary_screen.y) if primary_screen else 0,
        )

        window = webview.create_window(
            title="Contract Downloader",
            url=html_file,
            js_api=api,
            width=geometry["width"],
            height=geometry["height"],
            x=geometry["x"],
            y=geometry["y"],
            screen=primary_screen,
            min_size=(1000, 680),
            resizable=True,
        )
        if sys.platform == "darwin":
            def position_and_activate_window() -> None:
                # Cocoa may ignore x/y while constructing the WebKit window. Apply
                # the measured geometry again after the native window is visible.
                window.resize(geometry["width"], geometry["height"])
                window.move(geometry["x"], geometry["y"])
                _activate_macos_window()

            window.events.shown += position_and_activate_window

        # Serve bundled HTML/CSS/JS through pywebview's loopback server;
        # this avoids file:// and resource-path 404s in packaged .app bundles.
        # pywebview applies this file to the native window on Windows. This
        # matters for the portable build, where sys.executable is the stock
        # pythonw.exe and would otherwise show the Python icon in the taskbar.
        webview.start(
            debug=False,
            http_server=True,
            icon=icon_file if os.path.isfile(icon_file) else None,
        )
    except Exception as exc:
        log_path = Path.home() / ".contract_downloader" / "startup.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        _show_startup_message(
            "Contract Downloader could not start",
            f"{exc}\n\nDetails were saved to:\n{log_path}",
        )
    finally:
        if db is not None:
            db.close()
        instance.close()


if __name__ == "__main__":
    main()
