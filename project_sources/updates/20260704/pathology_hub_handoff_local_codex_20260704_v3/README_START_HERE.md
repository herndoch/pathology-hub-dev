# Pathology Hub — Local Codex Handoff Packet v3

Generated: 2026-07-04T18:47:04+00:00

This packet is for starting local work in VS Code + Codex. It is intentionally explicit about what is **live**, what is only **normalized/staged**, and what still needs proof.

## Read in this order

1. `docs/MASTER_HANDOFF_PACKET_20260704_FINAL.md`
2. `docs/JOURNAL_V4_4_STATE_AND_VERIFICATION.md`
3. `docs/HISTOPATHOLOGY_NEXT_STEP_PLAN.md`
4. `docs/API_BACKEND_DEBUG_NOTES.md`
5. `docs/CODEX_NEXT_ACTIONS.md`
6. `codex/CODEX_AGENT_PROMPT.md`

## Critical current state

- API remains one GPT Action: `searchEvidence` / `POST /evidence/search`.
- Journal v4.4 vector union was promoted by audit: **129,209 journal rows** = Modern Pathology + AJSP + Virchows Archiv.
- Histopathology has been located at `gs://pathology_hub/02_normalized/journals_batches/histopathology/`, but is **not yet added** to the live vector/docstore.
- The built-in v4.4 API proof JSON is defective because the script forgot to import `requests`.
- User manual health proof shows live manifest record count 129,209, but broad Virchows queries still returned AJSP FTS-only hits. Codex must run targeted API probes before claiming Virchows API retrieval works.
- Tag governance/curriculum policy decisions are recorded here, but v11 curriculum hardening should not be treated as live until its own run/audit ZIP is produced.

## Included evidence

- `evidence/JOURNAL_UNION_V4_4_AUDITS_ONLY.zip` — small audit ZIP, not the 1.5GB output ZIP.
- Extracted JSON audits under `evidence/journal_v4_4_audits/`.
- `logs/latest_colab_log_and_histopathology_locator.txt` — latest Colab log including Histopathology locator output.
- `packages/pathology_hub_journal_union_vector_rebuild_v4_4_retry_resume_package.zip` — last journal v4.4 notebook/script package.

## Not included

- Huge journal embeddings/FAISS/docstore artifacts. Retrieve them from GCS only if needed.
