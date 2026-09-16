"""E2E coverage for the isolated hierarchy sorter and final folder approval."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from scripts.gui_playwright_debug import RealBridge, start_server


INIT_BRIDGE_SCRIPT = """
window.pywebview = { api: new Proxy({}, { get: (t, name) => (...args) => window.__pw_api_call(name, args) }) };
window.addEventListener('pywebviewready', () => window.dispatchEvent(new Event('pywebviewready')));
"""

INPUT_CSV = (
    "PO_NUMBER;SUPPLIER;<|>;Region;Department\n"
    "PO001;ACME;;South;Finance\n"
    "PO002;ACME;;North;IT\n"
)

SORTABLE_SHA256 = "bf4241bc73fef7f11c59a283a69fe8051cdd31c6d8ff5a2b9ba219e7831fcf76"


@contextmanager
def hierarchy_page(
    tmp_path: Path,
    name: str,
    browser_name: str = "chromium",
) -> Iterator[tuple[Page, list[str]]]:
    """Open the real AppAPI bridge at hierarchy step 3 and clean up fully."""
    run_dir = tmp_path / name
    run_dir.mkdir()
    input_path = run_dir / f"{name}.csv"
    input_path.write_text(INPUT_CSV, encoding="utf-8")
    bridge = RealBridge(run_dir=run_dir)
    web_root = Path(__file__).resolve().parents[2] / "src" / "gui" / "web"
    server, _thread = start_server(web_root)
    page_errors: list[str] = []

    try:
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, browser_name)
            if not Path(browser_type.executable_path).exists():
                pytest.skip(f"Playwright {browser_name} runtime is not installed")
            browser = browser_type.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(20000)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.expose_function("__pw_api_call", lambda method, args: bridge.call(method, args))
            page.add_init_script(INIT_BRIDGE_SCRIPT)
            page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="domcontentloaded")
            page.locator("#file-input").set_input_files(str(input_path))
            expect(page.locator("#btn-next-input")).to_be_enabled(timeout=20000)
            expect(page.locator("#journey-top-action")).to_be_enabled(timeout=20000)
            page.click("#journey-top-action")
            expect(page.locator("#validation-feedback")).to_be_visible(timeout=20000)
            expect(page.locator("#journey-top-action")).to_be_enabled(timeout=20000)
            page.click("#journey-top-action")
            expect(page.locator("#hierarchy-sortable > li[data-column]").first).to_be_visible(timeout=20000)
            try:
                yield page, page_errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        bridge.close()


def hierarchy_dom_order(page: Page) -> list[str]:
    """Return fixed and reorderable levels in their visible DOM order."""
    return page.evaluate(
        """() => [
            ...[...document.querySelectorAll('#hierarchy-sortable > li[data-column]')]
                .map(node => node.dataset.column),
            document.querySelector('[data-fixed="po"]').dataset.fixed,
        ]"""
    )


def test_sortable_dependency_is_pinned_local_and_licensed() -> None:
    web_root = Path(__file__).resolve().parents[2] / "src" / "gui" / "web"
    library = web_root / "vendor" / "sortablejs" / "Sortable.min.js"
    license_file = web_root / "vendor" / "sortablejs" / "LICENSE"
    html = (web_root / "index.html").read_text(encoding="utf-8")

    assert hashlib.sha256(library.read_bytes()).hexdigest() == SORTABLE_SHA256
    assert "Sortable 1.15.7 - MIT" in library.read_text(encoding="utf-8")[:100]
    assert "MIT License" in license_file.read_text(encoding="utf-8")
    assert 'src="vendor/sortablejs/Sortable.min.js"' in html
    assert "cdn" not in html.lower()


@pytest.mark.parametrize("browser_name", ["chromium", "webkit"])
def test_drag_reorders_only_intermediate_levels(tmp_path: Path, browser_name: str) -> None:
    with hierarchy_page(tmp_path, f"hierarchy-drag-{browser_name}", browser_name) as (page, page_errors):
        movable = page.locator("#hierarchy-sortable > li[data-column]")
        assert movable.count() == 3
        assert page.evaluate("window.Sortable && window.Sortable.version") == "1.15.7"

        drag_handle = page.locator('#hierarchy-sortable > li[data-column="Region"] .drag-handle')
        last_item = movable.nth(2)
        handle_box = drag_handle.bounding_box()
        last_box = last_item.bounding_box()
        assert handle_box is not None and last_box is not None

        drag_x = handle_box["x"] + handle_box["width"] / 2
        drag_y = handle_box["y"] + handle_box["height"] / 2
        page.mouse.move(drag_x, drag_y)
        page.mouse.down()
        page.mouse.move(drag_x, drag_y + 8, steps=6)
        page.wait_for_selector(".hierarchy-drag-fallback")
        page.mouse.move(drag_x, last_box["y"] + last_box["height"] - 2, steps=18)
        page.mouse.up()
        page.wait_for_function(
            """() => [...document.querySelectorAll('#hierarchy-sortable > li[data-column]')]
            .map(node => node.dataset.column).join(',') === 'SUPPLIER,Department,Region'"""
        )

        assert hierarchy_dom_order(page) == ["SUPPLIER", "Department", "Region", "po"]
        assert "drag" in page.locator("#hierarchy-reorder-status").inner_text().lower()
        assert page.locator(".hierarchy-drag-fallback, .hierarchy-ghost, .hierarchy-chosen").count() == 0
        assert not page_errors, page_errors


def test_reorder_buttons_are_a_reliable_keyboard_alternative(tmp_path: Path) -> None:
    with hierarchy_page(tmp_path, "hierarchy-buttons") as (page, page_errors):
        region = page.locator('#hierarchy-sortable > li[data-column="Region"]')
        region.locator('[data-move-direction="down"]').click()

        assert hierarchy_dom_order(page) == ["SUPPLIER", "Department", "Region", "po"]
        assert page.locator('#hierarchy-sortable > li[data-column="SUPPLIER"] [data-move-direction="up"]').is_disabled()
        assert page.locator('#hierarchy-sortable > li[data-column="Region"] [data-move-direction="down"]').is_disabled()
        assert not page_errors, page_errors


def test_hierarchy_disable_survives_revalidation(tmp_path: Path) -> None:
    with hierarchy_page(tmp_path, "hierarchy-revalidate") as (page, page_errors):
        page.locator('[data-toggle-column="Region"]').click()
        assert page.locator('[data-reenable-column="Region"]').count() == 1
        page.locator('[data-journey-back="2"]').click()
        page.click("#btn-validate-file")
        expect(page.locator("#validation-feedback")).to_be_visible(timeout=20000)
        expect(page.locator("#journey-top-action")).to_be_enabled(timeout=20000)
        page.click("#journey-top-action")
        expect(page.locator("#hierarchy-disabled")).to_be_visible(timeout=20000)
        assert page.locator('[data-column="Region"]').count() == 0
        assert page.locator('[data-reenable-column="Region"]').count() == 1
        assert not page_errors, page_errors


def test_final_folder_approval_replaces_review_step(tmp_path: Path) -> None:
    with hierarchy_page(tmp_path, "final-folder-approval") as (page, page_errors):
        assert page.locator('[data-journey-step="4"]').count() == 0
        assert page.locator('[data-journey-panel="4"]').count() == 0
        assert page.locator("#folder-approval").is_visible()
        assert not page.locator("#btn-start-run").is_visible()
        assert page.locator("#journey-top-action").inner_text() == "Start download"
        assert page.locator("#journey-top-action").is_disabled()

        page.locator("#folder-approval").check()
        assert page.locator("#journey-top-action").is_enabled()
        assert not page_errors, page_errors
