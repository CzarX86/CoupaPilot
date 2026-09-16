@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo uv was not found. Install uv and run this file again.
    pause
    exit /b 1
)

echo Building the portable Contract Downloader Windows application...
uv run --group build python build.py --windows
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\ContractDownloader.exe
pause
