#!/usr/bin/env python3
"""Headless Playwright test for two 2026-08-03 fixes (computerUse was
unavailable this session; this is the automated fallback):

1. Inline citation labels must defer to the deterministic source_id->book
   URL mapping, not the model's freeform label text (the model sometimes
   writes a hallucinated-but-plausible book chip, e.g. "Gnepp" for a
   Bone/Soft Tissue citation that is actually softtissue_enzinger).
2. WHO citations for entities covered by who_genetic_syndromes_links_v0_1.json
   link to the real tumourclassification.iarc.who.int page, not only
   Pathology Hub's own WHO_HTML mirror.

Usage:
    ./scripts/run_local.sh &          # local dev server must be running
    python3 scripts/playwright_test_citation_who_links_v0_1.py [--base-url URL]
"""

from __future__ import annotations

import argparse
import re
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

        query_input = page.locator("#query-input")
        query_input.click()
        query_input.type("Sarcoma with BCOR Genetic Alterations", delay=20)
        page.wait_for_timeout(800)
        # Live tree-filter mode (no "@") — click the matching BST leaf node
        # directly (this entity is cross-listed under both bst and peds; the
        # tag itself pins the root regardless of which one gets clicked, but
        # be explicit so this test is deterministic).
        leaf_btn = page.locator(
            'button.oncotree-leaf[data-node*="BST::Round_Cell_Sarcomas::Sarcoma_with_BCOR_Genetic_Alterations"]'
        ).first
        leaf_btn.click()
        page.wait_for_selector("text=Prebuilt page", timeout=15000)
        _ok("opened cached BCOR sarcoma topic page")

        body_text = page.locator("#browse-content").inner_text()
        gnepp_links = page.locator("#browse-content a", has_text=re.compile(r"^Gnepp$"))
        if gnepp_links.count() > 0:
            _fail("citation still labeled 'Gnepp' on a Bone/Soft Tissue page", gnepp_links.count())
        enzinger_links = page.locator("#browse-content a", has_text=re.compile(r"^Enzinger$"))
        if enzinger_links.count() < 1:
            _fail("expected at least one 'Enzinger' citation label (was it 'Gnepp' before the fix?)", body_text[:300])
        _ok("citation label corrected", f"{enzinger_links.count()} 'Enzinger' link(s), 0 'Gnepp' link(s)")

        who_links = page.locator("#browse-content a", has_text=re.compile(r"^WHO$"))
        if who_links.count() < 1:
            _fail("no inline 'WHO' citation links found on the page", body_text[:300])
        who_hrefs = [who_links.nth(i).get_attribute("href") for i in range(who_links.count())]
        real_who = [h for h in who_hrefs if h and "tumourclassification.iarc.who.int" in h]
        mirror_who = [h for h in who_hrefs if h and "pathology-hub-0" in h]
        if not real_who:
            _fail("no WHO link points to the real tumourclassification.iarc.who.int site", who_hrefs)
        _ok(
            "WHO link points to the real WHO site",
            f"{len(real_who)} real WHO link(s): {real_who[0]}"
            + (f" (plus {len(mirror_who)} still on the mirror — expected if any WHO card lacks a syndrome-doc match)" if mirror_who else ""),
        )

        browser.close()

    print("\nAll citation/WHO-link checks passed.")


if __name__ == "__main__":
    main()
