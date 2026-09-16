import ctypes
import json

import pytest

from src.auth.cookie_store import (
    CookieStore,
    CookieStoreError,
    SecureSessionStore,
    _Credential,
    _WindowsCredentialBackend,
)


class MemoryBackend:
    def __init__(self):
        self.payload = None

    def load(self):
        return dict(self.payload) if self.payload else None

    def save(self, cookies):
        self.payload = dict(cookies)

    def clear(self):
        existed = self.payload is not None
        self.payload = None
        return {"success": True, "removed": ["memory"] if existed else []}


class FailingBackend(MemoryBackend):
    def load(self):
        raise CookieStoreError("Keychain access denied")


def test_secure_store_migrates_legacy_only_after_native_save(tmp_path):
    legacy = CookieStore(tmp_path / "cookies.json", tmp_path / "auth_cache.db")
    legacy.save({"_coupa_session": "legacy-secret"})
    backend = MemoryBackend()
    store = SecureSessionStore(legacy_store=legacy, backend=backend)

    assert store.migrate_legacy_cache() == {"_coupa_session": "legacy-secret"}
    assert backend.payload == {"_coupa_session": "legacy-secret"}
    assert not (tmp_path / "cookies.json").exists()
    assert not (tmp_path / "auth_cache.db").exists()
    assert store.load() == {"_coupa_session": "legacy-secret"}


def test_cookie_store_clear_releases_sqlite_lock_before_file_removal(tmp_path):
    legacy = CookieStore(tmp_path / "cookies.json", tmp_path / "auth_cache.db")
    legacy.save({"_coupa_session": "legacy-secret"})

    legacy.clear()
    (tmp_path / "auth_cache.db").unlink()

    assert not (tmp_path / "auth_cache.db").exists()


def test_secure_store_never_creates_plaintext_when_native_storage_is_unavailable(tmp_path):
    legacy = CookieStore(tmp_path / "cookies.json", tmp_path / "auth_cache.db")
    store = SecureSessionStore(legacy_store=legacy, backend=None)

    with pytest.raises(CookieStoreError, match="Native secure session storage"):
        store.save({"_coupa_session": "memory-only-secret"})
    assert not (tmp_path / "cookies.json").exists()
    assert not (tmp_path / "auth_cache.db").exists()


def test_secure_store_health_checks_access_without_exposing_cookie_values(tmp_path):
    backend = MemoryBackend()
    backend.save({"_coupa_session": "secret-cookie"})
    store = SecureSessionStore(
        legacy_store=CookieStore(tmp_path / "cookies.json", tmp_path / "auth_cache.db"),
        backend=backend,
    )

    health = store.health()

    assert health == {
        "backend": "MemoryBackend",
        "available": True,
        "readable": True,
        "has_session": True,
        "error": "",
    }
    assert "secret-cookie" not in json.dumps(health)


def test_secure_store_reports_native_read_failure_when_no_legacy_session_exists(tmp_path):
    store = SecureSessionStore(
        legacy_store=CookieStore(tmp_path / "cookies.json", tmp_path / "auth_cache.db"),
        backend=FailingBackend(),
    )

    with pytest.raises(CookieStoreError, match="Keychain access denied"):
        store.load()

    health = store.health()
    assert health["readable"] is False
    assert health["error"] == "Keychain access denied"


def test_windows_credential_manager_api_is_used_without_logging_the_cookie(monkeypatch):
    backend = _WindowsCredentialBackend()
    captured = {}

    class FakeApi:
        def CredWriteW(self, credential, flags):
            value = ctypes.cast(credential, ctypes.POINTER(_Credential)).contents
            captured["payload"] = ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode()
            return 1

        def CredDeleteW(self, target, credential_type, flags):
            captured["deleted"] = target
            return 1

    monkeypatch.setattr(backend, "_api", lambda: FakeApi())
    backend.save({"_coupa_session": "secret-cookie"})
    backend.clear()

    assert json.loads(captured["payload"])["_coupa_session"] == "secret-cookie"
    assert captured["deleted"] == "ContractDownloader/CoupaSession"
    assert captured["payload"] == json.dumps({"_coupa_session": "secret-cookie"}, separators=(",", ":"))
