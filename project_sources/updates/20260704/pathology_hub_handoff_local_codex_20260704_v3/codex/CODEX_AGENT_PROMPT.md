# Codex Agent Prompt — Pathology Hub Local Work

You are working on Pathology Hub, a multi-workstream pathology assistant. Treat the Master Project Spine as canonical if supplied. This handoff is an operational addendum from a long ChatGPT workstream.

Immediate task focus: **Journal Evidence RAG verification and Histopathology integration planning**.

Rules:

1. Use one API endpoint for GPT-facing search: `POST /evidence/search` with `X-API-Key`.
2. Do not claim a source is indexed/vectorized/API-exposed unless manifest/audit/API proof supports it.
3. Keep Evidence RAG, report-style RAG, gross templates, HTML rendering, backend API, and Custom GPT frontend separate.
4. Before writing rebuild code, inspect existing GCS artifacts and audits.
5. Do not download giant artifacts unless necessary; prefer manifest/audit/sample probes.
6. Do not add Histopathology until v4.4 Virchows API behavior is verified or backend ranking issue is understood.
7. If adding Histopathology, use v4.4 retry/resume embedding logic; write clear backups, staging, audits, and API proof.

Start by reading:

- `docs/MASTER_HANDOFF_PACKET_20260704_FINAL.md`
- `docs/JOURNAL_V4_4_STATE_AND_VERIFICATION.md`
- `docs/HISTOPATHOLOGY_NEXT_STEP_PLAN.md`
- `docs/API_BACKEND_DEBUG_NOTES.md`
- `docs/DO_NOT_DO.md`

Then run:

```bash
python scripts/gcs_journal_manifest_probe.py
python scripts/api_probe_journal.py --query "<exact Virchows title or DOI>" --require-journal "Virchows Archiv"
python scripts/histopathology_inventory.py
```
