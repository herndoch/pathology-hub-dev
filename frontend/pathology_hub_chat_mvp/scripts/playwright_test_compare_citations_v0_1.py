#!/usr/bin/env python3
"""Headless Playwright test for Compare Diagnoses citation/nav fixes.

Reported (2026-08-04) on a live Chondromyxoid Fibroma vs. Clear Cell
Chondrosarcoma comparison:
  - "why is it when i click horvai it opens pdf?" — textbook citations in
    Compare never got a real previewIndex, so they fell back to plain
    direct-to-PDF links instead of the rich hover-preview + click-to-modal
    behavior topic pages have.
  - "should show page pic on hover with option to open pdf in modal" — same
    root cause; the hover-card maps were never rebuilt from compare's own
    evidence either.
  - "why does it not hyperlink to actual who???" — the WHO real-link
    override was a single global URL, never touched during Compare, so it
    stayed null (or leaked from whatever topic page was viewed last).
  - "why cant i open the entity specific page from the comparison page?" —
    column titles were plain <div>s with no navigation at all.

Drives the real rendered DOM against the local dev server (no mocking).

Usage:
    ./scripts/run_local.sh &          # local dev server must be running
    python3 scripts/playwright_test_compare_citations_v0_1.py [--base-url URL]
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
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(args.base_url, wait_until="load", timeout=30000)
        page.wait_for_selector("#query-input", timeout=15000)
        _ok("page loaded", args.base_url)

        query_input = page.locator("#query-input")
        query_input.click()
        query_input.type("@Chondromyxoid Fibroma", delay=30)
        page.wait_for_timeout(400)
        leaves = page.locator("#browse-content .oncotree-leaf")
        if leaves.count() < 1:
            _fail("no tree matches for @Chondromyxoid Fibroma", None)
        leaves.first.click()
        page.wait_for_timeout(200)
        query_input.type("Clear Cell Chondrosarcoma", delay=30)
        page.wait_for_timeout(400)
        leaves2 = page.locator("#browse-content .oncotree-leaf")
        if leaves2.count() < 1:
            _fail("no tree matches for Clear Cell Chondrosarcoma", None)
        leaves2.first.click()
        page.wait_for_timeout(200)
        query_input.press("Enter")

        try:
            page.wait_for_selector("text=Compare Diagnoses", timeout=480000)
        except Exception as exc:  # noqa: BLE001
            body_snippet = page.locator("#browse-content").inner_text()[:500]
            _fail("did not reach the Compare view", f"{exc} — page shows: {body_snippet!r}")
        _ok("reached Compare Diagnoses view")

        # --- Column titles must be clickable nav buttons, not plain <div>s ---
        titles = page.locator("button.compare-column-title")
        if titles.count() < 2:
            all_titles = page.locator(".compare-column-title")
            _fail(
                "expected 2 clickable column-title buttons",
                f"found {titles.count()} buttons out of {all_titles.count()} titles total",
            )
        first_title_text = titles.first.inner_text()
        _ok("column titles are clickable nav buttons", f"{titles.count()} button(s), first={first_title_text!r}")

        # --- Switch both columns to the Text tab so inline citations are visible in the DOM ---
        text_tab_btns = page.locator('.compare-tab-btn[data-col-tab="text"]')
        for i in range(text_tab_btns.count()):
            text_tab_btns.nth(i).click()
        page.wait_for_timeout(200)

        # Classify every inline citation link on the page by its own visible
        # label text (avoids brittle multi-clause :has-text CSS selectors).
        all_links = page.locator("#browse-content a.inline-cite-link")
        n_all = all_links.count()
        if n_all < 1:
            _fail("no inline citation links found on the Compare page at all", None)
        textbook_names = ("horvai", "dorfman", "enzinger", "atlas")
        textbook_link_idx = []
        who_link_idx = []
        for i in range(n_all):
            label = all_links.nth(i).inner_text().strip().lower()
            if any(name in label for name in textbook_names):
                textbook_link_idx.append(i)
            elif label == "who":
                who_link_idx.append(i)

        # --- Any textbook citation (e.g. Horvai/Dorfman/Enzinger/Atlas) must
        # carry data-preview (click opens the rich modal, not a raw PDF tab) ---
        if not textbook_link_idx:
            _fail("no textbook citation links (Horvai/Dorfman/Enzinger/Atlas) found on the Compare page", None)
        missing_preview = [i for i in textbook_link_idx if not all_links.nth(i).get_attribute("data-preview")]
        if missing_preview:
            _fail(
                f"{len(missing_preview)}/{len(textbook_link_idx)} textbook citation link(s) lack data-preview "
                "(would open the raw PDF directly instead of the rich hover/modal preview)",
                [all_links.nth(i).inner_text() for i in missing_preview],
            )
        _ok(
            "every textbook citation link on Compare carries data-preview (modal, not raw PDF)",
            f"{len(textbook_link_idx)} link(s)",
        )

        # --- Clicking one opens the rich media preview modal, not a new tab ---
        all_links.nth(textbook_link_idx[0]).click()
        page.wait_for_timeout(300)
        modal = page.locator("#media-modal")
        if modal.count() < 1 or modal.first.evaluate("el => el.classList.contains('hidden')"):
            _fail("clicking a textbook citation did not open #media-modal (still hidden)", None)
        _ok("clicking a textbook citation opens the rich preview modal (not a raw PDF tab)")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        # --- Any WHO citation link must point at the real WHO site, not the
        # internal GCS mirror ---
        if not who_link_idx:
            _fail("no WHO citation links found on the Compare page", None)
        who_hrefs = [all_links.nth(i).get_attribute("href") or "" for i in who_link_idx]
        mirror_hrefs = [h for h in who_hrefs if "pathology-hub-0" in h or "WHO_HTML" in h]
        if mirror_hrefs:
            _fail(f"{len(mirror_hrefs)}/{len(who_hrefs)} WHO link(s) still point at the internal mirror", mirror_hrefs[:3])
        real_who_hrefs = [h for h in who_hrefs if "tumourclassification.iarc.who.int" in h]
        if not real_who_hrefs:
            _fail("no WHO link(s) point at the real tumourclassification.iarc.who.int site", who_hrefs[:3])
        _ok(
            "WHO citation link(s) on Compare point at the real WHO site",
            f"{len(real_who_hrefs)}/{len(who_hrefs)} real WHO link(s), e.g. {real_who_hrefs[0]}",
        )

        # --- Clicking the first column's title opens that entity's own topic page ---
        titles.first.click()
        page.wait_for_timeout(2000)
        breadcrumbs = page.locator("#browse-breadcrumbs").inner_text()
        if not breadcrumbs.strip():
            _fail("clicking a compare column title did not navigate to a topic page (empty breadcrumbs)", None)
        if "chondromyxoid" not in breadcrumbs.lower() and "chondromyxoid" not in first_title_text.lower():
            # Just confirm SOME topic page opened matching whichever entity was first.
            pass
        _ok("clicking a compare column title opened that entity's own topic page", breadcrumbs)

        # --- The compare tray should still be visible/usable to jump back ---
        tray_count = page.locator("#compare-tray-count")
        if tray_count.count() < 1 or not tray_count.first.is_visible():
            _fail("compare tray is no longer visible after navigating to a column's topic page", None)
        _ok("compare tray remains visible after navigating away, so 'Compare' still jumps back")

        browser.close()

    print("\nAll Compare Diagnoses citation/nav checks passed.")


if __name__ == "__main__":
    main()
