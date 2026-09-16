"""Local timesheet loader and small aggregate model for the GUI tab."""

from __future__ import annotations

import datetime
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


TIMESHEET_SHEET = "Resource Timesheet"

SUPPLIER_ALIASES = {
    "Accenture": ("accenture",),
    "Infosys": ("infosys",),
    "Deloitte": ("deloitte",),
    "EY / Ernst & Young": ("ernst & young", "ernst and young", "ey"),
    "Fractal": ("fractal",),
    "TCS / Tata Consultancy Services": ("tata consultancy", "tcs"),
    "NTT Data": ("ntt data", "nippon telegraph"),
    "Capgemini": ("capgemini",),
    "Cognizant": ("cognizant",),
    "LTI Mindtree / Larsen & Toubro": ("lti mindtree", "mindtree", "larsen & toubro"),
}


class TimesheetError(RuntimeError):
    """Safe, user-facing timesheet error."""


class TimesheetProvider:
    def __init__(self) -> None:
        self.last_analysis: dict[str, Any] | None = None

    @staticmethod
    def _slug(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    @staticmethod
    def _fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _column(columns: list[Any], *names: str) -> str | None:
        wanted = {TimesheetProvider._slug(name) for name in names}
        for column in columns:
            if TimesheetProvider._slug(column) in wanted:
                return str(column)
        return None

    @staticmethod
    def _number(series: pd.Series) -> pd.Series:
        return pd.to_numeric(
            series.astype(str)
            .str.replace("€", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip(),
            errors="coerce",
        ).fillna(0.0)

    @classmethod
    def _infer_supplier(cls, title: Any) -> str:
        value = cls._slug(title)
        for supplier, aliases in SUPPLIER_ALIASES.items():
            if any(cls._slug(alias) in value for alias in aliases):
                return supplier
        return "Unknown"

    @staticmethod
    def _date(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        if isinstance(value, (int, float)) or re.fullmatch(r"\d+(?:\.\d+)?", str(value).strip()):
            serial = float(value)
            if 20000 <= serial <= 60000:
                return (pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")).strftime("%Y-%m-%d")
        if isinstance(value, (datetime.datetime, datetime.date, pd.Timestamp)):
            return pd.Timestamp(value).strftime("%Y-%m-%d")
        return str(value).strip()

    @classmethod
    def _read_frame(cls, path: Path) -> tuple[pd.DataFrame, str]:
        extension = path.suffix.lower()
        if extension == ".csv":
            return pd.read_csv(path, dtype=object), "CSV"
        if extension not in {".xlsb", ".xlsx", ".xlsm", ".xls"}:
            raise TimesheetError("Select an .xlsb, .xlsx, .xlsm or .csv timesheet file.")
        try:
            engine = "pyxlsb" if extension == ".xlsb" else None
            workbook = pd.ExcelFile(path, engine=engine)
            sheet = next((name for name in workbook.sheet_names if cls._slug(name) == cls._slug(TIMESHEET_SHEET)), None)
            if not sheet:
                sheet = next((name for name in workbook.sheet_names if "timesheet" in cls._slug(name)), None)
            if not sheet:
                raise TimesheetError(f"The workbook does not contain a {TIMESHEET_SHEET} sheet.")
            return pd.read_excel(workbook, sheet_name=sheet, dtype=object), str(sheet)
        except TimesheetError:
            raise
        except ImportError as exc:
            raise TimesheetError(".xlsb support is unavailable in this build. Install the pyxlsb dependency.") from exc
        except Exception as exc:
            raise TimesheetError(f"Could not read the timesheet workbook: {exc}") from exc

    @classmethod
    def _normalize(cls, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
        if frame.empty:
            raise TimesheetError("The selected timesheet sheet is empty.")
        columns = [str(column) for column in frame.columns]
        pwo_column = cls._column(columns, "PWO", "PWO Number", "Project Work Order")
        billing_column = cls._column(columns, "Billing Type", "Contract Type", "Billing")
        bill_rate_column = cls._column(columns, "Actual Bill Rate", "Bill Rate")
        title_column = cls._column(columns, "Title", "Project Title", "SOW Title")
        resource_column = cls._column(columns, "Resource Name", "Resource", "Employee")
        period_column = cls._column(columns, "Period Start Date", "Period", "Date")
        days_column = cls._column(columns, "Days", "Day")
        fees_column = cls._column(columns, "Fees", "Fee", "Amount")
        level_column = cls._column(columns, "Level", "Resource Level")
        supplier_column = cls._column(columns, "Supplier", "Vendor", "Supplier Name")
        required = {"PWO": pwo_column, "Days": days_column, "Fees": fees_column}
        missing = [name for name, column in required.items() if not column]
        if missing:
            raise TimesheetError("Missing required timesheet columns: " + ", ".join(missing))

        result = pd.DataFrame(index=frame.index)
        result["pwo"] = frame[pwo_column].fillna("").astype(str).str.strip()
        result["billing_type"] = frame[billing_column].fillna("").astype(str).str.strip() if billing_column else ""
        result["bill_rate"] = frame[bill_rate_column].fillna("").astype(str).str.strip() if bill_rate_column else ""
        result["title"] = frame[title_column].fillna("").astype(str).str.strip() if title_column else ""
        result["resource_name"] = frame[resource_column].fillna("").astype(str).str.strip() if resource_column else ""
        result["period_start"] = frame[period_column].map(cls._date) if period_column else ""
        result["level"] = frame[level_column].fillna("").astype(str).str.strip() if level_column else ""
        result["days"] = cls._number(frame[days_column])
        result["fees"] = cls._number(frame[fees_column])
        if supplier_column:
            supplied = frame[supplier_column].fillna("").astype(str).str.strip()
            result["supplier"] = supplied.where(supplied != "", result["title"].map(cls._infer_supplier))
        else:
            result["supplier"] = result["title"].map(cls._infer_supplier)

        billing = result["billing_type"].str.lower()
        fixed_signal = "fixed price"
        fixed_mask = (
            billing.str.contains(fixed_signal, na=False)
            | result["bill_rate"].str.lower().str.contains(fixed_signal, na=False)
            | result["resource_name"].str.lower().str.contains(fixed_signal, na=False)
            | result["level"].str.lower().str.contains(fixed_signal, na=False)
        )
        known_mask = result["billing_type"].str.strip() != ""
        result["classification"] = "classification_pending"
        result.loc[fixed_mask, "classification"] = "fixed_price"
        result.loc[known_mask & ~fixed_mask, "classification"] = "tm"
        return result, {
            "supplier_column": supplier_column,
            "fixed_price_signal_column": bill_rate_column or billing_column,
            "supplier_inferred": not bool(supplier_column),
            "source_rows": int(len(result)),
        }

    @classmethod
    def _aggregate_rows(cls, frame: pd.DataFrame) -> list[dict[str, Any]]:
        usable = frame[frame["pwo"] != ""].copy()
        if usable.empty:
            return []
        grouped = usable.groupby(
            ["supplier", "pwo", "billing_type", "classification"],
            dropna=False,
            sort=True,
        )
        rows: list[dict[str, Any]] = []
        for (supplier, pwo, billing_type, classification), group in grouped:
            periods = [value for value in group["period_start"].tolist() if value]
            resources = sorted({value for value in group["resource_name"].tolist() if value})
            titles = sorted({value for value in group["title"].tolist() if value})
            rows.append({
                "supplier": str(supplier or "Unknown"),
                "pwo": str(pwo),
                "billing_type": str(billing_type),
                "classification": str(classification),
                "row_count": int(len(group)),
                "resource_count": len(resources),
                "resources": resources[:20],
                "title": " | ".join(titles[:3]),
                "period_start": min(periods) if periods else "",
                "period_end": max(periods) if periods else "",
                "days": round(float(group["days"].sum()), 4),
                "fees": round(float(group["fees"].sum()), 2),
            })
        return rows

    @staticmethod
    def _summary(rows: list[dict[str, Any]], source_rows: int, unmapped_rows: int) -> dict[str, Any]:
        tm = [row for row in rows if row["classification"] == "tm"]
        fixed = [row for row in rows if row["classification"] == "fixed_price"]
        pending = [row for row in rows if row["classification"] == "classification_pending"]
        suppliers = sorted({row["supplier"] for row in rows})
        return {
            "source_rows": int(source_rows),
            "mapped_rows": int(sum(row["row_count"] for row in rows)),
            "unmapped_pwo_rows": int(unmapped_rows),
            "pwo_count": len({row["pwo"] for row in rows}),
            "tm_rows": int(sum(row["row_count"] for row in tm)),
            "tm_pwo_count": len({row["pwo"] for row in tm}),
            "tm_days": round(sum(row["days"] for row in tm), 4),
            "tm_fees": round(sum(row["fees"] for row in tm), 2),
            "resource_assignments": int(sum(row["resource_count"] for row in tm)),
            "fixed_price_rows": int(sum(row["row_count"] for row in fixed)),
            "fixed_price_pwo_count": len({row["pwo"] for row in fixed}),
            "classification_pending_rows": int(sum(row["row_count"] for row in pending)),
            "classification_pending_pwo_count": len({row["pwo"] for row in pending}),
            "supplier_count": len(suppliers),
            "suppliers": suppliers,
        }

    @classmethod
    def _filtered(cls, analysis: dict[str, Any], supplier: str = "", scope: str = "tm") -> dict[str, Any]:
        rows = list(analysis.get("rows") or [])
        wanted_supplier = str(supplier or "").strip()
        if wanted_supplier:
            rows = [row for row in rows if row.get("supplier") == wanted_supplier]
        normalized_scope = str(scope or "tm").strip().lower()
        if normalized_scope == "tm":
            rows = [row for row in rows if row.get("classification") == "tm"]
        elif normalized_scope == "exceptions":
            rows = [row for row in rows if row.get("classification") != "tm"]
        result = dict(analysis)
        result["rows"] = rows
        result["filters"] = {"supplier": wanted_supplier, "scope": normalized_scope}
        full_summary = analysis.get("summary") or {}
        result["available_suppliers"] = list(full_summary.get("suppliers") or [])
        result["exception_summary"] = {
            "fixed_price_pwo_count": int(full_summary.get("fixed_price_pwo_count") or 0),
            "classification_pending_pwo_count": int(full_summary.get("classification_pending_pwo_count") or 0),
            "unmapped_pwo_rows": int(full_summary.get("unmapped_pwo_rows") or 0),
        }
        result["summary"] = cls._summary(
            rows,
            sum(int(row.get("row_count") or 0) for row in rows),
            0,
        )
        result["summary"]["unmapped_pwo_rows"] = 0
        result["reconciliation"] = {
            "status": "pending_mapping",
            "label": "Pending PWO / invoice linkage",
            "message": "The source does not yet expose a confirmed PWO-to-PO/invoice key.",
        }
        return result

    def load(self, path_value: str) -> dict[str, Any]:
        path = Path(str(path_value or "")).expanduser().resolve()
        if not path.is_file():
            raise TimesheetError("The selected timesheet file was not found.")
        frame, sheet = self._read_frame(path)
        normalized, metadata = self._normalize(frame)
        rows = self._aggregate_rows(normalized)
        analysis = {
            "source": {
                "path": str(path),
                "name": path.name,
                "sha256": self._fingerprint(path),
                "sheet": sheet,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            },
            "metadata": metadata,
            "rows": rows,
            "summary": self._summary(rows, len(normalized), int((normalized["pwo"] == "").sum())),
            "filters": {"supplier": "", "scope": "tm"},
            "reconciliation": {
                "status": "pending_mapping",
                "label": "Pending PWO / invoice linkage",
                "message": "The source does not yet expose a confirmed PWO-to-PO/invoice key.",
            },
        }
        self.last_analysis = analysis
        return self._filtered(analysis)

    def filter(self, analysis: dict[str, Any] | None, supplier: str = "", scope: str = "tm") -> dict[str, Any]:
        if not analysis:
            raise TimesheetError("No timesheet snapshot is available. Load a workbook first.")
        self.last_analysis = analysis
        return self._filtered(analysis, supplier, scope)
