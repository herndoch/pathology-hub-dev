"""Per-topic journal article links for the public Teaching topics map, judged on abstracts.

Local only, free NCBI E-utilities (no key, no Google, no Cloud Run), three requests a second.
For every public topic (WHO / Pathology Outlines leaf) PubMed is searched for pathology-journal
articles that mention the topic name in title or abstract and name the organ; each candidate's
title, abstract, MeSH headings and publication types are then fetched and the article is kept
only when the abstract shows it is about the topic:

  hit  = organ rule by name type (multi-word entity name: none; rare single word: organ in title,
         abstract or MeSH; generic term: organ in title or MeSH), AND one of
         (a) topic phrase in the title,
         (b) topic phrase in a MeSH heading,
         (c) topic phrase at least three times in the abstract, or once in its first sentence.
  miss = otherwise (a passing mention deep in the abstract is not a hit), and corrections,
         errata, comments, letters and retractions are always dropped.

OpenAlex (free, no key) adds pathology-journal works whose title contains the topic that PubMed's
relevance cap left out, and supplies citation counts. Abstracts are used only for the judgement;
the site shows titles and links. Reviews first, then most cited, then newest; at most
MAX_PER_TOPIC per topic. Open access = the article is in PubMed Central.

Output: frontend/pathology_hub_map_hub_v0_1/content/data/journal_links_v0_1.json
Cache:  frontend/pathology_hub_map_hub_v0_1/content/data/pubmed_abstract_cache_v0_2.json (resumable)
Flags:  --limit N (first N topics), --show (print every candidate with its verdict and reason)
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pm", ROOT / "scripts/build_pubmed_topic_articles_v0_1.py")
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)

OUT = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/journal_links_v0_1.json"
CACHE = ROOT / "frontend/pathology_hub_map_hub_v0_1/content/data/pubmed_abstract_cache_v0_2.json"
UA = {"User-Agent": "PathologyKnowledgeHub/0.1 (mailto:herndon.charlie@gmail.com)"}
DELAY = 0.34
MAX_PER_TOPIC = 10
RETMAX = 30
DROP_TYPES = re.compile(r"^(correction|corrigendum|erratum|retraction|comment|reply|response|letter)\b", re.I)


def norm(text: str) -> str:
    return pm.norm(text)


def efetch(pmids: list[str]) -> list[dict]:
    params = urllib.parse.urlencode({"db": "pubmed", "retmode": "xml", "id": ",".join(pmids), **pm.TOOL})
    req = urllib.request.Request(pm.EUTILS + "efetch.fcgi?" + params, headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                xml = resp.read()
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    out = []
    for art in ET.fromstring(xml).findall(".//PubmedArticle"):
        title_el = art.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip().rstrip(".") if title_el is not None else ""
        abstract = " ".join("".join(a.itertext()).strip() for a in art.findall(".//Abstract/AbstractText"))
        mesh = [m.find("DescriptorName").text or "" for m in art.findall(".//MeshHeading") if m.find("DescriptorName") is not None]
        pubtypes = [p.text or "" for p in art.findall(".//PublicationType")]
        ids = {i.get("IdType"): (i.text or "") for i in art.findall("./PubmedData/ArticleIdList/ArticleId")}
        year = ""
        for xp in (".//Article/Journal/JournalIssue/PubDate/Year", ".//ArticleDate/Year", ".//Article/Journal/JournalIssue/PubDate/MedlineDate"):
            el = art.find(xp)
            if el is not None and el.text:
                year = re.sub(r"\D.*", "", el.text.strip())[:4]
                break
        journal = ""
        for xp in (".//Journal/ISOAbbreviation", ".//Journal/Title"):
            el = art.find(xp)
            if el is not None and el.text:
                journal = el.text.strip()
                break
        out.append({
            "pmid": ids.get("pubmed") or (art.find(".//PMID").text if art.find(".//PMID") is not None else ""),
            "title": title, "abstract": abstract, "mesh": mesh, "pubtypes": pubtypes,
            "doi": ids.get("doi", ""), "pmc": ids.get("pmc", ""),
            "year": year,
            "journal": journal,
        })
    return out


def judge(rec: dict, specific: set[str], generic: set[str], context: list[str]) -> tuple[bool, str]:
    """Abstract-based match rule; returns (hit, reason)."""
    if DROP_TYPES.match(rec["title"] or ""):
        return False, "correction/letter"
    t = " " + norm(rec["title"]) + " "
    a = " " + norm(rec["abstract"]) + " "
    m = " " + " | ".join(norm(x) for x in rec["mesh"]) + " "
    # Organ requirement by how ambiguous the name is: a multi-word entity name ("luteinized
    # thecoma") needs none; a rare single word ("angiomyolipoma", or a drug name) needs the organ
    # somewhere in title, abstract or MeSH; a generic term needs it in the title or MeSH.
    organ_anywhere = not context or any(k in t + a + m for k in context)
    organ_in_title = not context or any(k in t + m for k in context)
    first_sentence = " " + norm(re.split(r"(?<=[.!?])\s", rec["abstract"].strip(), maxsplit=1)[0]) + " " if rec["abstract"] else ""
    for p in sorted(specific, key=len, reverse=True) + sorted(generic):
        pp = f" {p} "
        if p in generic and not organ_in_title:
            continue
        if p in specific and len(p.split()) == 1 and not organ_anywhere:
            continue
        if pp in t:
            return True, "in title"
        if pp in m:
            return True, "MeSH heading"
        n = a.count(pp)
        if n >= 3 or (n >= 1 and pp in first_sentence):
            return True, f"abstract x{n}"
    if any(f" {p} " in t + a for p in specific | generic):
        return False, "passing mention only" if any(f" {p} " in a for p in specific | generic) else "organ not named"
    return False, "no mention"


OPENALEX = "https://api.openalex.org/works"
MAILTO = "herndon.charlie@gmail.com"
OA_DELAY = 0.15


OA_COOLDOWN_S = 900
_oa_blocked_until = 0.0
_oa_skipped = False


def openalex_get(params: dict) -> dict:
    """One OpenAlex call. On HTTP 429 OpenAlex is skipped for OA_COOLDOWN_S seconds and the topic is
    marked so a later --openalex-fill pass can complete it, instead of stalling the whole run."""
    global _oa_blocked_until, _oa_skipped
    if time.time() < _oa_blocked_until:
        _oa_skipped = True
        return {}
    url = OPENALEX + "?" + urllib.parse.urlencode(dict(params, mailto=MAILTO))
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as resp:
                data = json.load(resp)
            time.sleep(OA_DELAY)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _oa_blocked_until = time.time() + OA_COOLDOWN_S
                _oa_skipped = True
                print(f"  ! OpenAlex 429: skipping OpenAlex for {OA_COOLDOWN_S // 60} min", flush=True)
                return {}
            if attempt == 1:
                _oa_skipped = True
                return {}
            time.sleep(2)
        except Exception:
            if attempt == 1:
                _oa_skipped = True
                return {}
            time.sleep(2)
    return {}


def pathology_venue(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in ("pathol", "cytol", "histopathol", "dermatopathol", "neuropathol"))


def openalex_candidates(phrases: set[str]) -> list[str]:
    """DOIs of pathology-journal works whose title contains one of the topic phrases (OpenAlex)."""
    dois: list[str] = []
    for p in sorted(phrases, key=len, reverse=True)[:2]:
        data = openalex_get({"filter": f"title.search:{p}", "per-page": 50, "sort": "cited_by_count:desc",
                             "select": "doi,primary_location"})
        for w in data.get("results", []):
            src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            if doi and pathology_venue(src) and doi not in dois:
                dois.append(doi)
    return dois


def openalex_citations(dois: list[str]) -> dict[str, int]:
    """Citation counts for up to 50 DOIs in one OpenAlex call."""
    out: dict[str, int] = {}
    for i in range(0, len(dois), 50):
        chunk = dois[i:i + 50]
        data = openalex_get({"filter": "doi:" + "|".join(chunk), "per-page": 50, "select": "doi,cited_by_count"})
        for w in data.get("results", []):
            out[(w.get("doi") or "").replace("https://doi.org/", "").lower()] = w.get("cited_by_count") or 0
    return out


def search_topic(leaf: dict, root_id: str, show: bool) -> tuple[list[dict], int, int]:
    global _oa_skipped
    _oa_skipped = False
    specific, generic = pm.topic_phrases(leaf)
    context = pm.topic_context(leaf, root_id)
    phrases = specific | generic
    if not phrases:
        return [], 0, 0
    clauses = [f'"{p}"[Title/Abstract]' for p in sorted(phrases)]
    term = "(" + " OR ".join(clauses) + ") AND " + pm.JOURNAL_CLAUSE
    # Only an ambiguous name (no multi-word entity phrase) is narrowed by organ in the query;
    # the abstract judgement enforces the organ rule on everything afterwards.
    if context and not any(len(p.split()) >= 2 for p in specific):
        term += " AND (" + " OR ".join(f'"{k.strip()}"[Title/Abstract]' for k in context) + ")"
    data = pm.get_json("esearch.fcgi", {"db": "pubmed", "retmax": RETMAX, "sort": "relevance", "term": term})
    calls = 1
    ids = list((data.get("esearchresult") or {}).get("idlist") or [])
    time.sleep(DELAY)
    # OpenAlex: pathology-journal works with the topic in the title that PubMed's cap or
    # organ filter left out; their PubMed records are fetched so the same abstract rule applies.
    extra_dois = openalex_candidates(phrases)
    calls += min(2, len(phrases))
    if extra_dois:
        doi_term = " OR ".join(f'"{d}"[doi]' for d in extra_dois[:40])
        found = pm.get_json("esearch.fcgi", {"db": "pubmed", "retmax": 40, "term": doi_term})
        calls += 1
        time.sleep(DELAY)
        for pmid in (found.get("esearchresult") or {}).get("idlist") or []:
            if pmid not in ids:
                ids.append(pmid)
    if not ids:
        return [], calls, 0
    recs = efetch(ids)
    calls += 1
    kept = []
    for rec in recs:
        hit, why = judge(rec, specific, generic, context)
        if show:
            print(f"     {'HIT ' if hit else 'miss'} [{why:20}] {rec['journal'][:22]:22} {rec['year']:4} {rec['title'][:90]}", flush=True)
        if not hit:
            continue
        kept.append({
            "t": rec["title"], "j": rec["journal"], "y": rec["year"][:4],
            "u": f"https://doi.org/{rec['doi']}" if rec["doi"] else f"https://pubmed.ncbi.nlm.nih.gov/{rec['pmid']}/",
            "p": rec["pmid"], "d": rec["doi"].lower(), "r": "Review" in rec["pubtypes"], "o": bool(rec["pmc"]), "w": why, "c": 0,
        })
    if kept:
        cites = openalex_citations([a["d"] for a in kept if a["d"]])
        calls += 1
        for a in kept:
            a["c"] = cites.get(a["d"], 0)
    # Reviews first; within each group the most cited, then the newest.
    kept.sort(key=lambda x: (x["r"], x["c"], x["y"] or "0000"), reverse=True)
    if show:
        for a in kept[:MAX_PER_TOPIC]:
            print(f"     -> {'REV' if a['r'] else '   '} cites={a['c']:4} {a['y']:4} {a['title'][:70] if 'title' in a else a['t'][:70]}", flush=True)
    return kept[:MAX_PER_TOPIC], calls, len(recs)


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    show = "--show" in sys.argv
    data = json.loads(pm.MAP.read_text(encoding="utf-8"))
    leaves: list[tuple[dict, str]] = []

    def walk(node: dict, root_id: str) -> None:
        if node.get("kind") == "leaf" and (node.get("who") or node.get("pathout")):
            leaves.append((node, root_id))
        for child in node.get("children") or []:
            walk(child, root_id)

    for root in data["roots"]:
        walk(root, root["id"])
    if limit:  # spread a small sample across the roots
        step = max(1, len(leaves) // limit)
        leaves = leaves[::step][:limit]

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    fill = "--openalex-fill" in sys.argv  # redo only topics whose OpenAlex step was skipped
    todo = [(lf, rid) for lf, rid in leaves
            if lf["path"] not in cache or show or (fill and cache[lf["path"]].get("oa_skipped"))]
    print(f"{len(leaves)} topics; {len(cache)} cached; {len(todo)} to search", flush=True)
    calls = candidates = 0
    started = time.time()
    for i, (leaf, root_id) in enumerate(todo, 1):
        if show:
            print(f"\n== {leaf['path']}", flush=True)
        try:
            found, n, cand = search_topic(leaf, root_id, show)
            calls += n
            candidates += cand
        except Exception as exc:
            print(f"  ! {leaf['path']}: {exc}", flush=True)
            time.sleep(5)
            continue
        cache[leaf["path"]] = {"hits": found, "candidates": cand, "oa_skipped": _oa_skipped}
        if i % 50 == 0 or i == len(todo):
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            with_hits = sum(1 for v in cache.values() if v["hits"])
            oa_missing = sum(1 for v in cache.values() if v.get("oa_skipped"))
            print(f"  {i}/{len(todo)} searched, {with_hits} topics with articles, {calls} calls, {candidates} candidates judged, {oa_missing} awaiting OpenAlex, {int(time.time() - started)}s", flush=True)
        time.sleep(DELAY)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if limit:
        return

    topics = {path: {"n": len(v["hits"]), "articles": [{k: a.get(k) for k in ("t", "j", "y", "u", "p", "r", "o", "c")} for a in v["hits"]]}
              for path, v in cache.items() if v["hits"]}
    all_hits = [a for v in cache.values() for a in v["hits"]]
    out = {
        "schema_version": "journal_links.v0_3",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "PubMed (NCBI E-utilities) searched per topic across pathology journals, plus OpenAlex title matches in pathology journals; each candidate judged on its PubMed abstract and MeSH headings. Titles and links only.",
        "method": "Kept when the organ is named and the topic phrase is in the title, in a MeSH heading, in the abstract's first sentence or three times in the abstract; passing mentions, corrections and letters dropped. Reviews first, then most cited (OpenAlex), then newest; up to %d per topic." % MAX_PER_TOPIC,
        "journals": pm.JOURNALS,
        "counts": {
            "topics_searched": len(cache),
            "topics_awaiting_openalex": sum(1 for v in cache.values() if v.get("oa_skipped")),
            "candidates_judged": sum(v["candidates"] for v in cache.values()),
            "topics_with_articles": len(topics),
            "articles_matched": len({a["p"] for a in all_hits}),
            "links_shown": sum(v["n"] for v in topics.values()),
            "open_access": len({a["p"] for a in all_hits if a["o"]}),
            "reviews": len({a["p"] for a in all_hits if a["r"]}),
        },
        "topics": topics,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("finished:", json.dumps(out["counts"]), f"{calls} PubMed calls this run", flush=True)


if __name__ == "__main__":
    main()
