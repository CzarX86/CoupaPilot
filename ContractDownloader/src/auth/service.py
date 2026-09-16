from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from pathlib import Path
from typing import Callable, Mapping

from src.auth.browser import (
    BrowserCatalog,
    BrowserKind,
    BrowserLogin,
    BrowserProfileManager,
    CorporateEdgeProfileDetector,
    EdgeDevToolsConnector,
    SeleniumBrowserLauncher,
    reap_orphaned_msedgedrivers,
)
from src.auth.cookie_store import CookieStore, CookieStoreError, SecureSessionStore
from src.auth.models import AuthState, SessionCheck
from src.auth.session_validator import SessionValidator


class AuthenticationActionRequired(RuntimeError):
    """Raised when authentication needs an explicit human correction."""


class AuthService:
    """Single authentication policy shared by GUI and CLI entry points."""

    def __init__(
        self,
        *,
        store: CookieStore | SecureSessionStore | None = None,
        validator: SessionValidator | None = None,
        catalog: type[BrowserCatalog] = BrowserCatalog,
        profiles: BrowserProfileManager | None = None,
        browser_login: BrowserLogin | None = None,
        edge_profile_detector: CorporateEdgeProfileDetector | None = None,
        edge_devtools_connector: EdgeDevToolsConnector | None = None,
        diagnostic_log_path: str | Path | None = None,
    ):
        self.store = store or SecureSessionStore()
        self.validator = validator or SessionValidator()
        self.catalog = catalog
        self.profiles = profiles or BrowserProfileManager()
        self.browser_login = browser_login or BrowserLogin(SeleniumBrowserLauncher())
        self.edge_profile_detector = edge_profile_detector or CorporateEdgeProfileDetector()
        self.edge_devtools_connector = edge_devtools_connector or EdgeDevToolsConnector()
        self.diagnostic_log_path = Path(diagnostic_log_path) if diagnostic_log_path else (
            Path.home() / ".contract_downloader" / "auth_diagnostics.jsonl"
        )
        self._diagnostic_lock = threading.Lock()
        self._auth_lock = threading.Lock()
        self._cookies: dict[str, str] | None = None

    @staticmethod
    def _safe_diagnostic_text(value: object) -> str:
        text = str(value or "").replace(str(Path.home()), "~")
        text = re.sub(r"(https?://[^\s'\"?]+)\?[^\s'\"]*", r"\1?[redacted]", text)
        return re.sub(
            r"(?i)(cookie|token|password|_coupa_session)\s*[=:]\s*[^\s,;]+",
            r"\1=[redacted]",
            text,
        )

    def record_diagnostic(self, event: str, **fields: object) -> None:
        """Append one support-safe authentication event; never fail login."""
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            **{
                key: self._safe_diagnostic_text(value) if isinstance(value, str) else value
                for key, value in fields.items()
                if value is not None
            },
        }
        try:
            with self._diagnostic_lock:
                self.diagnostic_log_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.diagnostic_log_path.parent.chmod(0o700)
                except OSError:
                    pass
                with self.diagnostic_log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                try:
                    self.diagnostic_log_path.chmod(0o600)
                except OSError:
                    pass
        except OSError:
            pass

    def latest_diagnostic(self) -> dict[str, object] | None:
        try:
            lines = self.diagnostic_log_path.read_text(encoding="utf-8").splitlines()
            return json.loads(lines[-1]) if lines else None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @property
    def cookies(self) -> dict[str, str] | None:
        return dict(self._cookies) if self._cookies else None

    def set_cookies(self, cookies: Mapping[str, str] | None) -> None:
        self._cookies = {str(key): str(value) for key, value in (cookies or {}).items() if value is not None} or None

    async def check(self) -> SessionCheck:
        """Load and validate the cache, preserving it during outages."""
        try:
            cached = self.store.load()
        except CookieStoreError as exc:
            return SessionCheck(
                AuthState.UNAVAILABLE,
                f"[SECURE_SESSION_READ_FAILED] {exc}",
                self.cookies or {},
                "secure_store",
            )
        result = await self.validator.validate(cached)
        if result.state in {AuthState.VALID, AuthState.UNAVAILABLE} and result.has_cached_session:
            if result.state is AuthState.VALID:
                try:
                    self.store.save(result.cookies)
                except CookieStoreError as exc:
                    result = SessionCheck(
                        result.state,
                        f"{result.message} [SECURE_SESSION_WRITE_FAILED] Secure session storage is unavailable; "
                        "this session will remain in memory only.",
                        result.cookies,
                        result.source,
                    )
            self.set_cookies(result.cookies)
            return result
        self.set_cookies(None)
        return result

    async def ensure_session(
        self,
        *,
        interactive: bool,
        browser_preference: str | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        fresh: bool = False,
        headless: bool = False,
    ) -> SessionCheck:
        """Return a usable session or optionally perform visible login.

        GUI callers pass ``interactive=True``. The GUI-launched CLI worker
        passes ``interactive=False`` so an expired session produces a clear
        authentication-required result instead of opening an untracked second
        browser. Direct CLI use can opt into the interactive path.
        """
        current = await self.check()
        if not fresh and (current.state is AuthState.VALID or (current.state is AuthState.UNAVAILABLE and current.has_cached_session)):
            return current
        if not interactive:
            return current
        return await self.authenticate(
            browser_preference=browser_preference,
            status_callback=status_callback,
            fresh=fresh,
            headless=headless,
            _skip_cache_check=True,
        )

    async def authenticate(
        self,
        *,
        browser_preference: str | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        fresh: bool = False,
        headless: bool = False,
        _skip_cache_check: bool = False,
    ) -> SessionCheck:
        """Capture a fresh session, refusing a concurrent sign-in attempt."""
        if not self._auth_lock.acquire(blocking=False):
            raise AuthenticationActionRequired(
                "[AUTH_IN_PROGRESS] A Coupa sign-in is already in progress."
            )
        try:
            return await self._authenticate(
                browser_preference=browser_preference,
                status_callback=status_callback,
                fresh=fresh,
                headless=headless,
                _skip_cache_check=_skip_cache_check,
            )
        finally:
            self._auth_lock.release()

    async def _authenticate(
        self,
        *,
        browser_preference: str | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        fresh: bool = False,
        headless: bool = False,
        _skip_cache_check: bool = False,
    ) -> SessionCheck:
        """Capture a fresh session through the existing Edge work profile."""
        attempt_id = f"{time.time_ns():x}"[-12:]
        started_at = time.monotonic()
        previous_state = "idle"
        callback = status_callback

        def report(state: str, message: str) -> None:
            nonlocal previous_state
            self.record_diagnostic(
                "auth_step",
                attempt_id=attempt_id,
                state=state,
                previous_state=previous_state,
                elapsed_ms=int((time.monotonic() - started_at) * 1000),
                message=message,
            )
            previous_state = state
            if callback:
                callback(state, message)

        status_callback = report
        report("starting", "Preparing Coupa sign-in…")
        reaped_drivers = reap_orphaned_msedgedrivers()
        if reaped_drivers:
            self.record_diagnostic(
                "edge_driver_reaped",
                attempt_id=attempt_id,
                code="EDGE_DRIVER_ORPHANED",
                pids=reaped_drivers,
            )
        if not fresh and not _skip_cache_check:
            # Check the shared cache before resolving a browser. A valid
            # session should not require a browser installation or a second
            # Coupa request after the caller already checked it.
            try:
                current = await self.check()
            except CookieStoreError as exc:
                report("error", f"[SECURE_SESSION_READ_FAILED] {exc}")
                raise
            if current.state is AuthState.VALID:
                if status_callback:
                    status_callback("success", "Cached Coupa session is valid.")
                return current

        preference = browser_preference
        if not preference or str(preference).strip().lower() in {"", "auto"}:
            # The official SSO path is Edge. Explicit Chrome remains available
            # only for compatibility with older integrations.
            preference = "edge"
        installation = self.catalog.select(preference)
        existing_profile = False
        profile_name: str | None = None
        debugger_address: str | None = None
        attached_session = False
        can_use_edge_session = installation.kind is BrowserKind.EDGE and isinstance(self.browser_login, BrowserLogin)
        if can_use_edge_session:
            report("checking", "Checking for a running Microsoft Edge DevTools endpoint…")
            debugger_address = self.edge_devtools_connector.discover()
            attached_session = bool(debugger_address)
            if not attached_session:
                self.record_diagnostic(
                    "edge_devtools",
                    attempt_id=attempt_id,
                    available=False,
                    code="EDGE_DEVTOOLS_NOT_AVAILABLE",
                )

        selected_corporate_profile = None
        if can_use_edge_session and not attached_session and Path(installation.executable).is_file():
            report("checking", "Detecting corporate Edge profile…")
            try:
                detection = self.edge_profile_detector.detect()
            except Exception as exc:
                raise AuthenticationActionRequired(
                    f"[EDGE_PROFILE_SELECTION_FAILED] Could not inspect the Edge profiles: {exc}"
                ) from exc
            if detection.state == "edge_must_be_closed":
                report("checking", "Checking Edge process and profile lock…")
                metadata = self.edge_profile_detector.detect(ignore_running=True)
                if metadata.state == "profile_detected" and metadata.selected:
                    raise AuthenticationActionRequired(
                        "[EDGE_PROFILE_IN_USE] Microsoft Edge is open. Close it completely with ⌘Q "
                        f"so the app can use the detected @unilever profile '{metadata.selected.profile_name}'. "
                        "Alternatively enable Edge remote debugging and try again."
                    )
                raise AuthenticationActionRequired(
                    "[EDGE_PROFILE_IN_USE] Microsoft Edge is open and its corporate profile cannot be selected. "
                    "Close it completely with ⌘Q and try again."
                )
            if detection.state == "action_required" and detection.candidates:
                code = detection.code or "EDGE_PROFILE_AMBIGUOUS"
                raise AuthenticationActionRequired(f"[{code}] {detection.message}")
            selected_corporate_profile = detection.selected
            if selected_corporate_profile is None and detection.code:
                self.record_diagnostic(
                    "edge_profile_selection",
                    attempt_id=attempt_id,
                    code=detection.code,
                    available_profiles=list(detection.available_profiles),
                )

        if fresh:
            self.store.clear()
            if not attached_session:
                self.profiles.clear(installation.kind)

        if attached_session:
            existing_profile = True
            self.record_diagnostic(
                "edge_auth_strategy",
                attempt_id=attempt_id,
                mode="devtools_attach",
                debugger_address=debugger_address,
            )
            profile_dir = self.profiles.path_for(installation.kind)
        else:
            # Edge 151+ refuses WebDriver remote debugging on the default Edge
            # data directory, so the real corporate profile cannot be reopened
            # through WebDriver. A one-time SSO sign-in in the dedicated app
            # profile is the supported path; the corporate-profile detection
            # above still drives the "Edge open" guidance and diagnostics.
            profile_dir = self.profiles.ensure(installation.kind)
            if can_use_edge_session:
                profile_name = "Default"
            if selected_corporate_profile is not None:
                report(
                    "checking",
                    "Detected the corporate @unilever profile; a one-time sign-in "
                    "in the dedicated Edge profile is required.",
                )
            self.record_diagnostic(
                "edge_auth_strategy",
                attempt_id=attempt_id,
                mode=(
                    "dedicated_profile_with_corporate_detected"
                    if selected_corporate_profile is not None
                    else "dedicated_profile_fallback"
                ),
                profile_path=str(profile_dir),
                profile_name=profile_name,
                corporate_profile=(
                    selected_corporate_profile.profile_name
                    if selected_corporate_profile is not None
                    else None
                ),
                corporate_display_name=(
                    selected_corporate_profile.display_name
                    if selected_corporate_profile is not None
                    else None
                ),
            )

        try:
            cookies = self.browser_login.capture(
                installation,
                profile_dir,
                headless=headless,
                status_callback=status_callback,
                existing_profile=existing_profile,
                profile_name=profile_name,
                debugger_address=debugger_address,
                attached_session=attached_session,
            )
            validation = await self.validator.validate(cookies)
        except AuthenticationActionRequired:
            raise
        except Exception as exc:
            launcher = getattr(self.browser_login, "launcher", None)
            diagnostics = getattr(launcher, "last_diagnostics", None)
            if diagnostics:
                self.record_diagnostic(
                    "edge_driver_diagnostics",
                    attempt_id=attempt_id,
                    **{str(key): value for key, value in diagnostics.items() if value is not None},
                )
            if "EDGE_REMOTE_DEBUGGING_REFUSED" in str(exc):
                report("action_required", str(exc))
                raise AuthenticationActionRequired(str(exc)) from exc
            report("error", str(exc))
            raise
        if validation.state is AuthState.EXPIRED:
            raise RuntimeError("Coupa rejected the captured session. Complete the sign-in and try again.")
        current_cookies = dict(validation.cookies) if validation.has_cached_session else cookies

        report("saving", "Saving secure session…")
        storage_warning = ""
        try:
            self.store.save(current_cookies)
        except CookieStoreError as exc:
            storage_warning = (
                f" [SECURE_SESSION_WRITE_FAILED] Secure storage is unavailable; "
                f"the session will remain in memory only ({exc})."
            )
        self.set_cookies(current_cookies)

        if validation.state is AuthState.UNAVAILABLE:
            result = SessionCheck(
                AuthState.UNAVAILABLE,
                "Sign-in completed; Coupa session validation is temporarily unavailable. The session will be tried during the run."
                + storage_warning,
                current_cookies,
                "capture",
            )
            if status_callback:
                status_callback("success", result.message)
            return result

        result = SessionCheck(
            AuthState.VALID,
            "Coupa session captured and validated." + storage_warning,
            current_cookies,
            "capture",
        )
        if status_callback:
            status_callback("success", result.message)
        return result

    def cancel(self) -> None:
        """Cancel an in-flight visible sign-in without touching cached state."""
        login = getattr(self, "browser_login", None)
        cancel = getattr(login, "cancel", None)
        if callable(cancel):
            cancel()

    def reset(self) -> dict[str, object]:
        """Clear cache and only profiles owned by the application."""
        result: dict[str, object] = {"success": True, "removed": []}
        try:
            cache_result = self.store.clear()
            result["removed"] = list(cache_result.get("removed", []))
        except CookieStoreError as exc:
            return {"success": False, "error": str(exc)}

        try:
            profiles = self.profiles.clear()
            result["removed"] = [*result["removed"], *profiles]  # type: ignore[list-item]
        except RuntimeError as exc:
            # The cache is already cleared safely; report the profile issue so
            # the user can close only the app-owned sign-in browser and retry.
            result["success"] = False
            result["error"] = str(exc)
        self.set_cookies(None)
        return result

    def browser_options(self, preference: str | None = None) -> dict[str, object]:
        options = dict(self.catalog.as_settings(preference))
        profile_info = getattr(self.profiles, "info", None)
        if profile_info:
            options["profiles"] = {
                kind.value: profile_info(kind)
                for kind in BrowserKind
            }
        else:
            options["profiles"] = {}
        return options


def run_async(coro):
    """Run a service coroutine from the synchronous pywebview/CLI bridge."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # pywebview API methods are synchronous, but this fallback keeps the
    # service usable from an embedding loop without nesting asyncio.run().
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
