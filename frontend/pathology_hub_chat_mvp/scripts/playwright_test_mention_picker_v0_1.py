#!/usr/bin/env python3
"""Headless Playwright test for the @mention entity picker.

History (per live user feedback, each redesign progressively closer to what
was actually wanted):
  2026-08-03: custom flat-row dropdown.
  2026-08-04 (v2): dropdown redesigned to render the live OncoTree instead
    of a flat list, but STILL a separate floating overlay ("why do i still
    see dropdown menu?").
  2026-08-04 (v3): no separate widget at all — an active "@mention" takes
    over browse-content with the SAME live OncoTree the rest of Browse
    uses, with "+" buttons on matching leaves instead of "VS" while
    composing ("i still see vs and not plus sign").
  2026-08-04 (v4, this version): "+" completely and unconditionally
    replaces "VS" everywhere in the OncoTree, with or without an active
    "@" ("i wanna completely replace the vs sign, ie from the get go can
    click a plus"). Each pick auto-primes a trailing "@" so the next
    mention can be typed immediately without retyping "@". The search bar
    highlights "@Label;" mention segments in the accent color, other text
    in the default text color, via a highlight overlay behind the (now
    text-transparent) input.

computerUse (manual browser testing) was unavailable this session — this is
the automated fallback per AGENTS.md guidance. Drives the real rendered DOM
against the local dev server (no mocking).

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
        # "load" (not "networkidle") — the health-check request the page
        # fires can take 30-40s+ against a cold Cloud Run backend, which
        # would otherwise stall networkidle well past a reasonable timeout.
        page.goto(args.base_url, wait_until="load", timeout=30000)
        page.wait_for_selector("#query-input", timeout=15000)
        _ok("page loaded", args.base_url)

        query_input = page.locator("#query-input")

        # --- No separate dropdown widget should exist in the DOM at all ---
        if page.locator("#mention-dropdown").count() > 0:
            _fail("a #mention-dropdown element still exists — should be removed entirely", None)
        _ok("no separate #mention-dropdown widget exists in the DOM")

        # --- "+" is unconditional: even a PLAIN (no "@") text search shows
        # "+" buttons on matching leaves, never "VS" — proving the button
        # isn't gated behind composing an @mention at all ---
        page.wait_for_selector(".oncotree-container", timeout=15000)
        browse_content = page.locator("#browse-content")
        query_input.click()
        query_input.type("sarcoma", delay=30)
        page.wait_for_timeout(400)
        if browse_content.locator(".oncotree-leaf").count() < 1:
            _fail("plain-text 'sarcoma' search found no OncoTree leaves", None)
        if browse_content.locator(".mention-add-btn").count() < 1:
            _fail("no unconditional + buttons on a plain-text (non-@) tree search", None)
        if browse_content.locator(".vs-btn:not(.mention-add-btn)").count() > 0:
            _fail("a plain VS button still renders in the OncoTree — should always be +", None)
        _ok("plain-text search (no @ typed) already shows + buttons, never VS")
        query_input.fill("")
        page.wait_for_timeout(300)

        # --- Type "@LCIS": the LIVE browse-content tree takes over in place ---
        query_input.click()
        query_input.type("@LCIS", delay=40)
        page.wait_for_timeout(400)
        if browse_content.locator(".oncotree-container").count() < 1:
            _fail("browse-content is not showing the live OncoTree for @LCIS", browse_content.inner_html()[:300])
        leaves = browse_content.locator(".oncotree-leaf")
        n_leaves = leaves.count()
        if n_leaves < 1:
            _fail("no OncoTree leaf nodes rendered for @LCIS", n_leaves)
        first_leaf_text = leaves.nth(0).inner_text()
        if "lcis" not in first_leaf_text.lower() and "lobular carcinoma in situ" not in first_leaf_text.lower():
            _fail("top @LCIS tree match doesn't look right", first_leaf_text)
        _ok("@LCIS took over browse-content with the live OncoTree", f"{first_leaf_text!r} ({n_leaves} leaf node(s))")

        # --- Matching leaves must show "+" buttons, not "VS" ---
        add_btns = browse_content.locator(".mention-add-btn")
        if add_btns.count() < 1:
            _fail("no + (mention-add) buttons rendered on matching leaves", add_btns.count())
        btn_text = add_btns.first.inner_text().strip()
        if btn_text != "+":
            _fail("leaf action button should read '+', not 'VS', while composing an @mention", btn_text)
        _ok("matching leaves show '+' buttons, not 'VS'", f"{add_btns.count()} button(s)")

        # --- Click the "+" button: inserts a semicolon-delimited mention AND
        # auto-primes a trailing "@" ready for the next pick ---
        add_btns.first.click()
        page.wait_for_timeout(250)
        val_after_first = query_input.input_value()
        if not val_after_first.startswith("@") or ";" not in val_after_first:
            _fail("clicking + did not insert a semicolon-delimited mention", val_after_first)
        if not val_after_first.endswith("@"):
            _fail("clicking + should auto-prime a trailing '@' for the next mention", val_after_first)
        _ok("clicked + inserted mention + auto-primed trailing @", val_after_first)
        tray_count = page.locator("#compare-tray-count").inner_text()
        if "1" not in tray_count:
            _fail("compare tray did not update after picking a mention from the tree", tray_count)
        _ok("compare tray reflects the pick immediately", tray_count)
        # Picking a mention returns to a clean, unfiltered Home tree.
        if browse_content.locator(".oncotree-match").count() > 0:
            _fail("tree should return to an unfiltered Home view after inserting a mention", None)
        _ok("tree returns to a clean Home view after inserting a mention")

        # --- Highlight overlay: the just-inserted mention segment should be
        # wrapped in .mention-highlight (accent color), distinguishing it
        # from plain text ---
        overlay = page.locator("#query-highlight-overlay")
        if overlay.locator(".mention-highlight").count() < 1:
            _fail("no .mention-highlight span in the overlay after inserting a mention", overlay.inner_html())
        mention_color = overlay.locator(".mention-highlight").first.evaluate("el => getComputedStyle(el).color")
        plain_color = overlay.evaluate("el => getComputedStyle(el).color")
        if mention_color == plain_color:
            _fail("mention segment isn't visually distinguished (same color as plain text)", mention_color)
        _ok("mention segment highlighted in a distinct color from plain text", f"{mention_color} vs {plain_color}")

        # --- Continue typing (no leading "@" needed — already primed) to
        # search + pick a second entity by clicking the leaf's label directly ---
        query_input.type("DCIS", delay=40)
        page.wait_for_timeout(400)
        leaves2 = browse_content.locator(".oncotree-leaf")
        if leaves2.count() < 1:
            _fail("no OncoTree leaf nodes rendered for auto-primed @ + 'DCIS'", leaves2.count())
        leaves2.first.click()
        page.wait_for_timeout(250)
        val_after_second = query_input.input_value()
        mention_count = val_after_second.count("@") - (1 if val_after_second.endswith("@") else 0)
        if mention_count < 2:
            _fail("expected 2 mentions in the query box", val_after_second)
        _ok("second mention (picked via leaf label click, no retyped @) inserted", val_after_second)

        # --- Submit with Enter: trailing bare "@" is stripped, routes to Compare ---
        query_input.press("Enter")
        page.wait_for_timeout(2000)
        try:
            page.wait_for_selector("text=Compare Diagnoses", timeout=480000)
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
        leaves3 = page.locator("#browse-content .oncotree-leaf")
        if leaves3.count() < 1:
            _fail("no tree matches for @Ewing Sarcoma", leaves3.count())
        leaves3.first.click()
        page.wait_for_timeout(150)
        # A bare trailing "@" is now auto-primed with nothing typed after it
        # — submitting as-is (no further mention) must still resolve to the
        # single entity picked, not a bogus 2nd empty mention.
        query_input.press("Enter")
        page.wait_for_timeout(2000)
        breadcrumbs = page.locator("#browse-breadcrumbs").inner_text()
        if "ewing" not in breadcrumbs.lower():
            _fail("single-mention submit did not open that entity's topic page", breadcrumbs)
        _ok("single mention (auto-primed trailing @ stripped on submit) opened topic page directly", breadcrumbs)

        # --- No redundant "Home" breadcrumb at the home level ---
        page.locator("#home-btn").click()
        page.wait_for_timeout(400)
        home_breadcrumbs = page.locator("#browse-breadcrumbs").inner_text().strip()
        if home_breadcrumbs:
            _fail("breadcrumb bar should be empty at the Browse home level", home_breadcrumbs)
        _ok("no redundant Home breadcrumb at the Browse home level")

        # --- @mention works even while starting from the Ask tab ---
        page.locator('.view-tab[data-view="ask"]').click()
        page.wait_for_timeout(200)
        query_input.click()
        query_input.type("@Osteosarcoma", delay=40)
        page.wait_for_timeout(500)
        if page.locator(".view-tab.active").inner_text().strip().lower() != "browse":
            _fail("typing @mention from the Ask tab did not switch to Browse", None)
        if page.locator("#browse-content .oncotree-leaf").count() < 1:
            _fail("no tree matches for @Osteosarcoma after switching from Ask", None)
        _ok("@mention from the Ask tab switches to Browse and shows the live tree")

        browser.close()

    print("\nAll mention-picker checks passed.")


if __name__ == "__main__":
    main()
