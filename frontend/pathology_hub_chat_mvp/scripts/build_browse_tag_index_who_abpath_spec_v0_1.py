#!/usr/bin/env python3
"""Build Browse nav from WHO + real ABPath AP Content Specifications only.

Replaces the bloated `abpath_source_tags.jsonl` ontology (~6k expanded tags)
with terminal entities parsed from the official ABPath Anatomic Pathology
Content Specifications PDF/DOCX, plus WHO leaves.

Inputs:
  - data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.pdf
    (or .docx)
  - Existing WHO leaves from the previous browse index snapshot
    (frontend/.../static/browse_tag_index_v0_1.json) when who_processed/ is
    unavailable in this environment; OR data/curriculum_map_v0_2/who_processed

Outputs:
  - outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
  - outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
  - frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json
  - 06_audits/abpath_content_specs/v0_1_pdf/… parse sidecars
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
MVP_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_REPO = REPO_ROOT / "scripts"
if str(SCRIPTS_REPO) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_REPO))

from parse_abpath_ap_content_specs_v0_1 import (  # noqa: E402
    LEVEL_SUFFIX_RE,
    normalize_whitespace,
    parse_rows,
    slugify,
    validate_rows,
    write_csv,
    write_jsonl,
    ROW_FIELDS,
)

PDF_PATH = REPO_ROOT / "data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.pdf"
DOCX_PATH = REPO_ROOT / "data/source_specs/ABPath_Anatomic_Pathology_Content_Specifications.docx"
WHO_DIR = REPO_ROOT / "data/curriculum_map_v0_2/who_processed"
PRIOR_INDEX = MVP_DIR / "static" / "browse_tag_index_v0_1.json"
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
WHO_SNAPSHOT = OUTPUT_DIR / "who_nav_leaves_snapshot_v0_1.json"
PATHOUT_TAG_CSV = REPO_ROOT / "audits/curriculum_map_readiness_v0/pathout_local_tag_review.csv"
AUDIT_DIR = REPO_ROOT / "06_audits/abpath_content_specs/v0_1_pdf"
INDEX_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.json"
AUDIT_PATH = OUTPUT_DIR / "browse_tag_index_v0_1.audit.json"
STATIC_COPY = MVP_DIR / "static" / "browse_tag_index_v0_1.json"

SCHEMA_VERSION = "browse_tag_index_v0_4"

# Content-spec major section number → Browse root id / display label.
#
# Major 4 ("Cardiovascular") deliberately maps into thorax_mediastinum, not
# its own "cardio" root (2026-08-02 feedback: WHO's own Thoracic Tumours
# volume classifies heart tumors under Thorax_Mediastinum::Heart — real WHO
# tags for this already exist in our data, e.g.
# "Thorax_Mediastinum::Heart::Benign::Cardiac_Rhabdomyoma" — and a separate
# flat "cardio" root with no organ segment ("ABPathSpec::cardio::benign::
# cardiac_myxoma") was both non-WHO-aligned and structurally shallower than
# every other root. See CARDIO_ABPATH_SPEC_RANGES / cardio_abpath_organ_and_category.
MAJOR_TO_ROOT: dict[int, tuple[str, str]] = {
    1: ("breast", "Breast"),
    2: ("gu", "Genitourinary"),
    3: ("gu", "Genitourinary"),
    4: ("thorax_mediastinum", "Thorax / Mediastinum"),
    5: ("hn", "Head and Neck"),
    6: ("gi", "Gastrointestinal"),
    7: ("endo", "Endocrine"),
    8: ("gyn", "Gynecologic"),
    9: ("gyn", "Gynecologic"),
    10: ("thorax_mediastinum", "Thorax / Mediastinum"),
    11: ("bst", "Bone / Soft Tissue"),
    12: ("cyto", "Cytopathology"),
    13: ("skin", "Dermatopathology"),
    14: ("forensic", "Forensic Pathology"),
    16: ("heme", "Hematolymphoid"),
    17: ("neuro", "Neuropathology"),
    18: ("peds", "Pediatric Pathology"),
}

# Skip TOC / non-entity noise if any slip through.
SKIP_ITEM_RE = re.compile(
    r"^(contents|overview|guidance|preparing for|american board|page\s*\d+)\b",
    re.I,
)

# --- Cytopathology organ-system reclassification -----------------------
#
# Reported problem (2026-08-01): every Cytopathology entity — WHO Cyto_*
# tags AND ABPath's major-section-12 content-spec rows — landed in ONE flat
# "Cytopathology" root with ~70 first-level Browse subcategories, most of
# them ABPath's own generic content-spec section headers ("Adenocarcinomas",
# "Malignant Neoplasms", "SIL", "Reactive/Reparative", …) that name a
# histologic category, not an organ. The user wants organ system to be the
# FIRST branch (e.g. Cyto_GYN -> "Gynecologic Cytopathology", Cyto_Heme ->
# "Hematolymphoid Cytopathology"), matching how every other Browse root
# already branches (breast, GU, GI, …), with the finer histologic category
# preserved as a second-level branch underneath.
#
# One canonical label per organ system, shared by WHO Cyto_<suffix> tags,
# PathOut Cyto_<suffix> tags, and ABPath content-spec major-section-12 rows,
# so all three provenances land in the SAME Browse subcategory bucket
# (bucket identity is the label string, see normalize_subcategory).
CYTO_SYSTEM_GYN = "Gynecologic Cytopathology"
CYTO_SYSTEM_FLUID = "Effusion / Serous & Synovial Fluid Cytopathology"
CYTO_SYSTEM_CNS_EYE = "CNS / Eye Cytopathology"
CYTO_SYSTEM_GU = "Genitourinary / Urinary Tract Cytopathology"
CYTO_SYSTEM_THORACIC = "Thoracic / Pulmonary Cytopathology"
CYTO_SYSTEM_GI = "Gastrointestinal Cytopathology"
CYTO_SYSTEM_HEPATOBILIARY = "Hepatobiliary / Pancreatic Cytopathology"
CYTO_SYSTEM_SALIVARY = "Salivary Gland Cytopathology"
CYTO_SYSTEM_THYROID = "Thyroid / Parathyroid Cytopathology"
CYTO_SYSTEM_HEME = "Hematolymphoid Cytopathology"
CYTO_SYSTEM_HN = "Head and Neck Cytopathology"
CYTO_SYSTEM_BREAST = "Breast Cytopathology"
CYTO_SYSTEM_MEDIASTINUM = "Mediastinum / Retroperitoneum Cytopathology"
CYTO_SYSTEM_ADRENAL = "Adrenal Cytopathology"
CYTO_SYSTEM_BONE_SOFT_TISSUE = "Bone / Soft Tissue Cytopathology"
CYTO_SYSTEM_GENERAL = "General Cytopathology Techniques & QA"

# Canonical system label -> native "Cyto_<Suffix>" tag prefix, matching the
# real WHO/PathOut `Cyto_<Suffix>` convention already present in source data
# (Cyto_Heme, Cyto_Pancreatobiliary, Cyto_Soft_Tissue, Cyto_Thoracic) so
# ABPath-derived leaves land under the exact same tag prefix as real WHO
# ones for that system and merge naturally, rather than a separate
# "ABPathSpec::cyto::…" synthetic wrapper (2026-08-02 feedback: "get rid of
# the abpath part and use current logic of things"). Systems with no real
# WHO Cyto_<Suffix> precedent yet (Adrenal, GU, GI, HN, Salivary, Thyroid,
# Breast, Mediastinum, CNS/Eye, Fluid, General) get a same-style native
# prefix invented from the organ name, consistent with the ones that do.
CYTO_SYSTEM_TO_NATIVE_PREFIX: dict[str, str] = {
    CYTO_SYSTEM_GYN: "Cyto_GYN",
    CYTO_SYSTEM_FLUID: "Cyto_Fluid",
    CYTO_SYSTEM_CNS_EYE: "Cyto_CNS_Eye",
    CYTO_SYSTEM_GU: "Cyto_GU",
    CYTO_SYSTEM_THORACIC: "Cyto_Thoracic",
    CYTO_SYSTEM_GI: "Cyto_GI",
    CYTO_SYSTEM_HEPATOBILIARY: "Cyto_Pancreatobiliary",
    CYTO_SYSTEM_SALIVARY: "Cyto_Salivary",
    CYTO_SYSTEM_THYROID: "Cyto_Thyroid",
    CYTO_SYSTEM_HEME: "Cyto_Heme",
    CYTO_SYSTEM_HN: "Cyto_HN",
    CYTO_SYSTEM_BREAST: "Cyto_Breast",
    CYTO_SYSTEM_MEDIASTINUM: "Cyto_Mediastinum",
    CYTO_SYSTEM_ADRENAL: "Cyto_Adrenal",
    CYTO_SYSTEM_BONE_SOFT_TISSUE: "Cyto_Soft_Tissue",
    CYTO_SYSTEM_GENERAL: "Cyto_General",
}

# The 5-tier Bethesda-style reporting scheme used across essentially every
# FNA/cytology reporting system (WHO's own International System for
# Reporting). Used two ways: (1) classify each ABPath-derived cyto leaf
# into one of the diagnostic tiers via keyword heuristics on its own label
# (never fabricated — every leaf here is a real content-spec/WHO entity,
# just re-bucketed); (2) emit one lightweight "Category" definition leaf
# per tier per system as a structural/navigational aid (2026-08-02
# feedback's Cyto_Adrenal::Category::* example) — these are standardized
# reporting-scheme labels, not sourced diagnosis content, and are disclosed
# as such in known_limitations.
CYTO_BETHESDA_TIERS = ["Nondiagnostic", "Benign", "Atypical", "Suspicious_For_Malignancy", "Malignant"]

_CYTO_BETHESDA_RULES: list[tuple[str, "re.Pattern"]] = [
    (
        "Malignant",
        re.compile(
            r"(?i)malignant|carcinoma|adenocarcinoma|sarcoma|lymphoma|leuk[ae]mia|"
            r"metasta|blastoma|malignancy"
        ),
    ),
    ("Suspicious_For_Malignancy", re.compile(r"(?i)suspicious")),
    ("Atypical", re.compile(r"(?i)atypia|atypical")),
    (
        "Nondiagnostic",
        re.compile(r"(?i)insufficient|inadequate|non-?diagnostic|unsatisfactory|contaminant"),
    ),
]


def cyto_bethesda_category(label: str) -> str:
    """Heuristic reporting-tier bucket for a real cyto diagnosis leaf's own
    label — never invented content, just a coarser grouping. Necessarily
    imperfect for genuinely borderline entities (e.g. pheochromocytoma);
    disclosed as a heuristic, not a WHO-authoritative call, in
    known_limitations. Defaults to "Benign" (the modal category) absent a
    stronger signal."""
    for tier, rx in _CYTO_BETHESDA_RULES:
        if rx.search(label or ""):
            return tier
    return "Benign"

# WHO/PathOut `Cyto_<Suffix>` tag prefixes only carry a per-organ suffix
# (e.g. "Cyto_GYN", "Cyto_Heme") — map each real suffix seen in source data
# to the same canonical system label used by the ABPath range table below.
# Unrecognized suffixes fall back to "<Suffix> Cytopathology" (own bucket,
# never dropped — see `cyto_who_system_label`).
CYTO_WHO_SUFFIX_LABELS: dict[str, str] = {
    "gyn": CYTO_SYSTEM_GYN,
    "gynecologic": CYTO_SYSTEM_GYN,
    "vulva": CYTO_SYSTEM_GYN,
    "vagina": CYTO_SYSTEM_GYN,
    "cervix": CYTO_SYSTEM_GYN,
    "fluid": CYTO_SYSTEM_FLUID,
    "fluids": CYTO_SYSTEM_FLUID,
    "effusion": CYTO_SYSTEM_FLUID,
    "effusions": CYTO_SYSTEM_FLUID,
    "serous": CYTO_SYSTEM_FLUID,
    "synovial": CYTO_SYSTEM_FLUID,
    "cns": CYTO_SYSTEM_CNS_EYE,
    "csf": CYTO_SYSTEM_CNS_EYE,
    "eye": CYTO_SYSTEM_CNS_EYE,
    "neuro": CYTO_SYSTEM_CNS_EYE,
    "gu": CYTO_SYSTEM_GU,
    "urinary": CYTO_SYSTEM_GU,
    "urine": CYTO_SYSTEM_GU,
    "bladder": CYTO_SYSTEM_GU,
    "kidney": CYTO_SYSTEM_GU,
    "kidneys": CYTO_SYSTEM_GU,
    "renal": CYTO_SYSTEM_GU,
    "prostate": CYTO_SYSTEM_GU,
    "thoracic": CYTO_SYSTEM_THORACIC,
    "thorax": CYTO_SYSTEM_THORACIC,
    "lung": CYTO_SYSTEM_THORACIC,
    "pulmonary": CYTO_SYSTEM_THORACIC,
    "respiratory": CYTO_SYSTEM_THORACIC,
    "gi": CYTO_SYSTEM_GI,
    "gi_tract": CYTO_SYSTEM_GI,
    "gastric": CYTO_SYSTEM_GI,
    "gastrointestinal": CYTO_SYSTEM_GI,
    "esophagus": CYTO_SYSTEM_GI,
    "pancreatobiliary": CYTO_SYSTEM_HEPATOBILIARY,
    "pancreas": CYTO_SYSTEM_HEPATOBILIARY,
    "pancreatic": CYTO_SYSTEM_HEPATOBILIARY,
    "biliary": CYTO_SYSTEM_HEPATOBILIARY,
    "liver": CYTO_SYSTEM_HEPATOBILIARY,
    "hepatobiliary": CYTO_SYSTEM_HEPATOBILIARY,
    "salivary": CYTO_SYSTEM_SALIVARY,
    "salivary_gland": CYTO_SYSTEM_SALIVARY,
    "thyroid": CYTO_SYSTEM_THYROID,
    "parathyroid": CYTO_SYSTEM_THYROID,
    "heme": CYTO_SYSTEM_HEME,
    "hematolymphoid": CYTO_SYSTEM_HEME,
    "lymphnode": CYTO_SYSTEM_HEME,
    "lymph_node": CYTO_SYSTEM_HEME,
    "hn": CYTO_SYSTEM_HN,
    "headandneck": CYTO_SYSTEM_HN,
    "head_and_neck": CYTO_SYSTEM_HN,
    "intraoral": CYTO_SYSTEM_HN,
    "breast": CYTO_SYSTEM_BREAST,
    "mediastinum": CYTO_SYSTEM_MEDIASTINUM,
    "retroperitoneum": CYTO_SYSTEM_MEDIASTINUM,
    "adrenal": CYTO_SYSTEM_ADRENAL,
    "soft_tissue": CYTO_SYSTEM_BONE_SOFT_TISSUE,
    "softtissue": CYTO_SYSTEM_BONE_SOFT_TISSUE,
    "bone": CYTO_SYSTEM_BONE_SOFT_TISSUE,
    "skin": CYTO_SYSTEM_BONE_SOFT_TISSUE,
    "general": CYTO_SYSTEM_GENERAL,
    "management": CYTO_SYSTEM_GENERAL,
}


def cyto_who_system_label(cyto_suffix: str) -> str:
    """Canonical organ-system Browse label for a WHO/PathOut `Cyto_<suffix>`
    tag prefix — never drops the leaf, falls back to "<Suffix> Cytopathology"
    for a suffix not in the curated map above (disclosed as a limitation)."""
    key = re.sub(r"[^a-z0-9]+", "_", (cyto_suffix or "").strip().lower()).strip("_")
    if key in CYTO_WHO_SUFFIX_LABELS:
        return CYTO_WHO_SUFFIX_LABELS[key]
    pretty = re.sub(r"[_\-]+", " ", (cyto_suffix or "").strip()).strip() or "General"
    return f"{pretty.title()} Cytopathology"


# ABPath's Anatomic Pathology Content Specifications major section 12
# ("Cytopathology Topics for Anatomic Pathology Residents") only labels
# ~11% of its own rows with a recoverable organ-system heading (DOCX
# paragraph-text parsing lost the rest — see `organ_system` always being
# empty in the parsed registry). Row order is stable (deterministic re-parse
# of a static source PDF/DOCX), so the true organ-system boundaries were
# reconstructed by hand once from the full ordered row dump — each range is
# a contiguous, content-verified organ block (e.g. rows 1-53 progress
# Pap/cervical screening -> SIL -> anogenital squamous lesions -> ovarian
# cysts, all Gynecologic). Ranges are inclusive of `abpath_spec_id`'s
# trailing sequence number *within major section 12 only*.
CYTO_ABPATH_SPEC_RANGES: list[tuple[int, int, str]] = [
    (1, 53, CYTO_SYSTEM_GYN),
    (54, 118, CYTO_SYSTEM_FLUID),
    (119, 150, CYTO_SYSTEM_CNS_EYE),
    (151, 178, CYTO_SYSTEM_GU),
    (179, 243, CYTO_SYSTEM_THORACIC),
    (244, 261, CYTO_SYSTEM_GI),
    (262, 312, CYTO_SYSTEM_HEPATOBILIARY),
    (313, 341, CYTO_SYSTEM_SALIVARY),
    (342, 366, CYTO_SYSTEM_THYROID),
    (367, 389, CYTO_SYSTEM_HEME),
    (390, 408, CYTO_SYSTEM_HN),
    (409, 429, CYTO_SYSTEM_BREAST),
    (430, 450, CYTO_SYSTEM_MEDIASTINUM),
    (451, 467, CYTO_SYSTEM_GU),
    (468, 477, CYTO_SYSTEM_ADRENAL),
    (478, 531, CYTO_SYSTEM_BONE_SOFT_TISSUE),
    (532, 561, CYTO_SYSTEM_GENERAL),
]


def cyto_abpath_system_for_spec_id(abpath_spec_id: str) -> Optional[str]:
    """Organ-system Browse label for an ABPath major-12 row, from its
    spec-id sequence number — see `CYTO_ABPATH_SPEC_RANGES`. None if the
    id is missing/unparseable (caller falls back to General)."""
    match = re.search(r"_(\d+)$", abpath_spec_id or "")
    if not match:
        return None
    n = int(match.group(1))
    for start, end, label in CYTO_ABPATH_SPEC_RANGES:
        if start <= n <= end:
            return label
    return None


# --- Cardiovascular (major 4) -> Thorax_Mediastinum::<Organ> reclassification
#
# Same problem/technique as Cytopathology above: ABPath's own major-4 rows
# never label an organ_system (parser gap), and the content itself
# alternates between genuinely cardiac topics (cardiomyopathy, myocarditis,
# cardiac tumors, transplant) and general vascular disease (vasculitis,
# aneurysms, hereditary vessel disease, atherosclerosis) with no other
# structural marker than raw row order. Reconstructed by hand from the
# ordered row dump, same as CYTO_ABPATH_SPEC_RANGES.
CARDIO_ORGAN_HEART = "Heart"
CARDIO_ORGAN_VESSELS = "Blood_Vessels"

CARDIO_ABPATH_SPEC_RANGES: list[tuple[int, int, str]] = [
    (1, 2, CARDIO_ORGAN_HEART),
    (3, 5, CARDIO_ORGAN_HEART),
    (6, 10, CARDIO_ORGAN_VESSELS),
    (11, 17, CARDIO_ORGAN_HEART),
    (18, 21, CARDIO_ORGAN_VESSELS),
    (22, 27, CARDIO_ORGAN_HEART),
    (28, 38, CARDIO_ORGAN_VESSELS),
    (39, 53, CARDIO_ORGAN_HEART),
]


def cardio_organ_for_spec_id(abpath_spec_id: str) -> str:
    """Heart vs Blood_Vessels for an ABPath major-4 row, from its spec-id
    sequence number — see CARDIO_ABPATH_SPEC_RANGES. Defaults to Heart
    (the majority organ for this major) if the id is unparseable."""
    match = re.search(r"_(\d+)$", abpath_spec_id or "")
    if not match:
        return CARDIO_ORGAN_HEART
    n = int(match.group(1))
    for start, end, organ in CARDIO_ABPATH_SPEC_RANGES:
        if start <= n <= end:
            return organ
    return CARDIO_ORGAN_HEART


# Browse topics must be actual diagnoses / disease entities — not cell types,
# normal anatomy, lab methods, QA, or generic curriculum headers.
DIAGNOSIS_HINT_RE = re.compile(
    r"(?i)\b("
    r"carcinoma|adenocarcinoma|sarcoma|lymphoma|leukemia|melanoma|myeloma|"
    r"adenoma|papilloma|hamartoma|blastoma|glioma|meningioma|schwannoma|"
    r"neoplasm|tumor|tumour|malignanc|metastas|in situ|dysplasia|metaplasia|"
    r"hyperplasia|polyp|cyst(?!ic fibrosis)|abscess|granuloma|"
    r"disease|disorder|syndrome|anomaly|malformation|atresia|"
    r"infection|pneumonia|hepatitis|nephritis|colitis|gastritis|dermatitis|"
    r"dermatosis|vasculitis|pemphigus|lupus|sarcoidosis|amyloid|"
    r"anemia|thalassemia|spherocytosis|elliptocytosis|thrombocytopenia|"
    r"hemophilia|thrombophilia|polycythemia|myelofibrosis|myelodysplas|"
    r"leukocytos|neutropenia|eosinophilia|mastocytosis|histiocytosis|"
    r"infarct|embolism|atherosclero|aneurysm|stenosis|thrombosis|"
    r"tuberculosis|histoplasma|candida|aspergillus|malaria|babesia|"
    r"mgus|mds\b|mpn\b|cmml|cll|sll|dlbcl|\baml\b|\ball\b|\bcml\b|"
    r"ptld|hlh\b|ttp\b|hus\b|dic\b|pnh\b|poems|"
    r"atypical |suspicious for|malignant |benign [a-z].*(oma|osis|itis)|"
    r"itis\b|osis\b|oma\b|omas\b"
    r")",
)

NON_DIAGNOSIS_ITEM_RE = re.compile(
    r"(?i)^(?:"
    r".*\bnormal anatomy\b.*|.+\bnormal histology\b.*|.+\bnormal cytology\b.*|"
    r"normal anatomy.*|normal histology.*|normal cytology.*|normal microanatomy.*|"
    r"normal (?:bladder|salivary|thyroid|breast|lung|liver|elements?|voided|upper urinary|hemostasis).*"
    r"|normal,? nilm$|normal development.*|normal / negative.*|normal hematopoiesis$"
    r"|physiologic changes.*"
    r"|diagnostic methodologies|basic methods|basic methodology|pitfalls|"
    r"general consideration|laboratory (?:management|inspections|diagnostics)|"
    r"rules and regulations|quality assurance.*|qa/qc.*|quality statistics|"
    r"coding and billing|.*\bbilling\b.*|informatics|safety|accreditation|"
    r"regulations and safety|compliance programs.*|"
    r"cytologic-histologic correlation.*|five-year retrospective review.*|"
    r"record and slide retention|reporting rates|rescreening.*|workload limits|"
    r"test development and validation|storage / preservation|"
    r".*\bancillary (?:studies|testing)\b.*|ihc and flow cytometry|"
    r"molecular studies\b.*|constitutional fish|neoplastic fish|"
    r"development of reference ranges.*|loss of heterozygosity studies|"
    r"vascular injection studies|blood stain pattern interpretation|"
    r".*\b(?:techniques?|methods?|methodology|processing|fixation|instrument(?:ation)?s?|"
    r"screening|sampling)\b.*"
    r"|.*\btesting\b$|.*\bmonitoring\b$"
    r"|sample collection and processing|preparatory techniques.*"
    r"|wbc analysis|rbc analysis|platelet analysis|"
    r"romanovsky type stains|routine and special histologic stains|"
    r"cytochemical and advanced hematology stains|"
    r"peripheral blood smear review|bone marrow review|fluid review|"
    r"review of other tissues in hematopathology|"
    r"classical|fish|advanced flow cytometry|lymphoid testing|myeloid testing|"
    r"pnh & other non-neoplastic disease testing|"
    r"alkaline & acid electrophoresis|capillary electrophoresis|"
    r"high performance liquid chromatography.*|isoelectric focusing|"
    r"advance hemoglobinopathy analysis|"
    r"antiplatelet agent monitoring|warfarin and warfarin monitoring|"
    r"heparin and heparinoid monitoring|direct thrombin and factor xa inhibitor monitoring|"
    r"clonality/lineage|translocations/mutations|coagulation-related molecular testing|"
    r"other molecular assays.*|other cytogenetic techniques.*"
    r"|adrenal cortical hormones|endocrine tests|"
    r"coagulation and fibrinolysis$|"
    r"advanced erythrocyte abnormalities|therapy related effects|"
    r"basal plate|chorionic villi|fetal vessels|maternal intervillous space|"
    r"membranes$|umbilical cord$|other elements\b.*|benign thyroid$|benign parathyroid$|"
    r"infectious$|malignant$|"
    r"fna performance-related safety measures|specimen adequacy$|"
    r"administration and management$|slide preparation$|"
    r"specimen requisition.*|unsatisfactory$|contaminants.*"
    r")$",
)

# Content-spec bucket headers that are curriculum folders, not diagnoses.
# Require plural folders (tumors/conditions/…) so "Benign Mixed Tumor" stays.
BUCKET_HEADER_ITEM_RE = re.compile(
    r"(?i)^(?:"
    r"(?:other )?(?:benign|malignant|premalignant|borderline|congenital|developmental|"
    r"familial|inflammatory|infectious|physiologic|metabolic|miscellaneous|"
    r"hereditary)(?:[,/ ].*)?(?:tumors|tumours|lesions|conditions|disorders|"
    r"neoplasms|changes|processes)$|"
    r"congenital,\s*developmental,\s*and\s*familial\s*conditions|"
    r"premalignant,\s*malignant,\s*and\s*borderline|"
    r"physiologic changes,\s*metabolic conditions.*"
    r"|benign soft tissue tumors of intermediate malignancy of uncertain type|"
    r"benign fibrous/myofibroblastic lesions|"
    r"benign fibrohistiocytic tumors|"
    r"benign osseous soft tissue tumors|"
    r"benign soft tissue tumors of uncertain type|"
    r"benign tumors of the synovium|"
    r"benign cartilaginous tumors|"
    r"benign bone cysts|"
    r"malignant cartilaginous soft tissue tumors|"
    r"malignant osseous soft tissue tumors|"
    r"other (?:uncommon )?carcinomas|"
    r"other (?:benign|malignant|chondroid|metabolic|mds|mpn|myeloproliferative|"
    r"histiocytic|cutaneous|mature|erythrocyte|body fluids|iatrogenic|"
    r"large b-cell|b lymphoblastic|aml|infectious|hemoglobinopath).*"
    r")$",
)

# Bare lineage / cell-type curriculum rows (keep when diagnosis-hinted).
CELL_TYPE_ITEM_RE = re.compile(
    r"(?i)^(?:"
    r"(?:other )?(?:myeloid|lymphoid) cells|"
    r"monocytes?(?:/dendritic cells)?(?:\s*[–—-].*)?|"
    r"neutrophils?(?:\s*[–—-].*)?|"
    r"eosinophils?(?:\s+and\s+basophils)?(?:/basophils(?:/mast cells)?)?(?:\s*[–—-].*)?|"
    r"basophils?(?:\s*[–—-].*)?|"
    r"lymphocytes?(?:\s*[–—-].*)?|"
    r"plasma cells?$|"
    r"macrophages?$|"
    r"dendritic cells?$|"
    r"plasmacytoid dendritic cells?$|"
    r"leukocytes?(?:\s*\(.*\))?$|"
    r"white cells and macrophages|"
    r"erythrocytes?(?:\s*\(rbcs?\))?$|"
    r"nk-?cells?$|"
    r"inflammatory cells$|"
    r"urothelial cells$|"
    r"squamous cells$|"
    r"squamous cell contamination$|"
    r"shed endometrial cells$|"
    r"alveolar macrophages$|"
    r"non-neoplastic mesothelial cells$|"
    r"choroid plexus and ependymal cells$|"
    r"bronchial\s*\(e\.g\..*cells.*\)|"
    r"other\s*\(e\.g\.,\s*mesothelial cells.*\)|"
    r"a\)\s*non-neoplastic\s*\(e\.g\.,\s*lymphocyte subsets\)"
    r")$",
)

GENERIC_HEADER_ITEM_RE = re.compile(
    r"(?i)^(?:"
    r"genetic abnormalities|miscellaneous|"
    r"indications for evaluation(?: and complications)?|"
    r"indications for evaluation, including imaging findings|"
    r"acquired|immune|inherited|iatrogenic|viral-associated|extranodal|classic$"
    r")$",
)

NON_DIAGNOSIS_PATH_RE = re.compile(
    r"(?i)("
    r"normal anatomy|normal histology|hematopoiesis and hemostasis|"
    r"general hematology testing and hematology instruments|"
    r"staining methods|"
    r"hematology & hematopathology-specific administration|"
    r"laboratory management|administration & management|"
    r"cytopathology billing|cytopathology qc/?qa|"
    r"cytopathology laboratory administration|"
    r"autopsy procedures|special anatomic procedures|"
    r"ancillary testing|indications\s*/\s*techniques|indications and sampling|"
    r"preparation techniques|specimen (?:collection|processing|adequacy)|"
    r"screening and review methods|screening, indications|"
    r"technical aspects and test utilization|"
    r"molecular analysis|cytogenetics|"
    r"fluid specimens|other techniques|"
    r"administration & management|selected topics/management"
    r")",
)

# Canonical subcategory ids/labels so WHO "Bone" and ABPath "Bones" collapse.
SUBCATEGORY_ALIASES: dict[str, tuple[str, str]] = {
    "bone": ("bone", "Bone"),
    "bones": ("bone", "Bone"),
    "soft tissue": ("soft_tissue", "Soft Tissue"),
    "soft_tissue": ("soft_tissue", "Soft Tissue"),
    "soft tissueadipocytic": ("soft_tissue", "Soft Tissue"),
    "soft_tissueadipocytic": ("soft_tissue", "Soft Tissue"),
    "round cell sarcomas": ("round_cell_sarcomas", "Round Cell Sarcomas"),
    "round_cell_sarcomas": ("round_cell_sarcomas", "Round Cell Sarcomas"),
    "cyst and neoplasms": ("cysts_and_neoplasms", "Cysts and Neoplasms"),
    "cysts and neoplasms": ("cysts_and_neoplasms", "Cysts and Neoplasms"),
    "malformation": ("malformations", "Malformations"),
    "malformations": ("malformations", "Malformations"),
    "joint": ("joints", "Joints"),
    "joints": ("joints", "Joints"),
    # Heme must always read as "Hematolymphoid" — root AND subcategory.
    "heme": ("hematolymphoid", "Hematolymphoid"),
    "hematolymphoid": ("hematolymphoid", "Hematolymphoid"),
    "hematopathology": ("hematolymphoid", "Hematolymphoid"),
    # A subcategory literally named "Other"/"Others" is a catch-all, not an
    # organ/family grouping — normalize to the standard "General" bucket.
    "other": ("general", "General"),
    "others": ("general", "General"),
    "miscellaneous": ("general", "General"),
    # WHO's narrow per-site tag vs ABPath's broader content-spec section
    # heading for the same anatomic scope — verified by inspecting leaf tags.
    "gtd": ("gestational_trophoblastic_disease", "Gestational Trophoblastic Disease"),
    "cervix": ("uterine_cervix", "Uterine Cervix"),
    "fallopian tube": ("fallopian_tubes_and_broad_ligaments", "Fallopian Tubes and Broad Ligaments"),
    "ear": ("ear_and_temporal_bone", "Ear and Temporal Bone"),
    "nasopharynx": ("nose_paranasal_sinuses_and_nasopharynx", "Nose, Paranasal Sinuses, and Nasopharynx"),
    "oropharynx": ("jaws_oral_cavity_and_oropharynx", "Jaws, Oral Cavity, and Oropharynx"),
}

# Acronyms to re-uppercase after title-casing all-caps ABPath section headers
# (e.g. "GROWTH FACTOR SIGNALING" -> "Growth Factor Signaling", not "DNA" -> "Dna").
_SUBCATEGORY_ACRONYM_WHITELIST = {
    "dna", "rna", "hla", "ebv", "hpv", "hhv", "hhv8", "kshv", "hiv", "hlh",
    "mgus", "poems", "cll", "sll", "dlbcl", "gist", "ihc", "fish", "pcr",
    "alk", "egfr", "kras", "braf", "idh", "idh1", "idh2", "who", "abpath",
    "nos", "gu", "hn", "gyn", "gi", "bst", "hpv16", "hpv18",
}


def _smart_titlecase_subcategory(raw: str) -> str:
    """Title-case ABPath section headers the PDF rendered in ALL CAPS (e.g.
    Molecular pathway categories), while leaving normal mixed-case text and
    short acronym labels (GU, HN, GI, GYN) untouched."""
    text = (raw or "").strip()
    if not text:
        return text
    if len(text) <= 4 and text.isupper():
        return text
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio < 0.7:
        return text
    words = []
    for word in text.split(" "):
        stripped = word.strip("()/,&")
        if stripped.lower() in _SUBCATEGORY_ACRONYM_WHITELIST:
            words.append(word.upper())
        else:
            words.append(word[:1].upper() + word[1:].lower() if word else word)
    return " ".join(words)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _singularize_token(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith("ses"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


# Filler words dropped from the generic subcategory key so "The Thyroid" /
# "Thyroid" and "The Adrenal Glands" / "Adrenal" collapse together.
_SUBCATEGORY_STOPWORDS = {"the", "of", "gland"}


def _generic_subcategory_key(label: str) -> str:
    """Plural/word-order/filler-word-insensitive key so e.g. "Bone" /
    "Bones", "The Thyroid" / "Thyroid", "The Adrenal Glands" / "Adrenal"
    collapse into one Browse subcategory without hand-listing every organ
    system in SUBCATEGORY_ALIASES."""
    text = re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).strip()
    all_tokens = [_singularize_token(t) for t in text.split() if t]
    tokens = [t for t in all_tokens if t not in _SUBCATEGORY_STOPWORDS]
    return " ".join(sorted(tokens or all_tokens))


# Aggressive dedupe cache: first canonical (sub_id, label) seen per generic
# key wins for the lifetime of one builder run (module-level, reset per run).
_SUBCATEGORY_CANON_CACHE: dict[str, tuple[str, str]] = {}


def normalize_subcategory(sub_label: str) -> tuple[str, str]:
    """Return canonical (sub_id, sub_label) for Browse grouping."""
    raw = normalize_whitespace((sub_label or "").replace("_", " "))
    raw = re.sub(r"^[A-Za-z0-9]+\.\s+", "", raw).strip() or "General"
    # Repair glued WHO segments: Soft TissueAdipocytic → Soft Tissue
    raw = re.sub(r"(?i)\bSoft TissueAdipocytic\b", "Soft Tissue", raw)
    raw = re.sub(r"(?i)\bSoft_TissueAdipocytic\b", "Soft Tissue", raw)
    # Known WHO source-data typo (doubled leading letter): VVagina -> Vagina.
    # Fixed here (label-level) rather than only in repair_who_tag(tag=...) so
    # it self-heals even when a stale who_nav_leaves_snapshot_v0_1.json still
    # carries the old sub_label text.
    raw = re.sub(r"(?i)^V+(agina)$", r"V\1", raw)
    # Strip OCR/PDF placeholder glyphs rendered as trailing "XXX".
    raw = re.sub(r"(?i)\s+x{2,}\s*$", "", raw).strip() or raw
    # Cosmetic: "The Adrenal Glands" -> "Adrenal Glands" — the leading
    # article added nothing and only made near-duplicates read as different.
    raw = re.sub(r"(?i)^the\s+", "", raw).strip() or raw
    raw = _smart_titlecase_subcategory(raw)
    key = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    if key in SUBCATEGORY_ALIASES:
        canon = SUBCATEGORY_ALIASES[key]
        _SUBCATEGORY_CANON_CACHE.setdefault(_generic_subcategory_key(raw), canon)
        return canon
    generic = _generic_subcategory_key(raw)
    cached = _SUBCATEGORY_CANON_CACHE.get(generic)
    if cached:
        return cached
    canon = (slugify(raw) or "general", raw)
    _SUBCATEGORY_CANON_CACHE[generic] = canon
    return canon


def repair_who_tag(tag: str) -> str:
    """Fix known malformed WHO tag segments before nav ingest."""
    tag = tag.replace("BST::Soft_TissueAdipocytic::", "BST::Soft_Tissue::Adipocytic::")
    tag = tag.replace("GYN::VVagina::", "GYN::Vagina::")
    return tag


# Single generic words that never stand alone as a real diagnosis name (no
# WHO/ABPath entity is literally just "Carcinoma" or "Benign" — real entries
# always carry a specific qualifier). Used two ways: (1) reject a leaf whose
# every token is in this set, and (2) reject any leaf starting with "Other"
# — a residual catch-all bucket, not something a topic-page prebuild can be
# meaningfully written for.
_GENERIC_BARE_TOKENS = {
    "benign", "malignant", "premalignant", "borderline", "carcinoma",
    "sarcoma", "lymphoma", "leukemia", "adenoma", "tumor", "tumour",
    "tumors", "tumours", "neoplasm", "neoplasms", "lesion", "lesions",
    "disorder", "disorders", "disease", "diseases", "syndrome",
    "infection", "infections", "infectious", "inflammatory", "other",
    "others", "general", "normal", "miscellaneous", "cyst", "cysts",
    "polyp", "polyps", "hyperplasia", "metaplasia", "dysplasia", "atypia",
    "metastasis", "metastases", "condition", "conditions", "change",
    "changes", "process", "processes", "topic", "topics", "type", "types",
}
_OTHER_LEAF_RE = re.compile(r"(?i)^other\b")


def looks_like_diagnosis(item: str) -> bool:
    """True when item text is a specific, nameable diagnosis/disease entity
    that a topic-page prebuild could meaningfully be written for — not a
    residual "Other ..." catch-all, and not a bare generic word/phrase with
    no organ- or entity-specific qualifier."""
    text = normalize_whitespace(item or "")
    if not text or SKIP_ITEM_RE.match(text):
        return False
    if NON_DIAGNOSIS_ITEM_RE.match(text):
        return False
    if BUCKET_HEADER_ITEM_RE.match(text):
        return False
    if GENERIC_HEADER_ITEM_RE.match(text):
        return False
    if CELL_TYPE_ITEM_RE.match(text) and not DIAGNOSIS_HINT_RE.search(text):
        return False
    # Parenthetical prep notes / contaminant lists are not diagnoses.
    if text.startswith("(e.g.") or text.startswith("(eg.") or text.startswith("("):
        return False
    # "Other <anything>" is a residual catch-all bucket, never a specific
    # entity — e.g. "Other malignancies involving the thyroid".
    if _OTHER_LEAF_RE.match(text):
        return False
    # Bare generic phrase with zero organ/entity-specific words at all
    # (e.g. "Carcinoma", "Benign", "Infections", "Cysts").
    tokens = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    if tokens and all(t in _GENERIC_BARE_TOKENS for t in tokens):
        return False
    return True


def is_methodology_path(path: str) -> bool:
    return bool(NON_DIAGNOSIS_PATH_RE.search(path or ""))


# Reported (2026-08-02): 215 leaves (mostly Dermatopathology, e.g. "a)
# Seborrheic Keratosis", "b) Warty Dyskeratoma") kept a leading list-marker
# in their label. Root cause: the DOCX parser's letter/roman hierarchy
# regexes only recognize "a." / "iii." (period), not "a)" / "iii)"
# (parenthesis) — some ABPath sections use the parenthesis style, so those
# lines fell through as plain terminal item_text with the marker still
# attached, rather than being classified as a subsection/category prefix.
# Stripped here (label-level only — no change to row order or the abpath_
# spec_id sequence the CYTO_*/CARDIO_* range tables above are keyed on).
# Applied BEFORE the diagnosis filter below, not just at tag-construction
# time — otherwise a masked "f) Other Variants of X" (starts with "f)",
# not "other") slips past the bare "Other ..." catch-all rejection that
# looks_like_diagnosis is supposed to enforce.
_LEADING_LIST_MARKER_RE = re.compile(r"^(?:[a-zA-Z]|[ivxlcIVXLC]+|\d+)\)\s+")


def _strip_leading_list_marker(text: str) -> str:
    return _LEADING_LIST_MARKER_RE.sub("", text or "", count=1).strip() or text


def is_diagnosis_content_spec_row(row: dict[str, Any]) -> bool:
    """Keep only diagnosis-like ABPath content-spec terminals for Browse nav."""
    item = _strip_leading_list_marker((row.get("item_text") or "").strip())
    if not looks_like_diagnosis(item):
        return False
    path = " / ".join(
        [
            row.get("major_section") or "",
            row.get("organ_system") or "",
            row.get("subsection") or "",
            row.get("category") or "",
        ]
    )
    # Methodology / QA / anatomy sections: keep only clear named diagnoses
    # (parser sometimes nests real disease names under Techniques).
    if is_methodology_path(path) and not DIAGNOSIS_HINT_RE.search(item):
        return False
    # Bucket headers never belong in nav even under disease sections.
    if BUCKET_HEADER_ITEM_RE.match(item):
        return False
    return True


def clean_pdf_line(line: str) -> str:
    line = normalize_whitespace(line)
    if not line:
        return ""
    if line == "American Board of Pathology":
        return ""
    if re.fullmatch(r"\d{1,3}", line):
        return ""
    # TOC leaders / dotted fills
    if "...." in line or "…" in line:
        # Keep major TOC lines that still look like "16. Hematopathology ..."
        if not re.match(r"^\d{1,2}\.\s+\S", line):
            return ""
        line = re.split(r"\s+\.{2,}", line)[0].strip()
    # Strip trailing page numbers: "Fibroadenoma C 98" → "Fibroadenoma C"
    line = re.sub(r"\s+\d{1,4}$", "", line).strip()
    return line


def extract_paragraphs_from_pdf(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    raw_lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw in text.splitlines():
            line = clean_pdf_line(raw)
            if line:
                raw_lines.append(line)

    # Rejoin OCR/PDF wraps like "p" + ". Syringomatous adenoma AR"
    merged: list[str] = []
    i = 0
    while i < len(raw_lines):
        cur = raw_lines[i]
        if re.fullmatch(r"[a-z]", cur) and i + 1 < len(raw_lines) and raw_lines[i + 1].startswith("."):
            merged.append(normalize_whitespace(cur + raw_lines[i + 1]))
            i += 2
            continue
        merged.append(cur)
        i += 1
    return merged


def major_number(major_section: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2})\.", major_section or "")
    return int(m.group(1)) if m else None


def normalize_label_key(text: str) -> str:
    """Super-aggressive dedupe key: same diagnosis entity should collide
    regardless of source formatting (WHO underscores vs ABPath prose,
    "&" vs "and", "Not Otherwise Specified" vs "NOS", hyphenation, casing)."""
    text = (text or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\bnot otherwise specified\b", "nos", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _who_style_tag_token(text: str) -> str:
    """Title_Case_With_Underscores tag token, matching the real WHO/PathOut
    tag convention (e.g. "Cardiac myxoma" -> "Cardiac_Myxoma") — distinct
    from slugify() (all-lowercase). Used only when constructing a tag that
    must be indistinguishable in format from a genuine WHO-sourced one
    (Cyto_<System>::…, Thorax_Mediastinum::<Organ>::…), never for the
    generic "ABPathSpec::<root>::…" wrapper used everywhere else."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    words = []
    for w in cleaned.split("_"):
        if not w:
            continue
        words.append(w if (w.isupper() and len(w) <= 5) else w[:1].upper() + w[1:])
    return "_".join(words)[:160] or "Item"


def content_spec_to_leaf(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    item = _strip_leading_list_marker((row.get("item_text") or "").strip())
    if not item or SKIP_ITEM_RE.match(item):
        return None
    if not row.get("abpath_level"):
        return None
    if not is_diagnosis_content_spec_row(row):
        return None
    maj = major_number(row.get("major_section") or "")
    if maj not in MAJOR_TO_ROOT:
        return None
    root_id, _root_label = MAJOR_TO_ROOT[maj]
    organ = (row.get("organ_system") or "").strip()
    category = (row.get("category") or "").strip()
    subsection = (row.get("subsection") or "").strip()
    # PDF line-wrap artifacts sometimes leave a parenthetical continuation
    # fragment (e.g. "(e.g., sclerosing adenosis, tubular adenosis,") or a
    # bare page-number token in category/organ_system/subsection — never use
    # that as a subcategory.
    organ, category, subsection = (
        v if v and not v.startswith("(") and not v.isdigit() else ""
        for v in (organ, category, subsection)
    )
    path = " / ".join(
        [
            row.get("major_section") or "",
            organ,
            subsection,
            category,
        ]
    )
    # Prefer organ-system as Browse subcategory. If the only hierarchy is a
    # methodology/QA folder, re-home diagnosis leaves under General so they
    # do not create Ancillary/Techniques nav buckets.
    if organ:
        fine_label = organ
    elif is_methodology_path(path):
        fine_label = "General"
    else:
        fine_label = category or subsection or "General"
    fine_id, fine_label = normalize_subcategory(fine_label)
    label = item
    # Cytopathology (major 12) and Cardiovascular (major 4) get a NATIVE
    # WHO-style tag (Cyto_<System>::<Category>::<Leaf> /
    # Thorax_Mediastinum::<Organ>::<Category>::<Leaf>) instead of the
    # generic "ABPathSpec::<root>::…" wrapper every other major uses — see
    # CYTO_SYSTEM_TO_NATIVE_PREFIX / cardio_organ_for_spec_id. Both majors'
    # own content-spec headers name a histologic category ("SIL",
    # "Adenocarcinomas", "Vasculitis", …), not an organ (parser gap — see
    # CYTO_ABPATH_SPEC_RANGES/CARDIO_ABPATH_SPEC_RANGES), and both already
    # have real WHO-tagged leaves under this exact native prefix
    # (Cyto_Heme::…, Thorax_Mediastinum::Heart::…) that these should merge
    # alongside rather than sit next to as a separately-formatted synthetic
    # tag (2026-08-02 feedback: "get rid of the abpath part and use current
    # logic of things").
    if maj == 12:
        sub_label = cyto_abpath_system_for_spec_id(row.get("abpath_spec_id") or "") or CYTO_SYSTEM_GENERAL
        sub_id, sub_label = normalize_subcategory(sub_label)
        native_prefix = CYTO_SYSTEM_TO_NATIVE_PREFIX.get(sub_label, f"Cyto_{_who_style_tag_token(sub_label)}")
        category = cyto_bethesda_category(label)
        tag = "::".join([native_prefix, category, _who_style_tag_token(label)])
    elif maj == 4:
        organ = cardio_organ_for_spec_id(row.get("abpath_spec_id") or "")
        sub_id, sub_label = normalize_subcategory(organ)
        tag = "::".join(["Thorax_Mediastinum", organ, _who_style_tag_token(fine_label), _who_style_tag_token(label)])
    else:
        sub_id, sub_label = fine_id, fine_label
        tag = "::".join(["ABPathSpec", root_id, sub_id, slugify(label) or "item"])
    return {
        "tag": tag,
        "label": label,
        "query": label,
        "provenance": "abpath",
        "root_id": root_id,
        "sub_id": sub_id,
        "sub_label": sub_label,
        "abpath_level": row.get("abpath_level"),
        "abpath_spec_id": row.get("abpath_spec_id"),
        "raw_path": row.get("raw_path"),
    }


def _who_leaf_from_parts(
    *,
    tag: str,
    label: str,
    query: str,
    root_id: str,
    sub_id: str,
    sub_label: str,
) -> Optional[dict[str, Any]]:
    # WHO also carries residual "Other ..." catch-alls and bare generic
    # entries; apply the same diagnosis-specificity filter as ABPath/PathOut
    # so nothing lands in nav that a prebuild couldn't be usefully written for.
    if not looks_like_diagnosis(label.replace("_", " ")):
        return None
    tag = repair_who_tag(tag)
    # Cyto_<Suffix> tags (any caller — fresh who_processed/, WHO snapshot, or
    # harvested from a prior index whose own sub_label may already be a
    # stale/ungrouped "Cyto Heme"-style label) always re-derive the Browse
    # subcategory from the tag's own root segment, never from the caller's
    # sub_label, so every provenance path lands in the same organ-system
    # bucket (see `cyto_who_system_label`).
    if tag.startswith("Cyto_"):
        sub_label = cyto_who_system_label(tag.split("::", 1)[0][len("Cyto_") :])
    sub_id, sub_label = normalize_subcategory(sub_label)
    # If tag path implies Soft_Tissue after repair, keep subcategory Soft Tissue.
    if tag.startswith("BST::Soft_Tissue::"):
        sub_id, sub_label = "soft_tissue", "Soft Tissue"
    elif tag.startswith("BST::Bone::"):
        sub_id, sub_label = "bone", "Bone"
    return {
        "tag": tag,
        "label": label,
        "query": query,
        "provenance": "who",
        "root_id": root_id,
        "sub_id": sub_id,
        "sub_label": sub_label,
    }


def harvest_who_from_browse_index(index: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep WHO entity tags only — never ABPathSpec or bloated ontology abpath-only."""
    leaves: list[dict[str, Any]] = []
    for root in index.get("roots") or []:
        for sub in root.get("subcategories") or []:
            for leaf in sub.get("leaves") or []:
                tag = leaf.get("tag") or ""
                if not isinstance(tag, str) or "::" not in tag:
                    continue
                if tag.startswith("ABPathSpec::"):
                    continue
                prov = str(leaf.get("provenance") or "").lower()
                if prov in {"abpath", "pathout"}:
                    continue
                if prov not in {"who", "both", ""}:
                    continue
                who_leaf = _who_leaf_from_parts(
                    tag=tag,
                    label=leaf.get("label") or tag.split("::")[-1],
                    query=leaf.get("query") or str(leaf.get("label") or "").replace("_", " "),
                    root_id=root["id"],
                    sub_id=sub["id"],
                    sub_label=sub["label"],
                )
                if who_leaf is not None:
                    leaves.append(who_leaf)
    return leaves


def load_who_leaves() -> tuple[list[dict[str, Any]], str]:
    """Prefer who_processed; else WHO snapshot; else WHO leaves from prior browse index."""
    leaves: list[dict[str, Any]] = []
    if WHO_DIR.is_dir() and any(WHO_DIR.glob("*.json")):
        for who_path in sorted(WHO_DIR.glob("*.json")):
            entities = json.loads(who_path.read_text(encoding="utf-8"))
            if not isinstance(entities, list):
                continue
            for entity in entities:
                for raw_tag in entity.get("tags") or []:
                    if not isinstance(raw_tag, str) or "::" not in raw_tag:
                        continue
                    raw_tag = repair_who_tag(raw_tag)
                    segments = raw_tag.split("::")
                    root_seg = segments[0]
                    if root_seg.startswith("Cyto_"):
                        root_id = "cyto"
                        sub_label = cyto_who_system_label(root_seg[len("Cyto_") :])
                    else:
                        root_id = re.sub(r"[^a-z0-9]+", "", root_seg.lower()) or slugify(root_seg)
                        sub_label = segments[1] if len(segments) > 2 else "General"
                    label = segments[-1]
                    sub_id, sub_label = normalize_subcategory(sub_label)
                    who_leaf = _who_leaf_from_parts(
                        tag=raw_tag,
                        label=label,
                        query=label.replace("_", " "),
                        root_id=root_id,
                        sub_id=sub_id,
                        sub_label=sub_label,
                    )
                    if who_leaf is not None:
                        leaves.append(who_leaf)
        return leaves, str(WHO_DIR.relative_to(REPO_ROOT))

    if WHO_SNAPSHOT.exists():
        payload = json.loads(WHO_SNAPSHOT.read_text(encoding="utf-8"))
        raw_leaves = payload.get("leaves") if isinstance(payload, dict) else payload
        if isinstance(raw_leaves, list) and raw_leaves:
            for leaf in raw_leaves:
                if not isinstance(leaf, dict) or not leaf.get("tag"):
                    continue
                who_leaf = _who_leaf_from_parts(
                    tag=leaf["tag"],
                    label=leaf.get("label") or leaf["tag"].split("::")[-1],
                    query=leaf.get("query") or str(leaf.get("label") or "").replace("_", " "),
                    root_id=leaf["root_id"],
                    sub_id=leaf.get("sub_id") or "general",
                    sub_label=leaf.get("sub_label") or "General",
                )
                if who_leaf is not None:
                    leaves.append(who_leaf)
            return leaves, str(WHO_SNAPSHOT.relative_to(REPO_ROOT))

    if not PRIOR_INDEX.exists():
        raise SystemExit(
            "No who_processed/, who_nav_leaves_snapshot_v0_1.json, or prior browse index"
        )
    prior = json.loads(PRIOR_INDEX.read_text(encoding="utf-8"))
    leaves = harvest_who_from_browse_index(prior)
    return leaves, f"{PRIOR_INDEX.relative_to(REPO_ROOT)}#who_harvest"


PATHOUT_ROOT_MAP = {
    "breast": "breast",
    "gi": "gi",
    "gu": "gu",
    "gyn": "gyn",
    "hn": "hn",
    "skin": "skin",
    "bst": "bst",
    "endo": "endo",
    "neuro": "neuro",
    "molecular": "molecular",
    "thorax_mediastinum": "thorax_mediastinum",
    "eye_orbit": "eye_orbit",
    "eye": "eye_orbit",
    "heme": "heme",
    "cyto": "cyto",
    "peds": "peds",
}

PATHOUT_DROP_TAG_RE = re.compile(
    r"(?i)(::Concept::|::Procedure_Specimen::|::Staging::|::Classification::|"
    r"UNRESOLVED_ROOT|_UNMAPPED_|PathOut_Residual|::Technique::|::Normal::)",
)

PROVENANCE_RANK = {"abpath": 0, "both": 1, "who": 2, "pathout": 3}


def pathout_root_and_sub(tag: str) -> tuple[Optional[str], str, str]:
    parts = [p for p in tag.split("::") if p]
    if len(parts) < 2:
        return None, "", ""
    head = parts[0]
    if head.startswith("Cyto_"):
        sub_id, sub_label = normalize_subcategory(cyto_who_system_label(head[len("Cyto_") :]))
        return "cyto", sub_id, sub_label
    if head.lower() == "soft_tissue":
        return "bst", "soft_tissue", "Soft Tissue"
    if head.upper() == "HEME":
        root_id = "heme"
    else:
        root_id = PATHOUT_ROOT_MAP.get(re.sub(r"[^a-z0-9]+", "_", head.lower()).strip("_"))
    if not root_id:
        return None, "", ""
    sub_id, sub_label = normalize_subcategory(parts[1].replace("_", " "))
    return root_id, sub_id, sub_label


def is_diagnosis_pathout_tag(tag: str) -> bool:
    if not tag or "::" not in tag:
        return False
    if PATHOUT_DROP_TAG_RE.search(tag):
        return False
    label = tag.split("::")[-1].replace("_", " ")
    return looks_like_diagnosis(label)


def load_pathout_leaves() -> tuple[list[dict[str, Any]], str, dict[str, int]]:
    """Load diagnosis-like PathOut tags from the local curriculum review CSV."""
    import csv

    stats = {
        "rows_read": 0,
        "dropped_unresolved_or_concept": 0,
        "dropped_non_diagnosis": 0,
        "kept": 0,
    }
    if not PATHOUT_TAG_CSV.exists():
        return [], "(missing pathout tag csv)", stats

    leaves: list[dict[str, Any]] = []
    seen: set[str] = set()
    with PATHOUT_TAG_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            stats["rows_read"] += 1
            tag = (row.get("tag") or "").strip()
            if not tag or tag in seen:
                continue
            if PATHOUT_DROP_TAG_RE.search(tag):
                stats["dropped_unresolved_or_concept"] += 1
                continue
            if not is_diagnosis_pathout_tag(tag):
                stats["dropped_non_diagnosis"] += 1
                continue
            root_id, sub_id, sub_label = pathout_root_and_sub(tag)
            if not root_id:
                stats["dropped_unresolved_or_concept"] += 1
                continue
            label = tag.split("::")[-1]
            seen.add(tag)
            leaves.append(
                {
                    "tag": tag,
                    "label": label,
                    "query": label.replace("_", " "),
                    "provenance": "pathout",
                    "root_id": root_id,
                    "sub_id": sub_id,
                    "sub_label": sub_label,
                }
            )
            stats["kept"] += 1
    return leaves, str(PATHOUT_TAG_CSV.relative_to(REPO_ROOT)), stats


def merge_who_pathout_leaves(
    who_leaves: list[dict[str, Any]],
    pathout_leaves: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union WHO + PathOut; on overlap keep WHO tag and mark provenance both."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for leaf in who_leaves:
        key = (leaf["root_id"], normalize_label_key(leaf["label"]))
        by_key[key] = dict(leaf)
        by_key[key]["provenance"] = "who"
    for leaf in pathout_leaves:
        key = (leaf["root_id"], normalize_label_key(leaf["label"]))
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dict(leaf)
            continue
        existing["provenance"] = "both"
    return list(by_key.values())


def build_roots(leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots: dict[str, dict] = {}
    root_labels = {rid: label for rid, label in MAJOR_TO_ROOT.values()}
    root_labels.update(
        {
            "cyto": "Cytopathology",
            "eye_orbit": "Eye / Orbit",
            "molecular": "Molecular",
            "peds": "Pediatric Pathology",
        }
    )

    for leaf in leaves:
        root_id = leaf["root_id"]
        root = roots.setdefault(
            root_id,
            {
                "id": root_id,
                "label": root_labels.get(root_id, root_id.replace("_", " ").title()),
                "kind": "cyto_aggregate" if root_id == "cyto" else "root",
                "leaf_count": 0,
                "subcategories": {},
            },
        )
        sub_id = leaf["sub_id"]
        sub = root["subcategories"].setdefault(
            sub_id,
            {"id": sub_id, "label": leaf["sub_label"], "leaf_count": 0, "leaves": []},
        )
        # Dedupe within subcategory by normalized label; prefer abpath > both > who > pathout
        rank = PROVENANCE_RANK.get(leaf["provenance"], 9)
        label_key = normalize_label_key(leaf["label"])
        existing_i = next(
            (i for i, e in enumerate(sub["leaves"]) if normalize_label_key(e["label"]) == label_key),
            None,
        )
        entry = {
            "tag": leaf["tag"],
            "label": leaf["label"],
            "provenance": leaf["provenance"],
            "query": leaf["query"],
        }
        if leaf.get("abpath_level"):
            entry["abpath_level"] = leaf["abpath_level"]
        if existing_i is None:
            sub["leaves"].append(entry)
        else:
            prev = sub["leaves"][existing_i]
            prev_rank = PROVENANCE_RANK.get(prev.get("provenance"), 9)
            if rank < prev_rank:
                if prev.get("provenance") in {"who", "pathout"} and leaf["provenance"] == "abpath":
                    entry["provenance"] = "both"
                elif prev.get("provenance") == "pathout" and leaf["provenance"] == "who":
                    entry["provenance"] = "both"
                sub["leaves"][existing_i] = entry
            elif prev.get("provenance") == "abpath" and leaf["provenance"] in {"who", "pathout"}:
                prev["provenance"] = "both"
            elif prev.get("provenance") == "who" and leaf["provenance"] == "pathout":
                prev["provenance"] = "both"
            elif prev.get("provenance") == "pathout" and leaf["provenance"] == "who":
                # Prefer WHO tag identity on overlap.
                entry["provenance"] = "both"
                sub["leaves"][existing_i] = entry

    final = []
    for root in sorted(roots.values(), key=lambda r: r["label"]):
        subs = []
        for sub in sorted(root["subcategories"].values(), key=lambda s: s["label"]):
            sub["leaves"] = sorted(sub["leaves"], key=lambda leaf: leaf["label"].casefold())
            sub["leaf_count"] = len(sub["leaves"])
            if sub["leaf_count"]:
                subs.append(sub)
        root["subcategories"] = subs
        root["leaf_count"] = sum(s["leaf_count"] for s in subs)
        if root["leaf_count"]:
            final.append(root)
    return final


def variant_payload(name: str, label: str, roots: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    prov = Counter(
        leaf.get("provenance")
        for root in roots
        for sub in root.get("subcategories") or []
        for leaf in sub.get("leaves") or []
    )
    return {
        "id": name,
        "label": label,
        "counts": {
            "leaves_total": sum(r["leaf_count"] for r in roots),
            "roots_total": len(roots),
            "leaves_who_only": prov.get("who", 0),
            "leaves_pathout_only": prov.get("pathout", 0),
            "leaves_both": prov.get("both", 0),
            "per_root_leaf_counts": {r["id"]: r["leaf_count"] for r in roots},
        },
        "roots": roots,
        **extra,
    }


def main() -> int:
    if PDF_PATH.exists():
        paragraphs = extract_paragraphs_from_pdf(PDF_PATH)
        source_doc = str(PDF_PATH.relative_to(REPO_ROOT))
    elif DOCX_PATH.exists():
        from parse_abpath_ap_content_specs_v0_1 import extract_paragraphs

        paragraphs = extract_paragraphs(DOCX_PATH)
        source_doc = str(DOCX_PATH.relative_to(REPO_ROOT))
    else:
        raise SystemExit(f"Missing content-spec PDF/DOCX under data/source_specs/")

    rows, warnings = parse_rows(paragraphs)
    validate_rows(rows)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(AUDIT_DIR / "abpath_ap_content_specs_v0_1.jsonl", rows)
    write_csv(AUDIT_DIR / "abpath_ap_content_specs_v0_1.csv", rows, ROW_FIELDS)
    write_csv(
        AUDIT_DIR / "abpath_ap_content_specs_v0_1_parse_warnings.csv",
        warnings,
        ["line_index", "raw_text", "warning_type", "detail"],
    )

    abpath_leaves: list[dict[str, Any]] = []
    skipped = 0
    skipped_non_diagnosis = 0
    dropped_non_diagnosis_samples: list[str] = []
    for row in rows:
        item = (row.get("item_text") or "").strip()
        if item and row.get("abpath_level") and major_number(row.get("major_section") or "") in MAJOR_TO_ROOT:
            if not is_diagnosis_content_spec_row(row):
                skipped_non_diagnosis += 1
                if len(dropped_non_diagnosis_samples) < 40:
                    dropped_non_diagnosis_samples.append(
                        f"{row.get('major_section')}|{item}"
                    )
        leaf = content_spec_to_leaf(row)
        if leaf is None:
            skipped += 1
            continue
        abpath_leaves.append(leaf)

    # One lightweight "Category" definition leaf per Bethesda-style
    # reporting tier per cyto system (2026-08-02 feedback's
    # Cyto_Adrenal::Category::Nondiagnostic/.../Malignant example) — a
    # navigational/structural aid mirroring the tier-definition leaves WHO's
    # own data already carries for a few systems (e.g.
    # Cyto_Heme::Malignant::Malignant_Category_Definition_And_Criteria).
    # Standardized reporting-scheme labels, not sourced diagnosis content —
    # disclosed in known_limitations, never counted as a WHO/ABPath entity.
    cyto_systems_present = {leaf["sub_label"] for leaf in abpath_leaves if leaf["root_id"] == "cyto"}
    for system_label in sorted(cyto_systems_present):
        native_prefix = CYTO_SYSTEM_TO_NATIVE_PREFIX.get(system_label, f"Cyto_{_who_style_tag_token(system_label)}")
        sub_id, sub_label = normalize_subcategory(system_label)
        for tier in CYTO_BETHESDA_TIERS:
            tier_readable = tier.replace("_", " ")
            label = f"{system_label} Reporting Category: {tier_readable}"
            abpath_leaves.append(
                {
                    "tag": "::".join([native_prefix, "Category", tier]),
                    "label": label,
                    "query": label,
                    "provenance": "abpath",
                    "root_id": "cyto",
                    "sub_id": sub_id,
                    "sub_label": sub_label,
                    "abpath_level": None,
                    "abpath_spec_id": None,
                    "raw_path": None,
                }
            )

    who_leaves, who_source = load_who_leaves()

    # Persist WHO snapshot so rebuilds do not depend on a bloated prior index.
    WHO_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    WHO_SNAPSHOT.write_text(
        json.dumps(
            {
                "schema_version": "who_nav_leaves_snapshot_v0_1",
                "generated_at": utc_now(),
                "source": who_source,
                "leaf_count": len(who_leaves),
                "leaves": who_leaves,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # Merge: index by root+label for both-marking.
    # Only mark both when the existing leaf is an ABPath content-spec entity.
    # Duplicate WHO labels must NOT become provenance=both.
    by_root_label: dict[tuple[str, str], dict] = {}
    for leaf in abpath_leaves:
        key = (leaf["root_id"], normalize_label_key(leaf["label"]))
        by_root_label[key] = leaf
    for leaf in who_leaves:
        key = (leaf["root_id"], normalize_label_key(leaf["label"]))
        existing = by_root_label.get(key)
        if existing is None:
            by_root_label[key] = leaf
            continue
        existing_tag = str(existing.get("tag") or "")
        if existing_tag.startswith("ABPathSpec::") or existing.get("provenance") == "abpath":
            existing["provenance"] = "both"

    merged = list(by_root_label.values())
    # Sanitize: abpath/both provenance is reserved for content-spec tags —
    # either the generic "ABPathSpec::<root>::…" wrapper, or one of the two
    # majors (Cytopathology, Cardiovascular) that deliberately use a native
    # WHO-style tag instead (2026-08-02: "get rid of the abpath part and use
    # current logic of things" — see CYTO_SYSTEM_TO_NATIVE_PREFIX /
    # cardio_organ_for_spec_id). Provenance itself is still set correctly by
    # source-list membership above; this only guards against a leaf whose
    # tag looks like neither pattern falsely claiming abpath/both.
    def _is_recognized_abpath_tag(tag: str) -> bool:
        if tag.startswith("ABPathSpec::"):
            return True
        if tag.startswith("Thorax_Mediastinum::") and (
            tag.startswith(f"Thorax_Mediastinum::{CARDIO_ORGAN_HEART}::")
            or tag.startswith(f"Thorax_Mediastinum::{CARDIO_ORGAN_VESSELS}::")
        ):
            return True
        return any(tag.startswith(f"{prefix}::") for prefix in CYTO_SYSTEM_TO_NATIVE_PREFIX.values())

    for leaf in merged:
        tag = str(leaf.get("tag") or "")
        if leaf.get("provenance") in {"abpath", "both"} and not _is_recognized_abpath_tag(tag):
            leaf["provenance"] = "who"
    roots = build_roots(merged)

    pathout_leaves, pathout_source, pathout_stats = load_pathout_leaves()
    who_only_roots = build_roots(who_leaves)
    who_pathout_merged = merge_who_pathout_leaves(who_leaves, pathout_leaves)
    who_pathout_roots = build_roots(who_pathout_merged)
    nav_variants = {
        "who": variant_payload(
            "who",
            "WHO only",
            who_only_roots,
            nav_sources=["who"],
            pathout_nav=False,
        ),
        "who_pathout": variant_payload(
            "who_pathout",
            "WHO + PathOutlines",
            who_pathout_roots,
            nav_sources=["who", "pathout"],
            pathout_nav=True,
            pathout_filter="diagnosis_entities_only",
            pathout_stats=pathout_stats,
        ),
    }

    prov = Counter(leaf["provenance"] for leaf in merged)
    per_root = {r["id"]: r["leaf_count"] for r in roots}
    generated_at = utc_now()

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "abpath_content_spec": source_doc,
            "abpath_content_spec_rows": len(rows),
            "who_source": who_source,
            "pathout_tag_csv": pathout_source,
            "prior_bloated_abpath_ontology": "excluded (abpath_source_tags.jsonl not used)",
        },
        "counts": {
            "abpath_content_spec_terminal_rows": len(rows),
            "abpath_nav_leaves": prov.get("abpath", 0) + prov.get("both", 0),
            "who_nav_leaves_input": len(who_leaves),
            "pathout_nav_leaves_input": len(pathout_leaves),
            "leaves_total": sum(r["leaf_count"] for r in roots),
            "leaves_abpath_only": prov.get("abpath", 0),
            "leaves_who_only": prov.get("who", 0),
            "leaves_both": prov.get("both", 0),
            "roots_total": len(roots),
            "content_spec_rows_skipped": skipped,
            "content_spec_rows_dropped_non_diagnosis": skipped_non_diagnosis,
            "parser_warnings": len(warnings),
            "per_root_leaf_counts": per_root,
            "variant_who_leaves_total": nav_variants["who"]["counts"]["leaves_total"],
            "variant_who_pathout_leaves_total": nav_variants["who_pathout"]["counts"]["leaves_total"],
        },
        "dedupe_rules": {
            "key": "root_id + normalize(label)",
            "canonical_preference": "abpath_content_spec_over_who",
            "nav_sources": ["abpath_content_spec", "who"],
            "provenance_values": ["abpath", "who", "both", "pathout"],
            "pathout_nav": False,
            "bloated_abpath_ontology_excluded": True,
            "default_nav_mode": "full",
            "abpath_means": "official_AP_content_specifications_diagnosis_entities_only",
            "abpath_topic_filter": "diagnosis_entities_only",
            "nav_variants": ["who", "who_pathout"],
            "nav_variant_notes": {
                "full": "default — WHO + ABPath content-spec diagnoses; PathOut citation-only",
                "who": "WHO classification entities only",
                "who_pathout": "WHO + diagnosis-filtered PathOutlines tags (optional explore mode)",
            },
        },
        "roots": roots,
        "nav_variants": nav_variants,
        "known_limitations": [
            "Default Browse nav = diagnosis-like ABPath AP Content Specifications + WHO.",
            "Optional nav_variants.who and nav_variants.who_pathout are explore modes only.",
            "PathOut is citation-only in the default full mode (pathout_nav=false).",
            "Cell types, normal anatomy/histology/cytology, lab methods, QA/billing, and generic headers are excluded from ABPath nav.",
            "PathOut variant also drops Concept/Staging/Procedure and non-diagnosis-like tags.",
            "The expanded abpath_source_tags.jsonl curriculum ontology is intentionally excluded.",
            "Content-spec tags use ABPathSpec::<root>::… identity — retrieval still uses the query/label text.",
            "Index is a local snapshot; not proof of API/vector coverage.",
            "Cytopathology (cyto root) subcategories are organ system first (e.g. 'Hematolymphoid Cytopathology'), not the raw ABPath content-spec header — see CYTO_SYSTEM_* constants and CYTO_ABPATH_SPEC_RANGES.",
            "ABPath major-section-12 organ-system boundaries were hand-reconstructed from the ordered row dump (the DOCX/PDF parser only recovers ~11% of section 12's own organ headers) and keyed on abpath_spec_id sequence ranges; re-verify ranges if the source PDF/DOCX content changes.",
            "A handful of ABPath cytopathology rows (e.g. anogenital squamous lesions) were merged into the closest matching organ system by clinical judgment, not an explicit ABPath organ label.",
            "ABPath-derived cyto leaves carry a native 'Cyto_<System>::<Category>::<Leaf>' tag (matching the real WHO/PathOut Cyto_<Suffix> convention) instead of the generic ABPathSpec:: wrapper; <Category> is a heuristic Bethesda-tier classification (cyto_bethesda_category) off the leaf's own label, not a WHO-authoritative call — expect some borderline entities (e.g. pheochromocytoma) to sit in an arguable tier.",
            "Each cyto system also carries 5 synthetic 'Cyto_<System>::Category::<Tier>' leaves (Nondiagnostic/Benign/Atypical/Suspicious_For_Malignancy/Malignant) — standardized reporting-scheme labels for navigation, not sourced diagnosis content; never counted toward WHO/ABPath entity totals.",
            "Cardiovascular (ABPath major 4) has no standalone Browse root — its content is folded into Thorax_Mediastinum::Heart / Thorax_Mediastinum::Blood_Vessels (WHO's own Thoracic Tumours volume classifies heart tumors there; real WHO Thorax_Mediastinum::Heart::… tags already existed in this index). Heart vs Blood_Vessels boundaries were hand-reconstructed from the ordered row dump (CARDIO_ABPATH_SPEC_RANGES), same caveat as the cyto ranges above.",
        ],
    }

    audit = {
        "schema_version": "browse_tag_index_who_abpath_spec_audit_v0_1",
        "generated_at": generated_at,
        "input_paths": [source_doc, who_source, pathout_source],
        "output_paths": [
            str(INDEX_PATH.relative_to(REPO_ROOT)),
            str(STATIC_COPY.relative_to(REPO_ROOT)),
            str(AUDIT_PATH.relative_to(REPO_ROOT)),
        ],
        "counts": index["counts"],
        "pathout_stats": pathout_stats,
        "nav_variant_counts": {
            "who": nav_variants["who"]["counts"],
            "who_pathout": nav_variants["who_pathout"]["counts"],
        },
        "dropped_non_diagnosis_samples": dropped_non_diagnosis_samples,
        "known_limitations": index["known_limitations"],
    }

    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    STATIC_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INDEX_PATH, STATIC_COPY)
    (AUDIT_DIR / "browse_rebuild_audit_v0_1.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(json.dumps(index["counts"], indent=2))
    print(
        json.dumps(
            {
                "variant_who": nav_variants["who"]["counts"],
                "variant_who_pathout": nav_variants["who_pathout"]["counts"],
                "pathout_stats": pathout_stats,
            },
            indent=2,
        )
    )
    print(f"Wrote {STATIC_COPY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
