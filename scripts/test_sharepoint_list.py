#!/usr/bin/env python3
"""Create one test item in a SharePoint/Microsoft List using an Edge session.

This intentionally uses the signed-in browser UI instead of Graph. It is a
small integration probe for tenants where app registration is unavailable.
Close all Edge windows before running so Playwright can open the profile.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Frame, Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


DEFAULT_FIELDS = {
    "alias": "Supplier Alias",
    "wsc_code": "WSC_Code",
    "uu_name": "Supplier_UU",
}


def default_edge_profile() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Microsoft Edge"
    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Microsoft/Edge/User Data"
    return Path.home() / ".config/microsoft-edge"


def visible(locator: Locator) -> Locator | None:
    for index in range(locator.count()):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


def frames(page: Page) -> Iterable[Page | Frame]:
    yield page
    yield from page.frames


def click_first(page: Page, patterns: list[re.Pattern[str]], description: str) -> None:
    for frame in frames(page):
        for pattern in patterns:
            candidate = visible(frame.get_by_role("button", name=pattern))
            if candidate:
                candidate.click()
                return
    raise RuntimeError(f"Could not find the SharePoint {description} button.")


def fill_field(page: Page, label: str, value: str) -> None:
    # SharePoint sometimes exposes the display label and sometimes only the
    # input title/aria-label. Try all three without relying on generated IDs.
    escaped = re.escape(label.replace("_", " "))
    patterns = [
        re.compile(escaped.replace(r"\ ", r"[ _]"), re.IGNORECASE),
        re.compile(re.escape(label), re.IGNORECASE),
    ]
    for frame in frames(page):
        candidates = [
            frame.get_by_label(patterns[0]),
            frame.locator(f"input[aria-label*='{label}'], textarea[aria-label*='{label}']"),
            frame.locator(f"input[title*='{label}'], textarea[title*='{label}']"),
        ]
        for locator in candidates:
            target = visible(locator)
            if target:
                target.fill(value)
                return
    raise RuntimeError(f"Could not find the SharePoint field '{label}'.")


def logged_in(page: Page) -> bool:
    url = page.url.lower()
    if "login.microsoftonline.com" in url or "login.live.com" in url:
        return False
    for frame in frames(page):
        try:
            if visible(frame.get_by_role("heading", name=re.compile(r"sign in|entrar", re.I))):
                return False
        except Exception:
            pass
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-url", default=os.getenv("SHAREPOINT_LIST_URL"), required=not os.getenv("SHAREPOINT_LIST_URL"))
    parser.add_argument("--alias", default="TEST_Supplier_Python")
    parser.add_argument("--wsc-code", default="UU-TEST-PYTHON")
    parser.add_argument("--uu-name", default="Test Supplier Python")
    parser.add_argument("--profile-dir", type=Path, default=Path(os.getenv("EDGE_PROFILE_DIR", default_edge_profile())))
    parser.add_argument("--profile-name", default=os.getenv("EDGE_PROFILE_NAME", "Default"))
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.profile_dir.exists():
        print(f"Edge profile not found: {args.profile_dir}", file=sys.stderr)
        print("Pass --profile-dir or set EDGE_PROFILE_DIR.", file=sys.stderr)
        return 2

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(args.profile_dir),
                channel="msedge",
                headless=False,
                args=[f"--profile-directory={args.profile_name}"],
                accept_downloads=False,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(args.timeout_ms)
                page.goto(args.list_url, wait_until="domcontentloaded")

                if not logged_in(page):
                    print("Complete the Microsoft sign-in in the opened Edge window, then press Enter here.")
                    input()
                    page.goto(args.list_url, wait_until="domcontentloaded")

                page.wait_for_timeout(2_000)
                click_first(
                    page,
                    [re.compile(r"^new$", re.I), re.compile(r"^novo$", re.I), re.compile(r"new item", re.I)],
                    "New",
                )
                page.wait_for_timeout(1_000)

                fill_field(page, DEFAULT_FIELDS["alias"], args.alias)
                fill_field(page, DEFAULT_FIELDS["wsc_code"], args.wsc_code)
                fill_field(page, DEFAULT_FIELDS["uu_name"], args.uu_name)
                click_first(page, [re.compile(r"^save$", re.I), re.compile(r"^salvar$", re.I)], "Save")
                page.wait_for_timeout(2_000)

                created = visible(page.get_by_text(args.alias, exact=True))
                if not created:
                    print("The form was submitted, but the new item was not visible in the list yet.")
                    print(f"Verify manually: {args.alias} / {args.wsc_code} / {args.uu_name}")
                    return 3

                print("SharePoint list item created successfully:")
                print(f"  Supplier Alias: {args.alias}")
                print(f"  WSC_Code:       {args.wsc_code}")
                print(f"  Supplier_UU:    {args.uu_name}")
                return 0
            finally:
                context.close()
    except PlaywrightTimeoutError as exc:
        print(f"SharePoint UI timed out: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"SharePoint list test failed: {exc}", file=sys.stderr)
        print("If Edge is already open, close all Edge windows and run again.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
