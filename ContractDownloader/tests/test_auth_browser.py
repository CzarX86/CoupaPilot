import json
import plistlib
import signal
import socket
import time
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import WebDriverException

from src.auth.browser import (
    BrowserCatalog,
    BrowserInstallation,
    BrowserKind,
    BrowserLogin,
    BrowserProfileManager,
    EdgeDevToolsConnector,
    EdgeDriverResolver,
    SeleniumBrowserLauncher,
    _list_msedgedriver_processes,
    build_browser_options,
    open_browser_profile_setup,
    reap_orphaned_msedgedrivers,
)


def test_browser_catalog_uses_os_default_in_auto_mode(monkeypatch):
    available = [
        BrowserInstallation(BrowserKind.CHROME, "Google Chrome", "/chrome"),
        BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge"),
    ]
    monkeypatch.setattr(BrowserCatalog, "detect", classmethod(lambda cls: available))
    monkeypatch.setattr(
        BrowserCatalog,
        "system_default_kind",
        classmethod(lambda cls: BrowserKind.CHROME),
    )

    assert BrowserCatalog.select("auto").kind is BrowserKind.CHROME
    assert BrowserCatalog.select("chrome").kind is BrowserKind.CHROME


def test_browser_catalog_falls_back_to_edge_when_os_default_is_unsupported(monkeypatch):
    available = [
        BrowserInstallation(BrowserKind.CHROME, "Google Chrome", "/chrome"),
        BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge"),
    ]
    monkeypatch.setattr(BrowserCatalog, "detect", classmethod(lambda cls: available))
    monkeypatch.setattr(BrowserCatalog, "system_default_kind", classmethod(lambda cls: None))

    assert BrowserCatalog.select("auto").kind is BrowserKind.EDGE


def test_macos_default_browser_parser_maps_chrome(monkeypatch):
    payload = plistlib.dumps({
        "LSHandlers": [{
            "LSHandlerURLScheme": "http",
            "LSHandlerRoleAll": "com.google.Chrome",
        }],
    })
    monkeypatch.setattr("src.auth.browser.sys.platform", "darwin")
    monkeypatch.setattr(
        "src.auth.browser.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=payload),
    )

    assert BrowserCatalog.system_default_kind() is BrowserKind.CHROME


def test_browser_catalog_rejects_unavailable_explicit_browser(monkeypatch):
    monkeypatch.setattr(
        BrowserCatalog,
        "detect",
        classmethod(lambda cls: [BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")]),
    )

    try:
        BrowserCatalog.select("chrome")
    except RuntimeError as exc:
        assert "Google Chrome" in str(exc)
    else:
        raise AssertionError("Expected an unavailable-browser error")


def test_browser_profile_manager_removes_stale_chromium_locks(tmp_path):
    profile = tmp_path / "edge"
    profile.mkdir()
    (profile / "SingletonLock").symlink_to("Dead-Machine-999999")
    (profile / "SingletonCookie").symlink_to("dead-cookie")
    manager = BrowserProfileManager(tmp_path / "browser_profiles")
    manager.root.mkdir(parents=True, exist_ok=True)
    manager.path_for = lambda kind: profile
    assert manager.ensure(BrowserKind.EDGE) == profile
    assert not (profile / "SingletonLock").exists()


def test_browser_profile_manager_recovers_orphaned_webdriver_on_macos(monkeypatch, tmp_path):
    manager = BrowserProfileManager(tmp_path / "browser_profiles")
    profile = manager.path_for(BrowserKind.EDGE)
    profile.mkdir(parents=True)
    (profile / "SingletonLock").symlink_to("Test-Mac-4242")
    process_info = {
        4242: (5000, f"/Applications/Microsoft Edge --test-type=webdriver --user-data-dir={profile}"),
        5000: (1, "/cache/selenium/msedgedriver --port=12345"),
    }
    terminated = set()

    def fake_kill(pid, sig):
        if sig == 0:
            if pid in terminated:
                raise ProcessLookupError
            return
        assert sig == signal.SIGTERM
        terminated.add(pid)

    monkeypatch.setattr("src.auth.browser.sys.platform", "darwin")
    monkeypatch.setattr(BrowserProfileManager, "_process_info", staticmethod(process_info.get))
    monkeypatch.setattr("src.auth.browser.os.kill", fake_kill)

    assert manager.ensure(BrowserKind.EDGE) == profile
    assert terminated == {4242, 5000}
    assert not (profile / "SingletonLock").exists()


def test_browser_profile_manager_registers_dedicated_profile(tmp_path):
    manager = BrowserProfileManager(tmp_path / "browser_profiles")
    path = manager.ensure(BrowserKind.CHROME)

    manifest = json.loads((tmp_path / "browser_profiles.json").read_text(encoding="utf-8"))
    assert manifest["profiles"]["chrome"]["path"] == str(path)
    assert manager.info(BrowserKind.CHROME)["registered"] is True
    assert manager.info(BrowserKind.CHROME)["exists"] is True

    removed = manager.clear(BrowserKind.CHROME)
    assert removed == [path.name]
    assert not path.exists()
    assert not (tmp_path / "browser_profiles.json").exists()


def test_browser_login_detects_authenticated_second_window(tmp_path):
    class SwitchTo:
        def __init__(self, driver):
            self.driver = driver

        def window(self, handle):
            self.driver.active = handle

    class MultiWindowDriver:
        def __init__(self):
            self.active = "main"
            self.windows = {
                "main": {"url": "edge://newtab", "cookies": {}},
                "coupa": {
                    "url": "https://unilever.coupahost.com/order_headers",
                    "cookies": {"_coupa_session": "session-from-second-window"},
                },
            }
            self.switch_to = SwitchTo(self)

        @property
        def window_handles(self):
            return list(self.windows)

        @property
        def current_url(self):
            return self.windows[self.active]["url"]

        def get(self, url):
            self.windows[self.active]["url"] = url

        def get_cookie(self, name):
            value = self.windows[self.active]["cookies"].get(name)
            return {"name": name, "value": value} if value else None

        def get_cookies(self):
            return [
                {"name": name, "value": value}
                for name, value in self.windows[self.active]["cookies"].items()
            ]

        def quit(self):
            return None

    driver = MultiWindowDriver()

    class Launcher:
        def launch(self, *args, **kwargs):
            return driver

    login = BrowserLogin(Launcher(), poll_interval=0.001, wait_timeout=0.2, final_navigation_timeout=0.2)
    login._profile_has_browser_account = lambda profile_dir: True
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    statuses = []

    cookies = login.capture(installation, tmp_path / "profile", status_callback=lambda state, message: statuses.append((state, message)))

    assert cookies["_coupa_session"] == "session-from-second-window"
    assert any("Multiple browser windows" in message for _, message in statuses)


def test_browser_options_use_an_app_owned_profile(tmp_path):
    installation = BrowserInstallation(BrowserKind.CHROME, "Google Chrome", "/chrome")
    options = build_browser_options(installation, tmp_path / "profile")

    arguments = set(options.arguments)
    assert f"--user-data-dir={tmp_path / 'profile'}" in arguments
    assert "--no-first-run" in arguments
    assert options.binary_location == "/chrome"


def test_browser_options_use_edge_user_data_root_with_existing_profile_name(tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    options = build_browser_options(
        installation,
        tmp_path / "Microsoft Edge",
        profile_name="Profile 1",
    )

    arguments = set(options.arguments)
    assert f"--user-data-dir={tmp_path / 'Microsoft Edge'}" in arguments
    assert "--profile-directory=Profile 1" in arguments


def test_browser_options_attach_to_existing_edge_devtools_session(tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    options = build_browser_options(
        installation,
        tmp_path / "Microsoft Edge",
        profile_name="Profile 1",
        debugger_address="127.0.0.1:9222",
    )

    assert options.debugger_address == "127.0.0.1:9222"
    assert not any(argument.startswith("--user-data-dir=") for argument in options.arguments)
    assert not any(argument.startswith("--profile-directory=") for argument in options.arguments)


def test_edge_devtools_connector_accepts_an_existing_edge_endpoint(monkeypatch, tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"Browser":"Microsoft Edge/128.0.0.0"}'

    monkeypatch.setattr("src.auth.browser.urlopen", lambda request, timeout: Response())

    assert EdgeDevToolsConnector.discover(tmp_path) == "127.0.0.1:9222"


def test_edge_devtools_connector_reads_profile_level_active_port(monkeypatch, tmp_path):
    profile = tmp_path / "Default"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("9333\n/devtools/browser/test", encoding="utf-8")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"Browser":"Edg/151.0.0.0"}'

    seen = []
    monkeypatch.setattr(
        "src.auth.browser.urlopen",
        lambda request, timeout: (seen.append(request.full_url), Response())[1],
    )

    assert EdgeDevToolsConnector.discover(tmp_path) == "127.0.0.1:9333"
    assert seen[0].endswith(":9333/json/version")


def test_selenium_launcher_explains_devtools_active_port_failure(monkeypatch, tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")

    def fail_to_start(**kwargs):
        raise WebDriverException("session not created: DevToolsActivePort file doesn't exist")

    monkeypatch.setattr("src.auth.browser.webdriver.Edge", fail_to_start)

    with pytest.raises(RuntimeError, match="did not expose a DevTools port") as error:
        SeleniumBrowserLauncher().launch(installation, tmp_path / "Microsoft Edge", profile_name="Profile 1")
    assert "Profile 1" in str(error.value)


def test_selenium_launcher_maps_default_dir_devtools_failure_to_refusal(monkeypatch, tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    real_user_data = tmp_path / "Microsoft Edge"

    def fail_to_start(**kwargs):
        raise WebDriverException("session not created: DevToolsActivePort file doesn't exist")

    monkeypatch.setattr("src.auth.browser.webdriver.Edge", fail_to_start)
    monkeypatch.setattr(
        "src.auth.browser.CorporateEdgeProfileDetector._user_data_dir",
        staticmethod(lambda: real_user_data),
    )

    with pytest.raises(RuntimeError, match="EDGE_REMOTE_DEBUGGING_REFUSED"):
        SeleniumBrowserLauncher().launch(installation, real_user_data, profile_name="Default")


def test_selenium_launcher_watchdog_bounds_slow_session_creation(monkeypatch, tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    monkeypatch.setattr(EdgeDriverResolver, "resolve", classmethod(lambda cls, installation: None))
    monkeypatch.setattr(SeleniumBrowserLauncher, "DRIVER_STARTUP_TIMEOUT", 1.0)

    def slow_start(**kwargs):
        time.sleep(60)
        return object()

    monkeypatch.setattr("src.auth.browser.webdriver.Edge", slow_start)
    monkeypatch.setattr(
        SeleniumBrowserLauncher,
        "_is_default_edge_data_dir",
        staticmethod(lambda profile_dir: False),
    )

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="EDGE_DRIVER_START_TIMEOUT"):
        SeleniumBrowserLauncher().launch(installation, tmp_path / "profile")
    assert time.monotonic() - started < 5


def test_list_msedgedriver_processes_parses_pgrep_and_ps(monkeypatch):
    def fake_run(command, **kwargs):
        if command[:2] == ["pgrep", "-x"]:
            return SimpleNamespace(returncode=0, stdout="42\n77\n")
        if command[:3] == ["ps", "-o", "ppid="]:
            return SimpleNamespace(returncode=0, stdout="1\n" if command[-1] == "42" else "500\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("src.auth.browser.subprocess.run", fake_run)

    assert _list_msedgedriver_processes() == [(42, 1), (77, 500)]


def test_edge_driver_resolver_rejects_mismatched_selenium_manager_driver(monkeypatch, tmp_path):
    executable = tmp_path / "Microsoft Edge"
    executable.write_text("browser", encoding="utf-8")
    sm_driver = tmp_path / "msedgedriver"
    sm_driver.write_text("driver", encoding="utf-8")
    monkeypatch.setattr(
        EdgeDriverResolver,
        "_browser_version",
        classmethod(lambda cls, installation: (151, 0, 4129, 101)),
    )
    monkeypatch.setattr(EdgeDriverResolver, "_cached_drivers", classmethod(lambda cls: []))

    class FakeSeleniumManager:
        def binary_paths(self, args):
            return {"driver_path": str(sm_driver)}

    monkeypatch.setattr(
        "selenium.webdriver.common.selenium_manager.SeleniumManager",
        lambda: FakeSeleniumManager(),
    )
    monkeypatch.setattr(
        EdgeDriverResolver,
        "_driver_version",
        classmethod(lambda cls, path: (152, 0, 0, 0)),
    )
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", str(executable))

    assert EdgeDriverResolver.resolve(installation) is None


def test_browser_login_timeout_includes_coupa_sso_timeout_code(tmp_path):
    class NeverAuthDriver:
        def __init__(self):
            self.switch_to = SimpleNamespace(window=lambda handle: None)

        @property
        def window_handles(self):
            return ["main"]

        @property
        def current_url(self):
            return "https://unilever.coupahost.com/order_headers"

        def get_cookie(self, name):
            return None

        def get(self, url):
            return None

        def quit(self):
            return None

    class Launcher:
        def launch(self, *args, **kwargs):
            return NeverAuthDriver()

    login = BrowserLogin(Launcher(), poll_interval=0.001, wait_timeout=0.05)
    login._profile_has_browser_account = lambda profile_dir: True

    with pytest.raises(TimeoutError, match="COUPA_SSO_TIMEOUT"):
        login.capture(
            BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge"),
            tmp_path / "profile",
            existing_profile=True,
        )


def test_browser_login_reports_missing_coupa_session_cookie(tmp_path):
    class AuthButNoCookiesDriver:
        def __init__(self):
            self.switch_to = SimpleNamespace(window=lambda handle: None)

        @property
        def window_handles(self):
            return ["main"]

        @property
        def current_url(self):
            return "https://unilever.coupahost.com/order_headers"

        def get_cookie(self, name):
            return {"name": name, "value": "session"} if name == "_coupa_session" else None

        def get_cookies(self):
            return []

        def get(self, url):
            return None

        def quit(self):
            return None

    class Launcher:
        def launch(self, *args, **kwargs):
            return AuthButNoCookiesDriver()

    login = BrowserLogin(Launcher(), poll_interval=0.001, wait_timeout=0.1, final_navigation_timeout=0.1)
    login._profile_has_browser_account = lambda profile_dir: True

    with pytest.raises(RuntimeError, match="COUPA_SESSION_NOT_FOUND"):
        login.capture(
            BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge"),
            tmp_path / "profile",
            existing_profile=True,
        )


def test_reap_orphaned_msedgedrivers_only_kills_reparented_drivers(monkeypatch):
    def fake_run(command, **kwargs):
        if command[:2] == ["pgrep", "-x"]:
            return SimpleNamespace(returncode=0, stdout="4242\n7777\n")
        if command[:3] == ["ps", "-o", "ppid="]:
            pid = command[-1]
            return SimpleNamespace(returncode=0, stdout="1\n" if pid == "4242" else "500\n")
        return SimpleNamespace(returncode=0, stdout="")

    killed = []

    def fake_kill(pid, sig):
        if sig == 0:
            raise ProcessLookupError
        killed.append((pid, sig))

    monkeypatch.setattr("src.auth.browser.subprocess.run", fake_run)
    monkeypatch.setattr("src.auth.browser.os.kill", fake_kill)

    assert reap_orphaned_msedgedrivers() == [4242]
    assert killed == [(4242, signal.SIGTERM)]


def test_edge_driver_resolver_prefers_exact_cached_driver(monkeypatch, tmp_path):
    executable = tmp_path / "Microsoft Edge"
    executable.write_text("browser", encoding="utf-8")
    exact = tmp_path / "151.0.4129.93" / "msedgedriver"
    compatible = tmp_path / "151.0.4129.107" / "msedgedriver"
    exact.parent.mkdir()
    compatible.parent.mkdir()
    exact.write_text("driver", encoding="utf-8")
    compatible.write_text("driver", encoding="utf-8")
    monkeypatch.setattr("src.auth.browser.os.access", lambda path, mode: True)
    monkeypatch.setattr(
        EdgeDriverResolver,
        "_browser_version",
        classmethod(lambda cls, installation: (151, 0, 4129, 93)),
    )
    monkeypatch.setattr(EdgeDriverResolver, "_cached_drivers", classmethod(lambda cls: [compatible, exact]))
    monkeypatch.setattr(
        EdgeDriverResolver,
        "_driver_version",
        classmethod(lambda cls, path: cls._version(path.parent.name)),
    )

    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", str(executable))

    assert EdgeDriverResolver.resolve(installation) == str(exact)


def test_selenium_launcher_bounds_driver_start_timeout(monkeypatch, tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    monkeypatch.setattr(EdgeDriverResolver, "resolve", classmethod(lambda cls, installation: None))

    def fail_to_start(**kwargs):
        raise RuntimeError("HTTPConnectionPool(host='localhost', port=55842): Read timed out.")

    monkeypatch.setattr("src.auth.browser.webdriver.Edge", fail_to_start)
    previous_timeout = socket.getdefaulttimeout()

    with pytest.raises(RuntimeError, match="EDGE_DRIVER_START_TIMEOUT"):
        SeleniumBrowserLauncher().launch(installation, tmp_path / "profile")

    assert socket.getdefaulttimeout() == previous_timeout


def test_selenium_launcher_stops_driver_service_when_session_creation_fails(monkeypatch, tmp_path):
    installation = BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge")
    service = SimpleNamespace(stop=lambda: setattr(service, "stopped", True), stopped=False)
    monkeypatch.setattr(EdgeDriverResolver, "resolve", classmethod(lambda cls, installation: "/driver"))
    monkeypatch.setattr("src.auth.browser.EdgeDriverService", lambda executable_path: service)

    def fail_to_start(**kwargs):
        raise WebDriverException("session not created: user data directory is already in use")

    monkeypatch.setattr("src.auth.browser.webdriver.Edge", fail_to_start)

    with pytest.raises(RuntimeError, match="EDGE_PROFILE_IN_USE"):
        SeleniumBrowserLauncher().launch(installation, tmp_path / "profile")

    assert service.stopped is True


@pytest.mark.parametrize(
    "kind",
    [
        BrowserKind.EDGE,
        BrowserKind.CHROME,
    ],
)
def test_profile_setup_opens_natively_outside_webdriver(monkeypatch, tmp_path, kind):
    captured = {}
    process = SimpleNamespace()

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr("src.auth.browser.subprocess.Popen", fake_popen)
    monkeypatch.setattr("src.auth.browser.sys.platform", "darwin")
    app_name = "Microsoft Edge" if kind is BrowserKind.EDGE else "Google Chrome"
    executable = tmp_path / f"{app_name}.app" / "Contents" / "MacOS" / app_name

    result = open_browser_profile_setup(
        BrowserInstallation(kind, kind.value, str(executable)),
        tmp_path / "profile",
    )

    assert result is process
    assert captured["command"][:4] == ["open", "-n", "-a", str(executable.parents[2])]
    assert f"--user-data-dir={tmp_path / 'profile'}" in captured["command"]
    assert not any("coupahost.com" in argument for argument in captured["command"])


class ProfileOnboardingDriver:
    def __init__(self, *, auth_after_cookie_checks=None):
        self.current_url = ""
        self.visited = []
        self.cookie_checks = 0
        self.auth_after_cookie_checks = auth_after_cookie_checks
        self.switch_to = SimpleNamespace(window=lambda handle: None)

    @property
    def window_handles(self):
        return ["main"]

    def get(self, url):
        self.current_url = url
        self.visited.append(url)

    def get_cookie(self, name):
        self.cookie_checks += 1
        sso_ready = (
            self.cookie_checks >= self.auth_after_cookie_checks
            if self.auth_after_cookie_checks
            else bool(self.visited)
        )
        if sso_ready and name == "_coupa_session":
            return {"name": name, "value": "session"}
        return None

    def get_cookies(self):
        return [{"name": "_coupa_session", "value": "session"}]

    def quit(self):
        return None


class ProfileSetupProcess:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


def browser_login(driver, *, wait_timeout, setup_calls=None, events=None):
    flow = events if events is not None else []

    def launch_driver(*args, **kwargs):
        flow.append("webdriver")
        return driver

    launcher = SimpleNamespace(launch=launch_driver)
    calls = setup_calls if setup_calls is not None else []

    def open_setup(installation, profile_dir):
        flow.append("profile_setup")
        calls.append((installation.kind, profile_dir))
        return ProfileSetupProcess()

    return BrowserLogin(
        launcher,
        poll_interval=0.001,
        wait_timeout=wait_timeout,
        profile_setup_launcher=open_setup,
    )


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (BrowserKind.EDGE, "Microsoft Edge"),
        (BrowserKind.CHROME, "Google Chrome"),
    ],
)
def test_browser_login_onboards_work_account_then_opens_coupa(tmp_path, kind, name):
    driver = ProfileOnboardingDriver()
    setup_calls = []
    events = []
    login = browser_login(driver, wait_timeout=0.2, setup_calls=setup_calls, events=events)
    account_checks = iter([False, True, True])
    login._profile_has_browser_account = lambda profile_dir: next(account_checks)
    statuses = []

    login.capture(
        BrowserInstallation(kind, name, f"/{kind.value}"),
        tmp_path / "profile",
        status_callback=lambda state, message: statuses.append((state, message)),
    )

    assert driver.visited[:2] == [
        "https://unilever.coupahost.com/order_headers",
        "https://unilever.coupahost.com/order_headers",
    ]
    assert setup_calls == [(kind, tmp_path / "profile")]
    assert events[:2] == ["profile_setup", "webdriver"]
    assert any(f"dedicated {name} profile" in message for _, message in statuses)
    assert any("opening Coupa with SSO" in message for _, message in statuses)


def test_chrome_account_onboarding_falls_back_to_coupa_login(tmp_path):
    driver = ProfileOnboardingDriver()
    login = browser_login(driver, wait_timeout=0)
    login._profile_has_browser_account = lambda profile_dir: False
    statuses = []

    cookies = login.capture(
        BrowserInstallation(BrowserKind.CHROME, "Google Chrome", "/chrome"),
        tmp_path / "profile",
        status_callback=lambda state, message: statuses.append((state, message)),
    )

    assert cookies["_coupa_session"] == "session"
    assert any("profile setup was not completed" in message for _, message in statuses)


def test_edge_account_onboarding_never_falls_back_to_coupa_login(tmp_path):
    driver = ProfileOnboardingDriver()
    login = browser_login(driver, wait_timeout=0)
    login._profile_has_browser_account = lambda profile_dir: False

    with pytest.raises(TimeoutError, match="dedicated Edge profile"):
        login.capture(
            BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge"),
            tmp_path / "profile",
        )

    assert driver.visited == []


def test_existing_profile_sso_skips_profile_onboarding(tmp_path):
    driver = ProfileOnboardingDriver(auth_after_cookie_checks=2)
    setup_calls = []
    login = browser_login(driver, wait_timeout=0.1, setup_calls=setup_calls)
    login._profile_has_browser_account = lambda profile_dir: True

    login.capture(
        BrowserInstallation(BrowserKind.CHROME, "Google Chrome", "/chrome"),
        tmp_path / "profile",
    )

    assert driver.visited == ["https://unilever.coupahost.com/order_headers"] * 2
    assert setup_calls == []


def test_attached_devtools_session_does_not_quit_existing_edge(tmp_path):
    driver = ProfileOnboardingDriver(auth_after_cookie_checks=1)
    driver.quit_called = False
    driver.quit = lambda: setattr(driver, "quit_called", True)
    driver.service = SimpleNamespace(stop=lambda: setattr(driver, "service_stopped", True))
    login = BrowserLogin(
        SimpleNamespace(launch=lambda *args, **kwargs: driver),
        poll_interval=0.001,
        wait_timeout=0.1,
        final_navigation_timeout=0.1,
    )

    cookies = login.capture(
        BrowserInstallation(BrowserKind.EDGE, "Microsoft Edge", "/edge"),
        tmp_path / "profile",
        debugger_address="127.0.0.1:9222",
        attached_session=True,
    )

    assert cookies["_coupa_session"] == "session"
    assert driver.quit_called is False
    assert driver.service_stopped is True
