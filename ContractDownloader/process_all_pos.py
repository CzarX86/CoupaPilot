import hashlib
import os
import sys
import asyncio
import time
import argparse
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
import pandas as pd
from src.db.session_db import SessionDB
from src.db.coupa_metadata import CoupaMetadataRepository
from src.engine.crawler import CoupaCrawler
from src.reports.coupa_excel import enrich_excel_report
from src.reports.attachment_relationships import build_attachment_relationships
from src.auth import AuthService, AuthState
from src.engine.msg_converter import find_msg_files, MsgToPdfConverter
from src.engine.input_schema import canonicalize_po_value, clean_scalar, detect_csv_separator, detect_po_parts, is_excel_numeric_coercion, is_placeholder_po, is_placeholder_supplier, is_valid_canonical_po, normalize_po_value, normalize_supplier_value

# CSV alongside this script (or override via INPUT_CSV env var)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.environ.get("INPUT_CSV", os.path.join(_SCRIPT_DIR, "input.csv"))
DOWNLOAD_DIR = os.path.expanduser("~/Downloads/CoupaAttachments")
DB_PATH = os.path.expanduser("~/.contract_downloader/cli_sessions.db")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process Coupa POs and download attachments")
    parser.add_argument(
        "--retry-last-errors",
        action="store_true",
        help="Create a new session with only ERROR rows from latest session",
    )
    parser.add_argument(
        "--download-root",
        default=DOWNLOAD_DIR,
        help="Base download directory (default: ~/Downloads/CoupaAttachments)",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Use this exact run directory instead of creating a timestamped directory",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=11,
        help="Concurrent downloads (1-11, default: 11)",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=None,
        help="Total attempts per PO (1-3; GUI settings may override)",
    )
    parser.add_argument(
        "--retry-session-id",
        type=int,
        default=None,
        help="Optional source session id for retry mode (uses latest with ERROR if omitted)",
    )
    parser.add_argument(
        "--retry-po",
        default=None,
        help="Retry one PO in a new session, preserving valid files",
    )
    parser.add_argument(
        "--retry-in-place-po",
        default=None,
        help="Retry one PO without creating a new session id",
    )
    parser.add_argument(
        "--retry-in-place-errors",
        action="store_true",
        help="Retry ERROR/SKIPPED rows in the existing session",
    )
    parser.add_argument(
        "--retry-in-place-supplier",
        default=None,
        help="Retry eligible rows for one supplier in the existing session",
    )
    parser.add_argument(
        "--provisional-retry",
        action="store_true",
        help="Run an edited PO in staging until the GUI commits or discards it",
    )
    parser.add_argument(
        "--retry-attempt-id",
        type=int,
        default=None,
        help="Provisional retry attempt id",
    )
    parser.add_argument(
        "--retry-staging-dir",
        default=None,
        help="Temporary directory for provisional retry files",
    )
    parser.add_argument(
        "--retry-incomplete-session-id",
        type=int,
        default=None,
        help="Retry only PENDING+ERROR rows from a specific interrupted session",
    )
    parser.add_argument(
        "--resume-in-place-session-id",
        type=int,
        default=None,
        help="Resume PENDING+ERROR rows in the existing session and preserve cumulative progress",
    )
    parser.add_argument(
        "--disable-circuit-breaker",
        action="store_true",
        help="Disable company-level circuit breaker and process 100%% of rows",
    )
    parser.add_argument(
        "--skip-msg-to-pdf",
        action="store_true",
        help="Skip automatic conversion of downloaded .msg files into .pdf",
    )
    parser.add_argument(
        "--overwrite-msg-pdf",
        action="store_true",
        help="Overwrite existing generated PDF files for .msg conversion",
    )
    parser.add_argument(
        "--msg-processing",
        choices=["disabled", "convert", "convert_extract"],
        default=None,
        help="MSG handling: disabled, convert to PDF, or convert and extract attachments",
    )
    parser.add_argument(
        "--deduplicate-files",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Identify identical files by SHA-256 and create hard-link/reference duplicates",
    )
    parser.add_argument(
        "--execution-type",
        choices=["AUTO", "PROD", "TEST"],
        default="AUTO",
        help="Session classification for retention policy (default: AUTO)",
    )
    return parser.parse_args()


def _detect_execution_type_from_name(name: str) -> str:
    text = (name or "").lower()
    test_tokens = ["test", "sample", "random", "probe", "debug"]
    return "TEST" if any(token in text for token in test_tokens) else "PROD"


def resolve_execution_type(args: argparse.Namespace, input_name: str, source_session_id: int | None = None, db: SessionDB | None = None) -> str:
    choice = (args.execution_type or "AUTO").upper()
    if choice in {"PROD", "TEST"}:
        return choice

    if source_session_id and db is not None:
        return db.get_session_execution_type(source_session_id)

    return _detect_execution_type_from_name(input_name)


def build_run_download_dir(download_root: str, mode: str, run_dir: str | None = None) -> str:
    if run_dir:
        resolved = os.path.abspath(os.path.expanduser(run_dir))
        os.makedirs(resolved, exist_ok=True)
        return resolved
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resolved = os.path.join(os.path.expanduser(download_root), f"run_{stamp}_{mode}")
    os.makedirs(resolved, exist_ok=True)
    return resolved


def _detect_csv_encoding(filepath: str) -> str:
    raw = Path(filepath).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _read_csv_text(filepath: str) -> str:
    path = Path(filepath)
    return path.read_bytes().decode(_detect_csv_encoding(filepath), errors="replace")


def detect_separator(filepath: str) -> str:
    sample = _read_csv_text(filepath)[:8192]
    return detect_csv_separator(sample)


def read_input_dataframe(filepath: str) -> pd.DataFrame:
    """Read the same CSV/XLSX input in the CLI and GUI workflows."""
    path = Path(filepath)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return pd.read_excel(path, sheet_name=0, dtype=str).fillna("")
    if suffix == ".xls":
        return pd.read_excel(path, sheet_name=0, dtype=str).fillna("")
    return pd.read_csv(
        path,
        sep=detect_separator(str(path)),
        dtype=str,
        encoding=_detect_csv_encoding(str(path)),
        skip_blank_lines=False,
    ).fillna("")


def _clean_folder_part(value: str) -> str:
    cleaned = str(value or "").strip()
    if cleaned.lower() in {"", "nan", "none"}:
        cleaned = "Unknown"
    cleaned = cleaned.replace("/", "_").replace("\\", "_")
    cleaned = "_".join(cleaned.split())
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("._")
    if len(cleaned) > 120:
        digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:10]
        cleaned = f"{cleaned[:108].rstrip('_')}_{digest}"
    return cleaned or "Unknown"


def _extract_hierarchy_columns(
    df: pd.DataFrame,
    requested_order: list[str] | None = None,
    supplier_column: str | None = None,
) -> tuple[list[str], bool]:
    sep_col = None
    for c in df.columns:
        if str(c).strip() == "<|>":
            sep_col = c
            break

    cols = [str(c) for c in df.columns]
    supplier_name = str(supplier_column or next(
        (column for column in cols if column.casefold() == "supplier"),
        "SUPPLIER",
    ))
    if sep_col is not None:
        sep_idx = cols.index(str(sep_col))
        optional_cols = cols[sep_idx + 1 :]
    elif requested_order is not None:
        # Non-standard inputs without the <|> separator: every column is a
        # hierarchy candidate; the GUI decides which ones to enable.
        optional_cols = [column for column in cols if column != supplier_name]
    else:
        # Plain CLI input without <|> and without an explicit order keeps the
        # classic behavior: only the supplier folder level is created.
        return [supplier_name] if supplier_name in cols else [], supplier_name in cols

    if requested_order is not None:
        # Explicit user order wins: these are exactly the columns the GUI
        # enabled, including Supplier wherever the user placed it.
        available = [supplier_name, *optional_cols] if supplier_name in cols else optional_cols
        allowed = {column.casefold(): column for column in available}
        requested = []
        seen = set()
        for column in requested_order:
            key = str(column).casefold()
            if key in allowed and key not in seen:
                requested.append(allowed[key])
                seen.add(key)
        hierarchy_cols = requested
    else:
        hierarchy_cols = [supplier_name, *optional_cols] if supplier_name in cols else optional_cols
    if not hierarchy_cols:
        return [], False

    # A column that is 100% empty in the input cannot drive folder creation.
    # The GUI still reports it as a warning; the pipeline simply ignores it.
    populated = []
    for col in hierarchy_cols:
        series = df[col].fillna("").astype(str).str.strip()
        series = series[(series != "") & (series.str.lower() != "nan")]
        if not series.empty:
            populated.append(col)
    if not populated:
        return hierarchy_cols, False
    return populated, True


def _build_output_subdir(
    row: pd.Series,
    supplier: str,
    hierarchy_cols: list[str],
    has_hierarchy_data: bool,
    supplier_column: str | None = None,
) -> str:
    # The PO itself is never a subdir part (it is the file level). When the
    # caller supplies an explicit hierarchy, Supplier is already in that list
    # at the position selected by the user.
    levels = hierarchy_cols if has_hierarchy_data and hierarchy_cols else []
    supplier_key = str(supplier_column or "SUPPLIER").casefold()
    if supplier_column is None and levels and not any(str(column).casefold() == supplier_key for column in levels):
        # Keep compatibility for direct callers that pass only optional levels.
        levels = [None, *levels]
    if not levels:
        levels = [None]

    parts = []
    seen_parts = set()
    for column in levels:
        value = supplier if column is None or str(column).casefold() == supplier_key else row.get(column, "")
        part = _clean_folder_part(value)
        if part.casefold() in seen_parts:
            continue
        parts.append(part)
        seen_parts.add(part.casefold())
    return PurePosixPath(*parts).as_posix()


def build_output_subdir_map_from_csv(input_csv: str) -> dict[str, str]:
    if not input_csv or not os.path.exists(input_csv):
        return {}

    from src.engine.input_schema import parse_mapping_env

    df = read_input_dataframe(input_csv)
    mapping = parse_mapping_env() or {}
    po_name = mapping.get("po") or "PO_NUMBER"
    supplier_name = mapping.get("supplier") or "SUPPLIER"
    hierarchy_order = None
    if os.environ.get("COUPA_HIERARCHY_ORDER"):
        try:
            hierarchy_order = json.loads(os.environ["COUPA_HIERARCHY_ORDER"])
        except json.JSONDecodeError:
            hierarchy_order = None
    hierarchy_cols, has_hierarchy_data = _extract_hierarchy_columns(df, hierarchy_order, supplier_name)
    po_to_subdir: dict[str, str] = {}

    for _, row in df.iterrows():
        po = clean_scalar(row.get(po_name, ""))
        supplier = clean_scalar(row.get(supplier_name, ""))
        po_key = normalize_po_value(po)
        if po_key and supplier:
            po_to_subdir[po_key] = _build_output_subdir(row, supplier, hierarchy_cols, has_hierarchy_data, supplier_name)
    return po_to_subdir


def list_attachment_names(download_folder: str) -> str:
    if not isinstance(download_folder, (str, os.PathLike)):
        return ""
    if not download_folder or not os.path.isdir(download_folder):
        return ""
    names = [
        name
        for name in sorted(os.listdir(download_folder))
        if os.path.isfile(os.path.join(download_folder, name))
    ]
    return " | ".join(names)


def export_original_like_excel_report(
    db: SessionDB,
    session_id: int,
    report_path: str,
    input_csv: str | None = None,
) -> str:
    cursor = db.conn.cursor()
    rows = cursor.execute(
        """
        SELECT po_number, company_code, status, attachment_count, error_message, remarks, download_folder, updated_at,
               expected_company_code, expected_legal_entity, access_diagnosis
        FROM po_downloads
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()

    db_df = pd.DataFrame([dict(r) for r in rows])
    if db_df.empty:
        db_df = pd.DataFrame(
            columns=[
                "po_number",
                "company_code",
                "status",
                "attachment_count",
                "error_message",
                "remarks",
                "download_folder",
                "updated_at",
                "expected_company_code",
                "expected_legal_entity",
                "access_diagnosis",
            ]
        )

    db_df["attachment_count"] = db_df["attachment_count"].fillna(0).astype(int)
    db_df["AttachmentName"] = db_df["download_folder"].apply(list_attachment_names)
    db_df["ATTACHMENTS_FOUND"] = db_df["attachment_count"]
    db_df["ATTACHMENTS_DOWNLOADED"] = db_df.apply(
        lambda r: r["attachment_count"] if str(r["status"]).upper() == "SUCCESS" else 0,
        axis=1,
    )
    db_df["STATUS"] = db_df["status"]
    db_df["ERROR_MESSAGE"] = db_df["error_message"].fillna("")
    db_df["REMARKS"] = db_df["remarks"].fillna("")
    db_df["DOWNLOAD_FOLDER"] = db_df["download_folder"].fillna("")
    db_df["LAST_PROCESSED"] = db_df["updated_at"].fillna("")
    db_df["EXPECTED_COMPANY_CODE"] = db_df["expected_company_code"].fillna(db_df["company_code"])
    db_df["EXPECTED_LEGAL_ENTITY"] = db_df["expected_legal_entity"].fillna("")
    db_df["ACCESS_DIAGNOSIS"] = db_df["access_diagnosis"].fillna("")
    db_df["COUPA_URL"] = db_df["po_number"].apply(
        lambda po: f"https://unilever.coupahost.com/order_headers/{str(po)[2:]}"
        if str(po).upper().startswith(("PO", "PM"))
        else f"https://unilever.coupahost.com/order_headers/{po}"
    )

    report_cols = {
        "po_number": "PO_NUMBER",
        "company_code": "SUPPLIER",
        "STATUS": "STATUS",
        "ATTACHMENTS_FOUND": "ATTACHMENTS_FOUND",
        "ATTACHMENTS_DOWNLOADED": "ATTACHMENTS_DOWNLOADED",
        "AttachmentName": "AttachmentName",
        "LAST_PROCESSED": "LAST_PROCESSED",
        "ERROR_MESSAGE": "ERROR_MESSAGE",
        "REMARKS": "REMARKS",
        "DOWNLOAD_FOLDER": "DOWNLOAD_FOLDER",
        "COUPA_URL": "COUPA_URL",
        "EXPECTED_COMPANY_CODE": "EXPECTED_COMPANY_CODE",
        "EXPECTED_LEGAL_ENTITY": "EXPECTED_LEGAL_ENTITY",
        "ACCESS_DIAGNOSIS": "ACCESS_DIAGNOSIS",
    }
    mapped = db_df[list(report_cols.keys())].rename(columns=report_cols)

    if input_csv and os.path.exists(input_csv):
        source_df = read_input_dataframe(input_csv)
        if "PO_NUMBER" in source_df.columns:
            source_df["PO_NUMBER"] = source_df["PO_NUMBER"].astype(str).str.strip()

        merged = source_df.merge(
            mapped,
            on="PO_NUMBER",
            how="left",
            suffixes=("", "_NEW"),
        )

        for col in [
            "STATUS",
            "ATTACHMENTS_FOUND",
            "ATTACHMENTS_DOWNLOADED",
            "AttachmentName",
            "LAST_PROCESSED",
            "ERROR_MESSAGE",
            "REMARKS",
            "DOWNLOAD_FOLDER",
            "COUPA_URL",
        ]:
            new_col = f"{col}_NEW"
            if new_col in merged.columns:
                merged[col] = merged[new_col].fillna(merged.get(col, ""))
                merged = merged.drop(columns=[new_col])

        if "SUPPLIER_NEW" in merged.columns:
            if "SUPPLIER" in merged.columns:
                merged["SUPPLIER"] = merged["SUPPLIER"].replace("", pd.NA).fillna(merged["SUPPLIER_NEW"])
                merged["SUPPLIER"] = merged["SUPPLIER"].fillna("")
            merged = merged.drop(columns=["SUPPLIER_NEW"])

        out_df = merged
    else:
        out_df = mapped.copy()
        out_df.insert(3, "Legal Entity", out_df["SUPPLIER"])
        out_df["<|>"] = ""

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    out_df.to_excel(report_path, index=False)
    try:
        metadata_repository = CoupaMetadataRepository(db)
        enrich_excel_report(
            report_path,
            metadata_repository.list_po_metadata(session_id),
            metadata_repository.list_line_metadata(session_id),
        )
    except Exception as metadata_error:
        # The attachment report remains usable even if metadata enrichment
        # fails; the error is visible in the CLI log for support diagnostics.
        print(f"[REPORT][COUPA_METADATA][ERROR] {metadata_error}")
    relationships = build_attachment_relationships(db.list_po_attachments(session_id))
    if relationships:
        with pd.ExcelWriter(report_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            pd.DataFrame(relationships).to_excel(writer, sheet_name="ATTACHMENT_RELATIONSHIPS", index=False)
    return report_path


def create_session_from_csv(
    db: SessionDB,
    input_csv: str,
    execution_type: str = "PROD",
    hierarchy_order: list[str] | None = None,
    po_column: str | None = None,
    supplier_column: str | None = None,
    description: str | None = None,
    source_metadata: dict | None = None,
) -> tuple[int, int]:
    cursor = db.conn.cursor()
    df = read_input_dataframe(input_csv)
    po_name = po_column or "PO_NUMBER"
    supplier_name = supplier_column or "SUPPLIER"
    hierarchy_cols, has_hierarchy_data = _extract_hierarchy_columns(df, hierarchy_order, supplier_name)
    session_id = db.create_session(
        os.path.basename(input_csv),
        execution_type=execution_type,
        description=description or None,
        source_metadata=source_metadata,
    )

    company_column = next((column for column in ("COMPANY_CODE", "POWERBI_COMPANY_CODE") if column in df.columns), None)
    legal_entity_column = next((column for column in ("LEGAL_ENTITY_NAME", "LEGAL_ENTITY_CODE") if column in df.columns), None)
    count = 0
    seen_suppliers: dict[str, str] = {}
    for _, row in df.iterrows():
        po = clean_scalar(row.get(po_name, ""))
        company = clean_scalar(row.get(supplier_name, ""))
        expected_company = clean_scalar(row.get(company_column, "")) if company_column else company
        expected_legal_entity = clean_scalar(row.get(legal_entity_column, "")) if legal_entity_column else ""
        if detect_po_parts(po)["multiple"] or detect_po_parts(po)["ambiguous"]:
            raise ValueError(f"Multiple or ambiguous PO values in input cell: {po}")
        po = canonicalize_po_value(po)
        if not is_valid_canonical_po(po):
            raise ValueError(f"Invalid PO value: {po}")
        po_key = normalize_po_value(po)
        supplier_key = normalize_supplier_value(company)
        if not po_key or not company:
            continue
        if is_placeholder_po(po) or is_excel_numeric_coercion(po) or is_placeholder_supplier(company):
            cursor.execute("DELETE FROM po_downloads WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            db.conn.commit()
            raise ValueError(f"Invalid PO value: {po}")
        previous_supplier = seen_suppliers.get(po_key)
        if previous_supplier is not None and previous_supplier != supplier_key:
            cursor.execute("DELETE FROM po_downloads WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            db.conn.commit()
            raise ValueError(f"PO {po} is linked to multiple Suppliers.")
        if previous_supplier is not None:
            continue
        output_subdir = _build_output_subdir(row, company, hierarchy_cols, has_hierarchy_data, supplier_name)
        cursor.execute(
            "INSERT OR IGNORE INTO po_downloads (session_id, po_number, company_code, output_subdir, status, expected_company_code, expected_legal_entity, supplier_name) VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)",
            (session_id, po, expected_company or company, output_subdir, expected_company or company, expected_legal_entity, company),
        )
        if cursor.rowcount:
            count += 1
            seen_suppliers[po_key] = supplier_key
    db.conn.commit()
    return session_id, count


def create_retry_session_from_last_errors(
    db: SessionDB,
    input_csv: str | None = None,
    source_session_id: int | None = None,
    execution_type: str = "PROD",
) -> tuple[int, int, int]:
    cursor = db.conn.cursor()

    if source_session_id is None:
        latest_row = cursor.execute(
            """
            SELECT s.id
            FROM sessions s
            WHERE EXISTS (
                SELECT 1 FROM po_downloads p
                WHERE p.session_id = s.id AND p.status = 'ERROR'
            )
            ORDER BY s.id DESC
            LIMIT 1
            """
        ).fetchone()
    else:
        latest_row = cursor.execute(
            """
            SELECT s.id
            FROM sessions s
            WHERE s.id = ?
            """,
            (source_session_id,),
        ).fetchone()
    if not latest_row:
        return 0, 0, 0

    source_session_id = int(latest_row["id"])
    error_rows = cursor.execute(
        "SELECT po_number, company_code, supplier_name, output_subdir FROM po_downloads WHERE session_id = ? AND status = 'ERROR' ORDER BY id ASC",
        (source_session_id,),
    ).fetchall()
    if not error_rows:
        return source_session_id, 0, 0

    po_to_subdir = build_output_subdir_map_from_csv(input_csv) if input_csv else {}

    session_id = db.create_session(f"retry_errors_from_{source_session_id}", execution_type=execution_type)
    for row in error_rows:
        output_subdir = row["output_subdir"]
        if (not output_subdir) and po_to_subdir:
            output_subdir = po_to_subdir.get(normalize_po_value(row["po_number"]), "")
        cursor.execute(
            "INSERT OR IGNORE INTO po_downloads (session_id, po_number, company_code, output_subdir, status, supplier_name) VALUES (?, ?, ?, ?, 'PENDING', ?)",
            (session_id, row["po_number"], row["company_code"], output_subdir, row["supplier_name"]),
        )
    db.conn.commit()
    return source_session_id, session_id, len(error_rows)


def prepare_in_place_retry(
    db: SessionDB,
    session_id: int,
    po_number: str | None = None,
    errors_only: bool = False,
    supplier: str | None = None,
) -> int:
    cursor = db.conn.cursor()
    if po_number:
        rows = cursor.execute(
            "SELECT po_number, status FROM po_downloads WHERE session_id = ? AND po_number = ?",
            (session_id, canonicalize_po_value(po_number)),
        ).fetchall()
    elif supplier:
        statuses = ("ERROR", "SKIPPED_VERIFICATION_REQUIRED") if errors_only else ("PENDING", "ERROR", "SKIPPED_VERIFICATION_REQUIRED")
        placeholders = ",".join("?" for _ in statuses)
        rows = cursor.execute(
            f"SELECT po_number, status FROM po_downloads WHERE session_id = ? AND COALESCE(NULLIF(supplier_name, ''), company_code) = ? AND status IN ({placeholders})",
            (session_id, supplier.strip(), *statuses),
        ).fetchall()
    else:
        statuses = ("ERROR", "SKIPPED_VERIFICATION_REQUIRED") if errors_only else ("PENDING", "ERROR", "SKIPPED_VERIFICATION_REQUIRED")
        placeholders = ",".join("?" for _ in statuses)
        rows = cursor.execute(
            f"SELECT po_number, status FROM po_downloads WHERE session_id = ? AND status IN ({placeholders})",
            (session_id, *statuses),
        ).fetchall()
    for row in rows:
        cursor.execute(
            "INSERT INTO retry_events (session_id, po_number, status_before) VALUES (?, ?, ?)",
            (session_id, row["po_number"], row["status"]),
        )
        cursor.execute(
            "UPDATE po_downloads SET status = 'PENDING', error_message = NULL, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE session_id = ? AND po_number = ?",
            (session_id, row["po_number"]),
        )
    db.conn.commit()
    return len(rows)


def create_retry_session_for_po(
    db: SessionDB,
    po_number: str,
    source_session_id: int | None = None,
    input_csv: str | None = None,
    execution_type: str = "PROD",
) -> tuple[int, int, int]:
    cursor = db.conn.cursor()
    normalized_po = canonicalize_po_value(po_number)
    if source_session_id is None:
        source_row = cursor.execute(
            "SELECT session_id FROM po_downloads WHERE po_number = ? ORDER BY session_id DESC LIMIT 1",
            (normalized_po,),
        ).fetchone()
    else:
        source_row = cursor.execute(
            "SELECT session_id FROM po_downloads WHERE session_id = ? AND po_number = ?",
            (source_session_id, normalized_po),
        ).fetchone()
    if not source_row:
        return 0, 0, 0

    source_session_id = int(source_row["session_id"])
    row = cursor.execute(
        "SELECT po_number, company_code, output_subdir FROM po_downloads WHERE session_id = ? AND po_number = ?",
        (source_session_id, normalized_po),
    ).fetchone()
    if not row:
        return source_session_id, 0, 0

    output_subdir = row["output_subdir"]
    if not output_subdir and input_csv:
        output_subdir = build_output_subdir_map_from_csv(input_csv).get(normalized_po, "")
    session_id = db.create_session(
        f"retry_po_{normalized_po}_from_{source_session_id}",
        execution_type=execution_type,
    )
    cursor.execute(
        "INSERT INTO po_downloads (session_id, po_number, company_code, output_subdir, status) VALUES (?, ?, ?, ?, 'PENDING')",
        (session_id, row["po_number"], row["company_code"], output_subdir),
    )
    db.conn.commit()
    return source_session_id, session_id, 1


def create_retry_session_from_incomplete(
    db: SessionDB,
    source_session_id: int,
    input_csv: str | None = None,
    execution_type: str = "PROD",
) -> tuple[int, int, int]:
    cursor = db.conn.cursor()

    exists = cursor.execute("SELECT 1 FROM sessions WHERE id = ?", (source_session_id,)).fetchone()
    if not exists:
        return 0, 0, 0

    rows = cursor.execute(
        """
        SELECT po_number, company_code, output_subdir
        FROM po_downloads
        WHERE session_id = ? AND status IN ('PENDING', 'ERROR')
        ORDER BY id ASC
        """,
        (source_session_id,),
    ).fetchall()
    if not rows:
        return source_session_id, 0, 0

    po_to_subdir = build_output_subdir_map_from_csv(input_csv) if input_csv else {}
    session_id = db.create_session(f"retry_incomplete_from_{source_session_id}", execution_type=execution_type)
    for row in rows:
        output_subdir = row["output_subdir"]
        if (not output_subdir) and po_to_subdir:
            output_subdir = po_to_subdir.get(normalize_po_value(row["po_number"]), "")
        cursor.execute(
            "INSERT OR IGNORE INTO po_downloads (session_id, po_number, company_code, output_subdir, status) VALUES (?, ?, ?, ?, 'PENDING')",
            (session_id, row["po_number"], row["company_code"], output_subdir),
        )
    db.conn.commit()
    return source_session_id, session_id, len(rows)


async def main():
    args = parse_args()
    args.concurrency = max(1, min(11, int(args.concurrency)))
    configured_retries = os.environ.get("COUPA_RETRY_ATTEMPTS")
    args.retry_attempts = max(1, min(3, int(configured_retries or args.retry_attempts or 1)))
    args.msg_processing = args.msg_processing or os.environ.get("COUPA_MSG_PROCESSING", "convert_extract")
    args.deduplicate_files = args.deduplicate_files if args.deduplicate_files is not None else os.environ.get("COUPA_DEDUPLICATE_FILES", "1") != "0"
    powerbi_source = False

    if not (args.retry_last_errors or args.retry_incomplete_session_id is not None or args.retry_po or args.retry_in_place_po or args.retry_in_place_errors or args.retry_in_place_supplier or args.provisional_retry) and not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Input file not found: {INPUT_CSV}")
        sys.exit(1)

    # --- Authentication ---
    auth_service = AuthService()
    interactive_auth = os.environ.get("COUPA_AUTH_INTERACTIVE", "1").strip().lower() not in {"0", "false", "no"}
    browser_preference = os.environ.get("COUPA_AUTH_BROWSER", "auto")
    auth_status = lambda state, message: print(f"[AUTH] {message}")
    auth_result = await auth_service.ensure_session(
        interactive=interactive_auth,
        browser_preference=browser_preference,
        status_callback=auth_status if interactive_auth else None,
    )
    cookies = dict(auth_result.cookies) if auth_result.cookies else None
    if auth_result.state is AuthState.VALID:
        print("[AUTH] Coupa session is valid.\n")
    elif auth_result.state is AuthState.UNAVAILABLE and cookies:
        print("[AUTH][WARNING] Coupa session could not be verified; keeping cached cookies and continuing.")
    elif auth_result.state is AuthState.EXPIRED:
        print("[AUTH] Cached session expired. Sign-in is required.")
    if not cookies:
        if not interactive_auth:
            print("[AUTH][ERROR] Authentication is required before the GUI pipeline can start.")
            raise SystemExit(3)
        print("[AUTH][ERROR] Coupa authentication did not produce a usable session.")
        raise SystemExit(3)

    db = SessionDB(DB_PATH)

    mode = "full"
    report_source_csv = INPUT_CSV
    source_session_id: int | None = None
    if args.provisional_retry:
        if not args.retry_attempt_id or not args.retry_session_id or not args.retry_staging_dir:
            print("[ERROR] Provisional retry requires attempt, session, and staging ids.")
            db.close()
            return
        attempt = db.conn.execute(
            "SELECT * FROM retry_attempts WHERE id = ? AND session_id = ? AND status = 'RUNNING'",
            (args.retry_attempt_id, args.retry_session_id),
        ).fetchone()
        if not attempt:
            print("[ERROR] Provisional retry attempt was not found or is no longer active.")
            db.close()
            return
        source_session_id = int(args.retry_session_id)
        session_id = source_session_id
        mode = "provisional_retry"
        run_type = resolve_execution_type(
            args,
            input_name=f"provisional_retry_{attempt['edited_po_number']}",
            source_session_id=source_session_id,
            db=db,
        )
        print(
            f"[INFO] Provisional retry: session={session_id}, "
            f"{attempt['original_po_number']} -> {attempt['edited_po_number']}, type={run_type}"
        )
    elif args.resume_in_place_session_id is not None:
        source_session_id = args.resume_in_place_session_id
        run_type = resolve_execution_type(
            args,
            input_name=f"resume_in_place_{source_session_id}",
            source_session_id=source_session_id,
            db=db,
        )
        session_id = source_session_id
        mode = "resume_in_place"
        pending_count = db.conn.execute(
            "SELECT COUNT(*) FROM po_downloads WHERE session_id = ? AND status IN ('PENDING', 'ERROR')",
            (session_id,),
        ).fetchone()[0]
        if not pending_count:
            print(f"[INFO] Session {session_id} has no pending or failed POs to resume.")
            db.close()
            return
        # Keep the previous SUCCESS/ERROR rows in this same session. The
        # worker retries ERROR rows directly, allowing the GUI to retain the
        # cumulative progress denominator and counters.
        print(f"[INFO] In-place resume: session={session_id}, pending_or_failed={pending_count}, type={run_type}")
    elif args.retry_in_place_po or args.retry_in_place_errors or args.retry_in_place_supplier:
        source_session_id = args.retry_session_id
        if not source_session_id:
            print("[ERROR] --retry-session-id is required for in-place retry.")
            db.close()
            return
        run_type = resolve_execution_type(
            args,
            input_name=f"retry_in_place_{source_session_id}",
            source_session_id=source_session_id,
            db=db,
        )
        count = prepare_in_place_retry(
            db,
            source_session_id,
            po_number=args.retry_in_place_po,
            errors_only=args.retry_in_place_errors,
            supplier=args.retry_in_place_supplier,
        )
        if count == 0:
            print(f"[INFO] Session {source_session_id} has no POs eligible for retry.")
            db.close()
            return
        session_id = source_session_id
        mode = "retry_in_place"
        # The report belongs to this same session and must be updated in place.
        # The archived input is selected again after the archive step below so
        # retries keep every original column in the existing workbook.
        print(f"[INFO] In-place retry: session={session_id}, POs={count}, type={run_type}")
    elif args.retry_po:
        run_type = resolve_execution_type(
            args,
            input_name=f"retry_po_{args.retry_po}",
            source_session_id=args.retry_session_id,
            db=db,
        )
        source_session_id, session_id, count = create_retry_session_for_po(
            db,
            po_number=args.retry_po,
            source_session_id=args.retry_session_id,
            input_csv=INPUT_CSV,
            execution_type=run_type,
        )
        if source_session_id == 0 or session_id == 0 or count == 0:
            print(f"[ERROR] PO {args.retry_po} was not found in the source session.")
            db.close()
            return
        mode = "retry_po"
        # Legacy CLI retry sessions still use the source schema for reporting;
        # the GUI uses the in-place path above to update the original workbook.
        print(f"[INFO] Single-PO retry: source_session={source_session_id}, PO={args.retry_po}, new_session={session_id}, type={run_type}")
    elif args.retry_incomplete_session_id is not None:
        run_type = resolve_execution_type(
            args,
            input_name=f"retry_incomplete_from_{args.retry_incomplete_session_id}",
            source_session_id=args.retry_incomplete_session_id,
            db=db,
        )
        source_session_id, session_id, count = create_retry_session_from_incomplete(
            db,
            source_session_id=args.retry_incomplete_session_id,
            input_csv=INPUT_CSV,
            execution_type=run_type,
        )
        if source_session_id == 0:
            print(f"[ERROR] Session {args.retry_incomplete_session_id} was not found.")
            db.close()
            sys.exit(1)
        if session_id == 0 or count == 0:
            print(f"[INFO] Session {source_session_id} has no pending or failed POs to resume.")
            db.close()
            return
        mode = "retry_incomplete"
        # Keep the source schema available when producing the retry report.
        print(f"[INFO] Incomplete-session retry: source_session={source_session_id}, pending_or_failed={count}, new_session={session_id}, type={run_type}")
    elif args.retry_last_errors:
        run_type = resolve_execution_type(
            args,
            input_name=f"retry_errors_from_{args.retry_session_id or 'latest'}",
            source_session_id=args.retry_session_id,
            db=db,
        )
        source_session_id, session_id, count = create_retry_session_from_last_errors(
            db,
            input_csv=INPUT_CSV,
            source_session_id=args.retry_session_id,
            execution_type=run_type,
        )
        if source_session_id == 0:
            print("[ERROR] No previous session was found for retry.")
            db.close()
            sys.exit(1)
        if session_id == 0 or count == 0:
            print(f"[INFO] Session {source_session_id} has no failed POs to retry.")
            db.close()
            return
        mode = "retry_errors"
        # Keep the source schema available when producing the retry report.
        print(f"[INFO] Failed-PO retry: source_session={source_session_id}, failed={count}, new_session={session_id}, type={run_type}")
    else:
        print(f"[INFO] Reading input: {INPUT_CSV}")
        run_type = resolve_execution_type(args, input_name=os.path.basename(INPUT_CSV))
        hierarchy_order = None
        if os.environ.get("COUPA_HIERARCHY_ORDER"):
            try:
                hierarchy_order = json.loads(os.environ["COUPA_HIERARCHY_ORDER"])
            except json.JSONDecodeError:
                hierarchy_order = None
        from src.engine.input_schema import parse_mapping_env
        column_mapping = parse_mapping_env() or {}
        from src.gui.api import AppAPI
        input_validation = AppAPI(db, args.download_root).validate_input_file(INPUT_CSV)
        if not input_validation.get("valid"):
            print("[ERROR] Input validation failed:")
            for validation_error in input_validation.get("errors", []):
                print(f"[ERROR] {validation_error}")
            db.close()
            sys.exit(2)
        column_mapping = input_validation.get("mapping") or column_mapping
        run_description = os.environ.get("COUPA_RUN_DESCRIPTION") or None
        source_metadata = None
        if os.environ.get("COUPA_SOURCE_METADATA"):
            try:
                parsed_metadata = json.loads(os.environ["COUPA_SOURCE_METADATA"])
                source_metadata = parsed_metadata if isinstance(parsed_metadata, dict) else None
            except json.JSONDecodeError:
                source_metadata = None
        powerbi_source = bool(
            source_metadata
            and source_metadata.get("source") == "Power BI PO Mass Download Dataset"
        )
        session_id, count = create_session_from_csv(
            db,
            INPUT_CSV,
            execution_type=run_type,
            hierarchy_order=hierarchy_order,
            po_column=column_mapping.get("po"),
            supplier_column=column_mapping.get("supplier"),
            description=run_description,
            source_metadata=source_metadata,
        )
        print(f"[INFO] {count} POs imported and queued for processing.")
        print(f"[INFO] Session type: {run_type}")

    run_download_dir = build_run_download_dir(args.download_root, mode, args.run_dir)
    db.conn.execute("UPDATE sessions SET concurrency = ? WHERE id = ?", (args.concurrency, session_id))
    db.conn.commit()
    archive_suffix = Path(INPUT_CSV).suffix or ".csv"
    archive_path = os.path.join(run_download_dir, f"input_source_{session_id}{archive_suffix}")
    if not args.provisional_retry:
        if os.path.exists(INPUT_CSV):
            db.archive_session_input(session_id, INPUT_CSV, archive_path)
        elif source_session_id:
            db.clone_session_input(source_session_id, session_id, archive_path)

    # Always build the workbook from the archived snapshot. For an in-place
    # retry this is the same session's source and the report path below is the
    # existing report, so the retry updates it instead of creating a reduced
    # second workbook.
    if os.path.exists(archive_path):
        report_source_csv = archive_path
    print(f"[INFO] Run folder: {run_download_dir}")
    if args.disable_circuit_breaker:
        print("[INFO] Circuit breaker disabled; processing every row.")

    cursor = db.conn.cursor()

    # --- Processing ---
    crawler = CoupaCrawler(
        db, session_id, run_download_dir,
        cookies=cookies,
        concurrency=args.concurrency,
        request_delay=0.03,
        enable_circuit_breaker=not args.disable_circuit_breaker,
        preserve_existing_files=bool(args.retry_po or args.retry_in_place_po or args.retry_in_place_errors or args.retry_in_place_supplier),
        cookie_store=auth_service.store,
    )

    resume_in_place = args.resume_in_place_session_id is not None
    status_filter = "status IN ('PENDING', 'ERROR')" if resume_in_place else "status = 'PENDING'"
    rows = cursor.execute(
        f"SELECT po_number, company_code, status, attachment_count FROM po_downloads WHERE session_id = ? AND {status_filter}",
        (session_id,),
    ).fetchall()

    company_pos: dict[str, list[str]] = {}
    for row in rows:
        company_pos.setdefault(str(row["company_code"] or ""), []).append(str(row["po_number"]))
    if company_pos and powerbi_source and not args.provisional_retry:
        print(f"[INFO] Checking Coupa access for {len(company_pos)} Company Code group(s)...", flush=True)
        try:
            access_checks = await crawler.preflight_company_access(company_pos)
            for company_code, check in access_checks.items():
                if check.get("confirmed"):
                    db.set_company_access_diagnosis(session_id, company_code, "ACCESS_DENIED_CONFIRMED")
                    db.suspend_company_code(session_id, company_code)
                    print(
                        f"[WARNING] Company Code {company_code}: access denied in {check['sampled']}/{check['sampled']} sample PO(s); queued POs were skipped.",
                        flush=True,
                    )
                elif check.get("denied"):
                    print(
                        f"[WARNING] Company Code {company_code}: mixed preflight result ({check['denied']} denied, {check['accessible']} accessible); processing POs individually.",
                        flush=True,
                    )
        except Exception as exc:
            print(f"[WARNING] Company Code preflight was inconclusive: {type(exc).__name__}: {exc}", flush=True)
        rows = cursor.execute(
            f"SELECT po_number, company_code, status, attachment_count FROM po_downloads WHERE session_id = ? AND {status_filter}",
            (session_id,),
        ).fetchall()

    pos_list = [(r["po_number"], r["company_code"]) for r in rows]
    all_rows = cursor.execute(
        "SELECT status, attachment_count FROM po_downloads WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    initial_success = sum(1 for row in all_rows if row["status"] == "SUCCESS")
    initial_errors = sum(1 for row in all_rows if row["status"] == "ERROR")
    initial_files = sum(int(row["attachment_count"] or 0) for row in all_rows if row["status"] == "SUCCESS")
    initial_status = {str(row["po_number"]): str(row["status"]) for row in rows}
    print(f"[INFO] Processing {len(pos_list)} POs with {crawler.concurrency} concurrent workers...\n")

    counters = {
        "done": initial_success + initial_errors if resume_in_place else 0,
        "ok": initial_success if resume_in_place else 0,
        "err": initial_errors if resume_in_place else 0,
        "files": initial_files if resume_in_place else 0,
    }
    total = len(all_rows) if resume_in_place else len(pos_list)
    start_ts = time.time()
    auth_pause = asyncio.Event()

    async def process_one(po_number, company_code):
        result = {"po": po_number, "success": False, "error": "No attempt completed"}
        for attempt in range(args.retry_attempts):
            result = await crawler.process_po(po_number, company_code)
            if result.get("auth_required"):
                auth_pause.set()
                print(
                    "[AUTH][PAUSED] Coupa rejected the HTTP session. Close Edge, recapture the work SSO session, then resume the pending POs.",
                    flush=True,
                )
                return result
            if result.get("success") or attempt == args.retry_attempts - 1:
                break
            await asyncio.sleep(min(5.0, 1.0 * (attempt + 1)))
        if not result.get("success"):
            print(
                f"[ERROR][PO {po_number}] {result.get('error') or 'Unknown error'} "
                f"[diagnostic_log={result.get('diagnostic_log') or crawler.diagnostic_log_path}]",
                flush=True,
            )
        previous_status = initial_status.get(str(po_number), "PENDING")
        if resume_in_place and previous_status == "ERROR":
            # An ERROR row was already counted before the pause. Retrying it
            # changes the outcome but must not advance the unique-PO counter.
            if result.get("success"):
                counters["ok"] += 1
                counters["err"] = max(0, counters["err"] - 1)
                counters["files"] += len(result.get("attachments", []))
        else:
            counters["done"] += 1
            if result.get("success"):
                counters["ok"] += 1
                counters["files"] += len(result.get("attachments", []))
            else:
                counters["err"] += 1
        done = counters["done"]
        if done % 25 == 0 or done == total:
            elapsed = time.time() - start_ts
            speed = done / elapsed * 60 if elapsed > 0 else 0
            remaining = total - done
            eta = int(remaining / (done / elapsed)) if done > 0 else 0
            print(
                f"[{done:>4}/{total}] ok={counters['ok']} err={counters['err']} "
                f"files={counters['files']}  speed={speed:.0f}/min  eta={eta//60}m{eta%60:02d}s",
                flush=True,
            )
        return result

    sem = asyncio.Semaphore(crawler.concurrency)

    async def bounded(po, co):
        async with sem:
            if auth_pause.is_set():
                return {"po": po, "success": False, "paused": True}
            return await process_one(po, co)

    try:
        results = await asyncio.gather(*[bounded(po, co) for po, co in pos_list], return_exceptions=True)
    except asyncio.CancelledError:
        # SIGINT is used by the GUI for a resumable pause. Cancellation is
        # expected here: completed rows are already committed and in-flight
        # rows remain PENDING for the reconciliation/resume session.
        await crawler.close()
        db.close()
        print("[INFO] Download pipeline interrupted safely; pending POs remain queued for resume.", flush=True)
        raise
    results = [r for r in results if not isinstance(r, BaseException)]
    if auth_pause.is_set():
        db.conn.execute(
            "UPDATE sessions SET status = 'RUN_PAUSED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        db.conn.commit()
        await crawler.close()
        db.close()
        print(
            "[RUN_PAUSED] Authentication is required. Completed POs were preserved; pending POs are ready to resume.",
            flush=True,
        )
        return
    if args.retry_in_place_po or args.retry_in_place_errors or args.retry_in_place_supplier:
        for result in results:
            po_value = str(result.get("po", ""))
            db.conn.execute(
                """
                UPDATE retry_events
                SET completed_at = CURRENT_TIMESTAMP,
                    status_after = (SELECT status FROM po_downloads WHERE session_id = ? AND po_number = ?),
                    error_message = ?
                WHERE id = (
                    SELECT id FROM retry_events
                    WHERE session_id = ? AND po_number = ? AND completed_at IS NULL
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (session_id, po_value, result.get("error"), session_id, po_value),
            )
        db.conn.commit()

    success = counters["ok"]
    failed = counters["err"]
    total_attachments = counters["files"]
    auth_fails = sum(1 for r in results if "Auth" in str(r.get("error", "")))
    rate_limits = sum(1 for r in results if "429" in str(r.get("error", "")))
    downloaded_files = sum(
        1 for r in results
        if r.get("success") and len(r.get("attachments", [])) > 0
    )

    if args.provisional_retry:
        attempt_status = "SUCCESS" if failed == 0 and success > 0 else "FAILED"
        first_error = next((str(r.get("error", "")) for r in results if not r.get("success")), None)
        db.conn.execute(
            "UPDATE retry_attempts SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (attempt_status, first_error, args.retry_attempt_id),
        )
        db.conn.commit()
        print(f"[INFO] Provisional retry finished with status: {attempt_status}")
        await crawler.close()
        db.close()
        return

    print(f"\n{'=' * 60}")
    print("  RESULT")
    print(f"  Success: {success} | Failed: {failed}")
    print(f"  POs with attachments: {downloaded_files}")
    print(f"  Total attachments: {total_attachments}")
    if auth_fails:
        print(f"  [WARNING] Authentication failures: {auth_fails}")
    if rate_limits:
        print(f"  [WARNING] Coupa rate limits (429): {rate_limits}")
    print(f"  Downloads: {run_download_dir}")
    print(f"{'=' * 60}")

    if not args.skip_msg_to_pdf and args.msg_processing != "disabled":
        try:
            msg_files = find_msg_files(Path(run_download_dir))
            if msg_files:
                converter = MsgToPdfConverter(
                    overwrite=args.overwrite_msg_pdf,
                    extract_attachments=args.msg_processing == "convert_extract",
                )
                summary = converter.convert_all(msg_files)
                print(
                    "[MSG2PDF] "
                    f"total={summary['total']} converted={summary['converted']} "
                    f"skipped={summary['skipped']} failed={summary['failed']}"
                )
                if summary["failed"]:
                    first_error = summary["errors"][0]
                    print(f"[MSG2PDF][WARNING] Example failure: {first_error['file']} -> {first_error['error']}")
            else:
                print("[MSG2PDF] No .msg files found for conversion")
        except Exception as e:
            print(f"[MSG2PDF][WARNING] MSG-to-PDF conversion failed: {e}")
    else:
        print("[MSG2PDF] MSG conversion disabled")

    if args.deduplicate_files:
        try:
            from src.engine.file_deduplicator import FileDeduplicator
            dedup_summary = FileDeduplicator().process_tree(Path(run_download_dir))
            print(
                "[DEDUP] "
                f"scanned={dedup_summary['scanned']} duplicates={dedup_summary['duplicates']} "
                f"hardlinks={dedup_summary['hardlinks']} references={dedup_summary['references']}"
            )
            if dedup_summary["errors"]:
                print(f"[DEDUP][WARNING] File-level failures: {len(dedup_summary['errors'])}")
        except Exception as e:
            print(f"[DEDUP][WARNING] Deduplication failed: {e}")

    report_path = os.path.join(run_download_dir, f"report_session_{session_id}.xlsx")
    try:
        saved_report = export_original_like_excel_report(
            db=db,
            session_id=session_id,
            report_path=report_path,
            input_csv=report_source_csv,
        )
        print(f"[REPORT] Excel report generated: {saved_report}")
    except Exception as e:
        print(f"[REPORT][ERROR] Excel report generation failed: {e}")

    db.conn.execute(
        "UPDATE sessions SET duration_seconds = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (max(0.0, time.time() - start_ts), session_id),
    )
    db.conn.commit()
    await crawler.close()
    db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        # Some frozen Python runtimes propagate SIGINT as CancelledError
        # instead of KeyboardInterrupt. A pause must not be reported as a
        # crashed pipeline or return exit code 1.
        print("\n[INFO] Run paused safely; pending POs remain queued for resume.", flush=True)
    except KeyboardInterrupt:
        print("\n[INFO] Run interrupted by the user (Ctrl+C).")
