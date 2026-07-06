#!/usr/bin/env python3
"""Parse ABPath Anatomic Pathology content specifications into a staged registry v0_1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "abpath_ap_content_specs_v0_1"
SOURCE_AUTHORITY = "ABPath"
SOURCE_DOCUMENT = "ABPath_Anatomic_Pathology_Content_Specifications.docx"
SOURCE_SCOPE = "ABPath_AP_primary_certification"
DEFAULT_INPUT = Path("data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.docx")
DEFAULT_AUDIT_DIR = Path("06_audits/abpath_content_specs/v0_1")
DEFAULT_REGISTRY_DIR = Path("outputs/abpath_registry_v0_1")

W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

EXPECTED_MAJOR_SECTIONS: dict[int, str] = {
    1: "Breast",
    2: "The Genitourinary System",
    3: "Male Reproductive System",
    4: "Cardiovascular",
    5: "Head and Neck",
    6: "The Digestive System",
    7: "The Endocrine System",
    8: "Female Reproductive System",
    9: "The Placenta",
    10: "The Respiratory Tract, Pleura, and Mediastinum",
    11: "Soft Tissue, Bones, and Joints",
    12: "Cytopathology Topics for Anatomic Pathology Residents",
    13: "Dermatopathology Topics for Anatomic Pathology Residents",
    14: "Forensic Pathology Topics for Anatomic Pathology Residents",
    16: "Hematopathology Topics for Anatomic Pathology Residents",
    17: "Neuropathology Topics for Anatomic Pathology Residents",
    18: "Pediatric Pathology Topics for Anatomic Pathology Residents",
}

AP_RESIDENT_TOPIC_MAJOR_NUMBERS = {16, 17, 18}

LEVEL_META = {
    "C": {
        "abpath_level_label": "Core / Foundational",
        "expected_resident_depth": "mastery",
    },
    "AR": {
        "abpath_level_label": "Advanced Resident",
        "expected_resident_depth": "competence",
    },
    "F": {
        "abpath_level_label": "Fellow / Advanced Practitioner",
        "expected_resident_depth": "superficial_familiarity_for_residents",
    },
}

ROW_FIELDS = [
    "abpath_spec_id",
    "source_authority",
    "source_document",
    "source_scope",
    "major_section",
    "organ_system",
    "subsection",
    "category",
    "item_text",
    "raw_path",
    "raw_text",
    "abpath_level",
    "abpath_level_label",
    "expected_resident_depth",
    "specialty_board_scope",
    "include_for_ap_primary_certification",
    "parser_confidence",
    "parser_note",
    "normalized_item_key",
]

LEVEL_SUFFIX_RE = re.compile(r"(?P<level>C|AR|F)\s*$")
MAJOR_LINE_RE = re.compile(r"^(\d{1,2})\.\s+(.+)$")
ORGAN_LINE_RE = re.compile(r"^([A-Z])\.\s+(.+)$")
NUMBERED_LINE_RE = re.compile(r"^(\d+)\.\s+(.+)$")
LETTER_LINE_RE = re.compile(r"^([a-z])\.\s+(.+)$")
ROMAN_LINE_RE = re.compile(
    r"^(?P<roman>(?:i{1,3}|iv|v|vi{0,3}|ix|x{1,3}|xi{0,3}|xiv|xv|xvi{0,3}|xviii|xix|xx))\.\s+(.+)$",
    re.IGNORECASE,
)
DASH_LINE_RE = re.compile(r"^[\u2013\u2014\-]\s+(.+)$")
ORGAN_SUBSITE_SPLIT_RE = re.compile(
    r"^(The\s+.+?(?:Tract|System|Glands|Bone|Liver|Bladder|Pancreas|Mediastinum|Pleura))\s+(The\s+.+)$",
    re.IGNORECASE,
)
SKIP_PREFIX_RE = re.compile(
    r"^(Preparing for|Fundamental Knowledge|Overview|Guidance:|Key to Designations|C = |The specific diseases|Contents$)",
    re.IGNORECASE,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def para_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.findall(".//w:t", W_NS):
        parts.append(node.text or "")
        if node.tail:
            parts.append(node.tail)
    return normalize_whitespace("".join(parts))


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\ufb01", "fi").replace("\ufb02", "fl")
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")[:120]


def extract_paragraphs(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find("w:body", W_NS)
    if body is None:
        raise RuntimeError("DOCX missing word/document.xml body")
    paragraphs = [normalize_whitespace(para_text(element)) for element in body if element.tag.endswith("}p")]
    return [paragraph for paragraph in paragraphs if paragraph]


def split_level_suffix(text: str) -> tuple[str, str | None, bool]:
    match = LEVEL_SUFFIX_RE.search(text)
    if not match:
        return text, None, False
    level = match.group("level")
    prefix = text[: match.start()].rstrip()
    ambiguous = bool(
        re.search(r"(?<![\w/])(C|AR|F)(?![\w/.])", prefix)
        and not re.search(r"\b(Hepatitis [ABC]|Protein [CS]|Type C|Hb C|AD- or AR-|including Type C)\b", prefix)
    )
    return prefix, level, ambiguous


def major_title_matches(number: int, title: str) -> bool:
    expected = EXPECTED_MAJOR_SECTIONS.get(number)
    if not expected:
        return False
    title_norm = normalize_whitespace(title)
    if title_norm == expected:
        return True
    if title_norm.startswith(expected):
        return True
    return slugify(title_norm).startswith(slugify(expected)[:24])


def is_major_section_line(text: str) -> tuple[int, str] | None:
    match = MAJOR_LINE_RE.match(text)
    if not match:
        return None
    number = int(match.group(1))
    title, level, _ = split_level_suffix(match.group(2))
    if level is not None:
        return None
    if major_title_matches(number, title):
        return number, title
    return None


def classify_prefix(text: str) -> tuple[str, str, str] | None:
    for pattern, kind in (
        (ORGAN_LINE_RE, "organ"),
        (ROMAN_LINE_RE, "roman"),
        (LETTER_LINE_RE, "letter"),
        (NUMBERED_LINE_RE, "numbered"),
        (DASH_LINE_RE, "dash"),
    ):
        match = pattern.match(text)
        if match:
            if kind == "roman":
                return kind, match.group("roman").lower(), match.group(2)
            if kind == "dash":
                return kind, "-", match.group(1)
            return kind, match.group(1), match.group(2)
    return None


def should_skip_paragraph(text: str) -> bool:
    if SKIP_PREFIX_RE.match(text):
        return True
    if text.startswith("Anatomic Pathology Content Specifications"):
        return True
    if "C = Core/Foundational Knowledge" in text and "AR = Advanced Resident" in text:
        return True
    return False


def find_content_start(paragraphs: list[str]) -> int:
    seen_contents = False
    for index, text in enumerate(paragraphs):
        if text.strip().lower() == "contents":
            seen_contents = True
            continue
        if seen_contents:
            major = is_major_section_line(text)
            if major and major[0] == 1 and major[1] == "Breast":
                return index
    for index, text in enumerate(paragraphs):
        major = is_major_section_line(text)
        if major and major[0] == 1:
            return index
    raise RuntimeError("Could not locate start of ABPath AP content body (1. Breast)")


class HierarchyState:
    def __init__(self) -> None:
        self.major_number: int | None = None
        self.major_section = ""
        self.organ_system = ""
        self.subsection = ""
        self.category = ""
        self.path_parts: list[str] = []
        self.pending_continuation = ""

    def set_major(self, number: int, title: str) -> None:
        self.major_number = number
        self.major_section = f"{number}. {title}"
        self.organ_system = ""
        self.subsection = ""
        self.category = ""
        self.path_parts = [self.major_section]
        self.pending_continuation = ""

    def set_organ(self, label: str, title: str) -> None:
        subsite: str | None = None
        subsite_match = ORGAN_SUBSITE_SPLIT_RE.match(title)
        if subsite_match:
            title = subsite_match.group(1)
            subsite = subsite_match.group(2)
        self.organ_system = f"{label}. {title}"
        self.subsection = subsite or ""
        self.category = ""
        self.path_parts = [self.major_section, self.organ_system]
        if self.subsection:
            self.path_parts.append(self.subsection)
        self.pending_continuation = ""

    def set_subsection(self, label: str, title: str) -> None:
        self.subsection = f"{label}. {title}"
        self.category = ""
        if self.organ_system:
            self.path_parts = [self.major_section, self.organ_system, self.subsection]
        else:
            self.path_parts = [self.major_section, self.subsection]
        self.pending_continuation = ""

    def set_category(self, title: str) -> None:
        self.category = title
        base = [self.major_section]
        if self.organ_system:
            base.append(self.organ_system)
        if self.subsection:
            base.append(self.subsection)
        base.append(self.category)
        self.path_parts = base
        self.pending_continuation = ""

    def raw_path(self, item_text: str) -> str:
        parts = list(self.path_parts)
        if item_text:
            parts.append(item_text)
        return "::".join(parts)


def parse_rows(paragraphs: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    start_index = find_content_start(paragraphs)
    state = HierarchyState()
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_majors: set[int] = set()
    seq_by_major: Counter[int] = Counter()

    for index in range(start_index, len(paragraphs)):
        raw_text = paragraphs[index]
        if should_skip_paragraph(raw_text):
            continue

        major = is_major_section_line(raw_text)
        if major:
            number, title = major
            state.set_major(number, title)
            seen_majors.add(number)
            continue

        classified = classify_prefix(raw_text)
        if classified:
            kind, label, remainder = classified
            body, level, ambiguous = split_level_suffix(remainder)
            if kind == "organ":
                state.set_organ(label, body if level is None else f"{body} {level}".strip())
                if level is not None:
                    warnings.append(
                        {
                            "line_index": index,
                            "raw_text": raw_text,
                            "warning_type": "organ_line_with_terminal_level",
                            "detail": "Organ heading carried a terminal C/AR/F marker; treated as hierarchy only.",
                        }
                    )
                if level is None:
                    continue
            elif kind in {"letter", "roman", "dash"}:
                if level is None:
                    state.set_subsection(label, body)
                    continue
            elif kind == "numbered":
                if level is None:
                    state.set_category(f"{label}. {body}")
                    continue

            item_text = body
            if state.pending_continuation:
                item_text = normalize_whitespace(f"{state.pending_continuation} {item_text}")
                state.pending_continuation = ""
            row, row_warnings = build_row(
                state=state,
                item_text=item_text,
                raw_text=raw_text,
                level=level,
                ambiguous=ambiguous,
                line_index=index,
                seq_by_major=seq_by_major,
            )
            rows.append(row)
            warnings.extend(row_warnings)
            continue

        body, level, ambiguous = split_level_suffix(raw_text)
        if level is not None:
            item_text = body
            if state.pending_continuation:
                item_text = normalize_whitespace(f"{state.pending_continuation} {item_text}")
                state.pending_continuation = ""
            row, row_warnings = build_row(
                state=state,
                item_text=item_text,
                raw_text=raw_text,
                level=level,
                ambiguous=ambiguous,
                line_index=index,
                seq_by_major=seq_by_major,
            )
            rows.append(row)
            warnings.extend(row_warnings)
            continue

        if state.path_parts:
            if state.pending_continuation:
                state.pending_continuation = normalize_whitespace(f"{state.pending_continuation} {raw_text}")
            elif rows and not state.category:
                state.set_category(raw_text)
            else:
                state.pending_continuation = raw_text
        else:
            warnings.append(
                {
                    "line_index": index,
                    "raw_text": raw_text,
                    "warning_type": "orphan_non_terminal_line",
                    "detail": "Non-terminal line appeared before hierarchy was established.",
                }
            )

    missing_majors = sorted(set(EXPECTED_MAJOR_SECTIONS) - seen_majors)
    if missing_majors:
        missing_titles = [f"{num}. {EXPECTED_MAJOR_SECTIONS[num]}" for num in missing_majors]
        raise RuntimeError(f"Missing expected major sections: {', '.join(missing_titles)}")

    return rows, warnings


def build_row(
    *,
    state: HierarchyState,
    item_text: str,
    raw_text: str,
    level: str,
    ambiguous: bool,
    line_index: int,
    seq_by_major: Counter[int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if state.major_number is None:
        raise RuntimeError(f"Terminal row without major section at line {line_index}: {raw_text!r}")

    seq_by_major[state.major_number] += 1
    spec_id = f"ABPATH_AP_{state.major_number:02d}_{seq_by_major[state.major_number]:05d}"
    level_meta = LEVEL_META[level]
    raw_path = state.raw_path(item_text)
    normalized_item_key = slugify(raw_path)

    if state.major_number in AP_RESIDENT_TOPIC_MAJOR_NUMBERS:
        specialty_board_scope = "AP_resident_topic_only_not_subspecialty_board_spec"
    else:
        specialty_board_scope = "ABPath_AP_primary_certification"

    parser_confidence = "high"
    parser_note = ""
    if ambiguous:
        parser_confidence = "medium"
        parser_note = "Level suffix matched at line end; embedded designation text may be present."
        warnings.append(
            {
                "line_index": line_index,
                "raw_text": raw_text,
                "warning_type": "ambiguous_level_suffix",
                "detail": parser_note,
            }
        )
    if not item_text:
        parser_confidence = "low"
        parser_note = "Empty item_text after level extraction."
        warnings.append(
            {
                "line_index": line_index,
                "raw_text": raw_text,
                "warning_type": "empty_item_text",
                "detail": parser_note,
            }
        )

    row = {
        "abpath_spec_id": spec_id,
        "source_authority": SOURCE_AUTHORITY,
        "source_document": SOURCE_DOCUMENT,
        "source_scope": SOURCE_SCOPE,
        "major_section": state.major_section,
        "organ_system": state.organ_system,
        "subsection": state.subsection,
        "category": state.category,
        "item_text": item_text,
        "raw_path": raw_path,
        "raw_text": raw_text,
        "abpath_level": level,
        "abpath_level_label": level_meta["abpath_level_label"],
        "expected_resident_depth": level_meta["expected_resident_depth"],
        "specialty_board_scope": specialty_board_scope,
        "include_for_ap_primary_certification": True,
        "parser_confidence": parser_confidence,
        "parser_note": parser_note,
        "normalized_item_key": normalized_item_key,
    }
    return row, warnings


def validate_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("Parser produced zero terminal rows")

    for row in rows:
        if not row.get("raw_text"):
            raise RuntimeError(f"Row missing raw_text: {row.get('abpath_spec_id')}")
        if row.get("abpath_level") not in LEVEL_META:
            raise RuntimeError(f"Row missing normalized abpath_level: {row.get('abpath_spec_id')}")
        if "map_status" in row:
            raise RuntimeError("Registry rows must not include map_status")
        if row.get("abpath_level") in {"C", "AR", "F"} and row.get("abpath_level_label") != LEVEL_META[row["abpath_level"]]["abpath_level_label"]:
            raise RuntimeError(f"Level label mismatch for {row.get('abpath_spec_id')}")

    ids = [row["abpath_spec_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate abpath_spec_id values detected")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_level_lookup(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    lookup_rows = []
    for level, meta in LEVEL_META.items():
        lookup_rows.append(
            {
                "abpath_level": level,
                "abpath_level_label": meta["abpath_level_label"],
                "expected_resident_depth": meta["expected_resident_depth"],
                "is_map_status": "false",
                "is_approval_decision": "false",
                "usage_note": "Training-level metadata for ABPath AP primary certification content specifications only.",
            }
        )
    lookup_rows.append(
        {
            "abpath_level": "SPECIALTY_BOARD_SCOPE",
            "abpath_level_label": "AP_resident_topic_only_not_subspecialty_board_spec",
            "expected_resident_depth": "n/a",
            "is_map_status": "false",
            "is_approval_decision": "false",
            "usage_note": "Marks neuro/peds/heme rows that appear in AP primary cert doc but do not replace separate specialty-board specifications.",
        }
    )
    return lookup_rows


def build_audit(
    *,
    input_docx: Path,
    output_paths: dict[str, str],
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    rows_by_level = Counter(row["abpath_level"] for row in rows)
    rows_by_major = Counter(row["major_section"] for row in rows)
    rows_by_organ = Counter(row["organ_system"] or "(none)" for row in rows)
    ambiguous = sum(1 for row in rows if row["parser_confidence"] != "high")
    neuro_peds_heme = sum(
        1 for row in rows if row["specialty_board_scope"] == "AP_resident_topic_only_not_subspecialty_board_spec"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "input_docx_path": str(input_docx),
        "output_paths": output_paths,
        "total_rows": len(rows),
        "rows_by_abpath_level": dict(sorted(rows_by_level.items())),
        "rows_by_major_section": dict(rows_by_major.most_common()),
        "rows_by_organ_system": dict(rows_by_organ.most_common()),
        "rows_without_level": 0,
        "rows_with_ambiguous_level": ambiguous,
        "neuro_peds_heme_rows_marked_ap_only": neuro_peds_heme,
        "parser_warnings_count": len(warnings),
        "limitations": [
            "Parsed from local DOCX paragraph text only; no tables were present in the source file.",
            "C/AR/F values are training-level metadata and are not map_status or approval decisions.",
            "Neuropathology, Pediatric Pathology, and Hematopathology rows are retained for AP primary-certification context only.",
            "This registry is staged for human review and metadata enrichment; it is not API/live and was not uploaded to GCS.",
            "Section 15 is absent in the source document; major sections 1-14 and 16-18 were required and validated.",
        ],
    }


def write_readme(path: Path) -> None:
    path.write_text(
        """# ABPath AP Content Specifications Registry v0_1

## What this registry is

A staged, local parse of the American Board of Pathology (ABPath) **Anatomic Pathology Primary Certification Content Specifications** DOCX. Each row is a terminal curriculum item that carries an ABPath training designation (`C`, `AR`, or `F`).

## What this registry is not

- Not an API/live deployment artifact
- Not a curriculum map or gapfill output
- Not a replacement for separate Neuropathology, Pediatric Pathology, or Hematopathology specialty-board specifications
- Not an approval/rejection decision layer for Pathology Hub content

## How to interpret C / AR / F

| Code | Label | Expected resident depth |
|------|-------|-------------------------|
| C | Core / Foundational | mastery |
| AR | Advanced Resident | competence |
| F | Fellow / Advanced Practitioner | superficial familiarity for residents |

These values are **training-level metadata only**. They must not be copied into `map_status` or used as approve/reject gates.

Rows in major sections 16–18 (Hematopathology, Neuropathology, Pediatric Pathology AP-resident topics) are included for AP primary-certification context and are tagged with:

`specialty_board_scope = AP_resident_topic_only_not_subspecialty_board_spec`

## How this can enrich curriculum mapping later

Future curriculum-map sidecars can join on `normalized_item_key` or fuzzy matches to `item_text` / `raw_path` to add:

- expected resident depth targets
- ABPath training-level context for lecture/textbook tags
- specialty-board scope disclaimers for neuro/peds/heme AP-resident topics

This is metadata enrichment only. It does not change v0_4 `map_status` values.

## Why this is not API/live

This package was generated locally, audited under `06_audits/abpath_content_specs/v0_1/`, and was not uploaded to GCS or promoted to production services.

## Files

- `abpath_ap_content_specs_v0_1.csv` — flat review/export file
- `abpath_ap_content_specs_v0_1.jsonl` — machine-readable registry rows
- `abpath_ap_content_specs_v0_1_audit.json` — parse audit with counts and limitations
- `abpath_ap_content_specs_v0_1_parse_warnings.csv` — non-fatal parser warnings

Companion lookup table:

- `outputs/abpath_registry_v0_1/abpath_level_lookup.csv`
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-docx", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--registry-dir", type=Path, default=DEFAULT_REGISTRY_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input_docx.exists():
        raise SystemExit(f"Input DOCX not found: {args.input_docx}")

    paragraphs = extract_paragraphs(args.input_docx)
    rows, warnings = parse_rows(paragraphs)
    validate_rows(rows)

    args.audit_dir.mkdir(parents=True, exist_ok=True)
    args.registry_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.audit_dir / "abpath_ap_content_specs_v0_1.csv"
    jsonl_path = args.audit_dir / "abpath_ap_content_specs_v0_1.jsonl"
    audit_path = args.audit_dir / "abpath_ap_content_specs_v0_1_audit.json"
    warnings_path = args.audit_dir / "abpath_ap_content_specs_v0_1_parse_warnings.csv"
    readme_path = args.audit_dir / "README.md"
    lookup_path = args.registry_dir / "abpath_level_lookup.csv"

    write_csv(csv_path, rows, ROW_FIELDS)
    write_jsonl(jsonl_path, rows)
    write_csv(
        warnings_path,
        warnings,
        ["line_index", "raw_text", "warning_type", "detail"],
    )
    write_csv(
        lookup_path,
        build_level_lookup(rows),
        [
            "abpath_level",
            "abpath_level_label",
            "expected_resident_depth",
            "is_map_status",
            "is_approval_decision",
            "usage_note",
        ],
    )
    write_readme(readme_path)

    output_paths = {
        "csv": str(csv_path),
        "jsonl": str(jsonl_path),
        "audit_json": str(audit_path),
        "parse_warnings_csv": str(warnings_path),
        "readme": str(readme_path),
        "level_lookup_csv": str(lookup_path),
    }
    audit = build_audit(
        input_docx=args.input_docx,
        output_paths=output_paths,
        rows=rows,
        warnings=warnings,
    )
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
