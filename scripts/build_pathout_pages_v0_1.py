#!/usr/bin/env python
"""Build pathout_pages_v0_1.json: map public topics (leaves with a `pathout`
field in unified_content_map_v0_1.json) to real PathologyOutlines.com topic
page URLs.

Input: a directory of `<chapter-slug>.txt` files, one line per PO topic in the
form `slug|title`, as scraped from the PathologyOutlines chapter index pages
(https://www.pathologyoutlines.com/<chapter-slug>.html). URL for a topic is
https://www.pathologyoutlines.com/topic/<slug>.html.

Run with: python -I scripts/build_pathout_pages_v0_1.py --po-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "frontend/pathology_hub_map_hub_v0_1/content/data/unified_content_map_v0_1.json"
OUT_PATH = REPO / "frontend/pathology_hub_map_hub_v0_1/content/data/pathout_pages_v0_1.json"
PO_BASE = "https://www.pathologyoutlines.com/topic/"

# Root -> PO slug prefixes that "fit" the root. None = any chapter fits.
# Stain / molecular-marker pages are only eligible for the Molecular root.
ROOT_PREFIXES: dict[str, list[str] | None] = {
    "Breast": ["breast"],
    "GI": ["colon", "stomach", "esophagus", "esphagus", "smallbowel", "ampulla", "anus",
           "appendix", "liver", "gallbladder", "pancreas"],
    "GU": ["bladder", "kidney", "prostate", "testis", "penscrotum", "penis", "adrenal",
           "adrenocortical"],
    "GYN": ["cervix", "uterus", "ovary", "vulva", "vagina", "fallopian", "placenta"],
    "Heme": ["lymphoma", "bonemarrow", "lymphnodes", "lymphnode", "hematology", "hemato",
             "leukemia", "myeloproliferative", "spleen", "boneneoplastic"],
    "HN": ["oralcavity", "salivaryglands", "larynx", "trachea", "nasal", "ear", "mandiblemaxilla",
           "thyroid", "parathyroid"],
    "Skin": ["skin"],
    "Neuro": ["cns", "CNS"],
    "BST": ["bone", "softtissue", "joints"],
    "Thorax_Mediastinum": ["lung", "pleura", "peritoneum", "mediastinum", "heart"],
    "Eye_Orbit": ["eye"],
    "Endo": ["thyroid", "parathyroid", "adrenal", "adrenocortical", "pancreas"],
    "Cytopathology": ["cytopathology"],
    "Molecular": ["molecular", "Molecular", "stains", "stain", "cdmarkers"],
    "Peds": None,
}

PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")


GENERIC = {"carcinoma", "tumor", "tumors", "tumour", "adenocarcinoma", "lesion", "lesions", "disease",
           "diseases", "syndrome", "type", "types", "variant", "variants", "conventional", "classic",
           "nos", "general", "overview", "positive", "associated", "related", "of", "the", "and",
           "with", "in", "cell", "cells", "pattern", "patterns", "benign", "malignant", "primary",
           "gland", "glands"}


def norm(s: str) -> str:
    s = s.lower().replace("_", " ").replace("-", " ").replace("/", " ")
    s = PUNCT_RE.sub(" ", s)
    s = SPACE_RE.sub(" ", s).strip()
    return " ".join("carcinoma" if w == "cancer" else w for w in s.split() if w != "and")


def core_tokens(q: str) -> frozenset:
    return frozenset(w for w in q.split() if w not in GENERIC)


def po_variants(title: str) -> list[str]:
    """Full title first, then title with parenthetical suffixes and ' / ' or
    ' & ' tails dropped."""
    out = [norm(title)]
    kept = norm(title.replace("(", " ").replace(")", " "))
    t = re.sub(r"\s*\([^)]*\)", "", title)
    t = re.sub(r"\s*\(pending\)\s*$", "", t, flags=re.I)
    for sep in (" / ", " & ", "-"):
        if sep in t:
            t2 = t.split(sep)[0]
            if t2.strip():
                out.append(norm(t2))
    out.append(norm(t))
    out.append(kept)
    out.extend([v.replace(" ", "") for v in list(out) if " " in v])
    seen, res = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res


def load_po(po_dir: Path) -> dict[str, dict]:
    topics: dict[str, dict] = {}
    for f in sorted(po_dir.glob("*.txt")):
        chapter = f.stem
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            slug, title = line.split("|", 1)
            slug = slug.strip().lstrip("/").removeprefix("topic/")
            slug = slug.split("#")[0].removesuffix(".html").strip()
            if not slug or not title.strip():
                continue
            t = topics.setdefault(slug, {"slug": slug, "titles": [], "chapters": set()})
            if title.strip() not in t["titles"]:
                t["titles"].append(title.strip())
            t["chapters"].add(chapter)
    return topics


CHAPTERS_OF: dict[str, set] = {}


def fits(slug: str, root: str) -> bool:
    """A PO topic fits a root when its slug starts with a fitting chapter prefix, or
    when it was listed on a chapter index page whose slug fits (e.g. cervix cytology
    topics listed on the cytopathology chapter page)."""
    prefixes = ROOT_PREFIXES.get(root)
    if prefixes is None:
        return True
    if any(slug.startswith(p) for p in prefixes):
        return True
    return any(any(ch.startswith(p) for p in prefixes) for ch in CHAPTERS_OF.get(slug, ()))


def leaves(map_json: dict) -> list[dict]:
    out: list[dict] = []

    def walk(n: dict) -> None:
        if n.get("kind") == "leaf":
            out.append(n)
        for c in n.get("children") or []:
            walk(c)

    for r in map_json["roots"]:
        walk(r)
    return out


def path_tokens(path: str) -> set:
    toks = set()
    for seg in path.split("::")[1:-1]:
        for w in seg.lower().split("_"):
            if len(w) >= 4:
                toks.add(w)
        toks.add(seg.lower().replace("_", ""))
    return toks


def affinity(slug: str, ptoks: set) -> int:
    sl = slug.lower()
    return 1 if any(sl.startswith(t) for t in ptoks) else 0


def choose(cands: list[str], root: str, ptoks: set = frozenset()) -> str | None:
    """Pick one slug from candidates: prefer chapter fit, then path affinity, then the
    shortest slug; skip stains unless Molecular."""
    cands = [c for c in cands if not (c.startswith(("stains", "stain", "cdmarkers", "molecular", "Molecular")) and root != "Molecular")]
    if not cands:
        return None
    fit = [c for c in cands if fits(c, root)]
    if len(fit) == 1:
        return fit[0]
    if len(fit) > 1:
        return sorted(fit, key=lambda s: (-affinity(s, ptoks), len(s), s))[0]
    if len(cands) == 1 and ROOT_PREFIXES.get(root) is None:
        return cands[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--po-dir", required=True, type=Path, help="directory of <chapter>.txt slug|title files")
    ap.add_argument("--map", type=Path, default=MAP_PATH)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--source-note", default="PathologyOutlines.com chapter index pages read on 2026-10-15")
    args = ap.parse_args()

    po = load_po(args.po_dir)
    CHAPTERS_OF.update({k: v["chapters"] for k, v in po.items()})
    # index: normalised variant -> list of slugs; exact index uses full title only
    exact_idx: dict[str, list[str]] = defaultdict(list)
    loose_idx: dict[str, list[str]] = defaultdict(list)
    for slug, t in po.items():
        for title in t["titles"]:
            vs = po_variants(title)
            if slug not in exact_idx[vs[0]]:
                exact_idx[vs[0]].append(slug)
            for v in vs:
                if slug not in loose_idx[v]:
                    loose_idx[v].append(slug)

    slug_lc = {k.lower(): k for k in po if len(k) >= 8}
    map_json = json.loads(args.map.read_text(encoding="utf-8"))
    lv = [l for l in leaves(map_json) if l.get("pathout")]

    result: dict[str, dict] = {}
    n_exact = n_partial = 0
    unmatched: list[str] = []
    for leaf in lv:
        root = leaf["path"].split("::")[0]
        p = leaf["pathout"]
        queries = []
        for q in (p.get("query"), p.get("label"), leaf.get("label")):
            if q and norm(q) and norm(q) not in queries:
                queries.append(norm(q))
        slug = None
        mode = None
        ptoks = path_tokens(leaf["path"])
        # 0) the query/label sometimes carries the PO slug itself (e.g. "Lymphnodesgranulomatous")
        for q in (p.get("query"), p.get("label"), leaf.get("label")):
            for w in (q or "").replace("_", " ").split():
                if w.lower() in slug_lc:
                    slug, mode = slug_lc[w.lower()], "exact"
                    break
            if slug:
                break
        # 1) exact full-title equality
        for q in queries:
            if slug:
                break
            slug = choose(exact_idx.get(q, []), root, ptoks)
            if slug:
                mode = "exact"
                break
        # 2) equality after dropping parenthetical / tail parts
        if not slug:
            for q in queries:
                slug = choose(loose_idx.get(q, []), root, ptoks) or choose(loose_idx.get(q.replace(" ", ""), []), root, ptoks)
                if slug:
                    mode = "exact"
                    break
        # 3) containment (shorter side >= 8 chars), only among chapter-fitting slugs.
        #    Before that, accept a core-token-identical PO title (stage 4 with jac == 1).
        for pass_min_jac in (1.0,):
          if not slug:
            for q in queries:
                qc = core_tokens(q)
                if not qc:
                    continue
                best = None
                for s_, t in po.items():
                    if not fits(s_, root) or (s_.startswith(("stains", "stain", "cdmarkers", "molecular", "Molecular")) and root != "Molecular"):
                        continue
                    for title in t["titles"]:
                        tc = core_tokens(po_variants(title)[0])
                        if tc and tc == qc and len(" ".join(sorted(qc))) >= 8:
                            cand = (affinity(s_, ptoks), -len(s_), s_)
                            if best is None or cand > best:
                                best = cand
                if best:
                    slug, mode = best[2], "partial"
                    break
        if not slug:
            for q in queries:
                cands = []
                for v, slugs in loose_idx.items():
                    short_s = v if len(v) <= len(q) else q
                    if len(short_s) < 12 and " " not in short_s:
                        continue
                    if len(short_s) < 8:
                        continue
                    po_in_q = (" " + v + " ") in (" " + q + " ") and " " in v and len(v) >= 12 and core_tokens(v)
                    q_in_po = (" " + q + " ") in (" " + v + " ") and " " in q
                    if po_in_q or q_in_po:
                        for s in slugs:
                            if s not in cands:
                                cands.append(s)
                cands = [c for c in cands if fits(c, root) and not (c.startswith(("stains", "stain", "cdmarkers", "molecular", "Molecular")) and root != "Molecular")]
                if cands:
                    # prefer the candidate whose title is longest (most specific overlap)
                    def score(s: str) -> tuple:
                        best = max((len(v) for v in po_variants(po[s]["titles"][0]) if (" " + v + " ") in (" " + q + " ") or (" " + q + " ") in (" " + v + " ")), default=0)
                        return (-affinity(s, ptoks), -best, len(s))
                    cands.sort(key=score)
                    slug = cands[0]
                    mode = "partial"
                    break
        # 4) core-token subset among chapter-fitting candidates (both sides >= 1 core token;
        #    the shorter side must have >= 8 characters of core text)
        if not slug:
            for q in queries:
                qc = core_tokens(q)
                if not qc:
                    continue
                best = None
                for s_, t in po.items():
                    if not fits(s_, root) or (s_.startswith(("stains", "stain", "cdmarkers", "molecular", "Molecular")) and root != "Molecular"):
                        continue
                    for title in t["titles"]:
                        tc = core_tokens(po_variants(title)[-1 if False else 0])
                        if not tc:
                            continue
                        if qc <= tc or tc <= qc:
                            shorter = qc if len(qc) <= len(tc) else tc
                            longer_q = q if shorter is tc else po_variants(title)[0]
                            acronym_ok = len(shorter) == 1 and len(next(iter(shorter))) >= 4 and longer_q.split()[-1] in shorter
                            if len(" ".join(sorted(shorter))) < 8 and not acronym_ok:
                                continue
                            jac = len(qc & tc) / len(qc | tc)
                            aff = affinity(s_, ptoks)
                            if qc < tc and jac < 0.75:
                                # PO page is more specific than the topic: only accept near-identical
                                continue
                            if tc < qc and len(tc) == 1 and not acronym_ok and not aff and len(next(iter(tc))) < 12:
                                # single generic PO word inside a longer topic name: needs chapter affinity
                                continue
                            cand = (aff, jac, -len(s_), s_)
                            if best is None or cand > best:
                                best = cand
                if best:
                    slug, mode = best[3], "partial"
                    break
        # 5) generic-word-stripped query equals a stripped PO title, unique within fitting chapter
        if not slug:
            for q in queries:
                qc = core_tokens(q)
                if not qc:
                    continue
                hits = []
                for s_, t in po.items():
                    if not fits(s_, root) or (s_.startswith(("stains", "stain", "cdmarkers", "molecular", "Molecular")) and root != "Molecular"):
                        continue
                    for title in t["titles"]:
                        if core_tokens(po_variants(title)[0]) == qc or core_tokens(po_variants(title)[-1]) == qc:
                            hits.append(s_)
                            break
                hits = sorted(set(hits), key=lambda x: (-affinity(x, ptoks), len(x), x))
                if len(hits) >= 1:
                    slug, mode = hits[0], "partial"
                    break
        if slug:
            if mode == "exact":
                n_exact += 1
            else:
                n_partial += 1
            result[leaf["path"]] = {"u": PO_BASE + slug + ".html", "t": po[slug]["titles"][0], "m": mode}
        else:
            unmatched.append(leaf["path"])

    out = {
        "schema_version": "pathout_pages.v0_1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": args.source_note,
        "counts": {
            "po_topics_crawled": len(po),
            "topics_with_pathout": len(lv),
            "matched": len(result),
            "exact": n_exact,
            "partial": n_partial,
        },
        "topics": result,
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["counts"], indent=1))
    print("unmatched:", len(unmatched))
    for u in unmatched[:40]:
        print("  ", u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
