from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Mapping


class CookieStoreError(RuntimeError):
    """Raised when the local session cache cannot be persisted."""


class CookieStore:
    """Persistent local cookie cache with legacy JSON/SQLite compatibility.

    The two existing formats are intentionally kept during the migration. The
    The atomic ``cookies.json`` snapshot is preferred when it contains the
    Coupa session cookie, while SQLite remains a fallback for installations
    created by older releases or interrupted writes. No expiration is inferred
    locally; Coupa remains authoritative.
    """

    def __init__(self, cookie_file: str | os.PathLike[str] | None = None, db_path: str | os.PathLike[str] | None = None):
        root = Path.home() / ".contract_downloader"
        self.cookie_file = Path(cookie_file).expanduser() if cookie_file else root / "cookies.json"
        self.db_path = Path(db_path).expanduser() if db_path else root / "auth_cache.db"

    @property
    def root(self) -> Path:
        return self.cookie_file.parent

    @staticmethod
    def _normalise(value: object) -> dict[str, str] | None:
        if not isinstance(value, Mapping):
            return None
        cookies = {str(key): str(item) for key, item in value.items() if item is not None}
        return cookies or None

    @staticmethod
    def _has_session(cookies: Mapping[str, str] | None) -> bool:
        return bool(cookies and cookies.get("_coupa_session"))

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_cache (
                    key TEXT PRIMARY KEY,
                    cookies_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def _load_db(self) -> dict[str, str] | None:
        if not self.db_path.exists():
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT cookies_json FROM auth_cache WHERE key = 'coupa'"
                ).fetchone()
            if not row:
                return None
            return self._normalise(json.loads(row[0]))
        except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _load_json(self) -> dict[str, str] | None:
        if not self.cookie_file.exists():
            return None
        try:
            return self._normalise(json.loads(self.cookie_file.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def load(self) -> dict[str, str] | None:
        database = self._load_db()
        legacy = self._load_json()
        # The JSON snapshot is written atomically before SQLite. Prefer it when
        # both copies contain a session: after a crash or locked SQLite file it
        # can contain the newest successful login while the DB still has the
        # previous cookie set. SQLite remains the fallback for older installs
        # where the JSON file is absent or incomplete.
        if self._has_session(legacy):
            return legacy
        if self._has_session(database):
            return database
        return database or legacy

    def save(self, cookies: Mapping[str, str]) -> None:
        normalised = self._normalise(cookies)
        if not self._has_session(normalised):
            raise CookieStoreError("Cannot cache a Coupa session without _coupa_session.")

        self._ensure_root()
        payload = json.dumps(normalised, separators=(",", ":"))
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cookie_file.parent,
                prefix=f".{self.cookie_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, self.cookie_file)
            temporary_path = None

            self._init_db()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO auth_cache (key, cookies_json, updated_at)
                    VALUES ('coupa', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        cookies_json = excluded.cookies_json,
                        updated_at = excluded.updated_at
                    """,
                    (payload, int(time.time())),
                )
                conn.commit()
        except (OSError, sqlite3.Error) as exc:
            raise CookieStoreError(f"Could not persist the Coupa session: {exc}") from exc
        finally:
            if temporary_path:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self) -> dict[str, object]:
        removed: list[str] = []
        try:
            self.cookie_file.unlink(missing_ok=True)
            removed.append("cookies")
        except OSError as exc:
            raise CookieStoreError(f"Could not clear cached cookies: {exc}") from exc

        if self.db_path.exists():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM auth_cache WHERE key = 'coupa'")
                    conn.commit()
                removed.append("auth_cache")
            except sqlite3.Error as exc:
                raise CookieStoreError(f"Could not clear authentication database: {exc}") from exc
        return {"success": True, "removed": removed}


class _Credential(ctypes.Structure):
    """Small ctypes view of Windows CREDENTIALW used by Credential Manager."""

    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class _WindowsCredentialBackend:
    """Native per-user Windows Credential Manager backend."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    def __init__(self, *, target: str = "ContractDownloader/CoupaSession"):
        self.target = target

    @staticmethod
    def _api():
        if os.name != "nt":
            raise CookieStoreError("Windows Credential Manager is only available on Windows.")
        try:
            api = ctypes.WinDLL("advapi32", use_last_error=True)
            api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_Credential))]
            api.CredReadW.restype = wintypes.BOOL
            api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
            api.CredWriteW.restype = wintypes.BOOL
            api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            api.CredDeleteW.restype = wintypes.BOOL
            api.CredFree.argtypes = [ctypes.c_void_p]
            api.CredFree.restype = None
            return api
        except (AttributeError, OSError) as exc:
            raise CookieStoreError(f"Windows Credential Manager is unavailable: {exc}") from exc

    def load(self) -> dict[str, str] | None:
        api = self._api()
        pointer = ctypes.POINTER(_Credential)()
        if not api.CredReadW(self.target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            if error == self.ERROR_NOT_FOUND:
                return None
            raise CookieStoreError(f"Could not read the Windows secure session (error {error}).")
        try:
            credential = pointer.contents
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            value = json.loads(raw.decode("utf-8"))
            return CookieStore._normalise(value)
        except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CookieStoreError("The Windows secure session is corrupted.") from exc
        finally:
            api.CredFree(pointer)

    def save(self, cookies: Mapping[str, str]) -> None:
        api = self._api()
        payload = json.dumps(dict(cookies), separators=(",", ":")).encode("utf-8")
        blob = ctypes.create_string_buffer(payload)
        credential = _Credential()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = self.target
        credential.CredentialBlobSize = len(payload)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "current-user"
        if not api.CredWriteW(ctypes.byref(credential), 0):
            error = ctypes.get_last_error()
            raise CookieStoreError(f"Could not save the Coupa session in Windows Credential Manager (error {error}).")

    def clear(self) -> dict[str, object]:
        api = self._api()
        if api.CredDeleteW(self.target, self.CRED_TYPE_GENERIC, 0):
            return {"success": True, "removed": ["windows_credential"]}
        error = ctypes.get_last_error()
        if error == self.ERROR_NOT_FOUND:
            return {"success": True, "removed": []}
        raise CookieStoreError(f"Could not clear the Windows secure session (error {error}).")


class _MacKeychainBackend:
    """Native macOS Keychain backend using the built-in ``security`` tool."""

    NOT_FOUND = 44

    def __init__(self, *, service: str = "ContractDownloader", account: str = "CoupaSession"):
        self.service = service
        self.account = account

    def load(self) -> dict[str, str] | None:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", self.account, "-s", self.service, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == self.NOT_FOUND:
            return None
        if result.returncode != 0:
            raise CookieStoreError("Could not read the Coupa session from macOS Keychain.")
        try:
            return CookieStore._normalise(json.loads(result.stdout.strip()))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CookieStoreError("The macOS secure session is corrupted.") from exc

    def save(self, cookies: Mapping[str, str]) -> None:
        payload = json.dumps(dict(cookies), separators=(",", ":"))
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-a",
                self.account,
                "-s",
                self.service,
                "-w",
                payload,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise CookieStoreError("Could not save the Coupa session in macOS Keychain.")

    def clear(self) -> dict[str, object]:
        result = subprocess.run(
            ["security", "delete-generic-password", "-a", self.account, "-s", self.service],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in {0, self.NOT_FOUND}:
            raise CookieStoreError("Could not clear the Coupa session from macOS Keychain.")
        return {"success": True, "removed": ["macos_keychain"] if result.returncode == 0 else []}


def _native_backend() -> _WindowsCredentialBackend | _MacKeychainBackend | None:
    if os.name == "nt":
        return _WindowsCredentialBackend()
    if sys.platform == "darwin":
        return _MacKeychainBackend()
    return None


_BACKEND_UNSET = object()


class SecureSessionStore:
    """Secure session cache with one-time legacy migration.

    ``CookieStore`` remains available as a compatibility adapter for old
    callers. New authentication flows use this class and never write a new
    plaintext cookie file. A legacy cache can be read temporarily so an
    upgrade does not force an unnecessary sign-in; it is deleted only after a
    successful native save.
    """

    def __init__(
        self,
        *,
        legacy_store: CookieStore | None = None,
        backend: _WindowsCredentialBackend | _MacKeychainBackend | None | object = _BACKEND_UNSET,
    ):
        self.legacy_store = legacy_store or CookieStore()
        self.backend = _native_backend() if backend is _BACKEND_UNSET else backend

    @property
    def native_available(self) -> bool:
        return self.backend is not None

    @property
    def backend_name(self) -> str:
        if isinstance(self.backend, _MacKeychainBackend):
            return "macOS Keychain"
        if isinstance(self.backend, _WindowsCredentialBackend):
            return "Windows Credential Manager"
        if self.backend is None:
            return "Unavailable"
        return type(self.backend).__name__

    def health(self) -> dict[str, object]:
        """Verify native-store access without exposing stored cookie values."""
        if self.backend is None:
            return {
                "backend": self.backend_name,
                "available": False,
                "readable": False,
                "has_session": False,
                "error": "Native secure session storage is unavailable.",
            }
        try:
            secure = self.backend.load()
        except CookieStoreError as exc:
            return {
                "backend": self.backend_name,
                "available": True,
                "readable": False,
                "has_session": False,
                "error": str(exc),
            }
        return {
            "backend": self.backend_name,
            "available": True,
            "readable": True,
            "has_session": CookieStore._has_session(secure),
            "error": "",
        }

    def load(self) -> dict[str, str] | None:
        if self.backend is not None:
            try:
                secure = self.backend.load()
                if CookieStore._has_session(secure):
                    return secure
            except CookieStoreError:
                # A temporarily unavailable native store must not prevent a
                # running app from using an already-existing legacy cache.
                legacy = self.legacy_store.load()
                if CookieStore._has_session(legacy):
                    return legacy
                raise
        return self.legacy_store.load()

    def save(self, cookies: Mapping[str, str]) -> None:
        normalised = CookieStore._normalise(cookies)
        if not CookieStore._has_session(normalised):
            raise CookieStoreError("Cannot cache a Coupa session without _coupa_session.")
        if self.backend is None:
            raise CookieStoreError(
                "Native secure session storage is unavailable; the session will remain in memory only."
            )
        self.backend.save(normalised)  # type: ignore[union-attr]
        # Plaintext is removed only after the native write has completed.
        self.legacy_store.clear()
        for path in (
            getattr(self.legacy_store, "cookie_file", None),
            getattr(self.legacy_store, "db_path", None),
        ):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError as exc:
                    raise CookieStoreError(f"Could not remove the legacy session cache: {exc}") from exc

    def clear(self) -> dict[str, object]:
        removed: list[str] = []
        if self.backend is not None:
            try:
                result = self.backend.clear()
                removed.extend(str(item) for item in result.get("removed", []))
            except CookieStoreError:
                # Best effort cleanup of the legacy cache still matters when
                # the platform store is temporarily locked or unavailable.
                pass
        legacy_result = self.legacy_store.clear()
        removed.extend(str(item) for item in legacy_result.get("removed", []))
        for path in (
            getattr(self.legacy_store, "cookie_file", None),
            getattr(self.legacy_store, "db_path", None),
        ):
            if path:
                try:
                    if Path(path).exists():
                        Path(path).unlink()
                        removed.append(Path(path).name)
                except OSError:
                    pass
        return {"success": True, "removed": removed}

    def migrate_legacy_cache(self) -> dict[str, str] | None:
        legacy = self.legacy_store.load()
        if not CookieStore._has_session(legacy):
            return None
        self.save(legacy)
        return legacy
