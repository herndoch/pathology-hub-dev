#!/usr/bin/env python3
"""Semantically tag lecture deck segments against canonical Heme::* leaves.

For each ASR utterance:
  1. Embed utterance (+ light neighbor context) with text-embedding-3-small
  2. Cosine against all 354 pre-embedded Heme::* browse leaves
  3. Pick argmax; apply soft lecture-prior bonus and sticky hold
  4. Below similarity floor → do_not_index

This replaces the keyword heuristic tagger for production-ish deck packaging.
Still not human gold. Still does not rebuild FAISS/API.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from openai import OpenAI


EMBEDDING_MODEL = "text-embedding-3-small"

DO_NOT_INDEX_PATTERNS = [
    r"^\s*thank you",
    r"\bi thank you\b",
    r"\bthanks?\b.{0,40}(attention|listening|time)\b",
    r"\backnowledg",
    r"\bdisclosures?\b",
    r"\bconflict of interest\b",
    r"hello,?\s+my name is",
    r"delighted to participate",
    r"society for hematopathology",
    r"virtual curriculum",
    r"any questions",
]

LECTURE_PRIORS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"aggressive_b", re.I), ["Heme::Mature_B_Cell::Large_B_Cell", "Heme::Mature_B_Cell::Burkitt"]),
    (re.compile(r"small_b_cell", re.I), ["Heme::Mature_B_Cell"]),
    (re.compile(r"hodgkin", re.I), ["Heme::Hodgkin_Lymphoma", "Heme::Mature_B_Cell"]),
    (re.compile(r"t_nk", re.I), ["Heme::Mature_T_NK_Cell", "Heme::T_NK_Cell"]),
    (re.compile(r"^heme_sh_aml", re.I), ["Heme::Acute_Myeloid_Leukemia", "Heme::Acute_Leukemia"]),
    (re.compile(r"mds_mpn", re.I), ["Heme::Myelodysplastic", "Heme::Myeloproliferative", "Heme::Myelodysplastic_Myeloproliferative", "Heme::Myeloid_Neoplasms"]),
    (re.compile(r"plasma_cell", re.I), ["Heme::Plasma_Cell_Neoplasm"]),
    (re.compile(r"histiocytic", re.I), ["Heme::Histiocytic_Dendritic_Cell", "Heme::Histiocytic_Dendritic"]),
    (re.compile(r"spleen", re.I), ["Heme::Mature_B_Cell::Splenic", "Heme::Non_Neoplastic", "Heme::Stroma_Derived"]),
    (re.compile(r"reactive", re.I), ["Heme::Non_Neoplastic", "Heme::Tumor_Like", "Heme::Infection"]),
    (re.compile(r"bm_failure|bm_intro|bm_systemic", re.I), ["Heme::Non_Neoplastic", "Heme::Myelodysplastic", "Heme::Stroma_Derived"]),
    (re.compile(r"ia_lpd|immune", re.I), ["Heme::Immune_Deficiency_Associated"]),
    (re.compile(r"pt_lpd|post.?transplant", re.I), ["Heme::Immune_Deficiency_Associated"]),
    (re.compile(r"ihc", re.I), ["Heme::Mature_B_Cell", "Heme::Mature_T_NK_Cell", "Heme::Hodgkin_Lymphoma"]),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lecture_priors(package_id: str) -> list[str]:
    priors: list[str] = []
    for pat, prefs in LECTURE_PRIORS:
        if pat.search(package_id):
            priors.extend(prefs)
    return priors


def is_housekeeping(text: str, start_sec: float, duration: Optional[float]) -> tuple[bool, str]:
    t = text.lower()
    open_cut = 120.0
    if duration and duration > 0:
        open_cut = min(180.0, max(90.0, duration * 0.03))
    if start_sec < open_cut and re.search(
        r"hello|my name is|delighted|society for hematopathology|virtual curriculum|"
        r"listed on this slide|entities that we will|overview|agenda|outline|disclosures",
        t,
    ):
        return True, "agenda_or_overview"
    if duration and start_sec > duration - 90 and re.search(r"thank|attention|questions|wrap", t):
        return True, "closing_summary"
    for pat in DO_NOT_INDEX_PATTERNS:
        if re.search(pat, t):
            return True, "thanks_or_housekeeping"
    if len(re.findall(r"[a-z0-9]+", t)) < 4:
        return True, "too_short"
    return False, ""


def embed_texts(client: OpenAI, texts: list[str], *, batch_size: int = 64) -> np.ndarray:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch, encoding_format="float")
        by_idx = sorted(resp.data, key=lambda d: d.index)
        vectors.extend([d.embedding for d in by_idx])
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return arr / norms


def build_context_texts(rows: list[dict[str, Any]], *, max_chars: int = 700) -> list[str]:
    texts = [(r.get("text") or "").strip() for r in rows]
    out: list[str] = []
    for i, cur in enumerate(texts):
        prev = texts[i - 1] if i > 0 else ""
        nxt = texts[i + 1] if i + 1 < len(texts) else ""
        # Neighbor context improves ASR-crumb semantics without changing segment identity.
        parts = [p for p in (prev, cur, nxt) if p]
        joined = " ".join(parts)
        if len(joined) > max_chars:
            # Keep current centered
            keep = cur
            budget = max_chars - len(keep) - 2
            left = prev[-(budget // 2) :] if prev else ""
            right = nxt[: budget - len(left)] if nxt else ""
            joined = " ".join(p for p in (left, keep, right) if p)
        out.append(joined or cur or " ")
    return out


def apply_prior_bonus(scores: np.ndarray, tags: list[str], priors: list[str], bonus: float = 0.03) -> np.ndarray:
    if not priors:
        return scores
    out = scores.copy()
    for i, tag in enumerate(tags):
        for j, pref in enumerate(priors):
            if tag.startswith(pref):
                out[i] += bonus * (1.0 - 0.15 * j)
                break
    return out


def pick_semantic(
    sims: np.ndarray,
    tags: list[str],
    priors: list[str],
    sticky_tag: Optional[str],
    *,
    min_sim: float,
    sticky_delta: float,
) -> tuple[Optional[str], str, float, float]:
    boosted = apply_prior_bonus(sims, tags, priors)
    best_i = int(np.argmax(boosted))
    best_tag = tags[best_i]
    best_raw = float(sims[best_i])
    best_boosted = float(boosted[best_i])

    sticky_raw = None
    sticky_boosted = None
    if sticky_tag and sticky_tag in tags:
        si = tags.index(sticky_tag)
        sticky_raw = float(sims[si])
        sticky_boosted = float(boosted[si])
        if sticky_boosted >= best_boosted - sticky_delta and sticky_raw >= min_sim - 0.02:
            return sticky_tag, "semantic_sticky_hold", sticky_raw, sticky_boosted

    if best_raw < min_sim:
        return None, "below_similarity_floor", best_raw, best_boosted
    return best_tag, "semantic_best_of_heme", best_raw, best_boosted


def tag_package(
    package_dir: Path,
    *,
    leaf_meta: dict[str, Any],
    leaf_matrix: np.ndarray,
    client: OpenAI,
    out_dir: Optional[Path],
    min_sim: float,
    sticky_delta: float,
) -> dict[str, Any]:
    out_dir = out_dir or package_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    package_id = manifest.get("package_id") or package_dir.name
    priors = lecture_priors(package_id)
    duration = manifest.get("duration_seconds")
    try:
        duration_f = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_f = None

    tags = [leaf["tag"] for leaf in leaf_meta["leaves"]]
    assert all(t.startswith("Heme::") for t in tags)

    rows = [json.loads(ln) for ln in (package_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Embed all segment contexts once
    ctx_texts = build_context_texts(rows)
    seg_matrix = embed_texts(client, ctx_texts)
    # sims: [n_segments, n_leaves]
    sims = seg_matrix @ leaf_matrix.T

    sticky: Optional[str] = None
    by_tag: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    indexable_rows: list[dict[str, Any]] = []
    sim_accepted: list[float] = []

    for i, row in enumerate(rows):
        text = row.get("text") or ""
        start = float(row.get("start_sec") or 0.0)
        hk, reason = is_housekeeping(text, start, duration_f)
        if hk:
            row["indexable"] = False
            row["primary_tag"] = None
            row["entity_name"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = reason
            row["tag_score"] = None
            row["tag_score_boosted"] = None
            reasons[reason] += 1
            if reason in {"agenda_or_overview", "thanks_or_housekeeping", "closing_summary"}:
                sticky = None
            continue

        tag, basis, raw, boosted = pick_semantic(
            sims[i], tags, priors, sticky, min_sim=min_sim, sticky_delta=sticky_delta
        )
        if not tag:
            row["indexable"] = False
            row["primary_tag"] = None
            row["entity_name"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = basis
            row["tag_score"] = round(raw, 4)
            row["tag_score_boosted"] = round(boosted, 4)
            reasons[basis] += 1
            continue

        row["indexable"] = True
        row["primary_tag"] = tag
        row["entity_name"] = tag.split("::")[-1]
        row["tag_status"] = "semantic_heme_browse_v0_1"
        row["tag_basis"] = basis
        row["tag_score"] = round(raw, 4)
        row["tag_score_boosted"] = round(boosted, 4)
        sticky = tag
        by_tag[tag] += 1
        sim_accepted.append(raw)
        indexable_rows.append(row)

    # frames: embed transcript_context alone
    frames_path = package_dir / "frames.jsonl"
    frames: list[dict[str, Any]] = []
    if frames_path.is_file():
        frames = [json.loads(ln) for ln in frames_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        ftexts = [(fr.get("transcript_context") or " ").strip() or " " for fr in frames]
        if ftexts:
            fmat = embed_texts(client, ftexts)
            fsims = fmat @ leaf_matrix.T
            for fr, srow in zip(frames, fsims):
                tag, basis, raw, boosted = pick_semantic(
                    srow, tags, priors, None, min_sim=min_sim, sticky_delta=sticky_delta
                )
                if tag:
                    fr["primary_tag"] = tag
                    fr["indexable"] = True
                    fr["tag_status"] = "semantic_heme_browse_v0_1"
                    fr["tag_basis"] = basis
                    fr["tag_score"] = round(raw, 4)
                    fr["tag_score_boosted"] = round(boosted, 4)
                else:
                    fr["primary_tag"] = None
                    fr["indexable"] = False
                    fr["tag_status"] = "below_similarity_floor"
                    fr["tag_basis"] = basis
                    fr["tag_score"] = round(raw, 4)
                    fr["tag_score_boosted"] = round(boosted, 4)

    counts = dict(manifest.get("counts") or {})
    counts.update(
        {
            "segments_total": len(rows),
            "segments_indexable": len(indexable_rows),
            "segments_do_not_index": len(rows) - len(indexable_rows),
            "frames_total": len(frames),
            "frames_indexable": sum(1 for f in frames if f.get("indexable")),
            "by_tag": dict(by_tag.most_common()),
            "do_not_index_reasons": dict(reasons),
            "heme_leaf_universe": len(tags),
            "semantic_similarity_mean": round(float(np.mean(sim_accepted)), 4) if sim_accepted else None,
            "semantic_similarity_median": round(float(np.median(sim_accepted)), 4) if sim_accepted else None,
            "semantic_min_sim": min_sim,
        }
    )
    manifest["counts"] = counts
    manifest["tagging"] = {
        "method": "semantic_best_of_canonical_Heme_browse_leaves_v0_1",
        "embedding_model": EMBEDDING_MODEL,
        "heme_leaf_count": len(tags),
        "lecture_priors": priors,
        "min_similarity": min_sim,
        "sticky_delta": sticky_delta,
        "created_at_utc": utc_now(),
    }
    limitations = [
        x
        for x in (manifest.get("known_limitations") or [])
        if "heuristic" not in x.lower() and "primary_tag chosen as best-matching" not in x
    ]
    limitations.insert(
        0,
        "primary_tag = cosine best match among canonical Heme::* browse leaf embeddings "
        f"({len(tags)} leaves, {EMBEDDING_MODEL}); soft lecture prior + sticky hold only.",
    )
    manifest["known_limitations"] = limitations

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "segments.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "segments_indexable.jsonl").open("w", encoding="utf-8") as f:
        for row in indexable_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if frames:
        with (out_dir / "frames.jsonl").open("w", encoding="utf-8") as f:
            for fr in frames:
                f.write(json.dumps(fr, ensure_ascii=False) + "\n")

    audit = {
        "schema_version": "lecture_deck_heme_browse_semantic_tag_audit.v0_1",
        "created_at_utc": utc_now(),
        "package_id": package_id,
        "input_paths": [str(package_dir / "segments.jsonl"), str(package_dir / "manifest.json")],
        "output_paths": [
            str(out_dir / "manifest.json"),
            str(out_dir / "segments.jsonl"),
            str(out_dir / "segments_indexable.jsonl"),
        ],
        "counts": counts,
        "lecture_priors": priors,
        "embedding_model": EMBEDDING_MODEL,
        "min_similarity": min_sim,
        "known_limitations": [
            "Semantic cosine over leaf embed texts — not human gold labels.",
            "ASR crumbs use neighbor context window for embedding only.",
            "Do not vectorize segments_*.jsonl; consolidate to chunks_indexable.jsonl.",
        ],
    }
    (out_dir / "tag_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument(
        "--leaf-dir",
        type=Path,
        default=Path("outputs/heme_browse_leaf_embeddings_v0_1"),
    )
    p.add_argument("--min-sim", type=float, default=0.38)
    p.add_argument("--sticky-delta", type=float, default=0.025)
    args = p.parse_args()

    meta = json.loads((args.leaf_dir / "heme_leaf_embeddings_meta.json").read_text(encoding="utf-8"))
    matrix = np.load(args.leaf_dir / "heme_leaf_embeddings.npy")
    if matrix.shape[0] != len(meta["leaves"]):
        raise SystemExit("leaf embedding rows != meta leaves")

    client = OpenAI()
    audit = tag_package(
        args.package_dir,
        leaf_meta=meta,
        leaf_matrix=matrix,
        client=client,
        out_dir=args.out_dir,
        min_sim=args.min_sim,
        sticky_delta=args.sticky_delta,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "package_id": audit["package_id"],
                "method": "semantic_best_of_heme",
                "segments_indexable": audit["counts"]["segments_indexable"],
                "sim_median": audit["counts"].get("semantic_similarity_median"),
                "top_tags": list(audit["counts"]["by_tag"].items())[:8],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
