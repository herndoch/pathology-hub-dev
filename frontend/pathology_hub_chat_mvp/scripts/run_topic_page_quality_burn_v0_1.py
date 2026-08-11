#!/usr/bin/env python3
"""Aggressive topic-page quality burn (v0_1).

Combines:
  1) Free structural scoring (score_topic_page_quality_v0_1)
  2) High-parallel LLM pathologist reviews across gpt-5.6-{luna,terra,sol}
  3) Dual-model disagreement pass on high-risk / needs_fixes pages
  4) Optional continuous pickup of newly written wild-prebuild pages
  5) Repair queue JSON for pages blocked / needs_fixes / poor structural band

Writes:
  - outputs/chat_mvp_topic_prepop_v0_1/pages/*.quality.json
  - outputs/chat_mvp_topic_prepop_v0_1/pages/*.review.json
  - outputs/.../topic_page_quality_burn_audit_v0_1.json
  - audits/topic_page_quality_burn_v0_1/quality_burn_audit_v0_1.json (repo-tracked summary)
  - outputs/.../topic_page_quality_repair_queue_v0_1.json

Examples:
  # Structural + 200 LLM reviews, 12 workers, round-robin 3 models
  python3 scripts/run_topic_page_quality_burn_v0_1.py --llm-limit 200 --parallel 12

  # Go ham: review everything not yet reviewed, keep scanning for new pages
  python3 scripts/run_topic_page_quality_burn_v0_1.py --llm-limit 0 --parallel 16 --continuous --continuous-minutes 180
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_DIR = SCRIPT_DIR.parent
REPO_ROOT = MVP_DIR.parents[1]
if str(MVP_DIR) not in sys.path:
    sys.path.insert(0, str(MVP_DIR))

import prompts  # noqa: E402
from openai_synthesizer import SUPPORTED_SYNTHESIS_MODELS, synthesize  # noqa: E402

# Reuse helpers from sibling scripts
sys.path.insert(0, str(SCRIPT_DIR))
from pathologist_review_topic_pages_v0_1 import (  # noqa: E402
    _parse_verdict,
    _slim_evidence_for_review,
)
from score_topic_page_quality_v0_1 import score_page  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT = OUTPUT_DIR / "topic_page_quality_burn_audit_v0_1.json"
AUDITS_COPY = REPO_ROOT / "audits/topic_page_quality_burn_v0_1/quality_burn_audit_v0_1.json"
REPAIR_QUEUE = OUTPUT_DIR / "topic_page_quality_repair_queue_v0_1.json"
BURN_SCHEMA = "topic_page_quality_burn_audit_v0_1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page_paths(pages_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in pages_dir.glob("*.json")
        if not p.name.endswith(".review.json")
        and not p.name.endswith(".quality.json")
        and not p.name.endswith(".review2.json")
        and p.name != "index.json"
    )


def _load(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def run_structural(pages_dir: Path, only_missing: bool) -> dict[str, Any]:
    paths = _page_paths(pages_dir)
    scored = 0
    bands: Counter[str] = Counter()
    high = 0
    for path in paths:
        side = path.parent / f"{path.stem}.quality.json"
        if only_missing and side.exists():
            q = _load(side)
            if q:
                bands[str(q.get("band") or "?")] += 1
                if q.get("priority_for_llm_review") == "high":
                    high += 1
            continue
        page = _load(path)
        if not page:
            continue
        q = score_page(page)
        q["page_json"] = _rel(path)
        side.write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        bands[q["band"]] += 1
        if q.get("priority_for_llm_review") == "high":
            high += 1
        scored += 1
    return {
        "pages_seen": len(paths),
        "newly_scored": scored,
        "bands": dict(bands),
        "high_priority": high,
    }


def _pick_review_targets(
    pages_dir: Path,
    llm_limit: Optional[int],
    prefer_high: bool,
    skip_reviewed: bool,
) -> list[Path]:
    paths = _page_paths(pages_dir)
    scored: list[tuple[int, Path]] = []
    for path in paths:
        if skip_reviewed and (path.parent / f"{path.stem}.review.json").exists():
            continue
        page = _load(path)
        if not page or not page.get("answer_markdown"):
            continue
        q = _load(path.parent / f"{path.stem}.quality.json") or score_page(page)
        # lower score = earlier; high priority first
        pri = 0 if q.get("priority_for_llm_review") == "high" else 1
        if not prefer_high:
            pri = 0
        scored.append((pri * 1000 + int(q.get("score") or 100), path))
    scored.sort(key=lambda t: t[0])
    out = [p for _, p in scored]
    if llm_limit is not None and llm_limit > 0:
        out = out[:llm_limit]
    return out


def _hostile_editor_prompt() -> str:
    return (
        "You are a hostile journal editor + board-certified anatomic pathologist tearing apart "
        "a draft ExpertPath-style topic page. You are NOT rewriting it.\n"
        "Use ONLY the draft + evidence JSON. Invent nothing.\n\n"
        "Hunt specifically for:\n"
        "- Claims not supported by any card excerpt\n"
        "- Wrong figure modality placement (gross/micro/cyto/imaging/IHC)\n"
        "- Missing Key Literature when literature cards exist\n"
        "- Textbook/WHO/PathOut cards present but unused\n"
        "- DDx table weak/missing despite rich evidence\n"
        "- Off-topic literature (wrong organ/system)\n"
        "- Citation labels that don't match the cited card\n\n"
        "OUTPUT EXACTLY:\n"
        "## Verdict\n"
        "- One of: `ready_for_human_review` | `needs_fixes` | `blocked_thin_evidence`\n"
        "- One short sentence why.\n\n"
        "## Fatal issues\n"
        "- Bullets (or `None`).\n\n"
        "## Evidence mismatches\n"
        "- Bullets naming the unsupported claim or misplaced figure (or `None`).\n\n"
        "## Must-fix before publish\n"
        "- 0–7 concrete edits (or `None`).\n"
        "Keep under ~35 bullets. No HTML."
    )


def _review_one(
    path: Path,
    model: str,
    mode: str = "pathologist",
    out_suffix: str = ".review.json",
) -> dict[str, Any]:
    page = _load(path)
    if not page:
        return {"ok": False, "tag": path.stem, "error": "unreadable", "model": model, "mode": mode}
    tag = page.get("tag") or path.stem
    label = page.get("label") or tag
    if not page.get("answer_markdown"):
        return {
            "ok": False,
            "tag": tag,
            "label": label,
            "error": "no_answer_markdown",
            "model": model,
            "mode": mode,
        }

    bundle = _slim_evidence_for_review(page)
    system = (
        prompts.pathologist_page_review_system_prompt()
        if mode == "pathologist"
        else _hostile_editor_prompt()
    )
    user_q = (
        f"Review the draft topic page for: {label}"
        if mode == "pathologist"
        else f"Hostile edit pass for: {label}"
    )
    result = synthesize(system, user_q, bundle, model=model)
    review = {
        "schema_version": (
            "topic_page_pathologist_review_v0_1"
            if mode == "pathologist"
            else "topic_page_hostile_editor_review_v0_1"
        ),
        "tag": tag,
        "label": label,
        "page_json": _rel(path),
        "generated_at": _utcnow(),
        "ok": bool(result.ok),
        "model": result.model,
        "mode": mode,
        "verdict": _parse_verdict(result.text) if result.ok else None,
        "review_markdown": result.text if result.ok else "",
        "error": result.error,
        "known_limitations": [
            "Advisory LLM critique only — not a human pathologist sign-off.",
            "Does not mutate the prebuild page JSON/markdown.",
        ],
    }
    out_path = path.parent / f"{path.stem}{out_suffix}"
    out_path.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "ok": review["ok"],
        "tag": tag,
        "label": label,
        "verdict": review.get("verdict"),
        "model": review.get("model"),
        "mode": mode,
        "page_path": _rel(path),
        "review_path": _rel(out_path),
        "error": review.get("error"),
    }


def run_llm_reviews(
    targets: list[Path],
    parallel: int,
    models: list[str],
    dual_on_bad: bool,
) -> list[dict[str, Any]]:
    if not targets:
        return []
    workers = max(1, min(parallel, 24))
    results: list[dict[str, Any]] = []
    # round-robin models
    jobs: list[tuple[Path, str, str, str]] = []
    for i, path in enumerate(targets):
        model = models[i % len(models)]
        jobs.append((path, model, "pathologist", ".review.json"))

    print(f"[llm] reviewing {len(jobs)} pages with {workers} workers; models={models}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(_review_one, path, model, mode, suffix): (path, model)
            for path, model, mode, suffix in jobs
        }
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 10 == 0 or done == len(jobs):
                v = Counter(x.get("verdict") or ("error" if not x.get("ok") else "?") for x in results)
                print(f"[llm] {done}/{len(jobs)} {dict(v)}", flush=True)

    if dual_on_bad:
        dual_targets = [
            Path(REPO_ROOT / r["page_path"])
            for r in results
            if r.get("verdict") in {"needs_fixes", "blocked_thin_evidence"}
            and r.get("page_path")
        ]
        # also dual-review structural high-priority that somehow got ready
        dual_jobs = []
        for i, path in enumerate(dual_targets):
            if not path.exists():
                # page_path may already be absolute-ish
                alt = PAGES_DIR / path.name
                path = alt if alt.exists() else path
            if not path.exists():
                continue
            # pick a different model than first review when possible
            first = _load(path.parent / f"{path.stem}.review.json") or {}
            used = first.get("model")
            alt_models = [m for m in models if m != used] or models
            dual_jobs.append((path, alt_models[i % len(alt_models)], "hostile", ".review2.json"))

        if dual_jobs:
            print(f"[llm-dual] hostile second pass on {len(dual_jobs)} pages", flush=True)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(_review_one, path, model, mode, suffix): path
                    for path, model, mode, suffix in dual_jobs
                }
                for fut in as_completed(futs):
                    results.append(fut.result())

    return results


def build_repair_queue(pages_dir: Path) -> dict[str, Any]:
    items = []
    for path in _page_paths(pages_dir):
        q = _load(path.parent / f"{path.stem}.quality.json") or {}
        r1 = _load(path.parent / f"{path.stem}.review.json") or {}
        r2 = _load(path.parent / f"{path.stem}.review2.json") or {}
        reasons = []
        if q.get("band") == "poor":
            reasons.append(f"structural_poor:{q.get('score')}")
        for f in q.get("flags") or []:
            if f.startswith("missing_") or f in {
                "not_ok_or_empty_answer",
                "abstract_filler_phrase",
                "double_paren_book_chip",
                "many_unmatched_urls",
            }:
                reasons.append(f"flag:{f}")
        for rev, name in ((r1, "review"), (r2, "review2")):
            if rev.get("verdict") in {"needs_fixes", "blocked_thin_evidence"}:
                reasons.append(f"{name}:{rev.get('verdict')}:{rev.get('model')}")
        if not reasons:
            continue
        page = _load(path) or {}
        items.append(
            {
                "tag": page.get("tag") or path.stem,
                "label": page.get("label"),
                "page_json": _rel(path),
                "structural_score": q.get("score"),
                "structural_band": q.get("band"),
                "verdict": r1.get("verdict"),
                "verdict2": r2.get("verdict"),
                "reasons": reasons,
                "priority": (
                    0
                    if any("blocked" in x or "poor" in x for x in reasons)
                    else 1
                ),
            }
        )
    items.sort(key=lambda x: (x["priority"], x.get("structural_score") or 999))
    queue = {
        "schema_version": "topic_page_quality_repair_queue_v0_1",
        "generated_at": _utcnow(),
        "counts": {"n": len(items)},
        "items": items,
        "known_limitations": [
            "Queue is advisory; rebuild via prebuild_topic_pages_pilot_v0_1.py.",
            "Does not delete prior pages — rewrite sidecars only.",
        ],
    }
    REPAIR_QUEUE.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return queue


def write_audit(
    structural: dict[str, Any],
    llm_results: list[dict[str, Any]],
    repair_n: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    verdicts: Counter[str] = Counter()
    models: Counter[str] = Counter()
    for r in llm_results:
        verdicts[str(r.get("verdict") or ("error" if not r.get("ok") else "?"))] += 1
        if r.get("model"):
            models[str(r["model"])] += 1
    audit = {
        "schema_version": BURN_SCHEMA,
        "generated_at": _utcnow(),
        "input_paths": [_rel(args.pages_dir)],
        "output_paths": [_rel(Path(args.audit_out)), _rel(AUDITS_COPY), _rel(REPAIR_QUEUE)],
        "counts": {
            "structural": structural,
            "llm_reviews": len(llm_results),
            "llm_ok": sum(1 for r in llm_results if r.get("ok")),
            "verdicts": dict(verdicts),
            "models": dict(models),
            "repair_queue_n": repair_n,
        },
        "sample_bad": [
            r
            for r in llm_results
            if r.get("verdict") in {"needs_fixes", "blocked_thin_evidence"} or not r.get("ok")
        ][:40],
        "known_limitations": [
            "LLM advisory only — not human pathologist sign-off.",
            "Structural scores are heuristic.",
            "Per-page review sidecars live under outputs/ (gitignored); summary audit copied to audits/.",
        ],
    }
    Path(args.audit_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.audit_out).write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDITS_COPY.parent.mkdir(parents=True, exist_ok=True)
    # slim tracked copy (no huge sample if needed — keep sample_bad)
    AUDITS_COPY.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    ap.add_argument("--llm-limit", type=int, default=250, help="0 = all unscored/unreviewed targets")
    ap.add_argument("--parallel", type=int, default=12)
    ap.add_argument(
        "--models",
        default=",".join(SUPPORTED_SYNTHESIS_MODELS),
        help="Comma-separated synthesis models for round-robin",
    )
    ap.add_argument("--skip-structural", action="store_true")
    ap.add_argument("--structural-only", action="store_true")
    ap.add_argument("--rescore-all", action="store_true")
    ap.add_argument("--no-dual", action="store_true")
    ap.add_argument("--continuous", action="store_true")
    ap.add_argument("--continuous-minutes", type=int, default=120)
    ap.add_argument("--continuous-sleep-s", type=int, default=45)
    ap.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--shuffle-within-band", action="store_true")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for m in models:
        if m not in SUPPORTED_SYNTHESIS_MODELS:
            raise SystemExit(f"Unsupported model {m}; allowlist={SUPPORTED_SYNTHESIS_MODELS}")

    all_llm: list[dict[str, Any]] = []
    deadline = time.time() + (args.continuous_minutes * 60 if args.continuous else 0)

    while True:
        structural = {"skipped": True}
        if not args.skip_structural:
            print("[structural] scoring…", flush=True)
            structural = run_structural(args.pages_dir, only_missing=not args.rescore_all)
            print(json.dumps(structural, indent=2), flush=True)

        if args.structural_only:
            queue = build_repair_queue(args.pages_dir)
            audit = write_audit(structural, all_llm, queue["counts"]["n"], args)
            print(json.dumps(audit["counts"], indent=2))
            return

        limit = None if args.llm_limit == 0 else args.llm_limit
        targets = _pick_review_targets(
            args.pages_dir,
            llm_limit=limit,
            prefer_high=True,
            skip_reviewed=True,
        )
        if args.shuffle_within_band:
            random.shuffle(targets)

        if not targets:
            print("[llm] no unreviewed targets", flush=True)
            if not args.continuous:
                break
        else:
            # In continuous mode, chew a chunk each loop so new pages get scored too
            chunk = targets if not args.continuous else targets[: max(20, args.parallel * 4)]
            batch = run_llm_reviews(
                chunk,
                parallel=args.parallel,
                models=models,
                dual_on_bad=not args.no_dual,
            )
            all_llm.extend(batch)

        queue = build_repair_queue(args.pages_dir)
        audit = write_audit(structural, all_llm, queue["counts"]["n"], args)
        print(
            f"[audit] llm_total={len(all_llm)} repair_queue={queue['counts']['n']} "
            f"verdicts={audit['counts'].get('verdicts')}",
            flush=True,
        )

        if not args.continuous:
            break
        if time.time() >= deadline:
            print("[continuous] deadline reached", flush=True)
            break
        time.sleep(max(5, args.continuous_sleep_s))

    print(f"Audit: {args.audit_out}")
    print(f"Tracked copy: {AUDITS_COPY}")
    print(f"Repair queue: {REPAIR_QUEUE}")


if __name__ == "__main__":
    main()
