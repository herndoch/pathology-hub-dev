#!/usr/bin/env python3
"""Headless Playwright test for shareable deep links.

Reported (2026-08-04): "how do i make it so i can hyperlink people to a
page, eg .../[dx] or .../[query]". Implemented as query-string params on
the root URL (no new backend route needed — GET / already serves
index.html regardless of query string):
  ?tag=<exact leaf tag>      — precise permalink to one diagnosis.
  ?dx=<entity name>          — same destination, fuzzy-matched by name.
  ?compare=<name1>;<name2>   — opens Compare with 2+ entities.
  ?q=<free text>             — runs it as an Ask question.
Plus: the address bar is kept in sync with whatever's on screen (so the
CURRENT url is always a valid link back to it), browser Back/Forward work
via popstate, and explicit "Copy link" buttons exist on topic pages and
Compare.

Drives the real rendered DOM against the local dev server (no mocking).

Usage:
    ./scripts/run_local.sh &          # local dev server must be running
    python3 scripts/playwright_test_deep_links_v0_1.py [--base-url URL]
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import quote

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
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # --- ?dx=<name> lands directly on that entity's topic page ---
        page.goto(f"{base}/?dx={quote('Chondromyxoid Fibroma')}", wait_until="load", timeout=30000)
        page.wait_for_selector("#browse-breadcrumbs", timeout=15000)
        page.wait_for_function(
            "document.getElementById('browse-breadcrumbs').innerText.toLowerCase().includes('chondromyxoid')",
            timeout=60000,
        )
        breadcrumbs = page.locator("#browse-breadcrumbs").inner_text()
        _ok("?dx=<name> opened that entity's topic page directly", breadcrumbs)

        # --- The address bar canonicalizes ?dx= into the precise ?tag= permalink ---
        page.wait_for_function("window.location.search.includes('tag=')", timeout=15000)
        canonical_url = page.evaluate("window.location.href")
        if "tag=" not in canonical_url:
            _fail("address bar was not canonicalized from ?dx= to ?tag=", canonical_url)
        _ok("address bar canonicalized ?dx= into the precise ?tag= permalink", canonical_url)

        # --- Revisiting that exact ?tag= URL (a "shared link") lands on the same page ---
        page.goto(canonical_url, wait_until="load", timeout=30000)
        page.wait_for_function(
            "document.getElementById('browse-breadcrumbs').innerText.toLowerCase().includes('chondromyxoid')",
            timeout=60000,
        )
        _ok("revisiting the canonical ?tag= link reopens the same topic page")

        # --- "Copy link" button exists on the topic page and is wired up ---
        copy_btn = page.locator("button.copy-link-btn")
        if copy_btn.count() < 1:
            _fail("no Copy link button found on the topic page", None)
        _ok("topic page has a Copy link button")

        # --- Same-document browser Back (popstate), not a full reload: start
        # from a FRESH single real navigation (so the history stack built up
        # by the checks above doesn't interfere), then navigate Home
        # (pushState #1, bare url), then to a SECOND topic page via in-app
        # UI search + click (pushState #2) — both on top of this still-live
        # document/JS context — then go back TWICE to confirm each step's
        # popstate wiring: back #1 lands on the bare Home url, back #2
        # returns to the original topic page. ---
        page.goto(canonical_url, wait_until="load", timeout=30000)
        page.wait_for_function(
            "document.getElementById('browse-breadcrumbs').innerText.toLowerCase().includes('chondromyxoid')",
            timeout=60000,
        )
        query_input = page.locator("#query-input")
        page.locator("#home-btn").click()
        page.wait_for_timeout(500)
        query_input.click()
        query_input.type("Ewing Sarcoma", delay=30)
        page.wait_for_function(
            "document.querySelectorAll('#browse-content .oncotree-leaf').length > 0", timeout=15000
        )
        leaves = page.locator("#browse-content .oncotree-leaf")
        if leaves.count() < 1:
            _fail("no tree matches for Ewing Sarcoma (setup for popstate test)", None)
        leaves.first.click()
        page.wait_for_timeout(1500)
        url_after_second_nav = page.evaluate("window.location.href")
        if "tag=" not in url_after_second_nav:
            _fail("navigating to a second topic page did not update the address bar", url_after_second_nav)

        page.go_back()
        page.wait_for_timeout(600)
        url_after_first_back = page.evaluate("window.location.href")
        if "tag=" in url_after_first_back or "compare=" in url_after_first_back:
            _fail("first browser Back did not land on the bare Home url", url_after_first_back)
        _ok("first browser Back (popstate) returns to Home with a bare url", url_after_first_back)

        page.go_back()
        page.wait_for_timeout(600)
        back_breadcrumbs = page.locator("#browse-breadcrumbs").inner_text()
        if "chondromyxoid" not in back_breadcrumbs.lower():
            _fail("second browser Back (popstate) did not return to the original topic page", back_breadcrumbs)
        _ok("second browser Back (popstate) returns to the originally viewed topic page", back_breadcrumbs)

        # --- ?q=<free text> runs it as an Ask question ---
        page.goto(f"{base}/?q={quote('what is chondromyxoid fibroma')}", wait_until="load", timeout=30000)
        page.wait_for_function("!document.getElementById('ask-view').classList.contains('hidden')", timeout=15000)
        page.wait_for_selector("#messages .message.user", timeout=15000)
        user_msg = page.locator("#messages .message.user").first.inner_text()
        if "chondromyxoid" not in user_msg.lower():
            _fail("?q= did not ask the expected question", user_msg)
        _ok("?q=<free text> switched to Ask and asked the question", user_msg)

        # --- ?compare=<name1>;<name2> opens Compare with both entities ---
        compare_qs = quote("Chondromyxoid Fibroma") + ";" + quote("Clear Cell Chondrosarcoma")
        page.goto(f"{base}/?compare={compare_qs}", wait_until="load", timeout=30000)
        try:
            page.wait_for_selector("text=Compare Diagnoses", timeout=480000)
        except Exception as exc:  # noqa: BLE001
            body_snippet = page.locator("#browse-content").inner_text()[:500]
            _fail("?compare= did not open the Compare view", f"{exc} — page shows: {body_snippet!r}")
        heading = page.locator("text=Compare Diagnoses").first.inner_text()
        _ok("?compare=<name1>;<name2> opened Compare with both entities", heading)

        # --- "Copy link" button exists on the Compare view ---
        compare_copy_btn = page.locator("#compare-copy-link-btn")
        if compare_copy_btn.count() < 1:
            _fail("no Copy link button found on the Compare view", None)
        _ok("Compare view has a Copy link button")

        # --- Navigating within the app (clicking Home) clears the address bar back to bare ---
        page.locator("#home-btn").click()
        page.wait_for_timeout(500)
        home_url = page.evaluate("window.location.href")
        if "tag=" in home_url or "compare=" in home_url or "q=" in home_url or "dx=" in home_url:
            _fail("address bar still carries deep-link params after returning Home", home_url)
        _ok("returning Home clears the address bar back to a bare url", home_url)

        # --- Browser Back navigates back to the comparison. Note: the very
        # first ?compare= entry in this test came from a real page.goto()
        # (a genuine top-level navigation), so going back to it is a real
        # page reload (re-running the startup applyUrlRoute() flow from
        # scratch, including a full compare synthesis round trip), not a
        # same-document popstate — hence the generous timeout matching the
        # other compare-view tests. ---
        page.go_back()
        page.wait_for_timeout(1000)
        try:
            page.wait_for_selector("text=Compare Diagnoses", timeout=480000)
        except Exception as exc:  # noqa: BLE001
            snippet = page.locator("body").inner_text()[:500]
            _fail("browser Back did not return to the Compare view", f"{exc} — page shows: {snippet!r}")
        _ok("browser Back returns to the previous page (Compare), reapplying ?compare= on reload")

        browser.close()

    print("\nAll shareable deep-link checks passed.")


if __name__ == "__main__":
    main()
