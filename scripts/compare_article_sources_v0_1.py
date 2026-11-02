"""Compare free literature search sources on a sample of public topics.

Sources: PubMed (E-utilities), OpenAlex, Europe PMC, Semantic Scholar. Same match rule for all:
the topic name appears as a whole phrase in the article title, the venue is a pathology
journal (name contains "pathol" / "cytol" / "histopathol"), and for generic names the organ is
in the title. Local only, polite rates. Prints a per-topic table and totals, and writes the
raw comparison to outputs/article_source_comparison_<date>.json.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pm", ROOT / "scripts/build_pubmed_topic_articles_v0_1.py")
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
UA = {"User-Agent": "PathologyKnowledgeHub/0.1 (mailto:herndon.charlie@gmail.com)"}
MAILTO = "herndon.charlie@gmail.com"
PER_ROOT = 2


def get(url: str, delay: float) -> dict:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as resp:
                data = json.load(resp)
            time.sleep(delay)
            return data
        except Exception as exc:
            if attempt == 3:
                print("   !", url[:80], exc, flush=True)
                return {}
            time.sleep(4 * (attempt + 1))
    return {}


def venue_ok(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in ("pathol", "cytol", "histopathol", "dermatopathol", "neuropathol"))


def keep(title: str, venue: str, specific, generic, context) -> bool:
    return bool(title) and venue_ok(venue) and pm.matches(title, specific, generic, context)


def openalex(phrase: str) -> list[dict]:
    q = urllib.parse.quote(phrase)
    url = f"https://api.openalex.org/works?filter=title.search:{q}&per-page=50&sort=cited_by_count:desc&mailto={MAILTO}"
    out = []
    for w in get(url, 0.2).get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        out.append({"t": w.get("title") or "", "v": src, "doi": (w.get("doi") or "").replace("https://doi.org/", "").lower(),
                    "y": w.get("publication_year"), "c": w.get("cited_by_count"), "oa": (w.get("open_access") or {}).get("is_oa"), "type": w.get("type")})
    return out


def europepmc(phrase: str) -> list[dict]:
    q = urllib.parse.quote(f'TITLE:"{phrase}" AND (JOURNAL:"*pathol*")')
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={q}&format=json&pageSize=50&resultType=lite"
    out = []
    for r in (get(url, 0.3).get("resultList") or {}).get("result", []):
        out.append({"t": r.get("title") or "", "v": r.get("journalTitle") or "", "doi": (r.get("doi") or "").lower(),
                    "y": r.get("pubYear"), "c": r.get("citedByCount"), "oa": r.get("isOpenAccess") == "Y", "type": r.get("pubType")})
    return out


def semanticscholar(phrase: str) -> list[dict]:
    q = urllib.parse.quote(phrase)
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=50&fields=title,year,venue,citationCount,isOpenAccess,externalIds,publicationTypes"
    out = []
    for p in get(url, 1.2).get("data", []):
        out.append({"t": p.get("title") or "", "v": p.get("venue") or "", "doi": ((p.get("externalIds") or {}).get("DOI") or "").lower(),
                    "y": p.get("year"), "c": p.get("citationCount"), "oa": p.get("isOpenAccess"), "type": ",".join(p.get("publicationTypes") or [])})
    return out


def pubmed(phrase_set, context) -> list[dict]:
    clauses = [f'"{p}"[Title]' for p in sorted(phrase_set)]
    term = "(" + " OR ".join(clauses) + ") AND " + pm.JOURNAL_CLAUSE
    if context:
        term += " AND (" + " OR ".join(f'"{k.strip()}"[Title/Abstract]' for k in context) + ")"
    data = pm.get_json("esearch.fcgi", {"db": "pubmed", "retmax": 50, "sort": "relevance", "term": term})
    time.sleep(0.34)
    ids = (data.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    summ = pm.get_json("esummary.fcgi", {"db": "pubmed", "id": ",".join(ids)})
    time.sleep(0.34)
    out = []
    for pmid in ids:
        rec = (summ.get("result") or {}).get(pmid) or {}
        ids_by_type = {a.get("idtype"): a.get("value") for a in rec.get("articleids") or []}
        out.append({"t": (rec.get("title") or "").rstrip("."), "v": rec.get("source") or "", "doi": (ids_by_type.get("doi") or "").lower(),
                    "y": (rec.get("pubdate") or "")[:4], "c": None, "oa": bool(ids_by_type.get("pmc")), "type": ",".join(rec.get("pubtype") or [])})
    return out


def main() -> None:
    data = json.loads(pm.MAP.read_text(encoding="utf-8"))
    sample = []
    for root in data["roots"]:
        leaves = []

        def walk(node):
            if node.get("kind") == "leaf" and (node.get("who") or node.get("pathout")):
                leaves.append(node)
            for c in node.get("children") or []:
                walk(c)
        walk(root)
        # spread the picks through the root so they are not all from the first branch
        step = max(1, len(leaves) // (PER_ROOT + 1))
        for k in range(PER_ROOT):
            if (k + 1) * step < len(leaves):
                sample.append((leaves[(k + 1) * step], root["id"]))
    print(f"{len(sample)} sample topics", flush=True)
    rows = []
    for leaf, root_id in sample:
        specific, generic = pm.topic_phrases(leaf)
        context = pm.topic_context(leaf, root_id)
        phrases = specific | generic
        if not phrases:
            continue
        phrase = sorted(phrases, key=len)[-1]
        res = {
            "pubmed": [a for a in pubmed(phrases, context) if keep(a["t"], a["v"], specific, generic, context)],
            "openalex": [a for a in openalex(phrase) if keep(a["t"], a["v"], specific, generic, context)],
            "europepmc": [a for a in europepmc(phrase) if keep(a["t"], a["v"], specific, generic, context)],
            "semanticscholar": [a for a in semanticscholar(phrase) if keep(a["t"], a["v"], specific, generic, context)],
        }
        dois = {s: {a["doi"] for a in v if a["doi"]} for s, v in res.items()}
        union = set().union(*dois.values())
        missed = union - dois["pubmed"]
        row = {"topic": leaf["path"], "phrase": phrase, "counts": {s: len(v) for s, v in res.items()},
               "union_dois": len(union), "not_in_pubmed": len(missed),
               "examples_not_in_pubmed": [a["t"][:80] for s in ("openalex", "europepmc", "semanticscholar") for a in res[s] if a["doi"] in missed][:3],
               "results": res}
        rows.append(row)
        c = row["counts"]
        print(f"  {leaf['path'][:58]:58} PM {c['pubmed']:3} OA {c['openalex']:3} EPMC {c['europepmc']:3} S2 {c['semanticscholar']:3} | union {len(union):3} missed-by-PubMed {len(missed):3}", flush=True)
    tot = {s: sum(r["counts"][s] for r in rows) for s in ("pubmed", "openalex", "europepmc", "semanticscholar")}
    print("TOTAL", tot, "union", sum(r["union_dois"] for r in rows), "not in pubmed", sum(r["not_in_pubmed"] for r in rows), flush=True)
    out = ROOT / "outputs" / f"article_source_comparison_{datetime.now(timezone.utc):%Y%m%d}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "rows": rows, "totals": tot}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
