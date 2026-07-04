Read AGENTS.md and the 20260704 handoff docs under project_sources/updates/20260704.

Workstream: Evidence/Lesson/Research RAG — curriculum mapping and tag governance.

Goal:
Create a local read-only Curriculum Map Readiness Audit v0. This is a confidence audit, not a live promotion.

Hard safety rules:
- Do not upload anything to GCS.
- Do not modify any GCS object.
- Do not run v11 promotion.
- Do not deploy Cloud Run.
- Do not update GPT Builder schema.
- Do not edit live OpenAPI files except local draft notes.
- Ask for approval before every gcloud command.
- Before downloading any GCS object larger than 500 MB, show the object size and ask separately.
- Prefer probe/sample mode before full local downloads.

Use current project truth:
- One live Action only: searchEvidence.
- Current proven API contract remains v1.5.8.
- Tag-aware API schemas are draft/reference only unless proven by live health/API proof.
- ABPath tags are gold tags.
- Textbook/lecture generated tags must not create ontology.
- PathOut local tags may be useful but need review.
- WHO tags should map to ABPath only when fuzzy match is high-confidence.
- Do not claim curriculum mapping is live.

Phase 0 — local source review:
Inspect local handoff docs and reference artifacts. Produce a short local note:
audits/curriculum_map_readiness_v0/phase0_source_review.md

Phase 1 — GCS existence/size probe only:
Prepare and, after approval, run read-only commands to check existence and sizes for:
- gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json
- gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl
- gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl
- gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl
- gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json

Save probe outputs under:
audits/curriculum_map_readiness_v0/gcs_probe/

Phase 2 — create audit script:
Create:
scripts/curriculum_map_readiness_v0.py

The script must support:
--probe-only
--sample-size N
--input-dir data/curriculum_map_readiness_v0
--output-dir audits/curriculum_map_readiness_v0

It should produce, when data are available:
- audit.json
- source_counts.csv
- visible_tag_counts_by_source.csv
- hidden_record_counts.csv
- forbidden_visible_tag_examples.csv
- inheritance_distance_summary.csv, if fields exist
- inheritance_examples.csv, if fields exist
- who_abpath_fuzzy_audit.csv
- pathout_local_tag_review.csv
- high_yield_root_examples.csv
- curriculum_tag_index_v0.sqlite
- README_REVIEW.md

Required audit questions:
1. How many visible curriculum tags exist by source?
2. How many records are hidden/unmapped/rejected by source?
3. Are forbidden tags visible?
   Forbidden patterns include:
   ::Lectures::
   ::Textbooks::
   Slide_
   Page_
   Digital_Pathology_Slide
   Pathology_Slide
   ::Error
4. How aggressive is inheritance, if inheritance fields exist?
5. Does PathOut create too many singleton/local tags?
6. Does WHO map cleanly to ABPath?
7. Do high-yield roots browse sensibly?
   Include:
   GYN::Ovary
   GU::Prostate
   Breast
   GI
   Lung
   Derm
   Bone
   Soft_Tissue
   Cyto

Phase 3 — sample-mode run only:
After script creation, ask before any gcloud read/download.
Run only a sample-sized local audit first. Do not run full mode unless explicitly approved.

Phase 4 — summarize:
Return:
- files created
- commands run
- whether any GCS was touched, read-only only
- preliminary confidence level
- blockers before v11/full curriculum promotion
