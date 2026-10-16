"""Per-topic journal article links for the public Teaching topics map, from PubMed.

Runs locally against the free NCBI E-utilities (no key, no Google, no Cloud Run), at most
three requests per second. For every public topic (a WHO / Pathology Outlines leaf of the
unified content map) it searches PubMed for articles whose TITLE contains the topic name,
limited to pathology journals, then keeps only articles that pass the match rule below.
Titles and links only; no abstracts are stored.

Match rule (checked locally on the returned titles, not trusted from the search):
  * the topic name, or its WHO / Pathology Outlines query, appears as a whole phrase in the
    article title (case-insensitive, punctuation ignored); and
  * the topic's organ (from its path or root) is named in the article title or abstract
    (asked of PubMed in the query); for generic names (one word, or a generic histology
    phrase such as "squamous cell carcinoma") the organ must be in the title itself; and
  * corrections, errata, comments and letters are dropped.
Reviews are listed first, then newest first; at most MAX_PER_TOPIC per topic. Open access is
flagged when PubMed Central holds the article; everything else is marked subscription.

Output: frontend/pathology_hub_map_hub_v0_1/content/data/journal_links_v0_1.json
Cache:  frontend/pathology_hub_map_hub_v0_1/content/data/pubmed_topic_cache_v0_1.json (resumable)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/unified_content_map_v0_1.json"
OUT = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/journal_links_v0_1.json"
CACHE = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/pubmed_topic_cache_v0_1.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL = {"tool": "PathologyKnowledgeHub", "email": "herndon.charlie@gmail.com"}
UA = {"User-Agent": "PathologyKnowledgeHub/0.1 (mailto:herndon.charlie@gmail.com)"}
DELAY = 0.34  # three requests per second without an API key
MAX_PER_TOPIC = 10
RETMAX = 20
MIN_PHRASE = 7

JOURNALS = [
    "Am J Surg Pathol", "Mod Pathol", "Virchows Arch", "Histopathology", "Hum Pathol",
    "Arch Pathol Lab Med", "Am J Clin Pathol", "Int J Surg Pathol", "Semin Diagn Pathol",
    "Adv Anat Pathol", "J Clin Pathol", "Pathology", "Head Neck Pathol", "Int J Gynecol Pathol",
    "Pediatr Dev Pathol", "J Cutan Pathol", "Am J Dermatopathol", "Cancer Cytopathol",
    "Diagn Cytopathol", "J Neuropathol Exp Neurol", "Brain Pathol", "Endocr Pathol",
    "Ann Diagn Pathol", "Pathol Int", "Pathol Res Pract", "Surg Pathol Clin", "Diagn Pathol",
    "Acta Cytol", "Cardiovasc Pathol", "J Pathol", "Acta Neuropathol", "Am J Pathol",
    "Dermatopathology (Basel)", "J Oral Pathol Med", "Oral Surg Oral Med Oral Pathol Oral Radiol",
    "Cytopathology", "J Am Soc Cytopathol", "Hematol Oncol", "Leuk Lymphoma", "Blood",
    "Haematologica", "Int J Clin Exp Pathol", "Case Rep Pathol", "Autops Case Rep",
]
JOURNAL_CLAUSE = "(" + " OR ".join(f'"{j}"[Journal]' for j in JOURNALS) + ")"

GENERIC = {
    "other", "general", "overview", "normal", "benign", "malignant", "cyst", "cysts", "tumor",
    "tumors", "tumour", "tumours", "carcinoma", "lymphoma", "adenoma", "infection", "infections",
    "inflammation", "trauma", "miscellaneous", "mixed", "nos", "unclassified", "sarcoma", "melanoma",
    "metastasis", "metastases", "dysplasia", "hyperplasia", "atrophy", "genetics", "staging",
    "inflammatory", "infectious", "congenital", "neoplastic", "malignancy", "precursor", "additional",
    "topics", "classification",
}
# Single words that are real search terms but occur in many organs: searched, but treated as
# generic (organ must be in the title or MeSH).
GENERIC_WORDS = {
    "heterotopia", "hamartoma", "hamartomas", "metaplasia", "fibromatosis", "papilloma", "papillomas",
    "adenocarcinoma", "adenocarcinomas", "carcinomas", "lymphomas", "sarcomas", "leiomyoma", "lipoma",
    "hemangioma", "schwannoma", "neurofibroma", "fibroma", "myxoma", "granuloma", "abscess", "ulcer",
    "calcification", "necrosis", "fibrosis", "nondiagnostic", "unsatisfactory", "angiosarcoma",
    "leiomyosarcoma", "liposarcoma", "rhabdomyosarcoma", "melanoma", "amyloidosis", "endometriosis",
    "tuberculosis", "actinomycosis", "histoplasmosis", "cryptococcosis", "aspergillosis", "candidiasis",
}
GENERIC_PHRASES = {
    "squamous cell carcinoma", "adenocarcinoma in situ", "basal cell carcinoma", "small cell carcinoma",
    "large cell carcinoma", "neuroendocrine tumor", "neuroendocrine carcinoma", "germ cell tumor",
    "germ cell tumors", "carcinoma in situ", "malignant melanoma", "metastatic carcinoma",
    "undifferentiated carcinoma", "clear cell carcinoma", "mucinous carcinoma", "papillary carcinoma",
    "spindle cell", "round cell", "granular cell tumor", "giant cell tumor", "solitary fibrous tumor",
    "normal anatomy", "normal histology", "anatomy and histology", "signet ring cell carcinoma",
    "mucinous adenocarcinoma", "adenosquamous carcinoma", "small cell", "large cell",
}
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
SKIP_SEGMENTS = {"other", "general", "genetics", "heme", "neoplastic", "benign", "malignant", "carcinoma",
                 "infectious", "inflammatory", "concept", "syndromes", "metastasis", "metastases"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("_", " "))).strip()


def get_json(endpoint: str, params: dict) -> dict:
    params = dict(params, retmode="json", **TOOL)
    req = urllib.request.Request(EUTILS + endpoint + "?" + urllib.parse.urlencode(params), headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.load(resp)
        except Exception as exc:  # 429 or network: back off and retry
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    return {}


def topic_phrases(leaf: dict) -> tuple[set[str], set[str]]:
    phrases = {norm(leaf.get("label") or "")}
    for src in (leaf.get("who"), leaf.get("pathout")):
        if src:
            phrases.add(norm(src.get("query") or src.get("label") or ""))
    # "Myofibroma and Myopericytoma" also searches each part.
    for p in list(phrases):
        for part in re.split(r"\s+(?:and|or|with|without|vs)\s+", p):
            phrases.add(part.strip())
    phrases = {p for p in phrases if len(p) >= MIN_PHRASE and p not in GENERIC}
    # Specific: a multi-word name, or a rare single word (nine letters or more) that is not a
    # generic histology term. Generic: everything else; those need the organ in the title.
    specific = {p for p in phrases if (len(p.split()) >= 2 and p not in GENERIC_PHRASES) or (len(p.split()) == 1 and len(p) >= 9 and p not in GENERIC_WORDS)}
    return specific, phrases - specific


def topic_context(leaf: dict, root_id: str) -> list[str]:
    segments = (leaf.get("path") or "").split("::")
    # Heme, Molecular and Peds paths name categories, not organs; use the root's keywords there.
    if len(segments) > 2 and root_id not in ("Heme", "Molecular", "Peds"):
        organ = norm(segments[1])
        if len(organ) >= 4 and organ not in GENERIC and organ not in SKIP_SEGMENTS:
            return [organ[:-1] if organ.endswith("s") else organ]
    return list(ROOT_KEYWORDS.get(root_id, []))


def matches(title: str, specific: set[str], generic: set[str], context: list[str]) -> bool:
    t = " " + norm(title) + " "
    if any(f" {p} " in t for p in specific):
        return True
    return bool(generic) and any(f" {p} " in t for p in generic) and any(k in t for k in context)


def search_topic(leaf: dict, root_id: str) -> tuple[list[dict], int]:
    specific, generic = topic_phrases(leaf)
    context = topic_context(leaf, root_id)
    if not specific and not generic:
        return [], 0
    clauses = [f'"{p}"[Title]' for p in sorted(specific | generic)]
    term = "(" + " OR ".join(clauses) + ") AND " + JOURNAL_CLAUSE
    # The organ must be named in the title or abstract, whatever the topic name, so a breast
    # topic never collects salivary-gland papers that happen to share a histology phrase.
    if context:
        term += " AND (" + " OR ".join(f'"{k.strip()}"[Title/Abstract]' for k in context) + ")"
    data = get_json("esearch.fcgi", {"db": "pubmed", "retmax": RETMAX, "sort": "relevance", "term": term})
    calls = 1
    ids = (data.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return [], calls
    time.sleep(DELAY)
    summ = get_json("esummary.fcgi", {"db": "pubmed", "id": ",".join(ids)})
    calls += 1
    kept = []
    for pmid in ids:
        rec = (summ.get("result") or {}).get(pmid) or {}
        title = (rec.get("title") or "").strip().rstrip(".")
        if not title or not matches(title, specific, generic, context):
            continue
        if re.match(r"^(correction|corrigendum|erratum|retraction|comment|reply|response|letter)\b", title, re.I):
            continue
        ids_by_type = {a.get("idtype"): a.get("value") for a in rec.get("articleids") or []}
        doi = ids_by_type.get("doi") or ""
        year = (rec.get("pubdate") or "")[:4]
        kept.append({
            "t": title,
            "j": rec.get("source") or rec.get("fulljournalname") or "",
            "y": year if year.isdigit() else "",
            "u": f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "p": pmid,
            "r": "Review" in (rec.get("pubtype") or []),
            "o": bool(ids_by_type.get("pmc")),
        })
    kept.sort(key=lambda a: (a["r"], a["y"] or "0000"), reverse=True)  # reviews first, then newest
    return kept[:MAX_PER_TOPIC], calls


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    data = json.loads(MAP.read_text(encoding="utf-8"))
    leaves: list[tuple[dict, str]] = []

    def walk(node: dict, root_id: str) -> None:
        if node.get("kind") == "leaf" and (node.get("who") or node.get("pathout")):
            leaves.append((node, root_id))
        for child in node.get("children") or []:
            walk(child, root_id)

    for root in data["roots"]:
        walk(root, root["id"])

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = [(lf, rid) for lf, rid in leaves if lf["path"] not in cache]
    if limit:
        todo = todo[:limit]
    print(f"{len(leaves)} public topics; {len(cache)} cached; {len(todo)} to search", flush=True)
    calls = 0
    started = time.time()
    for i, (leaf, root_id) in enumerate(todo, 1):
        try:
            found, n = search_topic(leaf, root_id)
            calls += n
        except Exception as exc:
            print(f"  ! {leaf['path']}: {exc}", flush=True)
            time.sleep(5)
            continue
        cache[leaf["path"]] = found
        if i % 50 == 0 or i == len(todo):
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            with_hits = sum(1 for v in cache.values() if v)
            print(f"  {i}/{len(todo)} searched, {with_hits} topics with articles, {calls} calls, {int(time.time() - started)}s", flush=True)
        time.sleep(DELAY)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    topics = {path: {"n": len(arts), "articles": arts} for path, arts in cache.items() if arts}
    distinct = {a["p"] for arts in cache.values() for a in arts}
    out = {
        "schema_version": "journal_links.v0_2",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "PubMed (NCBI E-utilities) title search per topic, limited to pathology journals; titles and links only.",
        "method": "Article kept only when the topic name (or its WHO / Pathology Outlines query) appears as a whole phrase in the article title; generic names also require the organ in the title. Reviews first, then newest; up to %d per topic. Open access = in PubMed Central." % MAX_PER_TOPIC,
        "journals": JOURNALS,
        "counts": {
            "topics_searched": len(cache),
            "topics_with_articles": len(topics),
            "articles_matched": len(distinct),
            "links_shown": sum(v["n"] for v in topics.values()),
            "open_access": len({a["p"] for arts in cache.values() for a in arts if a["o"]}),
            "reviews": len({a["p"] for arts in cache.values() for a in arts if a["r"]}),
        },
        "topics": topics,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("finished:", json.dumps(out["counts"]), f"{calls} PubMed calls this run", flush=True)


if __name__ == "__main__":
    main()
