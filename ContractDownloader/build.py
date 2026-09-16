"""
Build script for Contract Downloader portable executables.

Usage:
    uv run --group build python build.py          # build for current OS
    uv run --group build python build.py --macos   # macOS .app bundle
    uv run --group build python build.py --windows # Windows .exe (must run on Windows!)

Requirements:
    - Target OS: must build on the same OS you're targeting
    - macOS: creates .app bundle inside dist/
    - Windows: creates single .exe inside dist/
"""

import os
import plistlib
import sys
import subprocess
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "ContractDownloader"
ENTRY_POINT = str(PROJECT_ROOT / "src" / "main.py")
WEB_ASSETS_SRC = str(PROJECT_ROOT / "src" / "gui" / "web")
# The frozen app resolves assets from _MEIPASS/gui/web. Keep the package
# destination independent from the source tree's src/ prefix.
WEB_ASSETS_DEST = os.path.join("gui", "web")
VERSION_FILE = PROJECT_ROOT / ".version"

# Packages that PyInstaller may miss (no explicit import but loaded dynamically)
HIDDEN_IMPORTS = [
    "extract_msg",
    "fpdf",
    "bs4",
    "lxml",
    "pandas",
    "openpyxl",
    "pyxlsb",
    "httpx",
    "webview",
    "selenium",
    "selenium.webdriver.edge",
    "selenium.webdriver.edge.webdriver",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.webdriver",
    "src.auth",
    "src.auth.browser",
    "src.auth.cookie_store",
    "src.auth.models",
    "src.auth.service",
    "src.auth.session_validator",
    "src.powerbi_provider",
    "asyncio",
    "json",
    "sqlite3",
    "tkinter",
    "process_all_pos",
]

# Pillow's optional WebP extension can point to a virtual ``.dylibs`` path
# that PyInstaller 6.20 does not materialize correctly in a macOS bundle.
# The application only needs Pillow for screenshot/image handling, not WebP.
EXCLUDED_IMPORTS = ["PIL._webp"]


def _increment_version(value: str) -> str:
    parts = value.strip().lstrip("vV").split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid application version: {value!r}. Expected MAJOR.MINOR.PATCH.")
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


def bump_version() -> tuple[str, str]:
    current = VERSION_FILE.read_text(encoding="utf-8").strip()
    next_version = _increment_version(current)
    VERSION_FILE.write_text(f"{next_version}\n", encoding="utf-8")
    return current, next_version


def _set_macos_bundle_version(bundle: Path, version: str) -> None:
    info_plist = bundle / "Contents" / "Info.plist"
    with info_plist.open("rb") as stream:
        metadata = plistlib.load(stream)
    metadata["CFBundleShortVersionString"] = version
    metadata["CFBundleVersion"] = version
    with info_plist.open("wb") as stream:
        plistlib.dump(metadata, stream, fmt=plistlib.FMT_BINARY)
    subprocess.check_call(["codesign", "--force", "--deep", "--sign", "-", str(bundle)])


def get_separator() -> str:
    """PyInstaller uses ; on Windows, : on POSIX for --add-data."""
    return ";" if sys.platform.startswith("win") else ":"


def clean_dist():
    """Remove previous build artifacts."""
    for folder in ["dist", "build"]:
        path = PROJECT_ROOT / folder
        if path.exists():
            print(f"  Cleaning {folder}/ ...")
            shutil.rmtree(path, ignore_errors=True)
    spec_file = PROJECT_ROOT / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()


def build():
    print("=" * 60)
    print(f"  Building {APP_NAME} for {sys.platform}")
    print("=" * 60)

    clean_dist()

    previous_version, application_version = bump_version()
    print(f"  Version: {previous_version} -> {application_version}")

    is_windows = sys.platform.startswith("win")
    is_macos = sys.platform == "darwin"
    sep = get_separator()

    # Base command. macOS uses onedir because a .app bundle cannot be a
    # meaningful one-file artifact; Windows remains a single portable EXE.
    packaging_mode = "--onedir" if is_macos else "--onefile"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        packaging_mode,
        "--name", APP_NAME,
        "--windowed",  # no console window in GUI mode
        "--clean",
        "--noconfirm",
    ]

    # Add hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    for imp in EXCLUDED_IMPORTS:
        cmd.extend(["--exclude-module", imp])

    # Add web assets (HTML/CSS/JS for the GUI) and release version metadata.
    cmd.append(f"--add-data={WEB_ASSETS_SRC}{sep}{WEB_ASSETS_DEST}")
    if VERSION_FILE.exists():
        cmd.append(f"--add-data={VERSION_FILE}{sep}.")

    # macOS-specific: create .app bundle with icon
    if is_macos:
        cmd.extend([
            "--osx-bundle-identifier", "com.contractdownloader.app",
        ])
        # Look for an icon file
        icon_path = PROJECT_ROOT / "icon.icns"
        if icon_path.exists():
            cmd.append(f"--icon={icon_path}")
            print(f"  Using icon: {icon_path}")

    # Windows-specific metadata. Do not request elevation: the portable app
    # should run with the user's normal permissions.
    if is_windows:
        icon_candidates = [
            PROJECT_ROOT / "icon.ico",
            PROJECT_ROOT / "src" / "gui" / "web" / "favicon.ico",
        ]
        for icon_path in icon_candidates:
            if icon_path.exists():
                cmd.append(f"--icon={icon_path}")
                print(f"  Using icon: {icon_path}")
                break

    cmd.append(ENTRY_POINT)

    print(f"\n  Command: {' '.join(cmd)}\n")

    try:
        subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))
    except subprocess.CalledProcessError as e:
        VERSION_FILE.write_text(f"{previous_version}\n", encoding="utf-8")
        print(f"\n[ERROR] Build failed with exit code: {e.returncode}")
        sys.exit(1)

    # Keep the historical project-root shortcut in sync with the release
    # artifact. Users of this project commonly launch this exact .app path.
    if is_macos:
        built_bundle = PROJECT_ROOT / "dist" / f"{APP_NAME}.app"
        _set_macos_bundle_version(built_bundle, application_version)
        shortcut_bundle = PROJECT_ROOT / f"{APP_NAME}.app"
        executable = shortcut_bundle / "Contents" / "MacOS" / APP_NAME
        running = False
        if executable.exists():
            probe = subprocess.run(
                ["pgrep", "-f", str(executable)],
                capture_output=True,
                text=True,
                check=False,
            )
            running = probe.returncode == 0 and bool(probe.stdout.strip())
        if built_bundle.exists() and running:
            print(f"  [WARN] App is running; skipped project-root sync: {shortcut_bundle}")
            print(f"     Signed build remains available at: {built_bundle}")
        elif built_bundle.exists():
            if shortcut_bundle.exists():
                shutil.rmtree(shortcut_bundle, ignore_errors=True)
            subprocess.check_call(["ditto", str(built_bundle), str(shortcut_bundle)])
            print(f"  Synced project-root app: {shortcut_bundle}")

    # Show result
    dist_dir = PROJECT_ROOT / "dist"
    if dist_dir.exists():
        print("\n" + "=" * 60)
        print("  [OK] Build completed!")
        print("=" * 60)
        for f in sorted(dist_dir.iterdir()):
            size_mb = f.stat().st_size / (1024 * 1024) if f.is_file() else 0
            if f.is_file():
                print(f"  FILE {f.name} ({size_mb:.1f} MB)")
            else:
                print(f"  DIR  {f.name}/")
        print(f"\n  Location: {dist_dir}")
    else:
        print("\n[WARN] dist/ folder not found - build may have failed silently.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build Contract Downloader executable")
    parser.add_argument(
        "--macos", action="store_true",
        help="Build for macOS (default on macOS)"
    )
    parser.add_argument(
        "--windows", action="store_true",
        help="Build for Windows (must run on Windows!)"
    )
    parser.add_argument(
        "--skip-clean", action="store_true",
        help="Skip cleaning previous build artifacts"
    )
    args = parser.parse_args()

    # Cross-compilation check
    if args.windows and not sys.platform.startswith("win"):
        print("[ERROR] Cannot build Windows .exe on macOS!")
        print("   PyInstaller does not support cross-compilation.")
        print("   Options:")
        print("   1. Build on a Windows machine/VM")
        print("   2. Use GitHub Actions (windows-latest runner)")
        print("   3. Use a CI service with Windows runners")
        sys.exit(1)

    if not args.skip_clean:
        clean_dist()

    build()
