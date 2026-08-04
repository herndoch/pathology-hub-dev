#!/usr/bin/env python3
"""Headless Playwright test for the @mention entity picker (2026-08-03,
redesigned 2026-08-04 to render the live OncoTree instead of a flat list).

computerUse (manual browser testing) was unavailable this session — this is
the automated fallback per AGENTS.md guidance. Drives the real rendered DOM
against the local dev server (no mocking), so it actually exercises the
`currentMentionContext` / `renderMentionDropdown` / `selectMentionLeaf` /
`parseQueryMentions` wiring in app.js, not just static string checks.

Usage:
    ./scripts/run_local.sh &          # local dev server must be running
    python3 scripts/playwright_test_mention_picker_v0_1.py [--base-url URL]
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


def _ok(label: str, detail: str = "") -> None:
    print(f"  OK  {label}" + (f" — {detail}" if detail else ""))


def _fail(label: str, detail) -> None:
    print(f"  FAIL  {label}: {detail}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.base_url, wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#query-input", timeout=15000)
        _ok("page loaded", args.base_url)

        query_input = page.locator("#query-input")
        dropdown = page.locator("#mention-dropdown")

        # --- Type "@LCIS": expect the REAL OncoTree (not a flat list) ---
        query_input.click()
        query_input.type("@LCIS", delay=40)
        page.wait_for_timeout(400)
        if "hidden" in (dropdown.get_attribute("class") or ""):
            _fail("mention dropdown did not open for @LCIS", query_input.input_value())
        if dropdown.locator(".oncotree-container").count() < 1:
            _fail("mention dropdown is not rendering the live OncoTree", dropdown.inner_html()[:300])
        leaves = dropdown.locator(".oncotree-leaf")
        n_leaves = leaves.count()
        if n_leaves < 1:
            _fail("no OncoTree leaf nodes rendered for @LCIS", n_leaves)
        first_leaf_text = leaves.nth(0).inner_text()
        if "lcis" not in first_leaf_text.lower() and "lobular carcinoma in situ" not in first_leaf_text.lower():
            _fail("top @LCIS tree match doesn't look right", first_leaf_text)
        _ok("@LCIS opened the live OncoTree with a matching leaf", f"{first_leaf_text!r} ({n_leaves} leaf node(s))")

        # --- Click that leaf's VS button (the SAME button style used everywhere else in the tree) ---
        dropdown.locator(".vs-btn").first.click()
        page.wait_for_timeout(200)
        val_after_first = query_input.input_value()
        if not val_after_first.startswith("@") or ";" not in val_after_first:
            _fail("clicking the tree leaf's VS button did not insert a semicolon-delimited mention", val_after_first)
        _ok("clicked VS button on tree leaf inserted mention", val_after_first)
        tray_count = page.locator("#compare-tray-count").inner_text()
        if "1" not in tray_count:
            _fail("compare tray did not update after picking a mention from the tree", tray_count)
        _ok("compare tray reflects the pick immediately", tray_count)

        # --- Type "@DCIS" and pick the tree leaf by clicking its label directly ---
        query_input.type("@DCIS", delay=40)
        page.wait_for_timeout(400)
        leaves2 = dropdown.locator(".oncotree-leaf")
        if leaves2.count() < 1:
            _fail("no OncoTree leaf nodes rendered for @DCIS", leaves2.count())
        leaves2.first.click()
        page.wait_for_timeout(200)
        val_after_second = query_input.input_value()
        mention_count = val_after_second.count("@")
        if mention_count < 2:
            _fail("expected 2 mentions in the query box", val_after_second)
        _ok("second mention (picked via leaf label click) inserted", val_after_second)

        # --- Submit with Enter: expect routing straight to Compare ---
        query_input.press("Enter")
        page.wait_for_timeout(2000)
        # Compare view renders a "Compare Diagnoses" heading once /api/compare resolves —
        # give it real time since it calls OpenAI + the evidence backend for both entities.
        try:
            page.wait_for_selector("text=Compare Diagnoses", timeout=180000)
        except Exception as exc:  # noqa: BLE001
            body_snippet = page.locator("#browse-content").inner_text()[:500]
            _fail("did not reach the Compare view after submitting 2 mentions", f"{exc} — page shows: {body_snippet!r}")
        heading = page.locator("text=Compare Diagnoses").first.inner_text()
        _ok("submit with 2 mentions routed to Compare", heading)

        input_cleared = query_input.input_value()
        if input_cleared:
            _fail("query box should be cleared after routing to Compare", input_cleared)
        _ok("query box cleared after compare routing")

        # --- Single mention, no extra text: should open the topic page directly, not Compare ---
        page.locator("#home-btn").click()
        page.wait_for_timeout(500)
        query_input.click()
        query_input.type("@Ewing Sarcoma", delay=40)
        page.wait_for_timeout(400)
        leaves3 = dropdown.locator(".oncotree-leaf")
        if leaves3.count() < 1:
            _fail("no tree matches for @Ewing Sarcoma", leaves3.count())
        leaves3.first.click()
        page.wait_for_timeout(150)
        query_input.press("Enter")
        page.wait_for_timeout(2000)
        breadcrumbs = page.locator("#browse-breadcrumbs").inner_text()
        if "ewing" not in breadcrumbs.lower():
            _fail("single-mention submit did not open that entity's topic page", breadcrumbs)
        _ok("single mention (no extra text) opened topic page directly", breadcrumbs)

        # --- 2026-08-04 fix: no redundant "Home" breadcrumb at the home level ---
        page.locator("#home-btn").click()
        page.wait_for_timeout(400)
        home_breadcrumbs = page.locator("#browse-breadcrumbs").inner_text().strip()
        if home_breadcrumbs:
            _fail("breadcrumb bar should be empty at the Browse home level (redundant with the overlay Home button)", home_breadcrumbs)
        _ok("no redundant Home breadcrumb at the Browse home level")

        browser.close()

    print("\nAll mention-picker checks passed.")


if __name__ == "__main__":
    main()
