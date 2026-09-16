import hashlib
import json
import shutil
import sqlite3
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

@dataclass
class PODownload:
    session_id: int
    po_number: str
    company_code: str
    status: str = "PENDING"
    output_subdir: Optional[str] = None
    download_folder: Optional[str] = None
    attachment_count: Optional[int] = 0
    error_message: Optional[str] = None
    expected_company_code: Optional[str] = None
    expected_legal_entity: Optional[str] = None
    access_diagnosis: Optional[str] = None
    supplier_name: Optional[str] = None

class SessionDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_file TEXT NOT NULL,
                execution_type TEXT DEFAULT 'PROD',
                concurrency INTEGER DEFAULT 4,
                duration_seconds REAL,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS retry_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                po_number TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status_before TEXT,
                status_after TEXT,
                error_message TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS po_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                po_number TEXT NOT NULL,
                company_code TEXT NOT NULL,
                output_subdir TEXT,
                status TEXT DEFAULT 'PENDING',
                download_folder TEXT,
                attachment_count INTEGER DEFAULT 0,
                error_message TEXT,
                remarks TEXT,
                expected_company_code TEXT,
                expected_legal_entity TEXT,
                access_diagnosis TEXT,
                supplier_name TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id),
                UNIQUE(session_id, po_number)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS retry_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                original_po_number TEXT NOT NULL,
                edited_po_number TEXT NOT NULL,
                staging_dir TEXT NOT NULL,
                status TEXT DEFAULT 'RUNNING',
                error_message TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS powerbi_management_hierarchy_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                paths_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS powerbi_po_columns_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                columns_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS powerbi_po_column_selection_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                columns_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timesheet_analysis_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                source_path TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        self._migrate()

        self.conn.commit()

    def _migrate(self):
        """Add columns that may be missing from existing databases."""
        cursor = self.conn.cursor()
        sessions_existing = {row[1] for row in cursor.execute("PRAGMA table_info(sessions)")}
        if "execution_type" not in sessions_existing:
            cursor.execute(
                "ALTER TABLE sessions ADD COLUMN execution_type TEXT DEFAULT 'PROD'"
            )
        for column, definition in {
            "concurrency": "INTEGER DEFAULT 4",
            "duration_seconds": "REAL",
            "input_file_path": "TEXT",
            "input_file_blob": "BLOB",
            "input_file_sha256": "TEXT",
            "input_file_size": "INTEGER",
            "description": "TEXT",
            "source_metadata_json": "TEXT",
        }.items():
            if column not in sessions_existing:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {column} {definition}")

        existing = {row[1] for row in cursor.execute("PRAGMA table_info(po_downloads)")}

        if "remarks" not in existing:
            cursor.execute("ALTER TABLE po_downloads ADD COLUMN remarks TEXT")
        if "attachment_count" not in existing:
            cursor.execute(
                "ALTER TABLE po_downloads ADD COLUMN attachment_count INTEGER DEFAULT 0"
            )
        if "output_subdir" not in existing:
            cursor.execute(
                "ALTER TABLE po_downloads ADD COLUMN output_subdir TEXT"
            )
        for column, definition in {
            "expected_company_code": "TEXT",
            "expected_legal_entity": "TEXT",
            "access_diagnosis": "TEXT",
            "supplier_name": "TEXT",
        }.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE po_downloads ADD COLUMN {column} {definition}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS po_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                po_number TEXT NOT NULL,
                attachment_name TEXT NOT NULL,
                attachment_url TEXT,
                sha256 TEXT,
                size_bytes INTEGER,
                local_path TEXT,
                source_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_po_attachments_session_hash ON po_attachments(session_id, sha256)"
        )

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS powerbi_po_date_range_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                min_date TEXT,
                max_date TEXT,
                updated_at TEXT NOT NULL
            )
        ''')

    def get_powerbi_management_hierarchy(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT paths_json, updated_at FROM powerbi_management_hierarchy_cache WHERE id = 1"
        ).fetchone()
        if not row:
            return {"paths": [], "updated_at": None}
        try:
            paths = json.loads(row["paths_json"])
        except (TypeError, json.JSONDecodeError):
            paths = []
        return {
            "paths": paths if isinstance(paths, list) else [],
            "updated_at": row["updated_at"],
        }

    def save_powerbi_management_hierarchy(self, paths: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = [dict(path) for path in paths if isinstance(path, dict)]
        updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO powerbi_management_hierarchy_cache (id, paths_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET paths_json = excluded.paths_json, updated_at = excluded.updated_at
            """,
            (json.dumps(normalized, ensure_ascii=False), updated_at),
        )
        self.conn.commit()
        return {"paths": normalized, "updated_at": updated_at}

    def get_powerbi_po_columns(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT columns_json, updated_at FROM powerbi_po_columns_cache WHERE id = 1"
        ).fetchone()
        if not row:
            return {"columns": [], "updated_at": None}
        try:
            columns = json.loads(row["columns_json"])
        except (TypeError, json.JSONDecodeError):
            columns = []
        if isinstance(columns, list):
            columns = [dict(column) for column in columns if isinstance(column, dict)]
        return {
            "columns": columns if isinstance(columns, list) else [],
            "updated_at": row["updated_at"],
        }

    def save_powerbi_po_columns(self, columns: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = [dict(column) for column in columns if isinstance(column, dict)]
        updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO powerbi_po_columns_cache (id, columns_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                columns_json = excluded.columns_json,
                updated_at = excluded.updated_at
            """,
            (json.dumps(normalized, ensure_ascii=False), updated_at),
        )
        self.conn.commit()
        return {"columns": normalized, "updated_at": updated_at}

    def get_powerbi_po_column_selection(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT columns_json, updated_at FROM powerbi_po_column_selection_cache WHERE id = 1"
        ).fetchone()
        if not row:
            return {"columns": [], "updated_at": None}
        try:
            columns = json.loads(row["columns_json"])
        except (TypeError, json.JSONDecodeError):
            columns = []
        return {
            "columns": [str(column) for column in columns if str(column).strip()]
            if isinstance(columns, list) else [],
            "updated_at": row["updated_at"],
        }

    def save_powerbi_po_column_selection(self, columns: List[str]) -> Dict[str, Any]:
        normalized = []
        seen = set()
        for column in columns or []:
            key = str(column or "").strip()
            if key and key not in seen:
                seen.add(key)
                normalized.append(key)
        updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO powerbi_po_column_selection_cache (id, columns_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                columns_json = excluded.columns_json,
                updated_at = excluded.updated_at
            """,
            (json.dumps(normalized, ensure_ascii=False), updated_at),
        )
        self.conn.commit()
        return {"columns": normalized, "updated_at": updated_at}

    def get_powerbi_po_date_range(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT min_date, max_date, updated_at FROM powerbi_po_date_range_cache WHERE id = 1"
        ).fetchone()
        if not row:
            return {"min_date": None, "max_date": None, "updated_at": None}
        return {
            "min_date": row["min_date"],
            "max_date": row["max_date"],
            "updated_at": row["updated_at"],
        }

    def save_powerbi_po_date_range(self, date_range: Dict[str, Any]) -> Dict[str, Any]:
        updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        minimum = date_range.get("min_date") if isinstance(date_range, dict) else None
        maximum = date_range.get("max_date") if isinstance(date_range, dict) else None
        self.conn.execute(
            """
            INSERT INTO powerbi_po_date_range_cache (id, min_date, max_date, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                min_date = excluded.min_date,
                max_date = excluded.max_date,
                updated_at = excluded.updated_at
            """,
            (str(minimum or "") or None, str(maximum or "") or None, updated_at),
        )
        self.conn.commit()
        return {"min_date": minimum, "max_date": maximum, "updated_at": updated_at}

    def get_timesheet_analysis_cache(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT source_path, source_name, source_sha256, sheet_name, analysis_json, updated_at "
            "FROM timesheet_analysis_cache WHERE id = 1"
        ).fetchone()
        if not row:
            return {"analysis": None, "updated_at": None}
        try:
            analysis = json.loads(row["analysis_json"])
        except (TypeError, json.JSONDecodeError):
            analysis = None
        if not isinstance(analysis, dict):
            analysis = None
        return {
            "analysis": analysis,
            "source_path": row["source_path"],
            "source_name": row["source_name"],
            "source_sha256": row["source_sha256"],
            "sheet_name": row["sheet_name"],
            "updated_at": row["updated_at"],
        }

    def save_timesheet_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        source = analysis.get("source") if isinstance(analysis, dict) else None
        if not isinstance(source, dict):
            raise ValueError("Timesheet analysis is missing source metadata.")
        updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO timesheet_analysis_cache
                (id, source_path, source_name, source_sha256, sheet_name, analysis_json, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_path = excluded.source_path,
                source_name = excluded.source_name,
                source_sha256 = excluded.source_sha256,
                sheet_name = excluded.sheet_name,
                analysis_json = excluded.analysis_json,
                updated_at = excluded.updated_at
            """,
            (
                str(source.get("path") or ""),
                str(source.get("name") or ""),
                str(source.get("sha256") or ""),
                str(source.get("sheet") or ""),
                json.dumps(analysis, ensure_ascii=False),
                updated_at,
            ),
        )
        self.conn.commit()
        return {"analysis": analysis, "updated_at": updated_at}

    def create_session(
        self,
        input_file: str,
        execution_type: str = "PROD",
        description: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        normalized_type = (execution_type or "PROD").strip().upper()
        if normalized_type not in {"PROD", "TEST"}:
            normalized_type = "PROD"

        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (input_file, execution_type, status, description, source_metadata_json)
            VALUES (?, ?, 'PENDING', ?, ?)
        ''', (input_file, normalized_type, description or None, json.dumps(source_metadata, ensure_ascii=False) if source_metadata else None))
        self.conn.commit()
        return cursor.lastrowid

    def update_session_description(self, session_id: int, description: Optional[str] = None) -> bool:
        """Set the free-form run title/description used for audit context."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE sessions SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (description or None, session_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def archive_session_input(self, session_id: int, source_path: str, archive_path: str) -> str:
        source = Path(source_path).expanduser().resolve()
        archive = Path(archive_path).expanduser().resolve()
        data = source.read_bytes()
        archive.parent.mkdir(parents=True, exist_ok=True)
        if source != archive:
            shutil.copy2(source, archive)
        digest = hashlib.sha256(data).hexdigest()
        self.conn.execute(
            """
            UPDATE sessions
            SET input_file = ?, input_file_path = ?, input_file_blob = ?,
                input_file_sha256 = ?, input_file_size = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source.name, str(archive), data, digest, len(data), session_id),
        )
        self.conn.commit()
        return str(archive)

    def clone_session_input(self, source_session_id: int, target_session_id: int, archive_path: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT input_file, input_file_path, input_file_blob, input_file_sha256, input_file_size FROM sessions WHERE id = ?",
            (source_session_id,),
        ).fetchone()
        if not row:
            return None
        source_path = Path(row["input_file_path"]) if row["input_file_path"] else None
        data = row["input_file_blob"]
        if data is None and source_path and source_path.exists():
            data = source_path.read_bytes()
        if data is None:
            return None
        archive = Path(archive_path).expanduser().resolve()
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
        digest = row["input_file_sha256"] or hashlib.sha256(data).hexdigest()
        self.conn.execute(
            """
            UPDATE sessions
            SET input_file = ?, input_file_path = ?, input_file_blob = ?,
                input_file_sha256 = ?, input_file_size = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["input_file"] or archive.name, str(archive), data, digest, len(data), target_session_id),
        )
        self.conn.commit()
        return str(archive)

    def get_session_execution_type(self, session_id: int) -> str:
        session = self.get_session(session_id)
        if not session:
            return "PROD"
        value = str(session.get("execution_type") or "PROD").strip().upper()
        return value if value in {"PROD", "TEST"} else "PROD"

    def get_session(self, session_id: int) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def add_po(self, po: PODownload):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO po_downloads (session_id, po_number, company_code, output_subdir, status, download_folder, attachment_count, error_message, expected_company_code, expected_legal_entity, access_diagnosis, supplier_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            po.session_id,
            po.po_number,
            po.company_code,
            po.output_subdir,
            po.status,
            po.download_folder,
            po.attachment_count or 0,
            po.error_message,
            po.expected_company_code,
            po.expected_legal_entity,
            po.access_diagnosis,
            po.supplier_name,
        ))
        self.conn.commit()

    def record_po_attachment(
        self,
        session_id: int,
        po_number: str,
        attachment_name: str,
        *,
        attachment_url: Optional[str] = None,
        sha256: Optional[str] = None,
        size_bytes: Optional[int] = None,
        local_path: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO po_attachments
              (session_id, po_number, attachment_name, attachment_url, sha256,
               size_bytes, local_path, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, po_number, attachment_name, attachment_url, sha256,
             size_bytes, local_path, source_type),
        )
        self.conn.commit()

    def clear_po_attachments(self, session_id: int, po_number: str) -> None:
        self.conn.execute(
            "DELETE FROM po_attachments WHERE session_id = ? AND po_number = ?",
            (session_id, po_number),
        )
        self.conn.commit()

    def list_po_attachments(self, session_id: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM po_attachments WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_po_access_diagnosis(self, session_id: int, po_number: str, diagnosis: Optional[str]) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE po_downloads SET access_diagnosis = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE session_id = ? AND po_number = ?",
            (diagnosis or None, session_id, po_number),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def set_company_access_diagnosis(self, session_id: int, company_code: str, diagnosis: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE po_downloads SET access_diagnosis = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE session_id = ? AND company_code = ? AND status = 'PENDING'",
            (diagnosis, session_id, company_code),
        )
        self.conn.commit()
        return cursor.rowcount

    def update_po_status(self, session_id: int, po_number: str, status: str, download_folder: Optional[str] = None, attachment_count: Optional[int] = None, error_message: Optional[str] = None):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE po_downloads
            SET status = ?, download_folder = COALESCE(?, download_folder),
                attachment_count = COALESCE(?, attachment_count),
                error_message = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
            WHERE session_id = ? AND po_number = ?
        ''', (status, download_folder, attachment_count, error_message, session_id, po_number))
        self.conn.commit()

    def get_po(self, session_id: int, po_number: str) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM po_downloads WHERE session_id = ? AND po_number = ?', (session_id, po_number))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_company_stats(self, session_id: int, company_code: str) -> Dict[str, int]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status != 'PENDING' THEN 1 ELSE 0 END) as processed,
                SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) as errors,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success
            FROM po_downloads 
            WHERE session_id = ? AND company_code = ?
        ''', (session_id, company_code))
        
        row = cursor.fetchone()
        return {
            'total': row['total'] or 0,
            'processed': row['processed'] or 0,
            'errors': row['errors'] or 0,
            'success': row['success'] or 0
        }
        
    def suspend_company_code(self, session_id: int, company_code: str):
        """Marks pending POs of a company code as SKIPPED_VERIFICATION_REQUIRED"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE po_downloads 
            SET status = 'SKIPPED_VERIFICATION_REQUIRED', access_diagnosis = COALESCE(access_diagnosis, 'ACCESS_DENIED_LIKELY'), updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
            WHERE session_id = ? AND company_code = ? AND status = 'PENDING'
        ''', (session_id, company_code))
        self.conn.commit()

    def close(self):
        self.conn.close()
