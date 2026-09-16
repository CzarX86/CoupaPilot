from __future__ import annotations

import json
import os
import plistlib
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeDriverService

from src.auth.session_validator import AUTH_REDIRECT_MARKERS, COUPA_URL


class BrowserKind(StrEnum):
    EDGE = "edge"
    CHROME = "chrome"


@dataclass(frozen=True, slots=True)
class BrowserInstallation:
    kind: BrowserKind
    name: str
    executable: str


class BrowserCatalog:
    """Detect supported browsers and the OS default without reading profiles."""

    _DISPLAY_NAMES = {
        BrowserKind.EDGE: "Microsoft Edge",
        BrowserKind.CHROME: "Google Chrome",
    }

    @classmethod
    def _candidates(cls) -> dict[BrowserKind, list[str]]:
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA", "")
            program_files = os.environ.get("PROGRAMFILES", r"C:\\Program Files")
            program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)")
            return {
                BrowserKind.EDGE: [
                    os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
                    os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
                    os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                ],
                BrowserKind.CHROME: [
                    os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                ],
            }
        if sys.platform == "darwin":
            return {
                BrowserKind.EDGE: [
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    str(Path.home() / "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                ],
                BrowserKind.CHROME: [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                ],
            }
        return {
            BrowserKind.EDGE: ["/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable"],
            BrowserKind.CHROME: ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"],
        }

    @classmethod
    def detect(cls) -> list[BrowserInstallation]:
        detected: list[BrowserInstallation] = []
        for kind, candidates in cls._candidates().items():
            paths: Iterable[str | None] = [
                shutil.which("msedge") if kind is BrowserKind.EDGE else shutil.which("google-chrome"),
                shutil.which("microsoft-edge") if kind is BrowserKind.EDGE else shutil.which("chrome"),
                *candidates,
            ]
            selected = next(
                (
                    str(Path(path).expanduser())
                    for path in paths
                    if path and Path(path).expanduser().is_file()
                ),
                None,
            )
            if selected:
                detected.append(BrowserInstallation(kind, cls._DISPLAY_NAMES[kind], selected))
        return detected

    @staticmethod
    def _kind_from_identifier(identifier: object) -> BrowserKind | None:
        value = str(identifier or "").lower()
        if "edge" in value or "microsoft.edgemac" in value:
            return BrowserKind.EDGE
        if "chrome" in value or "googlechromes" in value or "chromium" in value:
            return BrowserKind.CHROME
        return None

    @classmethod
    def _macos_default_kind(cls) -> BrowserKind | None:
        try:
            result = subprocess.run(
                [
                    "defaults",
                    "export",
                    "com.apple.LaunchServices/com.apple.launchservices.secure",
                    "-",
                ],
                capture_output=True,
                check=False,
                timeout=4,
            )
            if result.returncode != 0 or not result.stdout:
                return None
            payload = plistlib.loads(result.stdout)
            handlers = payload.get("LSHandlers", []) if isinstance(payload, dict) else []
            if not isinstance(handlers, list):
                return None
            for scheme in ("http", "https"):
                for handler in handlers:
                    if not isinstance(handler, dict):
                        continue
                    if str(handler.get("LSHandlerURLScheme", "")).lower() != scheme:
                        continue
                    for key in ("LSHandlerRoleAll", "LSHandlerRoleViewer", "LSHandlerRoleEditor"):
                        kind = cls._kind_from_identifier(handler.get(key))
                        if kind:
                            return kind
            for handler in handlers:
                if not isinstance(handler, dict):
                    continue
                if handler.get("LSHandlerContentType") != "com.apple.default-app.web-browser":
                    continue
                for key in ("LSHandlerRoleAll", "LSHandlerRoleViewer", "LSHandlerRoleEditor"):
                    kind = cls._kind_from_identifier(handler.get(key))
                    if kind:
                        return kind
        except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, TypeError, ValueError):
            return None
        return None

    @classmethod
    def _windows_default_kind(cls) -> BrowserKind | None:
        try:
            import winreg

            for scheme in ("http", "https"):
                key_path = (
                    "Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\"
                    f"{scheme}\\UserChoice"
                )
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                kind = cls._kind_from_identifier(prog_id)
                if kind:
                    return kind
        except (ImportError, OSError):
            return None
        return None

    @classmethod
    def _linux_default_kind(cls) -> BrowserKind | None:
        try:
            result = subprocess.run(
                ["xdg-settings", "get", "default-url-scheme-handler", "http"],
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            if result.returncode == 0:
                return cls._kind_from_identifier(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
        return None

    @classmethod
    def system_default_kind(cls) -> BrowserKind | None:
        """Return the supported browser selected by the operating system."""
        if sys.platform == "darwin":
            return cls._macos_default_kind()
        if sys.platform.startswith("win"):
            return cls._windows_default_kind()
        if sys.platform.startswith("linux"):
            return cls._linux_default_kind()
        return None

    @classmethod
    def select(cls, preference: str | None = None) -> BrowserInstallation:
        available = cls.detect()
        if not available:
            raise RuntimeError("Microsoft Edge or Google Chrome is required for Coupa sign-in.")
        requested = str(preference or os.environ.get("COUPA_AUTH_BROWSER", "auto")).strip().lower()
        if requested in {"edge", "msedge", "microsoft-edge"}:
            selected = next((item for item in available if item.kind is BrowserKind.EDGE), None)
            if selected:
                return selected
            raise RuntimeError("Microsoft Edge was selected for Coupa sign-in but was not found.")
        if requested in {"chrome", "google-chrome"}:
            selected = next((item for item in available if item.kind is BrowserKind.CHROME), None)
            if selected:
                return selected
            raise RuntimeError("Google Chrome was selected for Coupa sign-in but was not found.")

        system_default = cls.system_default_kind()
        if system_default:
            selected = next((item for item in available if item.kind is system_default), None)
            if selected:
                return selected

        # If the OS default is unsupported (for example Safari), choose a
        # deterministic supported fallback without changing the OS setting.
        return next(
            (
                item
                for kind in (BrowserKind.EDGE, BrowserKind.CHROME)
                for item in available
                if item.kind is kind
            ),
            available[0],
        )

    @classmethod
    def as_settings(cls, preference: str | None = None) -> dict[str, Any]:
        available = cls.detect()
        system_default = cls.system_default_kind()
        selected = None
        try:
            selected = cls.select(preference).kind.value
        except RuntimeError:
            pass
        requested = str(preference or os.environ.get("COUPA_AUTH_BROWSER", "auto")).strip().lower()
        source = "settings" if requested not in {"", "auto"} else (
            "system_default" if system_default and any(item.kind is system_default for item in available) else "fallback"
        )
        return {
            "available": [
                {"id": item.kind.value, "name": item.name, "path": item.executable}
                for item in available
            ],
            "selected": selected,
            "system_default": system_default.value if system_default else None,
            "system_default_name": cls._DISPLAY_NAMES.get(system_default) if system_default else None,
            "selection_source": source,
        }


@dataclass(frozen=True, slots=True)
class ProfileCandidate:
    user_data_dir: Path
    profile_name: str
    evidence: tuple[str, ...]
    selection_score: int = 0
    display_name: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ProfileDetection:
    state: str
    candidates: tuple[ProfileCandidate, ...] = ()
    message: str = ""
    available_profiles: tuple[str, ...] = ()
    code: str = ""

    @property
    def selected(self) -> ProfileCandidate | None:
        return self.candidates[0] if self.state == "profile_detected" and len(self.candidates) == 1 else None


class CorporateEdgeProfileDetector:
    """Find the existing Edge profile that contains the corporate account."""

    # Regional Unilever accounts can use different email suffixes. Match the
    # stable corporate marker rather than one exact domain.
    CORPORATE_ACCOUNT_MARKER = "@unilever"
    CORPORATE_DOMAIN = "@unilever.com"

    @staticmethod
    def edge_is_running() -> bool:
        if os.name == "nt":
            command = ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/NH"]
        elif sys.platform == "darwin":
            # Helpers, crash reporters, and the updater may outlive the main
            # process. A helper alone is not proof that the profile is locked;
            # the live SingletonLock owner is checked separately.
            command = ["pgrep", "-x", "Microsoft Edge"]
        else:
            command = ["pgrep", "-f", "microsoft-edge|msedge"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=3)
            if os.name == "nt":
                return result.returncode == 0 and "no tasks" not in result.stdout.lower()
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _profile_lock_markers(user_data_dir: Path) -> tuple[str, ...]:
        return tuple(
            marker
            for marker in ("SingletonLock", "SingletonCookie", "SingletonSocket")
            if (user_data_dir / marker).is_symlink() or (user_data_dir / marker).exists()
        )

    @classmethod
    def _profile_lock_status(cls, user_data_dir: Path) -> dict[str, object]:
        markers = cls._profile_lock_markers(user_data_dir)
        owner_pid = BrowserProfileManager._lock_owner_pid(user_data_dir)
        owner_alive = BrowserProfileManager._lock_owner_alive(user_data_dir)
        owner = BrowserProfileManager._process_info(owner_pid) if owner_alive and owner_pid is not None else None
        owner_is_edge = bool(owner and "Microsoft Edge" in owner[1])
        return {
            "markers": markers,
            "owner_pid": owner_pid,
            "owner_alive": owner_alive,
            "owner_is_edge": owner_is_edge,
            "blocking": bool(owner_alive and (owner_is_edge or owner is None)),
        }

    @classmethod
    def _profile_lock_exists(cls, user_data_dir: Path) -> bool:
        return bool(cls._profile_lock_status(user_data_dir)["blocking"])

    @staticmethod
    def _mac_edge_process_count() -> int | None:
        if sys.platform != "darwin":
            return None
        try:
            result = subprocess.run(
                ["pgrep", "-f", "Microsoft Edge"],
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 1:
            return 0
        if result.returncode != 0:
            return None
        return len([line for line in result.stdout.splitlines() if line.strip()])

    def environment_status(self) -> dict[str, object]:
        """Return support-safe Edge process and profile-lock diagnostics."""
        user_data_dir = self._user_data_dir()
        lock = self._profile_lock_status(user_data_dir)
        return {
            "user_data_exists": user_data_dir.is_dir(),
            "main_process_running": self.edge_is_running(),
            "edge_process_count": self._mac_edge_process_count(),
            **lock,
        }

    @staticmethod
    def _user_data_dir() -> Path:
        if os.name == "nt":
            return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Microsoft/Edge/User Data"
        if sys.platform == "darwin":
            return Path.home() / "Library/Application Support/Microsoft Edge"
        return Path.home() / ".config/microsoft-edge"

    @staticmethod
    def _account_identity(preferences: object) -> dict[str, object]:
        """Read only account-identity fields from Preferences.

        This intentionally ignores URLs, titles, bookmarks, workspaces,
        ``custom_links`` and every other non-identity string. An arbitrary
        ``@unilever`` occurrence outside these fields is never proof that a
        profile belongs to the corporate account.
        """
        result: dict[str, object] = {
            "emails": [],
            "tenant_ids": [],
            "account_types": [],
            "aad": False,
        }
        if not isinstance(preferences, dict):
            return result
        accounts = preferences.get("account_info", [])
        if isinstance(accounts, list):
            for account in accounts:
                if not isinstance(account, dict):
                    continue
                email = account.get("email")
                if isinstance(email, str) and email.strip():
                    result["emails"].append(email.strip())  # type: ignore[union-attr]
                tenant = account.get("edge_account_tenant_id")
                if isinstance(tenant, str) and tenant.strip():
                    result["tenant_ids"].append(tenant.strip())  # type: ignore[union-attr]
                account_type = account.get("edge_account_type")
                if (
                    account_type is not None
                    and str(account_type).strip()
                    and str(account_type).strip().casefold() not in {"0", "none"}
                ):
                    result["account_types"].append(str(account_type).strip())  # type: ignore[union-attr]
                if account.get("is_relative_to_aad") is True:
                    result["aad"] = True
        profile = preferences.get("profile")
        if isinstance(profile, dict) and profile.get("is_relative_to_aad") is True:
            result["aad"] = True
        return result

    @staticmethod
    def _profile_identity(profile_metadata: object) -> dict[str, object]:
        """Read only identity metadata from ``Local State`` info_cache."""
        result: dict[str, object] = {
            "user_name": "",
            "gaia_name": "",
            "hosted_domain": "",
            "display_name": "",
            "consented": False,
        }
        if not isinstance(profile_metadata, dict):
            return result
        for key in ("user_name", "gaia_name", "hosted_domain"):
            value = profile_metadata.get(key)
            if isinstance(value, str):
                result[key] = value.strip()
        display = profile_metadata.get("name") or profile_metadata.get("shortcut_name")
        result["display_name"] = str(display).strip() if display else ""
        result["consented"] = profile_metadata.get("is_consented_primary_account") is True
        return result

    @classmethod
    def _identity_score(
        cls,
        profile_name: str,
        profile_metadata: object,
        preferences: object,
    ) -> tuple[int, tuple[str, ...], str, bool]:
        """Rank a profile from identity fields only.

        Returns ``(score, safe_evidence_paths, reason, is_corporate)``.
        ``is_corporate`` is true only when a corporate identity field matches
        ``@unilever``; ranking signals such as tenant id or AAD are never
        sufficient proof on their own.
        """
        account = cls._account_identity(preferences)
        meta = cls._profile_identity(profile_metadata)
        score = 0
        evidence: list[str] = []
        reasons: list[str] = []
        corporate_proof = False

        for index, email in enumerate(account["emails"]):
            if cls.CORPORATE_ACCOUNT_MARKER in str(email).casefold():
                score += 100
                evidence.append(f"Preferences.account_info[{index}].email")
                reasons.append("account email contains @unilever")
                corporate_proof = True

        for field in ("user_name", "gaia_name"):
            value = str(meta[field])
            if value and cls.CORPORATE_ACCOUNT_MARKER in value.casefold():
                score += 50
                evidence.append(f"Local State.profile.info_cache.{field}")
                reasons.append(f"{field} contains @unilever")
                corporate_proof = True

        hosted_domain = str(meta["hosted_domain"])
        if "unilever" in hosted_domain.casefold():
            score += 20
            evidence.append("Local State.profile.info_cache.hosted_domain")
            reasons.append("hosted_domain contains unilever")
            corporate_proof = True

        # Ranking-only signals. They resolve ties between corporate profiles
        # but never select a non-@unilever profile on their own.
        if account["tenant_ids"]:
            score += 40
            evidence.append("Preferences.account_info.edge_account_tenant_id")
        if account["account_types"]:
            score += 30
            evidence.append("Preferences.account_info.edge_account_type")
        if account["aad"]:
            score += 25
            evidence.append("Preferences.profile.is_relative_to_aad")
        if meta["consented"]:
            score += 10
            evidence.append("Local State.profile.info_cache.is_consented_primary_account")

        display_name = str(meta["display_name"])
        work_terms = ("work", "corporate", "business", "enterprise", "professional")
        if "unilever" in display_name.casefold():
            score += 5
            evidence.append("Local State.profile.info_cache.name")
            reasons.append("profile name contains unilever")
        elif any(term in display_name.casefold() for term in work_terms):
            score += 5
            evidence.append("Local State.profile.info_cache.name")
            reasons.append("profile name contains a work term")

        return score, tuple(dict.fromkeys(evidence)), "; ".join(reasons), corporate_proof

    @staticmethod
    def _display_name(profile_metadata: object) -> str:
        if not isinstance(profile_metadata, dict):
            return ""
        value = profile_metadata.get("name") or profile_metadata.get("shortcut_name")
        return str(value).strip() if value else ""

    @staticmethod
    def _read_json(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def detect(self, *, ignore_running: bool = False) -> ProfileDetection:
        user_data_dir = self._user_data_dir()
        if not ignore_running and (self.edge_is_running() or self._profile_lock_exists(user_data_dir)):
            return ProfileDetection(
                "edge_must_be_closed",
                message="Quit Microsoft Edge completely with ⌘Q so the existing work session can be captured.",
                code="EDGE_PROFILE_IN_USE",
            )

        if not user_data_dir.is_dir():
            return ProfileDetection(
                "action_required",
                message="The Microsoft Edge user-data directory was not found. Open Edge once and sign in with the work account.",
                code="EDGE_PROFILE_NOT_FOUND",
            )

        local_state = self._read_json(user_data_dir / "Local State")
        info_cache = local_state.get("profile", {}).get("info_cache", {}) if isinstance(local_state, dict) else {}
        candidates: list[ProfileCandidate] = []
        profile_names = set(info_cache) if isinstance(info_cache, dict) else set()
        profile_names.update(
            path.name
            for path in user_data_dir.iterdir()
            if path.is_dir() and (path.name == "Default" or path.name.startswith("Profile "))
        )
        available_profiles = tuple(sorted(profile_names, key=str.casefold))

        for profile_name in sorted(profile_names):
            profile_dir = user_data_dir / profile_name
            if not profile_dir.is_dir():
                continue
            profile_metadata = info_cache.get(profile_name) if isinstance(info_cache, dict) else None
            preferences = self._read_json(profile_dir / "Preferences")
            score, evidence, reason, is_corporate = self._identity_score(
                profile_name, profile_metadata, preferences
            )
            if is_corporate:
                candidates.append(
                    ProfileCandidate(
                        user_data_dir,
                        profile_name,
                        evidence,
                        score,
                        self._display_name(profile_metadata),
                        reason,
                    )
                )

        if len(candidates) == 1:
            return ProfileDetection(
                "profile_detected",
                tuple(candidates),
                f"Detected the Microsoft Edge work profile {candidates[0].profile_name} among "
                f"{len(available_profiles)} available profile(s).",
                available_profiles,
            )
        if len(candidates) > 1:
            ranked = sorted(
                candidates,
                key=lambda candidate: (-candidate.selection_score, candidate.profile_name.casefold()),
            )
            preferred, runner_up = ranked[0], ranked[1]
            if preferred.selection_score > runner_up.selection_score:
                return ProfileDetection(
                    "profile_detected",
                    (preferred,),
                    f"Selected the Microsoft Edge work profile {preferred.profile_name} because it is "
                    f"the strongest @unilever match among {len(available_profiles)} available profile(s).",
                    available_profiles,
                )
            return ProfileDetection(
                "action_required",
                tuple(ranked),
                "More than one Microsoft Edge profile contains an @unilever account, and no "
                "preferred work profile could be determined. Choose the work profile before continuing. "
                f"Available profiles: {', '.join(available_profiles)}.",
                available_profiles,
                code="EDGE_PROFILE_AMBIGUOUS",
            )
        return ProfileDetection(
            "action_required",
            message="No Microsoft Edge profile containing @unilever was detected. "
            f"Available profiles: {', '.join(available_profiles) or 'none'}. "
            "Sign in to the corporate profile and try again.",
            available_profiles=available_profiles,
            code="EDGE_PROFILE_NOT_FOUND",
        )

    def wait_until_closed(self, timeout: float = 60.0) -> bool:
        deadline = time.monotonic() + timeout
        user_data_dir = self._user_data_dir()
        while self.edge_is_running() or self._profile_lock_exists(user_data_dir):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)
        return True


class EdgeDevToolsConnector:
    """Discover only a loopback DevTools endpoint for an existing Edge."""

    DEFAULT_ADDRESS = "127.0.0.1:9222"

    @staticmethod
    def _is_loopback(address: str) -> bool:
        host = address.rsplit(":", 1)[0].strip("[]").casefold()
        return host in {"127.0.0.1", "localhost", "::1"}

    @classmethod
    def _addresses(cls, user_data_dir: Path | None = None) -> tuple[str, ...]:
        values: list[str] = []
        explicit = os.environ.get("COUPA_EDGE_DEBUGGER_ADDRESS", "").strip()
        if explicit:
            values.append(explicit)

        if user_data_dir is None:
            if os.name == "nt":
                user_data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Microsoft/Edge/User Data"
            elif sys.platform == "darwin":
                user_data_dir = Path.home() / "Library/Application Support/Microsoft Edge"
            else:
                user_data_dir = Path.home() / ".config/microsoft-edge"
        if user_data_dir:
            active_port_files = [user_data_dir / "DevToolsActivePort"]
            try:
                active_port_files.extend(
                    profile / "DevToolsActivePort"
                    for profile in user_data_dir.iterdir()
                    if profile.is_dir() and (profile.name == "Default" or profile.name.startswith("Profile "))
                )
            except OSError:
                pass
            for active_port_file in active_port_files:
                try:
                    port = int(active_port_file.read_text(encoding="utf-8").splitlines()[0])
                    if 1 <= port <= 65535:
                        values.append(f"127.0.0.1:{port}")
                except (OSError, TypeError, ValueError, IndexError):
                    continue

        values.append(cls.DEFAULT_ADDRESS)
        return tuple(dict.fromkeys(value for value in values if cls._is_loopback(value)))

    @staticmethod
    def _is_edge_endpoint(address: str) -> bool:
        try:
            request = Request(
                f"http://{address}/json/version",
                headers={"Accept": "application/json"},
            )
            with urlopen(request, timeout=0.5) as response:  # nosec B310 - loopback is enforced above
                payload = json.loads(response.read().decode("utf-8"))
            browser = str(payload.get("Browser") or payload.get("browser") or "")
            return "Microsoft Edge" in browser or "Edg/" in browser
        except (OSError, URLError, TimeoutError, TypeError, ValueError, json.JSONDecodeError):
            return False

    @classmethod
    def discover(cls, user_data_dir: Path | None = None) -> str | None:
        """Return a local Edge debugger address, if an existing session exposes one."""
        for address in cls._addresses(user_data_dir):
            if cls._is_edge_endpoint(address):
                return address
        return None


class EdgeDriverResolver:
    """Resolve a driver matching the installed Edge before Selenium starts it."""

    @staticmethod
    def _version(value: str) -> tuple[int, ...]:
        match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)", value or "")
        return tuple(int(part) for part in match.group(1).split(".")) if match else ()

    @classmethod
    def _versions_compatible(cls, driver_version: tuple[int, ...], browser_version: tuple[int, ...]) -> bool:
        """A driver matches when the first three components match Edge."""
        if not driver_version or not browser_version:
            return True
        return driver_version[:3] == browser_version[:3]

    @classmethod
    def _browser_version(cls, installation: BrowserInstallation) -> tuple[int, ...]:
        executable = Path(installation.executable)
        if not executable.is_file():
            return ()
        if sys.platform == "darwin":
            try:
                with (executable.parents[1] / "Info.plist").open("rb") as stream:
                    version = plistlib.load(stream).get("CFBundleShortVersionString")
                parsed = cls._version(str(version or ""))
                if parsed:
                    return parsed
            except (OSError, plistlib.InvalidFileException, TypeError, ValueError):
                pass
        try:
            result = subprocess.run(
                [str(executable), "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            return cls._version(f"{result.stdout} {result.stderr}")
        except (OSError, subprocess.SubprocessError):
            return ()

    @staticmethod
    def _cache_root() -> Path:
        configured = os.environ.get("SE_CACHE_PATH", "").strip()
        return Path(configured).expanduser() if configured else Path.home() / ".cache" / "selenium"

    @classmethod
    def _cached_drivers(cls) -> list[Path]:
        root = cls._cache_root() / "msedgedriver"
        try:
            return [
                path
                for path in root.glob("*/*/msedgedriver")
                if path.is_file() and os.access(path, os.X_OK)
            ]
        except OSError:
            return []

    @classmethod
    def _driver_version(cls, path: Path) -> tuple[int, ...]:
        try:
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            return cls._version(f"{result.stdout} {result.stderr}")
        except (OSError, subprocess.SubprocessError):
            return ()

    @classmethod
    def resolve(cls, installation: BrowserInstallation) -> str | None:
        """Prefer an exact cached EdgeDriver, then defer to Selenium Manager."""
        if installation.kind is not BrowserKind.EDGE or not Path(installation.executable).is_file():
            return None

        browser_version = cls._browser_version(installation)
        candidates = [(path, cls._driver_version(path)) for path in cls._cached_drivers()]
        if browser_version:
            exact = [path for path, version in candidates if version == browser_version]
            if exact:
                return str(sorted(exact, key=str)[-1])
            compatible = [
                path
                for path, version in candidates
                if len(version) >= 3 and len(browser_version) >= 3 and version[:3] == browser_version[:3]
            ]
            if compatible:
                return str(sorted(compatible, key=str)[-1])

        try:
            from selenium.webdriver.common.selenium_manager import SeleniumManager

            result = SeleniumManager().binary_paths(["--browser", "edge"])
            path = result.get("driver_path") if isinstance(result, dict) else None
            if not path or not Path(path).is_file():
                return None
            # Never trust Selenium Manager blindly: validate the downloaded
            # driver against the installed Edge before returning it.
            driver_version = cls._driver_version(Path(path))
            if browser_version and driver_version and not cls._versions_compatible(driver_version, browser_version):
                return None
            return str(path)
        except Exception:
            return None


class BrowserProfileManager:
    """Own and register only profiles created for app authentication."""

    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root).expanduser() if root else Path.home() / ".contract_downloader" / "browser_profiles"
        self.legacy_edge_profile = self.root.parent / "edge_auth_profile"
        self.manifest_path = self.root.parent / "browser_profiles.json"

    @staticmethod
    def _timestamp() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _read_manifest(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
            return {"profiles": profiles} if isinstance(profiles, dict) else {"profiles": {}}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {"profiles": {}}

    def _write_manifest(self, payload: dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_name(f".{self.manifest_path.name}.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.manifest_path)
            os.chmod(self.manifest_path, 0o600)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Could not register the app-owned browser profile: {exc}") from exc

    def path_for(self, kind: BrowserKind) -> Path:
        # New profiles live under browser_profiles/<browser>. Reuse the legacy
        # Edge location when it already exists so upgrades do not force a new
        # sign-in. Neither path is a user's normal browser profile.
        canonical = self.root / kind.value
        if kind is BrowserKind.EDGE and self.legacy_edge_profile.exists() and not canonical.exists():
            return self.legacy_edge_profile
        return canonical

    def ensure(self, kind: BrowserKind) -> Path:
        path = self.path_for(kind)
        path.mkdir(parents=True, exist_ok=True)
        if self.is_locked(path):
            recovered = self._reap_orphaned_webdriver(path) or self.clear_stale_lock(path)
            if not recovered:
                raise RuntimeError(f"Close the Contract Downloader sign-in browser before retrying {kind.value} sign-in.")
        try:
            os.chmod(self.root.parent, 0o700)
            os.chmod(self.root, 0o700)
            os.chmod(path, 0o700)
        except OSError:
            pass
        manifest = self._read_manifest()
        previous = manifest["profiles"].get(kind.value, {})
        manifest["profiles"][kind.value] = {
            "kind": kind.value,
            "path": str(path),
            "created_at": previous.get("created_at") or self._timestamp(),
            "last_used_at": self._timestamp(),
        }
        self._write_manifest(manifest)
        return path

    def info(self, kind: BrowserKind) -> dict[str, Any]:
        record = self._read_manifest()["profiles"].get(kind.value, {})
        path = self.path_for(kind)
        return {
            "id": kind.value,
            "path": str(path),
            "exists": path.exists(),
            "registered": bool(record),
            "created_at": record.get("created_at"),
            "last_used_at": record.get("last_used_at"),
        }

    @staticmethod
    def _lock_owner_pid(path: Path) -> int | None:
        lock = path / "SingletonLock"
        if not lock.is_symlink():
            return None
        try:
            target = os.readlink(lock)
        except OSError:
            return None
        match = re.search(r"-(\d+)$", target)
        return int(match.group(1)) if match else None

    @classmethod
    def _lock_owner_alive(cls, path: Path) -> bool:
        pid = cls._lock_owner_pid(path)
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    @staticmethod
    def _process_info(pid: int) -> tuple[int, str] | None:
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=,command=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            line = result.stdout.strip()
            if result.returncode != 0 or not line:
                return None
            parent, command = line.split(maxsplit=1)
            return int(parent), command
        except (OSError, subprocess.SubprocessError, TypeError, ValueError):
            return None

    @classmethod
    def _reap_orphaned_webdriver(cls, path: Path) -> bool:
        """Stop only an orphaned WebDriver tree using this app-owned profile."""
        if sys.platform != "darwin":
            return False
        owner_pid = cls._lock_owner_pid(path)
        owner = cls._process_info(owner_pid) if owner_pid is not None else None
        if not owner:
            return False
        parent_pid, owner_command = owner
        profile_argument = f"--user-data-dir={path}"
        if profile_argument not in owner_command or "--test-type=webdriver" not in owner_command:
            return False

        process_ids = [owner_pid]
        if parent_pid != 1:
            parent = cls._process_info(parent_pid)
            if not parent or parent[0] != 1 or "msedgedriver" not in parent[1]:
                return False
            process_ids.append(parent_pid)

        for pid in process_ids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError:
                return False

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and cls._lock_owner_alive(path):
            time.sleep(0.1)
        return cls.clear_stale_lock(path)

    @classmethod
    def clear_stale_lock(cls, path: Path) -> bool:
        """Remove orphaned Chromium lock markers from an app-owned profile."""
        if cls._lock_owner_alive(path):
            return False
        removed = False
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            marker = path / name
            if marker.is_symlink() or marker.exists():
                try:
                    marker.unlink()
                    removed = True
                except OSError:
                    return False
        return removed

    @classmethod
    def is_locked(cls, path: Path) -> bool:
        # Chromium creates one of these markers for a live user-data root. We
        # inspect only the app-owned profile, never the user's personal profile.
        if cls._lock_owner_alive(path):
            return True
        return any((path / name).is_symlink() or (path / name).exists() for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"))

    def clear(self, kind: BrowserKind | None = None) -> list[str]:
        kinds = [kind] if kind else list(BrowserKind)
        manifest = self._read_manifest()
        targets: list[tuple[BrowserKind, Path]] = []
        for item in kinds:
            selected = self.path_for(item)
            targets.append((item, selected))
            if item is BrowserKind.EDGE and self.legacy_edge_profile != selected and self.legacy_edge_profile.exists():
                targets.append((item, self.legacy_edge_profile))

        removed: list[str] = []
        for item, path in targets:
            if path.exists():
                if self.is_locked(path) and not self.clear_stale_lock(path):
                    raise RuntimeError(f"Close the Contract Downloader sign-in browser before resetting {path.name}.")
                try:
                    shutil.rmtree(path)
                except OSError as exc:
                    raise RuntimeError(f"Could not reset the app-owned browser profile: {exc}") from exc
                removed.append(path.name)
            manifest["profiles"].pop(item.value, None)
        if manifest["profiles"]:
            self._write_manifest(manifest)
        else:
            try:
                self.manifest_path.unlink(missing_ok=True)
            except OSError as exc:
                raise RuntimeError(f"Could not clear the browser profile registry: {exc}") from exc
        return removed


def build_browser_options(
    installation: BrowserInstallation,
    profile_dir: Path,
    *,
    headless: bool = False,
    profile_name: str | None = None,
    debugger_address: str | None = None,
) -> EdgeOptions | ChromeOptions:
    options: EdgeOptions | ChromeOptions
    if installation.kind is BrowserKind.EDGE:
        options = EdgeOptions()
    else:
        options = ChromeOptions()
    options.page_load_strategy = "eager"
    options.binary_location = installation.executable
    if debugger_address:
        options.debugger_address = debugger_address
        return options
    options.add_argument(f"--user-data-dir={profile_dir}")
    if profile_name:
        options.add_argument(f"--profile-directory={profile_name}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if headless:
        options.add_argument("--headless=new")
    # These flags only reduce Selenium's automation banner. They do not bypass
    # Coupa authentication or inject credentials.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def open_browser_profile_setup(
    installation: BrowserInstallation,
    profile_dir: Path,
) -> subprocess.Popen[bytes]:
    """Open account setup outside WebDriver so the OS sign-in broker can render."""
    browser_arguments = [
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    command = [installation.executable, *browser_arguments]
    if sys.platform == "darwin":
        app_bundle = Path(installation.executable).parents[2]
        command = ["open", "-n", "-a", str(app_bundle), "--args", *browser_arguments]
    try:
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError(
            f"Could not open {installation.name} profile setup: {exc}"
        ) from exc


class SeleniumBrowserLauncher:
    DRIVER_STARTUP_TIMEOUT = 20.0

    def __init__(self) -> None:
        self.last_diagnostics: dict[str, object] = {}

    @staticmethod
    def _version_label(version: tuple[int, ...]) -> str | None:
        return ".".join(str(part) for part in version) if version else None

    def _context(
        self,
        installation: BrowserInstallation,
        driver_path: str | None,
        service: EdgeDriverService | None,
        elapsed: float,
    ) -> dict[str, object]:
        browser_version = self._version_label(EdgeDriverResolver._browser_version(installation))
        driver_version = self._version_label(EdgeDriverResolver._driver_version(Path(driver_path))) if driver_path else None
        return {
            "browser": installation.name,
            "browser_version": browser_version,
            "driver_version": driver_version,
            "driver_path": str(driver_path) if driver_path else None,
            "port": getattr(service, "port", None) if service is not None else None,
            "elapsed_ms": int(elapsed * 1000),
        }

    @staticmethod
    def _kill_service_tree(service: EdgeDriverService | None) -> None:
        """Stop only the WebDriver service started by this launcher."""
        if service is None:
            return
        process = getattr(service, "process", None)
        if process is None or process.poll() is not None:
            return
        pid = process.pid
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        else:
            # Terminate Edge children spawned by msedgedriver first, then the
            # driver. ``pkill -P`` targets only descendants of the driver we
            # just started; it never touches a user's existing Edge window.
            try:
                subprocess.run(
                    ["pkill", "-TERM", "-P", str(pid)],
                    capture_output=True,
                    check=False,
                    timeout=3,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=3)
            except (OSError, subprocess.SubprocessError):
                pass
        except (OSError, subprocess.SubprocessError):
            pass

    @staticmethod
    def _is_default_edge_data_dir(profile_dir: Path) -> bool:
        try:
            return profile_dir.resolve() == CorporateEdgeProfileDetector._user_data_dir().resolve()
        except OSError:
            return False

    def _create_driver(
        self,
        installation: BrowserInstallation,
        options: EdgeOptions | ChromeOptions,
        service: EdgeDriverService | None,
    ) -> Any:
        if installation.kind is BrowserKind.EDGE:
            if service is not None:
                return webdriver.Edge(options=options, service=service)
            return webdriver.Edge(options=options)
        return webdriver.Chrome(options=options)

    def launch(
        self,
        installation: BrowserInstallation,
        profile_dir: Path,
        *,
        headless: bool = False,
        profile_name: str | None = None,
        debugger_address: str | None = None,
    ) -> Any:
        options = build_browser_options(
            installation,
            profile_dir,
            headless=headless,
            profile_name=profile_name,
            debugger_address=debugger_address,
        )
        driver_path = EdgeDriverResolver.resolve(installation)
        service = EdgeDriverService(executable_path=driver_path) if driver_path else None
        previous_socket_timeout = socket.getdefaulttimeout()
        started = time.monotonic()
        self.last_diagnostics = {}
        watchdog_fired = False
        try:
            socket.setdefaulttimeout(self.DRIVER_STARTUP_TIMEOUT)
            # Session creation can block for 60-120s inside msedgedriver when
            # Edge never produces DevToolsActivePort. Run it on a daemon thread
            # and bound the wait so a stalled handshake surfaces within 20s and
            # the service process is reaped instead of orphaned.
            result_holder: dict[str, Any] = {}
            error_holder: dict[str, BaseException] = {}
            done = threading.Event()

            def _run_driver() -> None:
                try:
                    result_holder["driver"] = self._create_driver(installation, options, service)
                except BaseException as exc:  # noqa: BLE001 - re-raised on caller thread
                    error_holder["error"] = exc
                finally:
                    done.set()

            worker = threading.Thread(target=_run_driver, name="edge-driver-start", daemon=True)
            worker.start()
            done.wait(timeout=self.DRIVER_STARTUP_TIMEOUT)
            if not done.is_set():
                watchdog_fired = True
                self._kill_service_tree(service)
                context = self._context(installation, driver_path, service, time.monotonic() - started)
                self.last_diagnostics = context
                if self._is_default_edge_data_dir(profile_dir) and not debugger_address:
                    raise RuntimeError(
                        "[EDGE_REMOTE_DEBUGGING_REFUSED] Microsoft Edge blocks WebDriver remote "
                        "debugging for its default profile directory, so the detected corporate "
                        "@unilever profile cannot be opened automatically. Sign in once using the "
                        "app profile, or start Microsoft Edge with remote debugging on a "
                        "non-default data directory and retry."
                    )
                raise RuntimeError(
                    f"[EDGE_DRIVER_START_TIMEOUT] Could not start {installation.name} within "
                    f"{self.DRIVER_STARTUP_TIMEOUT:g} seconds "
                    f"(Edge {context['browser_version']}, EdgeDriver {context['driver_version']}). "
                    "A previous WebDriver process may still be attached; the app will clean up "
                    "orphaned drivers on the next attempt."
                )
            if "error" in error_holder:
                raise error_holder["error"]
            return result_holder["driver"]
        except Exception as exc:
            if service is not None:
                try:
                    service.stop()
                except Exception:
                    pass
            if watchdog_fired:
                raise
            elapsed = time.monotonic() - started
            self.last_diagnostics = self._context(installation, driver_path, service, elapsed)
            detail = str(exc).casefold()
            if "read timed out" in detail or "httpconnectionpool" in detail or "max retries exceeded" in detail:
                raise RuntimeError(
                    f"[EDGE_DRIVER_START_TIMEOUT] Could not start {installation.name} within "
                    f"{self.DRIVER_STARTUP_TIMEOUT:g} seconds. Check that Edge and EdgeDriver are not "
                    "blocked by a stale process, then retry."
                ) from exc
            if "devtoolsactiveport" in detail:
                if debugger_address:
                    raise RuntimeError(
                        "[EDGE_DEVTOOLS_ATTACH_FAILED] Could not attach to the running Microsoft Edge "
                        f"session at {debugger_address}. Enable remote debugging and try again."
                    ) from exc
                if self._is_default_edge_data_dir(profile_dir):
                    raise RuntimeError(
                        "[EDGE_REMOTE_DEBUGGING_REFUSED] Microsoft Edge blocks WebDriver remote "
                        "debugging for its default profile directory, so the detected corporate "
                        "@unilever profile cannot be opened automatically. Sign in once using the app "
                        "profile, or start Microsoft Edge with remote debugging on a non-default data "
                        "directory and retry."
                    ) from exc
                profile_label = f"'{profile_name}'" if profile_name else "the default"
                raise RuntimeError(
                    "[EDGE_DRIVER_START_TIMEOUT] "
                    f"Microsoft Edge did not expose a DevTools port for profile {profile_label}. "
                    "Close any stale Edge process, clear the driver cache, and retry."
                ) from exc
            if "user data directory is already in use" in detail or "chrome not reachable" in detail:
                profile_label = f"'{profile_name}'" if profile_name else "the default"
                raise RuntimeError(
                    "[EDGE_PROFILE_IN_USE] "
                    f"Could not start {installation.name} for Coupa sign-in. "
                    f"The selected Edge profile {profile_label} is still in use, or another "
                    "authentication driver is still attached to it. Quit Microsoft Edge completely "
                    "with ⌘Q, wait a few seconds, and try again."
                ) from exc
            if "only supports microsoft edge version" in detail:
                raise RuntimeError(
                    "[EDGE_DRIVER_VERSION_MISMATCH] Microsoft Edge and EdgeDriver are incompatible. "
                    "Run host diagnostics and update Microsoft Edge before retrying."
                ) from exc
            raise RuntimeError(
                f"[BROWSER_START_FAILED] Could not start {installation.name} for Coupa sign-in. "
                "Run host diagnostics for the browser and driver details."
            ) from exc
        finally:
            socket.setdefaulttimeout(previous_socket_timeout)


def _list_msedgedriver_processes() -> list[tuple[int, int]]:
    """Return ``(pid, ppid)`` tuples for running msedgedriver processes."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "wmic",
                    "process",
                    "where",
                    "name='msedgedriver.exe'",
                    "get",
                    "ProcessId,ParentProcessId",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        processes: list[tuple[int, int]] = []
        for line in result.stdout.splitlines():
            numeric = [field for field in line.split(",") if field.strip().isdigit()]
            # wmic CSV rows end with ProcessId,ParentProcessId.
            if len(numeric) >= 2:
                processes.append((int(numeric[-1]), int(numeric[-2])))
        return processes

    try:
        result = subprocess.run(
            ["pgrep", "-x", "msedgedriver"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    processes: list[tuple[int, int]] = []
    for raw_pid in result.stdout.splitlines():
        pid = raw_pid.strip()
        if not pid.isdigit():
            continue
        try:
            parent = subprocess.run(
                ["ps", "-o", "ppid=", "-p", pid],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if parent.isdigit():
            processes.append((int(pid), int(parent)))
    return processes


def _is_orphan_driver(ppid: int) -> bool:
    if os.name == "nt":
        # On Windows a dead parent leaves the child re-parented to a system
        # process; conservatively treat 0/1 as orphaned and rely on the driver
        # holding no live session.
        return ppid in (0, 1)
    return ppid == 1


def _terminate_driver(pid: int) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def reap_orphaned_msedgedrivers() -> list[int]:
    """Terminate only orphaned WebDriver service processes.

    A failed session creation can leave ``msedgedriver`` reparented to
    ``launchd``/``init`` (ppid 1 on POSIX) while the Selenium ``Service`` object
    is already gone. These orphans hold a local port and confuse later launches.
    Only drivers whose parent is dead are terminated; a live Edge browser or a
    driver owned by another process is never touched.
    """
    reaped: list[int] = []
    for pid, ppid in _list_msedgedriver_processes():
        if not _is_orphan_driver(ppid):
            continue
        _terminate_driver(pid)
        reaped.append(pid)
    # Escalate only for survivors we already signalled on POSIX; ``reaped``
    # still lists every orphaned driver we terminated so callers can report it.
    if reaped and os.name != "nt":
        time.sleep(0.5)
        for pid in list(reaped):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            except OSError:
                continue
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
    return reaped


class BrowserLogin:
    """Perform the visible, user-driven login and return Coupa cookies."""

    def __init__(
        self,
        launcher: SeleniumBrowserLauncher | None = None,
        *,
        base_url: str = COUPA_URL,
        poll_interval: float = 0.25,
        wait_timeout: float = 300.0,
        final_navigation_timeout: float = 15.0,
        profile_setup_launcher: Callable[[BrowserInstallation, Path], Any] | None = None,
    ):
        self.launcher = launcher or SeleniumBrowserLauncher()
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.wait_timeout = wait_timeout
        self.final_navigation_timeout = final_navigation_timeout
        self.profile_setup_launcher = profile_setup_launcher or open_browser_profile_setup
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Ask an in-flight ``capture`` to stop waiting for user sign-in."""
        self._cancel_event.set()

    @staticmethod
    def _report(callback: Callable[[str, str], None] | None, state: str, message: str) -> None:
        if callback:
            callback(state, message)

    @staticmethod
    def _auth_redirect(url: str) -> bool:
        lowered = url.lower()
        return any(marker in lowered for marker in AUTH_REDIRECT_MARKERS)

    @staticmethod
    def _url(driver: Any) -> str:
        try:
            return str(driver.current_url or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _has_session_cookie(driver: Any) -> bool:
        try:
            cookie = driver.get_cookie("_coupa_session")
            return bool(cookie and cookie.get("value"))
        except Exception:
            return False

    @staticmethod
    def _window_handles(driver: Any) -> list[str]:
        try:
            return [str(handle) for handle in driver.window_handles]
        except Exception:
            return []

    @staticmethod
    def _profile_has_browser_account(profile_dir: Path) -> bool:
        try:
            preferences = json.loads(
                (profile_dir / "Default" / "Preferences").read_text(encoding="utf-8")
            )
            return bool(preferences.get("account_info"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def _authenticated_window(self, driver: Any) -> str | None:
        """Find a logged-in window, including SSO-created tabs/windows.

        Edge/Chrome may leave an initial new-tab window open while an SSO
        redirect completes in another window. Selenium's ``current_url`` only
        describes the active handle, so checking one handle can miss a valid
        login indefinitely.
        """
        for handle in self._window_handles(driver):
            try:
                driver.switch_to.window(handle)
                if self._is_authenticated(driver):
                    return handle
            except WebDriverException:
                continue
        return None

    @staticmethod
    def _cookies(driver: Any) -> dict[str, str]:
        try:
            return {
                str(cookie.get("name")): str(cookie.get("value"))
                for cookie in driver.get_cookies()
                if cookie.get("name") and cookie.get("value") is not None
            }
        except WebDriverException:
            return {}

    def _is_authenticated(self, driver: Any, url: str | None = None) -> bool:
        current = url if url is not None else self._url(driver)
        return (
            "unilever.coupahost.com" in current
            and not self._auth_redirect(current)
            and self._has_session_cookie(driver)
        )

    @staticmethod
    def _wait_for_profile_unlock(profile_dir: Path) -> None:
        deadline = time.monotonic() + 5.0
        while BrowserProfileManager.is_locked(profile_dir):
            if BrowserProfileManager.clear_stale_lock(profile_dir):
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Close the browser profile setup window before continuing Coupa sign-in."
                )
            time.sleep(0.1)

    @classmethod
    def _close_profile_setup(cls, process: Any, profile_dir: Path) -> None:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass
        owner_pid = BrowserProfileManager._lock_owner_pid(profile_dir)
        if owner_pid is not None and BrowserProfileManager._lock_owner_alive(profile_dir):
            try:
                os.kill(owner_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError as exc:
                raise RuntimeError(
                    "Close the browser profile setup window before continuing Coupa sign-in."
                ) from exc
        cls._wait_for_profile_unlock(profile_dir)

    def capture(
        self,
        installation: BrowserInstallation,
        profile_dir: Path,
        *,
        headless: bool = False,
        status_callback: Callable[[str, str], None] | None = None,
        existing_profile: bool = False,
        profile_name: str | None = None,
        debugger_address: str | None = None,
        attached_session: bool = False,
    ) -> dict[str, str]:
        self._report(
            status_callback,
            "starting",
            (
                "Connecting to the existing Microsoft Edge DevTools session…"
                if attached_session
                else (
                    f"Opening the detected Microsoft Edge work profile {profile_name or ''}…"
                    if existing_profile
                    else f"Opening {installation.name} with the Contract Downloader profile…"
                )
            ),
        )
        driver = None
        profile_setup = None
        self._cancel_event.clear()
        try:
            login_url = f"{self.base_url}/order_headers"
            if attached_session:
                self._report(
                    status_callback,
                    "capturing_session",
                    "Capturing the existing Coupa SSO session through Edge DevTools…",
                )
            elif existing_profile:
                self._report(
                    status_callback,
                    "capturing_session",
                    "Capturing the existing Coupa SSO session in the detected Edge work profile…",
                )
            elif not headless and not self._profile_has_browser_account(profile_dir):
                sso_note = (
                    "Click the profile icon, choose Sign in, and select your work account. "
                    "Sync is not required; Coupa will open automatically for SSO."
                    if installation.kind is BrowserKind.EDGE
                    else "Click the profile icon and sign in. Coupa will open automatically for SSO "
                    "when your organization enables it in Chrome."
                )
                self._report(
                    status_callback,
                    "user_action_required",
                    f"Sign in to this dedicated {installation.name} profile with your work account. {sso_note}",
                )
                self._wait_for_profile_unlock(profile_dir)
                try:
                    profile_setup = self.profile_setup_launcher(installation, profile_dir)
                    deadline = time.monotonic() + min(self.wait_timeout, 90.0)
                    while time.monotonic() < deadline:
                        if self._profile_has_browser_account(profile_dir):
                            break
                        time.sleep(self.poll_interval)
                finally:
                    if profile_setup is not None:
                        self._close_profile_setup(profile_setup, profile_dir)
                        profile_setup = None

                account_connected = self._profile_has_browser_account(profile_dir)
                if not account_connected and installation.kind is BrowserKind.EDGE:
                    raise TimeoutError(
                        "The dedicated Edge profile was not connected. Try again and sign in from the profile icon."
                    )
                message = (
                    "Browser profile connected; opening Coupa with SSO…"
                    if account_connected
                    else "Browser profile setup was not completed; opening the Coupa sign-in…"
                )
                self._report(status_callback, "checking", message)

            driver = self.launcher.launch(
                installation,
                profile_dir,
                headless=headless,
                profile_name=profile_name,
                debugger_address=debugger_address,
            )
            try:
                driver.get(login_url)
            except WebDriverException as exc:
                raise RuntimeError(f"Could not open Coupa in {installation.name}: {exc}") from exc
            handles = self._window_handles(driver)
            if len(handles) > 1:
                self._report(
                    status_callback,
                    "checking",
                    "Multiple browser windows detected; checking the Coupa session in each one…",
                )

            authenticated_handle = self._authenticated_window(driver)
            sso_deadline = time.monotonic() + min(self.wait_timeout, 3.0)
            while not authenticated_handle and time.monotonic() < sso_deadline:
                time.sleep(self.poll_interval)
                authenticated_handle = self._authenticated_window(driver)

            if authenticated_handle:
                self._report(status_callback, "checking", "Coupa is open; checking the current session…")
            else:
                self._report(
                    status_callback,
                    "waiting_sso",
                    f"Waiting for SSO… Complete the Coupa sign-in in {installation.name}.",
                )

            deadline = time.monotonic() + self.wait_timeout
            while not authenticated_handle:
                if self._cancel_event.is_set():
                    raise RuntimeError("[COUPA_SSO_CANCELLED] Coupa sign-in was cancelled.")
                if time.monotonic() >= deadline:
                    raise TimeoutError("[COUPA_SSO_TIMEOUT] Timed out waiting for the Coupa sign-in to complete.")
                time.sleep(self.poll_interval)
                authenticated_handle = self._authenticated_window(driver)

            self._report(status_callback, "validating", "Sign-in detected; validating the Coupa session…")
            try:
                driver.switch_to.window(authenticated_handle)
                driver.get(login_url)
            except WebDriverException as exc:
                raise RuntimeError(f"Could not validate the Coupa session in {installation.name}: {exc}") from exc

            deadline = time.monotonic() + self.final_navigation_timeout
            authenticated_handle = self._authenticated_window(driver)
            while time.monotonic() < deadline and not authenticated_handle:
                time.sleep(self.poll_interval)
                authenticated_handle = self._authenticated_window(driver)

            if not authenticated_handle:
                raise RuntimeError(
                    "[COUPA_SESSION_NOT_FOUND] The Coupa sign-in completed, but the authenticated Coupa window was not found."
                )
            driver.switch_to.window(authenticated_handle)
            cookies = self._cookies(driver)
            if not cookies.get("_coupa_session"):
                raise RuntimeError(
                    "[COUPA_SESSION_NOT_FOUND] The Coupa sign-in completed, but no Coupa session cookie was found."
                )
            return cookies
        finally:
            if profile_setup is not None:
                self._close_profile_setup(profile_setup, profile_dir)
            if driver is not None and attached_session:
                # Closing an attached WebDriver session must not close the
                # user's existing Edge window or its SSO session.
                service = getattr(driver, "service", None)
                stop = getattr(service, "stop", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        pass
            elif driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
