#!/usr/bin/env python3
"""Parse the user-supplied WHO Classification of Tumours chapter-link export
into a clean {normalized_name: [{volume, url, text}, ...]} lookup used to
send inline "WHO" citations to the REAL WHO Classification of Tumours site
(tumourclassification.iarc.who.int) instead of only Pathology Hub's own
self-hosted WHO_HTML mirror.

Input (not committed — human-provided, contact herndon.charlie@gmail.com for
a fresh export if this needs to be regenerated):
    WHO_Genetic_Tumour_Syndromes_Links_COMBINED_9da1.txt
    — 19 workbooks. Despite the filename, this is each WHO Classification of
    Tumours 5th-edition volume's FULL chapter link table (every diagnostic
    entity + every genetic-syndrome entry in that volume's table of
    contents), tab-delimited Text\tURL pairs, one workbook per volume.

Output:
    frontend/pathology_hub_chat_mvp/static/who_genetic_syndromes_links_v0_1.json

Coverage / precision notes (measured against the live browse index):
- ~1,619 of ~5,288 browse leaves (~31%) have at least one name match. Real
  gaps remain — most entities are NOT covered — so most WHO citations still
  correctly fall back to Pathology Hub's own WHO_HTML mirror link (which is
  still real WHO-sourced content, just self-hosted).
- The SAME entity name can appear in multiple WHO volumes with DIFFERENT
  chapter URLs (e.g. "Osteoma" is a distinct chapter in at least 3 volumes:
  Soft Tissue & Bone, Head & Neck, and Skin). This script keeps every
  {volume, url, text} candidate per normalized name rather than picking one
  arbitrarily; the caller (app.js) disambiguates using WHO_VOLUME_BY_ROOT —
  a browse-root -> dominant-WHO-volume-number mapping empirically derived by
  cross-tabulating browse-leaf root vs. matched volume counts (see
  docs/WHO_VOLUME_BY_ROOT_DERIVATION.md for the exact counts).

Usage:
    python3 scripts/build_who_genetic_syndromes_links_v0_1.py \\
        --input /path/to/WHO_Genetic_Tumour_Syndromes_Links_COMBINED_9da1.txt
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "static" / "who_genetic_syndromes_links_v0_1.json"

WORKBOOK_RE = re.compile(r"^WORKBOOK (\d+) OF (\d+): (.+)$")
VOLUME_RE = re.compile(r"/chaptercontent/(\d+)/(\d+)")

# Rows that are navigation/boilerplate, not a named entity/syndrome — never
# useful as a citation target and would otherwise pollute substring matching.
_SKIP_TEXT_RE = re.compile(
    r"(?i)^("
    r"website beta version|foreword|who classification of tumours.*editorial board|"
    r"how to cite this volume|introduction(\s+to.*)?|"
    r"guidelines for the reporting of sequence variants.*|"
    r"terms of use|privacy policy|\xa9.*iarc.*all rights reserved"
    r")$"
)

# Rows that are pathway/mechanism SECTION headers (e.g. "RAS-MAPK pathway"),
# not a named entity — keep them out of the lookup (they'd otherwise
# false-positive-match on generic words like "pathway").
_SECTION_HEADER_RE = re.compile(r"(?i)\b(pathway|signalling pathway|repair genes|processor)\s*$")


def _normalize(text: str) -> str:
    s = text.lower()
    s = re.sub(r"\([^)]*\)", " ", s)  # drop "(NF1)" gene-name parenthetical
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    current_workbook = None
    in_data = False
    for line in text.split("\n"):
        m = WORKBOOK_RE.match(line)
        if m:
            current_workbook = m.group(3)
            in_data = False
            continue
        if line.startswith("Text\tURL"):
            in_data = True
            continue
        if line.startswith("====") or line.startswith("SHEET") or line.startswith("ROWS:") or not line.strip():
            continue
        if not in_data or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        raw_text, url = parts[0].strip(), parts[1].strip()
        if not raw_text or not url.startswith("http"):
            continue
        if _SKIP_TEXT_RE.match(raw_text) or _SECTION_HEADER_RE.search(raw_text):
            continue
        vol_match = VOLUME_RE.search(url)
        volume = vol_match.group(1) if vol_match else None
        rows.append({"workbook": current_workbook, "volume": volume, "text": raw_text, "url": url})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    raw = args.input.read_text(encoding="utf-8")
    rows = parse_rows(raw)

    by_norm: dict[str, list[dict]] = {}
    dupes = 0
    for row in rows:
        norm = _normalize(row["text"])
        if not norm or len(norm) < 3:
            continue
        candidates = by_norm.setdefault(norm, [])
        if any(c["url"] == row["url"] for c in candidates):
            dupes += 1
            continue
        candidates.append({"text": row["text"], "url": row["url"], "volume": row["volume"]})

    multi_volume_names = sum(1 for cands in by_norm.values() if len({c["volume"] for c in cands}) > 1)

    output = {
        "schema_version": "who_genetic_syndromes_links_v0_2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_note": (
            "Human-supplied export of WHO Classification of Tumours 5th-edition "
            "per-volume chapter link tables (19 workbooks / volumes: every "
            "diagnostic entity + genetic-syndrome entry in each volume's table "
            "of contents, despite the filename). NOT a complete WHO entity map "
            "— real coverage gaps remain (~31% of current browse leaves match "
            "by name); unmatched entities keep the Pathology Hub WHO_HTML "
            "mirror link. Names ambiguous across >1 volume keep every "
            "candidate here — see app.js WHO_VOLUME_BY_ROOT for disambiguation."
        ),
        "input_paths": [str(args.input)],
        "output_paths": [str(args.output.relative_to(REPO_ROOT)) if args.output.is_relative_to(REPO_ROOT) else str(args.output)],
        "counts": {
            "rows_parsed": len(rows),
            "unique_normalized_entries": len(by_norm),
            "multi_volume_ambiguous_entries": multi_volume_names,
            "duplicate_rows_dropped": dupes,
        },
        "known_limitations": [
            "Coverage is partial (~31% of current browse leaves) — most WHO citations "
            "still correctly use the Pathology Hub WHO_HTML mirror link.",
            "Matching is by normalized entity NAME text only (gene-name parentheticals "
            "stripped); ambiguous (same-name, different-volume) entries are resolved by "
            "the caller's root->volume preference, not stored here.",
        ],
        "entries": by_norm,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["counts"], indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
