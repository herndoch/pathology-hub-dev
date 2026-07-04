# Curriculum Map Readiness Audit v0 - Phase 0 Source Review

Generated: 2026-07-04

## Scope

This is a local read-only source review for the Evidence/Lesson/Research RAG curriculum mapping and tag governance workstream. It is a confidence audit only, not a live promotion.

No GCS commands were run during Phase 0. No GCS objects were uploaded, modified, downloaded, or promoted.

## Local sources reviewed

- `AGENTS.md`
- `prompts/curriculum_map_readiness_v0.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/00_MASTER_HANDOFF_FOR_CODEX.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/01_LIVE_STATE_AND_PROOF.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/03_GCS_PATHS_AND_OBJECTS.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/06_TAG_POLICY_AND_GOVERNANCE.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/07_CURRICULUM_MAPPING_STRATEGY_AND_V11.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/support/CURRENT_STATUS_MACHINE_READABLE.json`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/support/GCS_PATH_REGISTRY.csv`
- `project_sources/updates/20260704/pathology_hub_handoff_local_codex_20260704_v3/CURRENT_STATE_MACHINE_READABLE.json`
- `project_sources/updates/20260704/pathology_hub_handoff_local_codex_20260704_v3/docs/DO_NOT_DO.md`
- `project_sources/updates/20260704/pathology_hub_handoff_local_codex_20260704_v3/docs/TAG_GOVERNANCE_CURRICULUM_HANDOFF.md`

## Current project truth from local handoff

- Canonical project: `pathology-annotation-project`.
- Canonical buckets: `gs://pathology_hub` and legacy/source `gs://pathology-hub-0`.
- Workstreams must stay separate; this review is only for Evidence/Lesson/Research RAG curriculum mapping and tag governance.
- One live GPT/API Action is documented: `searchEvidence` / `POST /evidence/search`.
- Current proven live API contract remains `evidence_search_response.v1.5.8`; health/service evidence in the handoff also points to v1.5.8.
- Tag-aware API schemas and tag-browse behavior are draft/reference only unless backed by live health/API proof.
- v10.5 governed cleanup is documented as promoted with a later valid v10.5.2 API proof showing HTTP 200 responses and forbidden primary-tag count 0 for representative searches.
- The valid v10.5.2 proof path is documented as `gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json`.
- v10.5 proof does not prove a fully tag-aware browse API is live.
- v11 curriculum hardening notebook/package exists locally in the handoff, but local docs explicitly say it was generated and not run/proven. It must not be marked live without output ZIP/audit/health/API proof.

## Governance policy to preserve

- ABPath tags are gold/source-truth.
- WHO processed rows under `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json` are tag-bearing source rows; WHO tags should map to ABPath only when fuzzy match is high confidence, with handoff policy using score >= 90.
- PathOut AP-diagnostic local tags are generally useful and can be auto-approved as local curriculum tags unless obvious junk/root-error is found.
- Textbook and lecture generated tags must not create curriculum ontology.
- Weak textbook/lecture chunks should map to approved tags or inherit nearest meaningful same-sequence context within explicit distance caps.
- Records without approved or valid inherited context should remain vector-searchable but hidden from tag browsing/curriculum maps.
- Secondary curriculum facets are out of scope for now.

## Forbidden visible tag patterns to audit

- `::Lectures::`
- `::Textbooks::`
- `Slide_`
- `Page_`
- `Digital_Pathology_Slide`
- `Pathology_Slide`
- `Benign_Cystic_Neck_Mass_Case_01`
- `::Error`

The Phase 2 prompt's minimum required forbidden patterns omit `Benign_Cystic_Neck_Mass_Case_01`, but local handoff governance docs include it. A future script should include it unless the user narrows the list.

## Candidate GCS inputs for Phase 1 probe

- v10.5.2 proof JSON: `gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json`
- Textbook backend docstore: `gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl`
- PathOut AP-diagnostic backend docstore: `gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl`
- Lecture STRICT_CYTO backend docstore: `gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl`
- WHO processed JSON files: `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json`

## Readiness assessment before GCS probe

Preliminary confidence: low-to-moderate.

Rationale:

- Local docs provide a coherent governance policy and identify the right backend-consumed docstore paths.
- v10.5.2 API proof supports that representative live searches no longer return forbidden primary-tag patterns, but it does not prove browse-ready curriculum maps or full-source tag cleanliness.
- v11 has not been proven live and must remain unpromoted.
- Actual object existence, object sizes, and local sample availability still need read-only Phase 1 GCS probing before any local audit script or sample-mode analysis can be responsibly designed.

## Blockers before v11 or full curriculum promotion

- Confirm existence and sizes of the required GCS inputs.
- Avoid downloading any object larger than 500 MB without separate size disclosure and approval.
- Build and run only a sample/local audit before any full-mode download or promotion.
- Produce explicit counts for visible tags, hidden/unmapped/rejected records, forbidden visible tag examples, inheritance distances, PathOut singleton/local tags, WHO to ABPath fuzzy mapping, and high-yield root browse examples.
- Do not deploy Cloud Run, update GPT Builder schema, or claim tag-aware curriculum browsing is live without live health/API proof and an audit.
