# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/main.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/gui/web', 'gui/web'), ('/Users/juliocezar/Dev/CoupaPilot/ContractDownloader/.version', '.')],
    hiddenimports=['extract_msg', 'fpdf', 'bs4', 'lxml', 'pandas', 'openpyxl', 'pyxlsb', 'httpx', 'webview', 'selenium', 'selenium.webdriver.edge', 'selenium.webdriver.edge.webdriver', 'selenium.webdriver.chrome', 'selenium.webdriver.chrome.webdriver', 'src.auth', 'src.auth.browser', 'src.auth.cookie_store', 'src.auth.models', 'src.auth.service', 'src.auth.session_validator', 'src.powerbi_provider', 'asyncio', 'json', 'sqlite3', 'tkinter', 'process_all_pos'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL._webp'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ContractDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/juliocezar/Dev/CoupaPilot/ContractDownloader/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ContractDownloader',
)
app = BUNDLE(
    coll,
    name='ContractDownloader.app',
    icon='/Users/juliocezar/Dev/CoupaPilot/ContractDownloader/icon.icns',
    bundle_identifier='com.contractdownloader.app',
)
