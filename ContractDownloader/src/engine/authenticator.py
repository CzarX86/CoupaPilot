"""Backward-compatible facade for the decoupled authentication domain.

New code should depend on ``src.auth``. The functions in this module remain
available because the CLI, integrations, and older installations may import
them directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from selenium import webdriver
from selenium.webdriver.edge.options import Options

from src.auth.browser import (
    BrowserCatalog,
    BrowserKind,
    BrowserProfileManager,
    SeleniumBrowserLauncher,
)
from src.auth.cookie_store import CookieStore, CookieStoreError
from src.auth.service import AuthService
from src.auth.session_validator import COUPA_URL, SessionValidator

COOKIE_FILE = os.path.expanduser("~/.contract_downloader/cookies.json")
AUTH_DB = os.path.expanduser("~/.contract_downloader/auth_cache.db")
EDGE_AUTH_PROFILE_DIR = Path.home() / ".contract_downloader" / "edge_auth_profile"
WORK_PROFILE_TOKENS = ("work", "trabalho", "business", "empresa", "corporate", "profissional")


def _store() -> CookieStore:
    # Construct on every call so existing callers/tests that override the
    # legacy module constants continue to work during the migration.
    return CookieStore(COOKIE_FILE, AUTH_DB)


def save_cached_cookies_db(cookies: Dict[str, str]) -> None:
    _store().save(cookies)


def load_cached_cookies_db() -> Optional[Dict[str, str]]:
    return _store()._load_db()


def load_cached_cookies() -> Optional[Dict[str, str]]:
    return _store().load()


def clear_cached_authentication(*, remove_app_profile: bool = False) -> Dict[str, Any]:
    """Compatibility reset; active GUI code uses ``AuthService.reset``.

    The legacy function retains its old broad Edge-process guard for callers
    that explicitly invoke it. The new service only checks the app-owned
    profile lock, so an unrelated personal Edge window no longer blocks reset.
    """
    if remove_app_profile and _edge_is_running():
        return {
            "success": False,
            "error": "Close all Microsoft Edge windows before resetting the Coupa sign-in state.",
        }
    try:
        result = _store().clear()
        if remove_app_profile:
            # This compatibility function is allowed to remove only the
            # explicitly named legacy app-owned profile. Never enumerate or
            # delete another Edge profile from the user's machine.
            profile = Path(EDGE_AUTH_PROFILE_DIR)
            if profile.exists():
                if BrowserProfileManager.is_locked(profile) and not BrowserProfileManager.clear_stale_lock(profile):
                    raise RuntimeError("Close the legacy Contract Downloader sign-in browser before resetting it.")
                shutil.rmtree(profile)
                result["removed"] = [*result.get("removed", []), profile.name]
        return result
    except (CookieStoreError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


async def validate_cookies_detailed(cookies: Dict[str, str]) -> tuple[bool, str]:
    result = await SessionValidator().validate(cookies)
    return result.authenticated, result.state.value


async def validate_cookies(cookies: Dict[str, str]) -> bool:
    valid, _reason = await validate_cookies_detailed(cookies)
    return valid


async def get_coupa_cookies(
    headless: bool = False,
    load_from_file: bool = True,
    fresh: bool = False,
    status_callback: Optional[Callable[[str, str], None]] = None,
    browser: str | None = None,
) -> Dict[str, str]:
    """Compatibility entry point backed by ``AuthService``."""
    service = AuthService(store=_store())
    effective_fresh = fresh or not load_from_file
    # This is an explicit sign-in action. Preserve the established UX: a valid
    # cache returns immediately, while an unavailable/expired cache opens the
    # selected browser. ``load_from_file=False`` is the legacy spelling for a
    # deliberately fresh login.
    result = await service.authenticate(
        browser_preference=browser,
        status_callback=status_callback,
        fresh=effective_fresh,
        headless=headless,
    )
    if result.cookies and result.state.value in {"valid", "unavailable"}:
        return dict(result.cookies)
    raise RuntimeError(result.message or "Coupa authentication is required.")


# ---------------------------------------------------------------------------
# Legacy Edge helpers. They remain import-compatible but are not used by the
# active AuthService path. In particular, the old profile-scoring heuristic is
# no longer used to choose a login profile.
# ---------------------------------------------------------------------------


def _edge_user_data_dir() -> Optional[Path]:
    configured = os.environ.get("COUPA_EDGE_USER_DATA_DIR", "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    if sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "Microsoft Edge")
    elif os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Microsoft" / "Edge" / "User Data")
    else:
        candidates.append(Path.home() / ".config" / "microsoft-edge")
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def _edge_profile_directory(user_data_dir: Path) -> str:
    """Legacy profile scorer retained only for old diagnostics/imports."""
    configured = os.environ.get("COUPA_EDGE_PROFILE_DIRECTORY", "").strip()
    if configured and (user_data_dir / configured).is_dir():
        return configured

    candidates: list[tuple[int, str]] = []
    try:
        info_cache = json.loads((user_data_dir / "Local State").read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
    except (OSError, ValueError, AttributeError):
        info_cache = {}
    for directory, info in info_cache.items():
        profile_path = user_data_dir / directory
        if not profile_path.is_dir() or not isinstance(info, dict):
            continue
        name = " ".join(str(info.get(key, "")) for key in ("name", "shortcut_name")).lower()
        hosted_domain = str(info.get("hosted_domain", "")).strip().lower()
        score = 10 if hosted_domain else 0
        if any(token in name for token in WORK_PROFILE_TOKENS):
            score += 5
        if info.get("is_consented_primary_account"):
            score += 1
        try:
            preferences = json.loads((profile_path / "Preferences").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            preferences = {}
        if preferences.get("profile", {}).get("is_relative_to_aad"):
            score += 10
        for account in preferences.get("account_info", []):
            if not isinstance(account, dict):
                continue
            if str(account.get("edge_account_tenant_id", "")).strip():
                score += 15
                break
            if str(account.get("edge_account_type", "")).strip().lower() not in {"", "0", "none"}:
                score += 8
                break
        candidates.append((score, directory))
    if candidates:
        candidates.sort(key=lambda item: (-item[0], item[1] != "Default", item[1]))
        return candidates[0][1]
    return "Default"


def _edge_options(headless: bool, user_data_dir: Optional[Path], profile_directory: str = "Default") -> Options:
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_directory}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _edge_is_running() -> bool:
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq msedge.exe"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            ).stdout.lower()
            return "msedge.exe" in output
        output = subprocess.run(
            ["ps", "-ax", "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        ).stdout.lower()
        return "microsoft edge" in output or "/msedge" in output
    except (OSError, subprocess.SubprocessError):
        return False


def _start_edge_with_profile(headless: bool, prefer_existing: bool = True) -> Any:
    installation = next((item for item in BrowserCatalog.detect() if item.kind is BrowserKind.EDGE), None)
    if installation is None:
        raise RuntimeError("Microsoft Edge was not found.")
    profiles = BrowserProfileManager()
    profile = profiles.ensure(BrowserKind.EDGE)
    return SeleniumBrowserLauncher().launch(installation, profile, headless=headless)


def _close_auth_driver(driver: Any) -> None:
    driver.quit()
