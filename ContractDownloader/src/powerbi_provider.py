"""Small Power BI query adapter used only by the Power BI GUI tab."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote


DATASET_ID = "45f78e7b-bb55-42f4-a5e3-8b790e6dfbb3"
INVOICE_DATASET_ID = "2cbe0c63-e1da-416e-b765-a87fd33d5ebe"
FAB_VERSION = "1.6.1"
MAX_SEARCH_ROWS = 500
MAX_PREVIEW_ROWS = 10_000
GRIR_PO_CHUNK_SIZE = 250

# Purchase Family / Commodity column confirmed in the PO semantic model. The
# provider validates this against INFO.VIEW.COLUMNS() and keeps it as a safe
# fallback when metadata discovery is unavailable.
PURCHASE_FAMILY_TABLE = "Commodity"
PURCHASE_FAMILY_COLUMN = "L2 Purchase Family Name"
PURCHASE_FAMILY_L1_TABLE = "Commodity"
PURCHASE_FAMILY_L1_COLUMN = "L1 Procurement Team Name"

# Patterns used to recognise the Purchase Family hierarchy L4 column.
_PF_TABLE_PATTERN = re.compile(r"(?i)family|commodit")
_PF_COLUMN_PATTERN = re.compile(r"(?i)(?:L\d+\s+)?purchase\s+family.*(?:name|desc)|(?:name|desc).*purchase\s+family")


# Catalog of fields confirmed by the PO semantic model queries used by this
# app. The UI consumes this list instead of maintaining a second field list.
POWERBI_PO_COLUMNS = (
    {
        "key": "po_number",
        "label": "PO number",
        "group": "PO identity",
        "source": "PurchaseOrder_Allocated[PO Number]",
        "table": "PurchaseOrder_Allocated",
        "column": "PO Number",
        "type": "text",
        "default": True,
        "required": True,
    },
    {
        "key": "po_creation_date",
        "label": "PO Creation Date",
        "group": "PO identity",
        "source": "PurchaseOrder_Allocated[PO Creation Date]",
        "table": "PurchaseOrder_Allocated",
        "column": "PO Creation Date",
        "type": "date",
        "default": True,
    },
    {
        "key": "year",
        "label": "Year",
        "group": "PO identity",
        "source": "PurchaseOrder_Allocated[Year]",
        "table": "PurchaseOrder_Allocated",
        "column": "Year",
        "type": "text",
        "default": False,
    },
    {
        "key": "management_unit_l1",
        "label": "Management Unit L1",
        "group": "Management Unit",
        "source": "Cost Centre[Management Unit L1 Name]",
        "table": "Cost Centre",
        "column": "Management Unit L1 Name",
        "type": "text",
        "default": False,
    },
    {
        "key": "management_unit_l2",
        "label": "Management Unit L2",
        "group": "Management Unit",
        "source": "Cost Centre[Management Unit L2 Name]",
        "table": "Cost Centre",
        "column": "Management Unit L2 Name",
        "type": "text",
        "default": False,
    },
    {
        "key": "management_unit_l3",
        "label": "Management Unit L3",
        "group": "Management Unit",
        "source": "Cost Centre[Management Unit L3 Name]",
        "table": "Cost Centre",
        "column": "Management Unit L3 Name",
        "type": "text",
        "default": True,
    },
    {
        "key": "management_unit_l4",
        "label": "Management Unit L4",
        "group": "Management Unit",
        "source": "Cost Centre[Management Unit L4 Name]",
        "table": "Cost Centre",
        "column": "Management Unit L4 Name",
        "type": "text",
        "default": False,
    },
    {
        "key": "management_unit_l5",
        "label": "Management Unit L5",
        "group": "Management Unit",
        "source": "Cost Centre[Management Unit L5 Name]",
        "table": "Cost Centre",
        "column": "Management Unit L5 Name",
        "type": "text",
        "default": False,
    },
    {
        "key": "management_unit_l6",
        "label": "Management Unit L6",
        "group": "Management Unit",
        "source": "Cost Centre[Management Unit L6 Name]",
        "table": "Cost Centre",
        "column": "Management Unit L6 Name",
        "type": "text",
        "default": False,
    },
    {
        "key": "crg",
        "label": "CRG",
        "group": "Cost Centre",
        "source": "Cost Centre[Cost Reporting Group Code]",
        "table": "Cost Centre",
        "column": "Cost Reporting Group Code",
        "type": "text",
        "default": False,
    },
    {
        "key": "supplier_uu",
        "label": "Supplier UU",
        "group": "Supplier",
        "source": "Supplier - Codes[SupplierHierarchyUU]",
        "table": "Supplier - Codes",
        "column": "SupplierHierarchyUU",
        "type": "text",
        "default": True,
    },
    {
        "key": "supplier_gu",
        "label": "Supplier GU code",
        "group": "Supplier",
        "source": "Supplier - Codes[SupplierHierarchyGU]",
        "table": "Supplier - Codes",
        "column": "SupplierHierarchyGU",
        "type": "text",
        "default": False,
    },
    {
        "key": "supplier_s",
        "label": "Supplier S code",
        "group": "Supplier",
        "source": "Supplier - Codes[SupplierHierarchyS]",
        "table": "Supplier - Codes",
        "column": "SupplierHierarchyS",
        "type": "text",
        "default": False,
    },
    {
        "key": "legal_entity_code",
        "label": "Legal Entity code",
        "group": "Company",
        "source": "Company[L4 Legal Entity Code]",
        "table": "Company",
        "column": "L4 Legal Entity Code",
        "type": "text",
        "default": True,
    },
    {
        "key": "legal_entity_name",
        "label": "Legal Entity name",
        "group": "Company",
        "source": "Company[L4 Legal Entity Name]",
        "table": "Company",
        "column": "L4 Legal Entity Name",
        "type": "text",
        "default": True,
    },
    {
        "key": "company_code",
        "label": "Company code",
        "group": "Company",
        "source": "Company[L5 Company Code]",
        "table": "Company",
        "column": "L5 Company Code",
        "type": "text",
        "default": True,
    },
    {
        "key": "company_name",
        "label": "Company name",
        "group": "Company",
        "source": "Company[L5 Company Name]",
        "table": "Company",
        "column": "L5 Company Name",
        "type": "text",
        "default": False,
    },
    {
        "key": "commitment_value_eur",
        "label": "Commitment value (EUR)",
        "group": "Measures",
        "source": "Measure[Commitment Value EUR]",
        "measure": "Commitment Value EUR",
        "type": "currency",
        "default": True,
    },
    {
        "key": "goods_received_value_eur",
        "label": "Goods received value (EUR)",
        "group": "Measures",
        "source": "Measure[Goods Received Value EUR]",
        "measure": "Goods Received Value EUR",
        "type": "currency",
        "default": False,
    },
    {
        "key": "po_document_amount",
        "label": "PO document amount",
        "group": "Measures",
        "source": "Purchase Order[DocumentCurrencyAmount]",
        "table": "Purchase Order",
        "column": "DocumentCurrencyAmount",
        "aggregation": "SUM",
        "type": "currency",
        "default": False,
    },
    {
        "key": "po_reporting_eur",
        "label": "PO reporting amount (EUR)",
        "group": "Measures",
        "source": "Purchase Order[ReportingCurrencyEuroAmount]",
        "table": "Purchase Order",
        "column": "ReportingCurrencyEuroAmount",
        "aggregation": "SUM",
        "type": "currency",
        "default": False,
    },
    {
        "key": "goods_received_document_amount",
        "label": "Goods received document amount",
        "group": "Measures",
        "source": "Purchase Order[GoodsReceiptDocumentCurrencyAmount]",
        "table": "Purchase Order",
        "column": "GoodsReceiptDocumentCurrencyAmount",
        "aggregation": "SUM",
        "type": "currency",
        "default": False,
    },
    {
        "key": "goods_received_reporting_eur",
        "label": "Goods received reporting amount (EUR)",
        "group": "Measures",
        "source": "Purchase Order[GoodsReceiptReportingCurrencyEuroAmount]",
        "table": "Purchase Order",
        "column": "GoodsReceiptReportingCurrencyEuroAmount",
        "aggregation": "SUM",
        "type": "currency",
        "default": False,
    },
)

POWERBI_PO_COLUMN_BY_KEY = {item["key"]: item for item in POWERBI_PO_COLUMNS}
DEFAULT_POWERBI_PO_COLUMNS = tuple(item["key"] for item in POWERBI_PO_COLUMNS if item.get("default") or item.get("required"))
POWERBI_DOWNLOAD_FOLDER_COLUMNS = ("crg", "year")


PRIORITY_SUPPLIERS = [
    {"alias": "Accenture", "uu": "WCSCUU61646", "official_name": "ACCENTURE PUBLIC LIMITED COMPANY", "provisional": True},
    {"alias": "Infosys", "uu": "WCSCUU60776", "official_name": "INFOSYS LIMITED", "provisional": True},
    {"alias": "Deloitte", "uu": "WCSCUU61655", "official_name": "DELOITTE TOUCHE TOHMATSU LIMITED", "provisional": True},
    {"alias": "EY", "uu": "WCSCUU61677", "official_name": "ERNST & YOUNG GLOBAL LIMITED", "provisional": True},
    {"alias": "Fractal", "uu": "WCSCUU93195", "official_name": "FRACTAL ANALYTICS INC", "provisional": True},
    {"alias": "TCS", "uu": "WCSCUU536885", "official_name": "TATA CONSULTANCY SERVICES LIMITED", "provisional": True},
    {"alias": "NTT", "uu": "WCSCUU67818", "official_name": "NIPPON TELEGRAPH AND TELEPHONE EAST CORPORATION", "provisional": True},
    {"alias": "Capgemini", "uu": "WCSCUU208186", "official_name": "CAPGEMINI OUTSOURCING SERVICES", "provisional": True},
    {"alias": "Cognizant", "uu": "WCSCUU60775", "official_name": "COGNIZANT TECHNOLOGY SOLUTIONS CORPORATION", "provisional": True},
    {"alias": "LTI Mindtree", "uu": "WCSCUU75570", "official_name": "LARSEN AND TOUBRO LIMITED", "provisional": True},
]


class PowerBIError(RuntimeError):
    """Safe, user-facing Power BI integration error."""


class PowerBIProvider:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or (Path.home() / ".contract_downloader")
        self.cache_path = self.state_dir / "powerbi_supplier_cache.json"
        self._login_process: subprocess.Popen[str] | None = None
        self._cancel_event = threading.Event()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None
        self._discovered_family_column: tuple[str, str] | None = None
        self._last_preview_diagnostics: dict[str, Any] | None = None
        self._po_columns_source = "provider"
        self.set_po_columns(list(POWERBI_PO_COLUMNS))

    def cancel_query(self) -> None:
        """Request cancellation of the currently running Power BI query.

        Safe to call from any thread (the GUI calls it while a preview query
        is in flight). The running helper process is terminated so the query
        returns promptly instead of waiting for the full timeout.
        """
        self._cancel_event.set()
        with self._process_lock:
            process = self._active_process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    @staticmethod
    def _field(row: dict[str, Any], name: str) -> Any:
        normalized_name = str(name).replace("'", "")
        suffix = f"[{normalized_name}]"
        for key, value in row.items():
            normalized_key = str(key).replace("'", "")
            if normalized_key == normalized_name or normalized_key == suffix or normalized_key.endswith(suffix):
                return value
        return None

    @staticmethod
    def _dax_text(value: str) -> str:
        return '"' + str(value).replace('"', '""') + '"'

    @staticmethod
    def _dax_value(value: Any) -> str:
        if value is None or value == "":
            return "BLANK()"
        return PowerBIProvider._dax_text(str(value))

    @staticmethod
    def _split_hierarchy_value(value: Any) -> tuple[str, str]:
        text = str(value or "").strip()
        if ":" not in text:
            return text, ""
        name, code = text.rsplit(":", 1)
        return name.strip(), code.strip()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value or "").upper().replace("&", "AND").split())

    @classmethod
    def _score(cls, query: str, candidate: str) -> float:
        query_norm = cls._normalize(query)
        candidate_norm = cls._normalize(candidate)
        if not query_norm or not candidate_norm:
            return 0.0
        if query_norm in candidate_norm:
            return 1.0
        query_tokens = query_norm.split()
        token_scores = []
        for token in query_tokens:
            token_scores.append(1.0 if token in candidate_norm else SequenceMatcher(None, token, candidate_norm).ratio())
        token_coverage = sum(token_scores) / len(token_scores) if token_scores else 0.0
        return max(SequenceMatcher(None, query_norm, candidate_norm).ratio(), token_coverage * 0.95)

    def _command_prefix(self) -> list[str]:
        configured = os.environ.get("COUPAPILOT_FAB_COMMAND", "").strip()
        if configured:
            return shlex.split(configured)
        fab = shutil.which("fab")
        if fab:
            return [fab]
        uv = shutil.which("uv")
        if not uv:
            for candidate in ("/opt/homebrew/bin/uv", "/usr/local/bin/uv"):
                if Path(candidate).is_file():
                    uv = candidate
                    break
        if uv:
            return [uv, "tool", "run", "--from", f"ms-fabric-cli=={FAB_VERSION}", "fab"]
        raise PowerBIError("Power BI helper not found. Install the official Fabric CLI or configure COUPAPILOT_FAB_COMMAND.")

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        cache_dir = self.state_dir / "fabric-cli-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        environment.setdefault("UV_CACHE_DIR", str(cache_dir))
        return environment

    @staticmethod
    def _safe_process_error(result: subprocess.CompletedProcess[str]) -> str:
        lines = []
        for line in (result.stderr or "").splitlines() + (result.stdout or "").splitlines():
            lowered = line.lower()
            if any(secret in lowered for secret in ("token", "account:", "principal id", "tenant id", "app id")):
                continue
            if line.strip():
                lines.append(line.strip())
        return " ".join(lines[-4:]) or f"Power BI helper exited with code {result.returncode}."

    def _run(self, arguments: list[str], timeout: float = 60.0) -> str:
        self._cancel_event.clear()
        try:
            process = subprocess.Popen(
                self._command_prefix() + arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._environment(),
            )
        except OSError as exc:
            raise PowerBIError(f"Could not start the Power BI helper: {exc}") from exc
        with self._process_lock:
            self._active_process = process
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise PowerBIError("Power BI query timed out.") from None
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None
        if self._cancel_event.is_set():
            raise PowerBIError("Power BI query cancelled.")
        if process.returncode != 0:
            result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
            raise PowerBIError(self._safe_process_error(result))
        return stdout or ""

    def _run_json(self, arguments: list[str], payload: dict[str, Any], timeout: float = 90.0) -> dict[str, Any]:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
                json.dump(payload, handle, ensure_ascii=False)
                temporary_path = handle.name
            raw = self._run(arguments + ["-i", temporary_path], timeout=timeout)
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink()
                except OSError:
                    pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            raise PowerBIError("Power BI helper returned an invalid response.")
        try:
            response = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise PowerBIError("Power BI helper returned an unreadable response.") from exc
        if int(response.get("status_code", 200)) != 200:
            raise PowerBIError("Power BI rejected the query. Verify the login and dataset permissions.")
        return response

    @staticmethod
    def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
        text = response.get("text") or {}
        results = text.get("results") or []
        tables = results[0].get("tables") if results else []
        return list((tables or [{}])[0].get("rows") or [])

    def _execute_dataset_query(self, dataset_id: str, dax: str, timeout: float = 120.0) -> list[dict[str, Any]]:
        response = self._run_json(
            [
                "api",
                "-A",
                "powerbi",
                f"datasets/{dataset_id}/executeQueries",
                "-X",
                "post",
                "-H",
                "content-type=application/json",
            ],
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
            timeout=timeout,
        )
        return self._rows(response)

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _effective_rate(cls, reporting_eur: Any, document_amount: Any) -> float | None:
        amount = cls._number(document_amount)
        if abs(amount) <= 1e-9:
            return None
        return cls._number(reporting_eur) / amount

    def analyze_grir(self, po_numbers: list[str]) -> list[dict[str, Any]]:
        """Compare full PO lifecycle receipts against invoices, by selected PO."""
        selected = sorted({str(value).strip() for value in po_numbers if str(value).strip() and str(value).strip().upper() != "UNK"})
        if not selected:
            return []

        goods_by_po: dict[str, dict[str, Any]] = {}
        invoices_by_po: dict[str, dict[str, Any]] = {}
        for start in range(0, len(selected), GRIR_PO_CHUNK_SIZE):
            chunk = selected[start : start + GRIR_PO_CHUNK_SIZE]
            values = ", ".join(self._dax_text(value) for value in chunk)
            goods_filter = f"TREATAS({{{values}}}, 'Purchase Order'[PO Number])"
            invoice_filter = f"TREATAS({{{values}}}, 'Invoice'[PO Number])"
            goods_rows = self._execute_dataset_query(
                DATASET_ID,
                f"""EVALUATE
SUMMARIZECOLUMNS(
    'Purchase Order'[PO Number],
    {goods_filter},
    "Goods Received EUR", SUM('Purchase Order'[GoodsReceiptReportingCurrencyEuroAmount]),
    "PO Lines", COUNTROWS('Purchase Order')
)""",
            )
            invoice_rows = self._execute_dataset_query(
                INVOICE_DATASET_ID,
                f"""EVALUATE
SUMMARIZECOLUMNS(
    'Invoice'[PO Number],
    {invoice_filter},
    "Invoice Received EUR", SUM('Invoice'[ReportingCurrencyEuroAmount]),
    "Invoice Ledger Lines", COUNTROWS('Invoice'),
    "Invoice Documents", DISTINCTCOUNT('Invoice'[Accounting Document Number]),
    "Invoice Numbers", DISTINCTCOUNT('Invoice'[Purchase Invoice Number])
)""",
            )
            for row in goods_rows:
                po = str(self._field(row, "PO Number") or "").strip()
                if po:
                    goods_by_po[po] = {
                        "goods_received_eur": self._number(self._field(row, "Goods Received EUR")),
                        "po_lines": int(self._number(self._field(row, "PO Lines"))),
                    }
            for row in invoice_rows:
                po = str(self._field(row, "PO Number") or "").strip()
                if po:
                    invoices_by_po[po] = {
                        "invoice_received_eur": self._number(self._field(row, "Invoice Received EUR")),
                        "invoice_ledger_lines": int(self._number(self._field(row, "Invoice Ledger Lines"))),
                        "invoice_documents": int(self._number(self._field(row, "Invoice Documents"))),
                        "invoice_numbers": int(self._number(self._field(row, "Invoice Numbers"))),
                    }

        result = []
        for po in selected:
            goods = goods_by_po.get(po, {})
            invoices = invoices_by_po.get(po, {})
            goods_value = goods.get("goods_received_eur", 0.0)
            invoice_value = invoices.get("invoice_received_eur", 0.0)
            variance = goods_value - invoice_value
            invoice_count = invoices.get("invoice_numbers", 0) or invoices.get("invoice_documents", 0)
            if invoice_count == 0:
                status = "no_invoice"
            elif abs(variance) <= 0.01:
                status = "balanced"
            elif variance > 0:
                status = "goods_received_gt_invoice"
            else:
                status = "invoice_received_gt_goods"
            result.append({
                "po_number": po,
                "goods_received_eur": goods_value,
                "invoice_received_eur": invoice_value,
                "variance_eur": variance,
                "po_lines": goods.get("po_lines", 0),
                "invoice_count": invoice_count,
                "invoice_ledger_lines": invoices.get("invoice_ledger_lines", 0),
                "status": status,
            })
        return result

    def analyze_grir_fx(self, po_numbers: list[str]) -> list[dict[str, Any]]:
        """Compare effective invoice FX with the selected PO baseline."""
        selected = sorted({
            str(value).strip()
            for value in po_numbers
            if str(value).strip() and str(value).strip().upper() != "UNK"
        })
        if not selected:
            return []

        po_by_number: dict[str, dict[str, Any]] = {}
        invoices_by_po: dict[str, list[dict[str, Any]]] = {}
        for start in range(0, len(selected), GRIR_PO_CHUNK_SIZE):
            chunk = selected[start : start + GRIR_PO_CHUNK_SIZE]
            values = ", ".join(self._dax_text(value) for value in chunk)
            po_filter = f"TREATAS({{{values}}}, 'Purchase Order'[PO Number])"
            invoice_filter = f"TREATAS({{{values}}}, 'Invoice'[PO Number])"
            po_rows = self._execute_dataset_query(
                DATASET_ID,
                f"""EVALUATE
SUMMARIZECOLUMNS(
    'Purchase Order'[PO Number],
    {po_filter},
    "Commitment Value EUR", 'Measure'[Commitment Value EUR],
    "PO Document Amount", SUM('Purchase Order'[DocumentCurrencyAmount]),
    "PO Reporting EUR", SUM('Purchase Order'[ReportingCurrencyEuroAmount]),
    "Goods Received Document Amount", SUM('Purchase Order'[GoodsReceiptDocumentCurrencyAmount]),
    "Goods Received EUR", SUM('Purchase Order'[GoodsReceiptReportingCurrencyEuroAmount]),
    "PO Currencies", DISTINCTCOUNT('Purchase Order'[DocumentCurrencySK])
)""",
            )
            invoice_rows = self._execute_dataset_query(
                INVOICE_DATASET_ID,
                f"""EVALUATE
SUMMARIZECOLUMNS(
    'Invoice'[PO Number],
    'Invoice'[PO Line Number],
    'Invoice'[Purchase Invoice Number],
    'Invoice'[Accounting Document Number],
    'Invoice'[Document Date],
    'Document Currency'[Document Currency Code],
    {invoice_filter},
    "Invoice Document Amount", SUM('Invoice'[DocumentCurrencyAmount]),
    "Invoice Reporting EUR", SUM('Invoice'[ReportingCurrencyEuroAmount]),
    "Invoice Ledger Lines", COUNTROWS('Invoice')
)""",
            )
            for row in po_rows:
                po = str(self._field(row, "PO Number") or "").strip()
                if po:
                    po_by_number[po] = {
                        "commitment_value_eur": self._number(self._field(row, "Commitment Value EUR")),
                        "po_document_amount": self._number(self._field(row, "PO Document Amount")),
                        "po_reporting_eur": self._number(self._field(row, "PO Reporting EUR")),
                        "goods_received_document_amount": self._number(self._field(row, "Goods Received Document Amount")),
                        "goods_received_eur": self._number(self._field(row, "Goods Received EUR")),
                        "po_currencies": int(self._number(self._field(row, "PO Currencies"))),
                    }
            for row in invoice_rows:
                po = str(self._field(row, "PO Number") or "").strip()
                if not po:
                    continue
                document_amount = self._number(self._field(row, "Invoice Document Amount"))
                reporting_eur = self._number(self._field(row, "Invoice Reporting EUR"))
                invoices_by_po.setdefault(po, []).append({
                    "invoice_number": str(self._field(row, "Purchase Invoice Number") or "").strip(),
                    "accounting_document_number": str(self._field(row, "Accounting Document Number") or "").strip(),
                    "po_line_number": str(self._field(row, "PO Line Number") or "").strip(),
                    "document_date": self._field(row, "Document Date"),
                    "document_currency": str(self._field(row, "Document Currency Code") or "").strip(),
                    "document_amount": document_amount,
                    "reporting_eur": reporting_eur,
                    "invoice_ledger_lines": int(self._number(self._field(row, "Invoice Ledger Lines"))),
                    "invoice_fx_rate": self._effective_rate(reporting_eur, document_amount),
                })

        result = []
        for po in selected:
            baseline = po_by_number.get(po, {})
            invoices = invoices_by_po.get(po, [])
            po_rate = None
            goods_rate = None
            if baseline.get("po_currencies", 0) == 1:
                po_rate = self._effective_rate(baseline.get("po_reporting_eur"), baseline.get("po_document_amount"))
                goods_rate = self._effective_rate(
                    baseline.get("goods_received_eur"),
                    baseline.get("goods_received_document_amount"),
                )

            invoice_received_eur = sum(row["reporting_eur"] for row in invoices)
            goods_received_eur = baseline.get("goods_received_eur", 0.0)
            grir_total = goods_received_eur - invoice_received_eur
            invoice_value_at_po_rate = None
            fx_impact = None
            grir_ex_fx = None
            if po_rate is not None:
                invoice_value_at_po_rate = sum(row["document_amount"] * po_rate for row in invoices)
                fx_impact = invoice_received_eur - invoice_value_at_po_rate
                grir_ex_fx = goods_received_eur - invoice_value_at_po_rate
                for row in invoices:
                    if row["invoice_fx_rate"] is None:
                        row["fx_delta_vs_po"] = None
                        row["fx_impact_eur"] = None
                        row["status"] = "no_invoice_fx"
                    else:
                        row["fx_delta_vs_po"] = row["invoice_fx_rate"] - po_rate
                        row["fx_impact_eur"] = row["reporting_eur"] - row["document_amount"] * po_rate
                        row["status"] = "fx_variance" if abs(row["fx_delta_vs_po"]) > 0.000001 else "fx_aligned"
            else:
                for row in invoices:
                    row["fx_delta_vs_po"] = None
                    row["fx_impact_eur"] = None
                    row["status"] = "po_fx_unavailable" if row["invoice_fx_rate"] is not None else "no_fx"
            result.append({
                "po_number": po,
                "commitment_value_eur": baseline.get("commitment_value_eur", 0.0),
                "goods_received_eur": goods_received_eur,
                "invoice_received_eur": invoice_received_eur,
                "grir_total_eur": grir_total,
                "fx_impact_eur": fx_impact,
                "grir_ex_fx_eur": grir_ex_fx,
                "po_fx_rate": po_rate,
                "goods_received_fx_rate": goods_rate,
                "po_fx_status": "available" if po_rate is not None else "unavailable_or_ambiguous",
                "sow_fx_status": "unavailable",
                "invoices": invoices,
            })
        return result

    def relationship_data(self, po_numbers: list[str]) -> dict[str, Any]:
        """Return the Power BI fields needed by the LAB relationship tree."""
        rows = self.analyze_grir_fx(po_numbers)
        return {
            "pos": {
                row["po_number"]: {
                    "commitment_value_eur": row.get("commitment_value_eur", 0.0),
                }
                for row in rows
                if row.get("po_number")
            },
            "invoices": {
                row["po_number"]: [
                    {
                        **invoice,
                        "po_number": row["po_number"],
                    }
                    for invoice in row.get("invoices", [])
                ]
                for row in rows
                if row.get("po_number")
            },
        }

    def auth_status(self) -> dict[str, Any]:
        try:
            raw = self._run(["auth", "status"], timeout=30)
        except PowerBIError as exc:
            return {"available": False, "authenticated": False, "message": str(exc)}
        authenticated = "logged in: true" in raw.lower()
        return {
            "available": True,
            "authenticated": authenticated,
            "message": "Power BI session available." if authenticated else "Power BI sign-in required.",
        }

    def start_login(self) -> dict[str, Any]:
        if self._login_process and self._login_process.poll() is None:
            return {"started": False, "message": "Power BI sign-in is already in progress."}
        try:
            self._login_process = subprocess.Popen(
                self._command_prefix() + ["auth", "login"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
                start_new_session=True,
            )
        except OSError as exc:
            raise PowerBIError(f"Could not start Power BI sign-in: {exc}") from exc
        return {"started": True, "message": "Complete Power BI sign-in in the browser, then validate the session."}

    def get_supplier_cache(self) -> list[dict[str, Any]]:
        custom: list[dict[str, Any]] = []
        try:
            loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
            custom = loaded.get("custom", []) if isinstance(loaded, dict) else []
        except (OSError, ValueError):
            pass
        return [*PRIORITY_SUPPLIERS, *self._clean_suppliers(custom, set(item["uu"] for item in PRIORITY_SUPPLIERS))]

    @staticmethod
    def _clean_suppliers(suppliers: list[dict[str, Any]], reserved: set[str] | None = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen = set(reserved or set())
        for item in suppliers:
            if not isinstance(item, dict):
                continue
            uu = str(item.get("uu") or "").strip()
            if not uu or uu in seen:
                continue
            seen.add(uu)
            result.append({
                "alias": str(item.get("alias") or item.get("official_name") or uu).strip(),
                "uu": uu,
                "official_name": str(item.get("official_name") or item.get("alias") or uu).strip(),
                "gu": str(item.get("gu") or "").strip(),
                "sap_codes": sorted({str(code).strip() for code in item.get("sap_codes", []) if str(code).strip()}),
                "provisional": bool(item.get("provisional", False)),
                "source": str(item.get("source") or "Power BI").strip(),
            })
        return result

    def save_suppliers(self, suppliers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority_codes = {item["uu"] for item in PRIORITY_SUPPLIERS}
        custom = self._clean_suppliers(suppliers, priority_codes)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps({"version": 1, "custom": custom}, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get_supplier_cache()

    def delete_supplier(self, uu: str) -> list[dict[str, Any]]:
        """Remove one user-managed UU mapping; built-in mappings are immutable."""
        target = str(uu or "").strip()
        if not target or target in {item["uu"] for item in PRIORITY_SUPPLIERS}:
            return self.get_supplier_cache()
        try:
            loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
            custom = loaded.get("custom", []) if isinstance(loaded, dict) else []
        except (OSError, ValueError):
            custom = []
        return self.save_suppliers([item for item in custom if str(item.get("uu") or "").strip() != target])

    def search_suppliers(self, term: str) -> list[dict[str, Any]]:
        query_term = str(term or "").strip()
        if len(query_term) < 2:
            raise PowerBIError("Enter at least two characters to search suppliers.")
        tokens = re.findall(r"[A-Z0-9]+", self._normalize(query_term))
        tokens = tokens or [self._normalize(query_term)]
        token_conditions = []
        for token in tokens:
            escaped = self._dax_text(token)
            token_conditions.append(
                "(" + " || ".join([
                    f"CONTAINSSTRING(UPPER('Supplier - Codes'[SupplierHierarchyUU]), {escaped})",
                    f"CONTAINSSTRING(UPPER('Supplier - Codes'[SupplierHierarchyGU]), {escaped})",
                    f"CONTAINSSTRING(UPPER('Supplier - Codes'[SupplierHierarchyS]), {escaped})",
                ]) + ")"
            )
        match_expression = " && ".join(token_conditions)
        dax = f"""EVALUATE
TOPN(
    {MAX_SEARCH_ROWS},
    FILTER(
        SUMMARIZECOLUMNS(
            'Supplier - Codes'[SupplierHierarchyUU],
            'Supplier - Codes'[SupplierHierarchyGU],
            'Supplier - Codes'[SupplierHierarchyS]
        ),
        {match_expression}
    ),
    'Supplier - Codes'[SupplierHierarchyUU], ASC,
    'Supplier - Codes'[SupplierHierarchyGU], ASC,
    'Supplier - Codes'[SupplierHierarchyS], ASC
)"""
        response = self._run_json(
            ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
        )
        grouped: dict[str, dict[str, Any]] = {}
        for row in self._rows(response):
            uu_name, uu = self._split_hierarchy_value(self._field(row, "SupplierHierarchyUU"))
            gu_name, gu = self._split_hierarchy_value(self._field(row, "SupplierHierarchyGU"))
            sap_name, sap = self._split_hierarchy_value(self._field(row, "SupplierHierarchyS"))
            # A match in SU/GU is useful only when it can be resolved to the
            # canonical UU. Never create a lower-level pseudo supplier.
            if not uu:
                continue
            item = grouped.setdefault(uu, {"uu": uu, "official_name": uu_name or uu, "gu": gu, "sap_codes": set(), "matches": set()})
            if uu_name and not item["official_name"]:
                item["official_name"] = uu_name
            if gu and not item["gu"]:
                item["gu"] = gu
            if sap:
                item["sap_codes"].add(sap)
            for name in (uu_name, gu_name, sap_name):
                if name and self._score(query_term, name) >= 0.35:
                    item["matches"].add(name)
        results = []
        for item in grouped.values():
            names = [item["official_name"], *sorted(item["matches"])]
            score = max(self._score(query_term, name) for name in names)
            results.append({
                "alias": item["official_name"],
                "official_name": item["official_name"],
                "uu": item["uu"],
                "gu": item["gu"],
                "sap_codes": sorted(item["sap_codes"]),
                "matches": sorted(item["matches"]),
                "score": round(score, 3),
                "source": "Power BI",
            })
        return sorted(results, key=lambda value: (-value["score"], value["official_name"].upper()))[:100]

    def validate_supplier_cache(self) -> dict[str, Any]:
        suppliers = self.get_supplier_cache()
        codes = [item["uu"] for item in suppliers if item.get("uu")]
        if not codes:
            return {"checked": 0, "valid": [], "invalid": []}
        code_filter = " || ".join(
            f"CONTAINSSTRING('Supplier - Codes'[SupplierHierarchyUU], {self._dax_text(code)})"
            for code in codes
        )
        dax = f"""EVALUATE
SELECTCOLUMNS(
    FILTER(
        VALUES('Supplier - Codes'[SupplierHierarchyUU]),
        {code_filter}
    ),
    "SupplierHierarchyUU", 'Supplier - Codes'[SupplierHierarchyUU]
)"""
        response = self._run_json(
            ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
        )
        found = {
            self._split_hierarchy_value(self._field(row, "SupplierHierarchyUU"))[1]
            or str(self._field(row, "SupplierHierarchyUU") or "").strip()
            for row in self._rows(response)
        }
        valid = [item for item in suppliers if item["uu"] in found]
        invalid = [item for item in suppliers if item["uu"] not in found]
        return {"checked": len(suppliers), "valid": valid, "invalid": invalid}

    def management_hierarchy(self) -> list[dict[str, Any]]:
        levels = [f"Management Unit L{index} Name" for index in range(1, 7)]
        columns = ",\n".join(f"    'Cost Centre'[{self._dax_text(level)[1:-1]}]" for level in levels)
        dax = f"""EVALUATE
SUMMARIZECOLUMNS(
{columns},
    "Commitment Value EUR", 'Measure'[Commitment Value EUR],
    "Goods Received Value EUR", 'Measure'[Goods Received Value EUR]
)"""
        response = self._run_json(
            ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
            timeout=120,
        )
        paths = []
        seen: set[tuple[str, ...]] = set()
        for row in self._rows(response):
            values = tuple(str(self._field(row, level) or "").strip() for level in levels)
            if values in seen or not any(values):
                continue
            seen.add(values)
            paths.append({f"l{index}": value for index, value in enumerate(values, start=1)})
        return paths

    def _get_json(self, arguments: list[str], timeout: float = 90.0) -> dict[str, Any]:
        """Run a GET-style Power BI API call and parse its JSON response."""
        raw = self._run(arguments, timeout=timeout)
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            raise PowerBIError("Power BI helper returned an invalid response.")
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise PowerBIError("Power BI helper returned an unreadable response.") from exc

    def _purchase_family_column(self) -> tuple[str, str]:
        """Discover the Purchase Family L4 column from dataset metadata.

        ExecuteQueries datasets do not expose the Push API ``/tables`` endpoint.
        ``INFO.VIEW.COLUMNS()`` is the supported metadata query for this
        semantic model. The result is cached for the process lifetime.
        """
        if self._discovered_family_column:
            return self._discovered_family_column
        try:
            response = self._run_json(
                ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
                {"queries": [{"query": "EVALUATE INFO.VIEW.COLUMNS()"}], "serializerSettings": {"includeNulls": True}},
                timeout=120,
            )
            candidates = []
            for row in self._rows(response):
                table_name = str(self._field(row, "Table") or "").strip()
                column_name = str(self._field(row, "Name") or "").strip()
                hidden = str(self._field(row, "IsHidden") or "").casefold() == "true"
                if hidden or not table_name or not column_name:
                    continue
                if table_name.casefold() == PURCHASE_FAMILY_TABLE.casefold() and column_name.casefold() == PURCHASE_FAMILY_COLUMN.casefold():
                    candidates.append((0, table_name, column_name))
                elif _PF_TABLE_PATTERN.search(table_name) and _PF_COLUMN_PATTERN.search(column_name):
                    candidates.append((1, table_name, column_name))
            if candidates:
                _, table_name, column_name = sorted(candidates)[0]
                self._discovered_family_column = (table_name, column_name)
                return self._discovered_family_column
        except PowerBIError:
            pass
        return (PURCHASE_FAMILY_TABLE, PURCHASE_FAMILY_COLUMN)

    def purchase_families(self) -> dict[str, Any]:
        """Purchase Family values grouped under their Procurement Team parent."""
        table, column = self._purchase_family_column()
        column_ref = f"'{table}'[{column}]"
        l1_ref = f"'{PURCHASE_FAMILY_L1_TABLE}'[{PURCHASE_FAMILY_L1_COLUMN}]"
        dax = f"EVALUATE\nSUMMARIZECOLUMNS({l1_ref}, {column_ref})"
        response = self._run_json(
            ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
            timeout=120,
        )
        groups: dict[str, set[str]] = {}
        names: set[str] = set()
        for row in self._rows(response):
            family = str(self._field(row, column) or "").strip()
            if not family:
                continue
            names.add(family)
            parent = str(self._field(row, PURCHASE_FAMILY_L1_COLUMN) or "").strip() or "Unassigned"
            groups.setdefault(parent, set()).add(family)
        hierarchy = [
            {"name": parent, "families": [{"name": name} for name in sorted(families)]}
            for parent, families in sorted(groups.items(), key=lambda item: item[0].casefold())
        ]
        return {
            "families": [{"name": name} for name in sorted(names)],
            "hierarchy": hierarchy,
            "column": column_ref,
            "hierarchy_column": l1_ref,
        }

    def last_preview_diagnostics(self) -> dict[str, Any] | None:
        """Return the most recent preview request without credentials or rows."""
        return self._last_preview_diagnostics

    def po_creation_date_range(self) -> dict[str, str | None]:
        """Return the confirmed minimum and maximum PO creation dates."""
        dax = """EVALUATE
ROW(
    "Min PO Creation Date", MIN('PurchaseOrder_Allocated'[PO Creation Date]),
    "Max PO Creation Date", MAX('PurchaseOrder_Allocated'[PO Creation Date])
)"""
        response = self._run_json(
            ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
            timeout=120,
        )
        rows = self._rows(response)
        if not rows:
            return {"min_date": None, "max_date": None}
        row = rows[0]
        return {
            "min_date": self._normalize_powerbi_date(self._field(row, "Min PO Creation Date")),
            "max_date": self._normalize_powerbi_date(self._field(row, "Max PO Creation Date")),
        }

    @staticmethod
    def _public_po_column(item: dict[str, Any]) -> dict[str, Any]:
        public_keys = {
            "key", "label", "group", "semantic_group", "source", "table",
            "table_label", "column", "measure", "aggregation", "type",
            "measure_table", "data_type", "default", "required", "hidden",
        }
        return {key: value for key, value in item.items() if key in public_keys}

    @staticmethod
    def _metadata_column_key(table_name: str, column_name: str) -> str:
        identity = f"{table_name}\x00{column_name}"
        safe = re.sub(r"[^a-z0-9]+", "_", identity.lower()).strip("_")
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
        return f"dataset_{safe}_{digest}"

    @staticmethod
    def _metadata_column_type(column: dict[str, Any]) -> str:
        value = str(column.get("dataType") or column.get("type") or "").lower()
        if "date" in value or "time" in value:
            return "date"
        if any(token in value for token in ("int", "decimal", "double", "float", "numeric", "currency")):
            return "number"
        if "bool" in value:
            return "boolean"
        return "text"

    @staticmethod
    def _metadata_measure_key(table_name: str, measure_name: str) -> str:
        identity = f"{table_name}\x00{measure_name}"
        safe = re.sub(r"[^a-z0-9]+", "_", identity.lower()).strip("_")
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
        return f"measure_{safe}_{digest}"

    def _metadata_column_spec(
        self,
        table: dict[str, Any],
        column: dict[str, Any],
        static_by_source: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, Any] | None:
        table_name = str(table.get("name") or "").strip()
        column_name = str(column.get("name") or "").strip()
        if not table_name or not column_name:
            return None
        source_key = (table_name.casefold(), column_name.casefold())
        static = static_by_source.get(source_key, {})
        table_label = str(table.get("displayName") or table_name).strip()
        return {
            **static,
            "key": static.get("key") or self._metadata_column_key(table_name, column_name),
            "label": str(static.get("label") or column.get("displayName") or column_name).strip(),
            "group": table_label,
            "semantic_group": static.get("group") or "",
            "source": f"{table_name}[{column_name}]",
            "table": table_name,
            "table_label": table_label,
            "column": column_name,
            "type": static.get("type") or self._metadata_column_type(column),
            "data_type": str(column.get("dataType") or column.get("type") or "").strip(),
            "default": bool(static.get("default")),
            "required": bool(static.get("required")),
            "hidden": bool(column.get("isHidden", column.get("hidden", False))),
        }

    def _discover_po_columns(self) -> list[dict[str, Any]]:
        tables_response = self._get_json(
            ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/tables", "-X", "get"],
            timeout=60,
        )
        tables = [table for table in tables_response.get("value") or [] if isinstance(table, dict)]
        if not tables:
            raise PowerBIError("Power BI returned no dataset tables.")

        static_by_source = {
            (str(item.get("table")).casefold(), str(item.get("column")).casefold()): item
            for item in POWERBI_PO_COLUMNS
            if item.get("table") and item.get("column")
        }
        static_by_measure = {
            str(item.get("measure")).casefold(): item
            for item in POWERBI_PO_COLUMNS
            if item.get("measure")
        }
        discovered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for table in tables:
            table_name = str(table.get("name") or "").strip()
            if not table_name:
                continue
            column_items = table.get("columns")
            if not isinstance(column_items, list) or not column_items:
                columns_response = self._get_json(
                    [
                        "api", "-A", "powerbi",
                        f"datasets/{DATASET_ID}/tables/{quote(table_name, safe='')}/columns",
                        "-X", "get",
                    ],
                    timeout=60,
                )
                column_items = columns_response.get("value") or []
            for column in column_items:
                if not isinstance(column, dict):
                    continue
                spec = self._metadata_column_spec(table, column, static_by_source)
                if spec is None or spec["key"] in seen:
                    continue
                seen.add(spec["key"])
                discovered.append(spec)

            for measure in table.get("measures") or []:
                if not isinstance(measure, dict):
                    continue
                measure_name = str(measure.get("name") or "").strip()
                if not measure_name:
                    continue
                static = static_by_measure.get(measure_name.casefold(), {})
                key = static.get("key") or self._metadata_measure_key(table_name, measure_name)
                if key in seen:
                    continue
                seen.add(key)
                table_label = str(table.get("displayName") or table_name).strip()
                discovered.append({
                    **static,
                    "key": key,
                    "label": str(measure.get("displayName") or static.get("label") or measure_name).strip(),
                    "group": table_label,
                    "semantic_group": static.get("group") or "Measures",
                    "source": f"{table_name}[{measure_name}]",
                    "table": table_name,
                    "table_label": table_label,
                    "measure": measure_name,
                    "measure_table": table_name,
                    "type": static.get("type") or "number",
                    "data_type": "measure",
                    "default": bool(static.get("default")),
                    "required": bool(static.get("required")),
                    "hidden": bool(measure.get("isHidden", measure.get("hidden", False))),
                })

        if not discovered:
            raise PowerBIError("Power BI returned no dataset columns.")

        # Measures and confirmed calculated fields are not always exposed by
        # the table-columns endpoint, so retain the existing safe fallbacks.
        for item in POWERBI_PO_COLUMNS:
            if item["key"] not in seen:
                discovered.append(dict(item))
        return discovered

    def discover_po_columns(self) -> list[dict[str, Any]]:
        """Refresh the PO catalog from dataset tables and their columns."""
        try:
            columns = self._discover_po_columns()
            self.set_po_columns(columns)
            self._po_columns_source = "metadata"
        except PowerBIError:
            # ponytail: retain the confirmed catalog when metadata access is unavailable.
            self.set_po_columns(list(POWERBI_PO_COLUMNS))
            self._po_columns_source = "provider-fallback"
        return self.active_po_columns()

    def set_po_columns(self, columns: list[dict[str, Any]]) -> None:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in columns:
            if not isinstance(raw, dict) or not raw.get("key"):
                continue
            key = str(raw["key"])
            if key in seen:
                continue
            base = dict(POWERBI_PO_COLUMN_BY_KEY.get(key, {}))
            base.update(raw)
            if key == "supplier_uu":
                # This field is intentionally presented as the normalized UU
                # name. The raw semantic-model value also contains the UU code.
                base["label"] = "Supplier UU"
            normalized.append(base)
            seen.add(key)
        if not normalized:
            normalized = [dict(item) for item in POWERBI_PO_COLUMNS]
            seen = {item["key"] for item in normalized}
        for key in POWERBI_DOWNLOAD_FOLDER_COLUMNS:
            if key not in seen and key in POWERBI_PO_COLUMN_BY_KEY:
                normalized.append(dict(POWERBI_PO_COLUMN_BY_KEY[key]))
        self._po_columns = normalized
        self._po_column_by_key = {item["key"]: item for item in normalized}
        self._default_po_columns = tuple(
            item["key"] for item in normalized if item.get("default") or item.get("required")
        )

    def active_po_columns(self) -> list[dict[str, Any]]:
        return [self._public_po_column(item) for item in self._po_columns]

    def po_columns_source(self) -> str:
        return self._po_columns_source

    @staticmethod
    def po_columns() -> list[dict[str, Any]]:
        """Return the safe, user-facing inventory for the PO dataset."""
        return [PowerBIProvider._public_po_column(item) for item in POWERBI_PO_COLUMNS]

    @staticmethod
    def _dax_reference(table: str, column: str) -> str:
        table_name = str(table).replace("'", "''")
        column_name = str(column).replace("]", "]]")
        return f"'{table_name}'[{column_name}]"

    def _selected_po_columns(self, columns: list[str] | None) -> list[dict[str, Any]]:
        requested = self._default_po_columns if columns is None else columns
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        unknown: list[str] = []
        for key in requested:
            normalized = str(key).strip()
            if normalized in seen:
                continue
            spec = self._po_column_by_key.get(normalized)
            if spec is None:
                unknown.append(normalized)
                continue
            seen.add(normalized)
            selected.append(spec)
        if unknown:
            raise PowerBIError(f"Unsupported PO dataset column(s): {', '.join(unknown)}")
        if "po_number" not in seen:
            selected.insert(0, self._po_column_by_key.get("po_number", POWERBI_PO_COLUMN_BY_KEY["po_number"]))
        return selected

    @staticmethod
    def _normalize_powerbi_date(value: Any) -> str | None:
        if value is None or str(value).strip() in {"", "None", "NaT"}:
            return None
        text = str(value).strip()
        if len(text) == 8 and text.isdigit():
            try:
                return datetime.strptime(text, "%Y%m%d").date().isoformat()
            except ValueError:
                return text
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return text[:10] if len(text) >= 10 else text
        return parsed.date().isoformat()

    @staticmethod
    def _period_ranges(periods: list[str] | None) -> list[tuple[date, date]]:
        """Normalize year/quarter/month selections to merged date ranges."""
        ranges: list[tuple[date, date]] = []
        for raw in periods or []:
            value = str(raw or "").strip().upper()
            try:
                if len(value) == 4 and value.isdigit():
                    start = date(int(value), 1, 1)
                    end = date(int(value) + 1, 1, 1)
                elif len(value) == 7 and value[4] == "-" and value[5:].isdigit():
                    year, month = int(value[:4]), int(value[5:])
                    if not 1 <= month <= 12:
                        continue
                    start = date(year, month, 1)
                    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
                elif len(value) == 7 and value[4] == "-" and value[5] == "Q" and value[6].isdigit():
                    year, quarter = int(value[:4]), int(value[6])
                    if not 1 <= quarter <= 4:
                        continue
                    month = (quarter - 1) * 3 + 1
                    start = date(year, month, 1)
                    end = date(year + (quarter == 4), 1 if quarter == 4 else month + 3, 1)
                else:
                    continue
            except ValueError:
                continue
            ranges.append((start, end))
        ranges.sort()
        merged: list[tuple[date, date]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _dax_date(value: date) -> str:
        # The semantic model exposes PO Creation Date as an integer (YYYYMMDD),
        # not as a DAX date value.
        return f"{value.year:04d}{value.month:02d}{value.day:02d}"

    @classmethod
    def _preview_value(cls, row: dict[str, Any], spec: dict[str, Any]) -> Any:
        field_names = [
            spec.get("source"),
            spec.get("column"),
            spec.get("measure"),
            spec.get("label"),
        ]
        value = None
        for field_name in field_names:
            if not field_name:
                continue
            value = cls._field(row, field_name)
            if value is not None:
                break
        if spec["key"] == "supplier_uu":
            return cls._split_hierarchy_value(value)[0]
        if spec["key"].startswith("supplier_"):
            return cls._split_hierarchy_value(value)[1]
        if spec.get("type") == "date":
            return cls._normalize_powerbi_date(value)
        return value

    def preview_pos(
        self,
        year: str,
        uu_codes: list[str],
        management_paths: list[dict[str, Any]] | None = None,
        columns: list[str] | None = None,
        date_periods: list[str] | None = None,
        family_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        uu_codes = sorted({str(code).strip() for code in uu_codes if str(code).strip()})
        selected_columns = self._selected_po_columns(columns)
        selected_keys = {str(spec.get("key") or "") for spec in selected_columns}
        for key in POWERBI_DOWNLOAD_FOLDER_COLUMNS:
            if key not in selected_keys and key in self._po_column_by_key:
                selected_columns.append(self._po_column_by_key[key])
        ranges = self._period_ranges(date_periods)
        if not ranges and year:
            ranges = self._period_ranges([str(year)])
        query_ranges = ranges or [None]
        families = sorted({str(name or "").strip() for name in (family_names or []) if str(name or "").strip()})
        paths = management_paths or []
        self._last_preview_diagnostics = {
            "source": "Power BI PO Mass Download Dataset",
            "dataset_id": DATASET_ID,
            "filters": {
                "supplier_uu_codes": uu_codes,
                "management_unit_paths": paths,
                "po_creation_periods": [str(period) for period in (date_periods or [])],
                "date_ranges": [
                    {"start": start.isoformat(), "end_exclusive": end.isoformat()}
                    for start, end in ranges
                ],
                "purchase_families": families,
            },
            "selected_columns": [
                {"key": spec["key"], "source": spec.get("source")}
                for spec in selected_columns
            ],
            "queries": [],
        }
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for date_range in query_ranges:
            filters = []
            if date_range:
                start, end = date_range
                reference = self._dax_reference("PurchaseOrder_Allocated", "PO Creation Date")
                filters.append(f"FILTER(VALUES({reference}), {reference} >= {self._dax_date(start)} && {reference} < {self._dax_date(end)})")
            elif year:
                filters.append(f"TREATAS({{{self._dax_text(str(year))}}}, 'Time'[Year])")
            if uu_codes:
                code_filter = " || ".join(
                    f"CONTAINSSTRING('Supplier - Codes'[SupplierHierarchyUU], {self._dax_text(code)})"
                    for code in uu_codes
                )
                filters.append(f"FILTER(VALUES('Supplier - Codes'[SupplierHierarchyUU]), {code_filter})")
            if paths:
                tuples = []
                for path in paths:
                    tuples.append("(" + ", ".join(self._dax_value(path.get(f"l{index}")) for index in range(1, 7)) + ")")
                filters.append("TREATAS({" + ", ".join(tuples) + "}, 'Cost Centre'[Management Unit L1 Name], 'Cost Centre'[Management Unit L2 Name], 'Cost Centre'[Management Unit L3 Name], 'Cost Centre'[Management Unit L4 Name], 'Cost Centre'[Management Unit L5 Name], 'Cost Centre'[Management Unit L6 Name])")
            if families:
                family_table, family_column = self._purchase_family_column()
                family_ref = f"'{family_table}'[{family_column}]"
                family_values = ", ".join(self._dax_text(name) for name in families)
                filters.append(f"TREATAS({{{family_values}}}, {family_ref})")
            filter_text = ",\n        " + ",\n        ".join(filters) if filters else ""
            group_columns: list[str] = []
            expressions: list[str] = []
            for spec in selected_columns:
                if spec.get("aggregation"):
                    reference = self._dax_reference(spec["table"], spec["column"])
                    expressions.append(f'    "{spec["label"]}", {spec["aggregation"]}({reference})')
                elif spec.get("column"):
                    reference = self._dax_reference(spec["table"], spec["column"])
                    if reference not in group_columns:
                        group_columns.append(reference)
                elif spec.get("measure"):
                    measure_table = spec.get("measure_table") or spec.get("table") or "Measure"
                    expressions.append(f'    "{spec["measure"]}", {self._dax_reference(measure_table, spec["measure"])}')
            query_columns = ",\n".join(f"    {reference}" for reference in group_columns)
            query_expressions = ",\n" + ",\n".join(expressions) if expressions else ""
            dax = f"""EVALUATE
SUMMARIZECOLUMNS(
{query_columns}{filter_text}{query_expressions}
)"""
            request_body = {
                "queries": [{"query": dax}],
                "serializerSettings": {"includeNulls": True},
            }
            query_diagnostic = {
                "date_range": {
                    "start": date_range[0].isoformat(),
                    "end_exclusive": date_range[1].isoformat(),
                } if date_range else None,
                "request": request_body,
                "rows_returned": None,
            }
            self._last_preview_diagnostics["queries"].append(query_diagnostic)
            try:
                response = self._run_json(
                    ["api", "-A", "powerbi", f"datasets/{DATASET_ID}/executeQueries", "-X", "post", "-H", "content-type=application/json"],
                    request_body,
                    timeout=120,
                )
            except PowerBIError as exc:
                query_diagnostic["error"] = str(exc)
                raise
            rows = self._rows(response)
            query_diagnostic["rows_returned"] = len(rows)
            if len(rows) > MAX_PREVIEW_ROWS:
                period_label = f" for {date_range[0].isoformat()} to {date_range[1].isoformat()}" if date_range else ""
                raise PowerBIError(f"The preview returned more than {MAX_PREVIEW_ROWS} rows{period_label}. Narrow the filters or choose smaller date periods.")
            for row in rows:
                normalized = {spec["key"]: self._preview_value(row, spec) for spec in selected_columns}
                for key in POWERBI_DOWNLOAD_FOLDER_COLUMNS:
                    if normalized.get(key) is None:
                        normalized.pop(key, None)
                identity = json.dumps(normalized, sort_keys=True, default=str)
                if identity not in seen:
                    seen.add(identity)
                    output.append(normalized)
        return output
