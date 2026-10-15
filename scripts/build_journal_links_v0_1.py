"""Build the public journal-article links for the Teaching topics map.

Input: the archived journal article browser list (titles, journals, DOIs and publisher URLs
from the retired AJSP / Modern Pathology / Virchows Archiv corpus; see
docs/JOURNALS_RETIRED_ARCHIVE.md). No article text is used and no API is called.

Output: frontend/pathology_hub_map_hub_v0_1/content/data/journal_links_v0_1.json mapping each
public topic (WHO / Pathology Outlines leaf, keyed by its leaf path) to articles whose title
contains the topic name as a phrase. Each article carries title, journal, year, and one link
(DOI, publisher URL, or a PubMed title search when neither was recorded).
"""
from __future__ import annotations

import csv
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / (
    "project_sources/updates/20260704/pathology_hub_handoff_local_codex_20260704_v3/"
    "evidence/journal_v4_4_audits/journal_article_browser_v4_articles.csv"
)
MAP = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/unified_content_map_v0_1.json"
OUT = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/journal_links_v0_1.json"
MAX_PER_TOPIC = 25
MIN_PHRASE = 7
GENERIC = {
    "other", "general", "overview", "normal", "benign", "malignant", "cyst", "cysts", "tumor",
    "tumors", "tumour", "tumours", "carcinoma", "lymphoma", "adenoma", "infection", "infections",
    "inflammation", "trauma", "miscellaneous", "mixed", "nos", "unclassified", "sarcoma", "melanoma",
}
GENERIC_PHRASES = {
    "squamous cell carcinoma", "adenocarcinoma in situ", "basal cell carcinoma", "small cell carcinoma",
    "large cell carcinoma", "neuroendocrine tumor", "neuroendocrine carcinoma", "germ cell tumor",
    "germ cell tumors", "carcinoma in situ", "malignant melanoma", "metastatic carcinoma",
    "undifferentiated carcinoma", "clear cell carcinoma", "mucinous carcinoma", "papillary carcinoma",
    "spindle cell", "round cell", "granular cell tumor", "giant cell tumor", "solitary fibrous tumor",
    "normal anatomy", "normal histology", "anatomy and histology",
}
# A generic phrase (single word, or one of GENERIC_PHRASES) only counts when the title also names the
# organ system of the topic's root, so "Adenocarcinoma" under GI::Colon matches colon papers only.
ROOT_KEYWORDS = {
    "Breast": ["breast", "mammary"],
    "BST": ["bone", "soft tissue", "sarcoma", "osseous", "skeletal", "cartilag"],
    "Cytopathology": ["cytolog", "cytopatholog", "fine needle", "aspirat", "smear", "pap test", "effusion", "fluid"],
    "Endo": ["thyroid", "parathyroid", "adrenal", "pituitary", "neuroendocrine", "endocrine", "pancrea"],
    "Eye_Orbit": ["ocular", "orbit", "conjunctiv", "eyelid", "lacrimal", "uvea", "retin", "cornea", " eye "],
    "GI": ["gastr", "esophag", "colon", "colorectal", "rectal", "anal ", "intestin", "appendi", "stomach", "duoden", "bowel", "biliary", "bile duct", "gallbladder", "liver", "hepat", "pancrea"],
    "GU": ["kidney", "renal", "bladder", "urothel", "prostat", "testi", "penile", "penis", "urinary", "urethr", "adrenal"],
    "GYN": ["cervi", "uterine", "uterus", "endometri", "ovar", "vulva", "vagina", "fallopian", "gestational", "placenta", "gynecolog"],
    "Heme": ["lymphoma", "leukemia", "myelo", "lymphoid", "hematolog", "bone marrow", "plasma cell", "histiocyt", "hodgkin"],
    "HN": ["head and neck", "oral", "salivary", "laryn", "pharyn", "sinonasal", "nasal", "thyroid", "jaw", "odontogenic", "tongue", "tonsil", " ear "],
    "Molecular": ["molecular", "mutation", "gene", "genomic", "sequencing", "fusion"],
    "Neuro": ["brain", "glioma", "glial", "central nervous", " cns ", "meningioma", "neuro", "spinal", "pituitary", "nerve"],
    "Peds": ["pediatric", "children", "childhood", "infant", "neonatal"],
    "Skin": ["skin", "cutaneous", "dermat", "melanocyt", "epiderm"],
    "Thorax_Mediastinum": ["lung", "pulmonary", "pleura", "mediastin", "thymic", "thymus", "heart", "cardiac", "thoracic"],
}
SUBSCRIPTION_JOURNALS = {
    "The American Journal of Surgical Pathology",
    "Virchows Archiv",
    "Modern Pathology",
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("_", " "))).strip()


def leaf_phrases(leaf: dict) -> set[str]:
    phrases = {norm(leaf.get("label") or "")}
    for src in (leaf.get("who"), leaf.get("pathout")):
        if src:
            phrases.add(norm(src.get("query") or src.get("label") or ""))
    return {p for p in phrases if len(p) >= MIN_PHRASE and p not in GENERIC}


def article_link(row: dict) -> tuple[str, str]:
    doi = (row.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}", "doi"
    url = (row.get("url") or "").strip()
    if url.startswith("http"):
        return url, "publisher"
    term = urllib.parse.quote(row["title"].strip())
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={term}", "pubmed_search"


def main() -> None:
    with ARTICLES.open(encoding="utf-8", errors="replace") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("title") or "").strip()]
    articles = []
    for r in rows:
        link, kind = article_link(r)
        year = (r.get("published") or "")[:4]
        articles.append({
            "t": r["title"].strip(),
            "j": r["journal"].strip(),
            "y": year if year.isdigit() else "",
            "u": link,
            "k": kind,
            "s": r["journal"].strip() in SUBSCRIPTION_JOURNALS,
            "_n": " " + norm(r["title"]) + " ",
        })

    data = json.loads(MAP.read_text(encoding="utf-8"))
    leaves: list[dict] = []

    def walk(node: dict, root_id: str) -> None:
        if node.get("kind") == "leaf" and (node.get("who") or node.get("pathout")):
            node["_root"] = root_id
            leaves.append(node)
        for child in node.get("children") or []:
            walk(child, root_id)

    for root in data["roots"]:
        walk(root, root["id"])

    topics: dict[str, list[dict]] = {}
    links = 0
    used = set()
    for leaf in leaves:
        phrases = leaf_phrases(leaf)
        if not phrases:
            continue
        specific = {p for p in phrases if len(p.split()) >= 2 and p not in GENERIC_PHRASES}
        generic = phrases - specific
        # Context: the organ segment of the path when it is one (GI::Colon -> "colon"), otherwise the
        # root's keywords. Generic phrases never match outside that context.
        context = list(ROOT_KEYWORDS.get(leaf["_root"], []))
        segments = (leaf.get("path") or "").split("::")
        if len(segments) > 2:
            organ = norm(segments[1])
            if len(organ) >= 4 and organ not in GENERIC and organ not in {"other", "general", "genetics", "heme", "neoplastic", "benign", "malignant", "carcinoma", "infectious", "inflammatory", "concept", "syndromes", "metastasis", "metastases"}:
                context = [organ[:-1] if organ.endswith("s") else organ]
        found = [
            a for a in articles
            if any(f" {p} " in a["_n"] for p in specific)
            or (generic and any(f" {p} " in a["_n"] for p in generic) and any(k in a["_n"] for k in context))
        ]
        if not found:
            continue
        found.sort(key=lambda a: (a["y"] or "0000", a["t"]), reverse=True)
        kept = [{k: v for k, v in a.items() if k != "_n"} for a in found[:MAX_PER_TOPIC]]
        topics[leaf["path"]] = {"n": len(found), "articles": kept}
        links += len(kept)
        used.update(a["t"] for a in found)

    out = {
        "schema_version": "journal_links.v0_1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Archived journal article browser list (AJSP, Modern Pathology, Virchows Archiv); titles, DOIs and publisher URLs only.",
        "method": f"Topic name or WHO/Pathology Outlines query appears as a phrase in the article title; phrases shorter than {MIN_PHRASE} characters and generic words skipped; up to {MAX_PER_TOPIC} newest shown per topic.",
        "counts": {
            "articles_in_list": len(articles),
            "topics_with_articles": len(topics),
            "articles_matched": len(used),
            "links_shown": links,
        },
        "topics": topics,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(out["counts"]), OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
