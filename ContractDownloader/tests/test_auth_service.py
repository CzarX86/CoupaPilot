import asyncio
import json

import pytest

from src.auth.browser import (
    BrowserInstallation,
    BrowserKind,
    BrowserLogin,
    ProfileCandidate,
    ProfileDetection,
)
from src.auth.cookie_store import CookieStoreError
from src.auth.models import AuthState, SessionCheck
from src.auth.service import AuthService


class FakeStore:
    def __init__(self, cookies=None):
        self.cookies = cookies
        self.saved = None
        self.cleared = False

    def load(self):
        return self.cookies

    def save(self, cookies):
        self.saved = dict(cookies)
        self.cookies = dict(cookies)

    def clear(self):
        self.cleared = True
        self.cookies = None
        return {"success": True, "removed": ["cookies"]}


class ReadFailingStore(FakeStore):
    def load(self):
        raise CookieStoreError("Keychain access denied")


class WriteFailingStore(FakeStore):
    def save(self, cookies):
        raise CookieStoreError("Keychain locked")


class FakeValidator:
    def __init__(self, states):
        self.states = iter(states)

    async def validate(self, cookies):
        state = next(self.states)
        return SessionCheck(state, state.value, cookies or {}, "cache")


class FakeCatalog:
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")

    @classmethod
    def select(cls, preference=None):
        return cls.installation

    @classmethod
    def as_settings(cls, preference=None):
        return {"available": [{"id": "edge", "name": "Microsoft Edge", "path": "/edge"}], "selected": "edge"}


class FakeProfiles:
    def __init__(self, tmp_path):
        self.path = tmp_path / "edge-profile"
        self.cleared = []

    def ensure(self, kind):
        self.path.mkdir()
        return self.path

    def clear(self, kind=None):
        self.cleared.append(kind)
        return ["edge-profile"]

    def path_for(self, kind):
        return self.path


class FakeLogin:
    def __init__(self):
        self.calls = 0

    def capture(self, installation, profile_dir, **kwargs):
        self.calls += 1
        return {"_coupa_session": "new-session"}


def test_worker_mode_keeps_cached_session_when_validation_is_unavailable(tmp_path):
    store = FakeStore({"_coupa_session": "cached"})
    login = FakeLogin()
    service = AuthService(
        store=store,
        validator=FakeValidator([AuthState.UNAVAILABLE]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=login,
    )

    result = asyncio.run(service.ensure_session(interactive=False))

    assert result.state is AuthState.UNAVAILABLE
    assert result.has_cached_session
    assert result.cookies["_coupa_session"] == "cached"
    assert login.calls == 0


def test_interactive_login_continues_when_secure_store_cannot_be_read(tmp_path):
    store = ReadFailingStore()
    login = FakeLogin()
    service = AuthService(
        store=store,
        validator=FakeValidator([AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=login,
        diagnostic_log_path=tmp_path / "auth.jsonl",
    )

    result = asyncio.run(service.ensure_session(interactive=True))

    assert result.state is AuthState.VALID
    assert login.calls == 1
    assert store.saved == {"_coupa_session": "new-session"}


def test_validated_session_refresh_is_persisted(tmp_path):
    class RefreshingValidator:
        async def validate(self, cookies):
            return SessionCheck(
                AuthState.VALID,
                "valid",
                {"_coupa_session": "refreshed"},
                "cache",
            )

    store = FakeStore({"_coupa_session": "cached"})
    service = AuthService(
        store=store,
        validator=RefreshingValidator(),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=FakeLogin(),
    )

    result = asyncio.run(service.check())

    assert result.state is AuthState.VALID
    assert store.saved == {"_coupa_session": "refreshed"}


def test_interactive_mode_reauthenticates_after_expiry(tmp_path):
    store = FakeStore({"_coupa_session": "expired"})
    login = FakeLogin()
    service = AuthService(
        store=store,
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=login,
    )

    result = asyncio.run(service.ensure_session(interactive=True))

    assert result.state is AuthState.VALID
    assert result.cookies["_coupa_session"] == "new-session"
    assert login.calls == 1
    assert store.saved == {"_coupa_session": "new-session"}


def test_interactive_login_persists_cookie_refreshed_by_validation(tmp_path):
    class RefreshingValidator:
        def __init__(self):
            self.calls = 0

        async def validate(self, cookies):
            self.calls += 1
            if self.calls == 1:
                return SessionCheck(AuthState.EXPIRED, "expired", cookies or {}, "cache")
            return SessionCheck(
                AuthState.VALID,
                "valid",
                {"_coupa_session": "refreshed-after-login"},
                "cache",
            )

    store = FakeStore({"_coupa_session": "expired"})
    service = AuthService(
        store=store,
        validator=RefreshingValidator(),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=FakeLogin(),
    )

    result = asyncio.run(service.ensure_session(interactive=True))

    assert result.cookies["_coupa_session"] == "refreshed-after-login"
    assert store.saved == {"_coupa_session": "refreshed-after-login"}


def test_reset_only_delegates_to_cache_and_app_profiles(tmp_path):
    store = FakeStore({"_coupa_session": "cached"})
    profiles = FakeProfiles(tmp_path)
    service = AuthService(
        store=store,
        validator=FakeValidator([]),
        catalog=FakeCatalog,
        profiles=profiles,
        browser_login=FakeLogin(),
    )

    result = service.reset()

    assert result["success"] is True
    assert store.cleared is True
    assert profiles.cleared == [None]
    assert service.cookies is None


def test_official_edge_capture_uses_detected_existing_profile(tmp_path):
    store = FakeStore()
    profiles = FakeProfiles(tmp_path)
    login = BrowserLogin()
    capture = {}

    def fake_capture(installation, profile_dir, **kwargs):
        capture.update({"installation": installation, "profile_dir": profile_dir, **kwargs})
        return {"_coupa_session": "new-session"}

    login.capture = fake_capture

    service = AuthService(
        store=store,
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=profiles,
        browser_login=login,
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: None})(),
    )

    result = asyncio.run(service.ensure_session(interactive=True))

    assert result.state is AuthState.VALID
    assert capture["existing_profile"] is False
    assert capture["attached_session"] is False
    assert capture["profile_name"] == "Default"
    assert capture["profile_dir"] == profiles.path
    assert profiles.path.exists()


def test_edge_capture_uses_dedicated_profile_when_corporate_is_detected(tmp_path):
    edge_executable = tmp_path / "Microsoft Edge"
    edge_executable.write_text("fake", encoding="utf-8")
    real_user_data = tmp_path / "Microsoft Edge User Data"
    candidate = ProfileCandidate(
        real_user_data,
        "Profile 2",
        ("Preferences.account_info",),
        150,
        "Unilever Work",
        "account email contains @unilever",
    )

    class Catalog(FakeCatalog):
        installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", str(edge_executable))

    class Detector:
        def detect(self, *, ignore_running=False):
            return ProfileDetection("profile_detected", (candidate,), "detected", ("Default", "Profile 2"))

    store = FakeStore()
    profiles = FakeProfiles(tmp_path)
    login = BrowserLogin()
    capture = {}
    login.capture = lambda installation, profile_dir, **kwargs: (
        capture.update({"profile_dir": profile_dir, **kwargs}) or {"_coupa_session": "new-session"}
    )
    trace = tmp_path / "auth.jsonl"
    service = AuthService(
        store=store,
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=Catalog,
        profiles=profiles,
        browser_login=login,
        edge_profile_detector=Detector(),
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: None})(),
        diagnostic_log_path=trace,
    )

    result = asyncio.run(service.ensure_session(interactive=True))

    assert result.state is AuthState.VALID
    assert capture["profile_dir"] == profiles.path
    assert capture["profile_name"] == "Default"
    assert capture["existing_profile"] is False
    assert profiles.path.exists()

    strategy = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("event") == "edge_auth_strategy"][0]
    assert strategy["mode"] == "dedicated_profile_with_corporate_detected"
    assert strategy["corporate_profile"] == "Profile 2"
    assert strategy["corporate_display_name"] == "Unilever Work"


def test_edge_capture_stops_instead_of_opening_wrong_profile_when_edge_is_open(tmp_path):
    edge_executable = tmp_path / "Microsoft Edge"
    edge_executable.write_text("fake", encoding="utf-8")

    class Catalog(FakeCatalog):
        installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", str(edge_executable))

    class Detector:
        def detect(self, *, ignore_running=False):
            if ignore_running:
                candidate = ProfileCandidate(tmp_path / "real", "Default", ("Preferences.account_info",), 150)
                return ProfileDetection("profile_detected", (candidate,), "detected", ("Default",))
            return ProfileDetection("edge_must_be_closed", message="Quit Edge")

    service = AuthService(
        store=FakeStore(),
        validator=FakeValidator([AuthState.EXPIRED]),
        catalog=Catalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=BrowserLogin(),
        edge_profile_detector=Detector(),
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: None})(),
    )

    with pytest.raises(RuntimeError, match="EDGE_PROFILE_IN_USE"):
        asyncio.run(service.ensure_session(interactive=True))


def test_edge_capture_attaches_to_existing_devtools_session_before_fallback(tmp_path):
    store = FakeStore()
    profiles = FakeProfiles(tmp_path)
    login = BrowserLogin()
    capture = {}

    def fake_capture(installation, profile_dir, **kwargs):
        capture.update({"installation": installation, "profile_dir": profile_dir, **kwargs})
        return {"_coupa_session": "new-session"}

    login.capture = fake_capture
    service = AuthService(
        store=store,
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=profiles,
        browser_login=login,
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: "127.0.0.1:9222"})(),
    )

    result = asyncio.run(service.ensure_session(interactive=True))

    assert result.state is AuthState.VALID
    assert capture["existing_profile"] is True
    assert capture["attached_session"] is True
    assert capture["debugger_address"] == "127.0.0.1:9222"
    assert not profiles.path.exists()


def test_authentication_failure_records_safe_structured_trace(tmp_path):
    login = BrowserLogin()
    login.capture = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("[EDGE_PROFILE_IN_USE] profile failed")
    )
    trace = tmp_path / "auth_diagnostics.jsonl"
    service = AuthService(
        store=FakeStore(),
        validator=FakeValidator([AuthState.EXPIRED]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=login,
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: None})(),
        diagnostic_log_path=trace,
    )

    with pytest.raises(RuntimeError, match="EDGE_PROFILE_IN_USE"):
        asyncio.run(service.ensure_session(interactive=True))

    records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["state"] == "error"
    assert records[-1]["previous_state"] == "checking"
    assert records[-1]["message"] == "[EDGE_PROFILE_IN_USE] profile failed"
    assert "_coupa_session" not in trace.read_text(encoding="utf-8")


def test_check_surfaces_secure_session_write_failed(tmp_path):
    service = AuthService(
        store=WriteFailingStore({"_coupa_session": "cached"}),
        validator=FakeValidator([AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=FakeLogin(),
    )

    result = asyncio.run(service.check())

    assert result.state is AuthState.VALID
    assert "SECURE_SESSION_WRITE_FAILED" in result.message


def test_authenticate_rejects_concurrent_attempt(tmp_path):
    service = AuthService(
        store=FakeStore(),
        validator=FakeValidator([AuthState.EXPIRED]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=FakeLogin(),
    )
    assert service._auth_lock.acquire(blocking=False) is True
    try:
        with pytest.raises(RuntimeError, match="AUTH_IN_PROGRESS"):
            asyncio.run(service.authenticate())
    finally:
        service._auth_lock.release()


def test_authenticate_records_devtools_unavailable_diagnostic(tmp_path):
    trace = tmp_path / "auth.jsonl"
    login = BrowserLogin()
    login.capture = lambda *args, **kwargs: {"_coupa_session": "new-session"}
    service = AuthService(
        store=FakeStore(),
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=login,
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: None})(),
        diagnostic_log_path=trace,
    )

    asyncio.run(service.ensure_session(interactive=True))

    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    devtools = [event for event in events if event.get("event") == "edge_devtools"]
    assert devtools
    assert devtools[0]["code"] == "EDGE_DEVTOOLS_NOT_AVAILABLE"


def test_authenticate_records_orphaned_driver_code(monkeypatch, tmp_path):
    trace = tmp_path / "auth.jsonl"
    monkeypatch.setattr("src.auth.service.reap_orphaned_msedgedrivers", lambda: [4242])
    service = AuthService(
        store=FakeStore(),
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=FakeCatalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=FakeLogin(),
        diagnostic_log_path=trace,
    )

    asyncio.run(service.ensure_session(interactive=True))

    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    reaped = [event for event in events if event.get("event") == "edge_driver_reaped"]
    assert reaped
    assert reaped[0]["code"] == "EDGE_DRIVER_ORPHANED"
    assert reaped[0]["pids"] == [4242]


def test_edge_profile_selection_failure_code(tmp_path):
    edge_executable = tmp_path / "Microsoft Edge"
    edge_executable.write_text("fake", encoding="utf-8")

    class Catalog(FakeCatalog):
        installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", str(edge_executable))

    class FailingDetector:
        def detect(self, *, ignore_running=False):
            raise OSError("cannot read Local State")

    login = BrowserLogin()
    login.capture = lambda *args, **kwargs: {"_coupa_session": "new-session"}
    service = AuthService(
        store=FakeStore(),
        validator=FakeValidator([AuthState.EXPIRED, AuthState.VALID]),
        catalog=Catalog,
        profiles=FakeProfiles(tmp_path),
        browser_login=login,
        edge_profile_detector=FailingDetector(),
        edge_devtools_connector=type("DevTools", (), {"discover": lambda self: None})(),
    )

    with pytest.raises(RuntimeError, match="EDGE_PROFILE_SELECTION_FAILED"):
        asyncio.run(service.ensure_session(interactive=True))
