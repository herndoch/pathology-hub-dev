#!/usr/bin/env python3
"""A/B OPENAI_MODEL candidates for topic-page synthesis (G16).

Starts a ephemeral uvicorn subprocess per model, runs fixed entity probes via
POST /api/chat (mode=topic_page), records timing + section presence, writes audit.

Does NOT overwrite prebuilt pages in outputs/.../pages/.

Usage:
    python3 scripts/model_ab_topic_synthesis_v0_1.py
    python3 scripts/model_ab_topic_synthesis_v0_1.py --models gpt-4.1-mini gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

MVP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MVP_DIR.parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
AUDIT_PATH = OUTPUT_DIR / "model_ab_topic_synthesis_v0_1.json"

DEFAULT_MODELS = ("gpt-4.1-mini", "gpt-4o-mini", "gpt-4o", "gpt-4.1")
DEFAULT_PORT = 8011

ENTITIES = [
    {
        "key": "middle_ear_scc",
        "tag": "HN::Ear::Middle_Ear_Squamous_Cell_Carcinoma",
        "label": "Middle Ear SCC",
        "query": "middle ear squamous cell carcinoma",
        "category_context": "Head & Neck > Ear",
    },
    {
        "key": "gct_bone",
        "tag": "BST::Bone::Giant_Cell::Intermediate::Giant_Cell_Tumor_Of_Bone",
        "label": "GCT of Bone",
        "query": "giant cell tumor of bone",
        "category_context": "Bone & Soft Tissue > Bone",
    },
    {
        "key": "jgcgt",
        "tag": "GYN::Ovary::Neoplastic::Sex_Cord_Stromal::Malignant::Juvenile_Granulosa_Cell_Tumor",
        "label": "Juvenile Granulosa Cell Tumor",
        "query": "juvenile granulosa cell tumor ovary",
        "category_context": "Gynecologic > Ovary",
    },
]

REQUIRED_SECTIONS = (
    "Key Facts",
    "Microscopic",
    "Differential Diagnosis",
)


def _wait_health(base_url: str, timeout_s: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last_err = ""
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{base_url}/api/health", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException as exc:
            last_err = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Server not healthy at {base_url}: {last_err}")


def _section_hits(answer: str) -> dict[str, bool]:
    return {sec: bool(re.search(rf"##\s*{re.escape(sec)}\b", answer, re.I)) for sec in REQUIRED_SECTIONS}


def _run_entity(base_url: str, entity: dict, timeout_s: int) -> dict:
    payload = {
        "query": entity["query"],
        "mode": "topic_page",
        "category_context": entity["category_context"],
        "page_tag": entity["tag"],
        "include_figures": False,
        "max_figures": 0,
    }
    started = time.monotonic()
    resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout_s)
    elapsed_s = round(time.monotonic() - started, 1)
    resp.raise_for_status()
    body = resp.json()
    answer = body.get("answer") or ""
    debug = body.get("debug") or {}
    return {
        "ok": bool(body.get("ok")) and bool(answer),
        "elapsed_s": elapsed_s,
        "model_reported": body.get("model"),
        "answer_chars": len(answer),
        "sections_present": _section_hits(answer),
        "cards": len(body.get("cards") or []),
        "variant_timing_ms": sum(v.get("elapsed_ms", 0) for v in (debug.get("variant_timing") or [])),
        "error": body.get("error") or body.get("answer_error"),
    }


def _score_run(run: dict) -> float:
    if not run.get("ok"):
        return -1.0
    sections = run.get("sections_present") or {}
    section_score = sum(1 for v in sections.values() if v)
    # Prefer complete sections with lower elapsed time
    return section_score * 1000 - float(run.get("elapsed_s") or 9999)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--entities", nargs="+", default=[e["key"] for e in ENTITIES])
    args = parser.parse_args()

    entity_map = {e["key"]: e for e in ENTITIES}
    entities = [entity_map[k] for k in args.entities if k in entity_map]
    if not entities:
        raise SystemExit("No valid entities selected.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"
    venv_python = MVP_DIR / ".venv/bin/python"
    python = str(venv_python if venv_python.exists() else sys.executable)

    model_results: list[dict] = []

    for model in args.models:
        print(f"\n=== Model: {model} ===")
        env = os.environ.copy()
        env["OPENAI_MODEL"] = model
        env["PORT"] = str(args.port)
        proc = subprocess.Popen(
            [python, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=str(MVP_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            health = _wait_health(base_url)
            if not (health.get("secrets") or {}).get("openai", {}).get("present"):
                print(f"  SKIP {model}: OPENAI_API_KEY not present")
                model_results.append({"model": model, "skipped": True, "reason": "no_openai_key"})
                continue

            runs: list[dict] = []
            for entity in entities:
                print(f"  {entity['label']}...", flush=True)
                try:
                    run = _run_entity(base_url, entity, args.timeout_s)
                    run["entity_key"] = entity["key"]
                    run["label"] = entity["label"]
                    runs.append(run)
                    print(
                        f"    ok={run['ok']} {run['elapsed_s']}s "
                        f"sections={sum(run['sections_present'].values())}/{len(REQUIRED_SECTIONS)}"
                    )
                except Exception as exc:  # noqa: BLE001
                    runs.append(
                        {
                            "entity_key": entity["key"],
                            "label": entity["label"],
                            "ok": False,
                            "error": str(exc),
                        }
                    )
                    print(f"    FAILED: {exc}")

            scores = [_score_run(r) for r in runs if not r.get("skipped")]
            avg_elapsed = round(
                sum(r.get("elapsed_s", 0) for r in runs if r.get("ok")) / max(1, sum(1 for r in runs if r.get("ok"))),
                1,
            )
            model_results.append(
                {
                    "model": model,
                    "health_openai_model": health.get("openai_model"),
                    "avg_elapsed_s": avg_elapsed,
                    "runs": runs,
                    "score": round(sum(scores) / max(1, len(scores)), 1),
                }
            )
        finally:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)

    # Pick winner among non-skipped models with all sections on majority of runs
    candidates = [m for m in model_results if not m.get("skipped") and m.get("runs")]
    winner = None
    if candidates:
        winner = max(candidates, key=lambda m: (m.get("score", -1), -m.get("avg_elapsed_s", 9999)))

    audit = {
        "schema_version": "model_ab_topic_synthesis_v0_1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_paths": ["POST /api/chat mode=topic_page"],
        "output_paths": [str(AUDIT_PATH.relative_to(REPO_ROOT))],
        "models_tested": args.models,
        "entities_tested": [e["key"] for e in entities],
        "required_sections": list(REQUIRED_SECTIONS),
        "results": model_results,
        "recommended_model": winner.get("model") if winner else None,
        "known_limitations": [
            "Single-run per model/entity; variance can be large.",
            "Models must be enabled on the OpenAI account; failures recorded per run.",
            "Quality scoring is heuristic (section headers + latency); human review advised.",
        ],
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {AUDIT_PATH}")
    if winner:
        print(f"Recommended OPENAI_MODEL: {winner['model']} (avg {winner.get('avg_elapsed_s')}s)")


if __name__ == "__main__":
    main()
