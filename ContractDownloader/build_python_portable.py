"""Build a transparent Windows bundle using the official embedded Python runtime.

The resulting directory is portable: it does not require Python installation and
avoids the self-extracting PyInstaller bootloader used by the single-file build.
This script must run on Windows so uv resolves Windows wheels.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
PRODUCT_NAME = "Contract Downloader"
PRODUCT_SLUG = "ContractDownloader"
PRODUCT_VERSION = (PROJECT_ROOT / ".version").read_text(encoding="utf-8").strip() if (PROJECT_ROOT / ".version").exists() else "1.0.0"
BUNDLE_NAME = "ContractDownloader-python-portable"
BUNDLE_DIR = DIST_DIR / BUNDLE_NAME
RUNTIME_DIR = BUNDLE_DIR / "runtime"
APP_DIR = BUNDLE_DIR / "app"
PYTHON_VERSION = "3.12.10"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
PYTHON_EMBED_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_runtime(cache_path: Path) -> None:
    if cache_path.exists() and _sha256(cache_path) == PYTHON_EMBED_SHA256:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading official Python {PYTHON_VERSION} embedded runtime...")
    urllib.request.urlretrieve(PYTHON_EMBED_URL, cache_path)
    actual = _sha256(cache_path)
    if actual != PYTHON_EMBED_SHA256:
        cache_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Embedded Python checksum mismatch: expected {PYTHON_EMBED_SHA256}, got {actual}"
        )


def _project_dependencies() -> list[str]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        data = tomllib.load(stream)
    return list(data["project"]["dependencies"])


def _configure_runtime() -> None:
    pth_files = list(RUNTIME_DIR.glob("python*._pth"))
    if len(pth_files) != 1:
        raise RuntimeError("Could not identify the embedded Python ._pth file")
    pth_files[0].write_text(
        "python312.zip\n.\nLib\nLib\\site-packages\n..\\app\nimport site\n",
        encoding="utf-8",
    )
    (RUNTIME_DIR / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def _install_dependencies() -> None:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to assemble the portable dependency directory")
    command = [
        uv,
        "pip",
        "install",
        "--target",
        str(RUNTIME_DIR / "Lib" / "site-packages"),
        "--python-version",
        "3.12",
        *_project_dependencies(),
    ]
    print("Installing Windows dependencies into the portable runtime...")
    subprocess.check_call(command, cwd=PROJECT_ROOT)


def _prune_windows_long_path_resources() -> None:
    """Remove optional lxml resources that trigger Explorer's 260-char limit."""
    optional_paths = [
        RUNTIME_DIR / "Lib" / "site-packages" / "lxml" / "isoschematron",
    ]
    for path in optional_paths:
        shutil.rmtree(path, ignore_errors=True)


def _copy_application() -> None:
    shutil.copytree(
        PROJECT_ROOT / "src",
        APP_DIR / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy2(PROJECT_ROOT / "process_all_pos.py", APP_DIR / "process_all_pos.py")
    shutil.copy2(PROJECT_ROOT / ".version", APP_DIR / ".version")


def _write_launchers() -> None:
    (APP_DIR / "launcher.py").write_text(
        '''from __future__ import annotations

import ctypes
import runpy
import traceback
from datetime import datetime
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parent.parent
MAIN = BUNDLE_DIR / "app" / "src" / "main.py"
LOG = BUNDLE_DIR / "startup.log"


def write_log(message: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as stream:
            stream.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\\n")
    except OSError:
        pass


write_log("Starting Contract Downloader")
try:
    runpy.run_path(str(MAIN), run_name="__main__")
except Exception:
    details = traceback.format_exc()
    write_log(details)
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Contract Downloader could not start.\\n\\nSee startup.log in the application folder.",
            "Contract Downloader",
            0x10,
        )
    except Exception:
        pass
    raise
''',
        encoding="utf-8",
    )
    (BUNDLE_DIR / "Start-ContractDownloader.cmd").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set \"COUPA_PYTHON_PORTABLE=1\"\r\n"
        "set \"COUPA_BUNDLE_DIR=%~dp0\"\r\n"
        "cd /d \"%~dp0\"\r\n"
        "if not exist \"%~dp0.zone-unblocked\" (\r\n"
        "  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"$ErrorActionPreference = 'Stop'; try { Get-ChildItem -LiteralPath $env:COUPA_BUNDLE_DIR -Recurse -File | Unblock-File; Set-Content -LiteralPath (Join-Path $env:COUPA_BUNDLE_DIR '.zone-unblocked') -Value 'ok' -Encoding ascii; exit 0 } catch { $_ | Out-File -FilePath (Join-Path $env:COUPA_BUNDLE_DIR 'startup.log') -Append; exit 1 }\"\r\n"
        "  if errorlevel 1 (echo Could not prepare the portable files. See startup.log. & pause & exit /b 1)\r\n"
        ")\r\n"
        "if not exist \"%~dp0runtime\\pythonw.exe\" (echo Portable Python runtime was not found. & pause & exit /b 1)\r\n"
        "start \"Contract Downloader\" \"%~dp0runtime\\pythonw.exe\" \"%~dp0app\\launcher.py\"\r\n"
        "exit /b 0\r\n",
        encoding="ascii",
    )
    (BUNDLE_DIR / "ContractDownloader-Diagnostics.cmd").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set \"COUPA_PYTHON_PORTABLE=1\"\r\n"
        "cd /d \"%~dp0\"\r\n"
        "\"%~dp0runtime\\python.exe\" -c \"import importlib.util, pathlib, sys; required=('webview','pandas','selenium','openpyxl','truststore'); missing=[name for name in required if importlib.util.find_spec(name) is None]; app=pathlib.Path(sys.argv[1]); app_missing=not (app/'src'/'main.py').is_file(); print('Portable runtime:', sys.version.split()[0]); print('Application files:', 'MISSING' if app_missing else 'OK'); print('Dependencies:', 'MISSING: '+', '.join(missing) if missing else 'OK'); raise SystemExit(1 if (missing or app_missing) else 0)\" \"%~dp0app\"\r\n"
        "pause\r\n",
        encoding="ascii",
    )
    (BUNDLE_DIR / "contract-downloader.json").write_text(
        json.dumps(
            {
                "format": 1,
                "application": PRODUCT_NAME,
                "version": PRODUCT_VERSION,
                "python": PYTHON_VERSION,
                "architecture": "x86_64",
                "automatic_update_check_default": False,
                "manual_updates": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (BUNDLE_DIR / "LEIA-ME.txt").write_text(
        "Contract Downloader - Windows portable edition\n"
        "===============================================\n\n"
        "Leia as instruções do arquivo INSTRUCOES_CONTRACT_DOWNLOADER.md antes de iniciar.\n\n"
        "Não é necessário instalar Python ou executar como administrador.\n"
        "Se o aplicativo não abrir, verifique startup.log nesta pasta.\n",
        encoding="utf-8",
    )
    shutil.copy2(
        PROJECT_ROOT / "docs" / "INSTRUCOES_CONTRACT_DOWNLOADER.md",
        BUNDLE_DIR / "INSTRUCOES_CONTRACT_DOWNLOADER.md",
    )


def _write_manifest() -> None:
    manifest = BUNDLE_DIR / "MANIFEST.sha256"
    lines = []
    for path in sorted(BUNDLE_DIR.rglob("*")):
        if path.is_file() and path != manifest:
            relative = path.relative_to(BUNDLE_DIR).as_posix()
            lines.append(f"{_sha256(path)}  {relative}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _smoke_test() -> None:
    python = RUNTIME_DIR / "python.exe"
    smoke_environment = dict(os.environ)
    smoke_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.check_call(
        [
            str(python),
            "-c",
            (
                "import bs4, extract_msg, httpx, lxml, openpyxl, pandas, selenium, truststore, webview; "
                "import src.main, process_all_pos; "
                "print('Portable import smoke test passed')"
            ),
        ],
        cwd=BUNDLE_DIR,
        env=smoke_environment,
    )


def build() -> Path:
    if not sys.platform.startswith("win"):
        raise SystemExit("[ERROR] The Python portable bundle must be built on Windows")

    shutil.rmtree(BUNDLE_DIR, ignore_errors=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    cache = PROJECT_ROOT / ".cache" / Path(PYTHON_EMBED_URL).name
    _download_runtime(cache)
    with zipfile.ZipFile(cache) as archive:
        archive.extractall(RUNTIME_DIR)
    _configure_runtime()
    _install_dependencies()
    _prune_windows_long_path_resources()
    _copy_application()
    _write_launchers()
    _smoke_test()
    _write_manifest()
    print(f"[OK] Python portable bundle created at {BUNDLE_DIR}")
    return BUNDLE_DIR


if __name__ == "__main__":
    build()
