# Prompt for Next ChatGPT Conversation Guiding Local Codex

You are helping me work locally in VS Code/Codex on Pathology Hub. Use the attached handoff packet as source truth.

Task focus:
- Evidence/Lesson/Research RAG only.
- Implement/use governed curriculum tags.
- Add real tag-aware retrieval to existing one-action `searchEvidence` API.
- Preserve current v1.5.8 compatibility.

Important facts:
- Live API uses `POST /evidence/search` with header `X-API-Key`.
- Working key value is Colab `HUB_API` / GCP Secret Manager `pathology-hub-api-key`; old Colab `X-API-Key` and `PATHOLOGY_HUB_API_KEY` were stale.
- Governed cleanup v10.5 is promoted and API-proven for standard searches: 200/200/200 with 0 forbidden artifact primary-tags.
- Explicit tag browse/search-by-tag is not proven live yet.
- WHO tag-bearing processed files are under `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json`.
- PathOut tags are auto-approved local curriculum tags.
- Lecture/textbook generated artifact tags should not appear in visible tag surfaces.

Read `README_START_HERE.md`, `docs/00_MASTER_HANDOFF_FOR_CODEX.md`, `docs/04_LOCAL_VSCODE_CODEX_RUNBOOK.md`, and `docs/05_BACKEND_TAG_RUNTIME_IMPLEMENTATION_PLAN.md`, then help me set up local repo/tasks and write/refactor code safely.
