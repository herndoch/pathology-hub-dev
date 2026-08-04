#!/usr/bin/env python3
"""Headless Playwright test for the @mention entity picker (2026-08-03).

computerUse (manual browser testing) was unavailable this session — this is
the automated fallback per AGENTS.md guidance. Drives the real rendered DOM
against the local dev server (no mocking), so it actually exercises the
`currentMentionContext` / `mentionSuggestionsFor` / `selectMentionSuggestion`
/ `parseQueryMentions` wiring in app.js, not just static string checks.

Usage:
    ./scripts/run_local.sh &          # local dev server must be running
    python3 scripts/playwright_test_mention_picker_v0_1.py [--base-url URL]
"""

from __future__ import annotations

import argparse
import sys
import time

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

        # --- Type "@LCIS" and expect the dropdown to populate ---
        query_input.click()
        query_input.type("@LCIS", delay=40)
        page.wait_for_timeout(300)
        if dropdown.get_attribute("class") and "hidden" in (dropdown.get_attribute("class") or ""):
            _fail("mention dropdown did not open for @LCIS", page.locator("#query-input").input_value())
        rows = dropdown.locator(".mention-row")
        n_rows = rows.count()
        if n_rows < 1:
            _fail("no mention suggestions rendered for @LCIS", n_rows)
        first_row_text = rows.nth(0).locator(".mention-row-label").inner_text()
        if "lcis" not in first_row_text.lower() and "lobular carcinoma in situ" not in first_row_text.lower():
            _fail("top @LCIS suggestion doesn't look right", first_row_text)
        _ok("@LCIS autocomplete populated", f"top suggestion: {first_row_text!r} ({n_rows} rows)")

        # --- Click the "+" on the first suggestion ---
        rows.nth(0).locator(".mention-add-btn").click()
        page.wait_for_timeout(150)
        val_after_first = query_input.input_value()
        if not val_after_first.startswith("@") or ";" not in val_after_first:
            _fail("clicking + did not insert a semicolon-delimited mention", val_after_first)
        _ok("clicked + inserted mention", val_after_first)

        # --- Type "@DCIS" and select the top suggestion too ---
        query_input.type("@DCIS", delay=40)
        page.wait_for_timeout(300)
        rows2 = dropdown.locator(".mention-row")
        if rows2.count() < 1:
            _fail("no mention suggestions rendered for @DCIS", rows2.count())
        second_label = rows2.nth(0).locator(".mention-row-label").inner_text()
        rows2.nth(0).locator(".mention-add-btn").click()
        page.wait_for_timeout(150)
        val_after_second = query_input.input_value()
        mention_count = val_after_second.count("@")
        if mention_count < 2:
            _fail("expected 2 mentions in the query box", val_after_second)
        _ok("second mention inserted", val_after_second)

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
        rows3 = dropdown.locator(".mention-row")
        if rows3.count() < 1:
            _fail("no suggestions for @Ewing Sarcoma", rows3.count())
        rows3.nth(0).locator(".mention-add-btn").click()
        page.wait_for_timeout(150)
        query_input.press("Enter")
        page.wait_for_timeout(2000)
        breadcrumbs = page.locator("#browse-breadcrumbs").inner_text()
        if "ewing" not in breadcrumbs.lower():
            _fail("single-mention submit did not open that entity's topic page", breadcrumbs)
        _ok("single mention (no extra text) opened topic page directly", breadcrumbs)

        browser.close()

    print("\nAll mention-picker checks passed.")


if __name__ == "__main__":
    main()
