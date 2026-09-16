import json
import plistlib
from pathlib import Path

import build_python_portable as portable
import build


def test_embedded_python_download_is_pinned():
    assert portable.PYTHON_EMBED_URL.startswith("https://www.python.org/ftp/python/")
    assert len(portable.PYTHON_EMBED_SHA256) == 64
    int(portable.PYTHON_EMBED_SHA256, 16)


def test_portable_dependencies_exclude_test_and_packaging_tools():
    dependencies = portable._project_dependencies()

    assert any(value.startswith("pywebview") for value in dependencies)
    assert any(value.startswith("truststore") for value in dependencies)
    assert not any(value.startswith("pytest") for value in dependencies)
    assert not any(value.startswith("pyinstaller") for value in dependencies)


def test_portable_launcher_uses_official_pythonw_and_manual_updates(monkeypatch, tmp_path):
    bundle = tmp_path / "portable"
    runtime = bundle / "runtime"
    app = bundle / "app"
    runtime.mkdir(parents=True)
    app.mkdir()
    monkeypatch.setattr(portable, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(portable, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(portable, "APP_DIR", app)

    portable._write_launchers()

    launcher = (bundle / "Start-ContractDownloader.cmd").read_text(encoding="ascii")
    python_launcher = (app / "launcher.py").read_text(encoding="utf-8")
    metadata = json.loads((bundle / "contract-downloader.json").read_text(encoding="utf-8"))
    assert "COUPA_PYTHON_PORTABLE=1" in launcher
    assert "Unblock-File" in launcher
    assert ".zone-unblocked" in launcher
    assert "runtime\\pythonw.exe" in launcher
    assert "Contract Downloader" in launcher
    assert "startup.log" in launcher
    diagnostics = (bundle / "ContractDownloader-Diagnostics.cmd").read_text(encoding="ascii")
    assert "find_spec" in diagnostics
    assert "import src.main" not in diagnostics
    assert (bundle / "LEIA-ME.txt").is_file()
    assert (bundle / "INSTRUCOES_CONTRACT_DOWNLOADER.md").is_file()
    assert "runpy.run_path" in python_launcher
    assert metadata["automatic_update_check_default"] is False
    assert metadata["manual_updates"] is True


def test_windows_build_launcher_uses_the_native_executable_and_icon():
    launcher = (Path(build.PROJECT_ROOT) / "build_windows.cmd").read_text(encoding="ascii")

    assert "build.py --windows" in launcher
    assert "dist\\ContractDownloader.exe" in launcher
    assert (Path(build.PROJECT_ROOT) / "icon.ico").is_file()


def test_build_increments_patch_version(monkeypatch, tmp_path):
    version_file = tmp_path / ".version"
    version_file.write_text("1.4.9\n", encoding="utf-8")
    monkeypatch.setattr(build, "VERSION_FILE", version_file)

    previous, current = build.bump_version()

    assert previous == "1.4.9"
    assert current == "1.4.10"
    assert version_file.read_text(encoding="utf-8") == "1.4.10\n"


def test_macos_bundle_version_updates_info_plist(monkeypatch, tmp_path):
    bundle = tmp_path / "ContractDownloader.app"
    info_plist = bundle / "Contents" / "Info.plist"
    info_plist.parent.mkdir(parents=True)
    info_plist.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "0.0.0"}))
    calls = []
    monkeypatch.setattr(build.subprocess, "check_call", lambda command: calls.append(command))

    build._set_macos_bundle_version(bundle, "2.3.4")

    metadata = plistlib.loads(info_plist.read_bytes())
    assert metadata["CFBundleShortVersionString"] == "2.3.4"
    assert metadata["CFBundleVersion"] == "2.3.4"
    assert calls == [["codesign", "--force", "--deep", "--sign", "-", str(bundle)]]
