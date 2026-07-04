# Codex Next Actions

## 0. Set up local environment

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project pathology-annotation-project
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp scripts/.env.example .env
# edit .env with PATHOLOGY_HUB_API_KEY and optional OPENAI_API_KEY
```

## 1. Verify current journal live state

```bash
python scripts/gcs_journal_manifest_probe.py
python scripts/api_probe_journal.py --query "<exact Virchows title>" --require-journal "Virchows Archiv"
```

## 2. If Virchows API proof fails

Inspect backend search/fusion before adding Histopathology. Look specifically for:

- whether vector search is called for journals;
- whether journal FAISS/docstore load uses latest GCS paths;
- whether result formatter preserves `journal` from vector docstore;
- whether FTS-only results dominate RRF.

## 3. Inventory Histopathology

```bash
python scripts/histopathology_inventory.py
```

## 4. Plan Histopathology append

Use v4.4 retry/resume logic as template. Add `journals_batches/histopathology/journal_chunks.jsonl` as a candidate source. Do not embed until duplicate detection and API proof strategy are ready.

## 5. Tag governance follow-up

Do not resume curriculum/tag work until journal verification is complete, unless user explicitly switches workstreams. If resumed, use `docs/TAG_GOVERNANCE_CURRICULUM_HANDOFF.md`.
