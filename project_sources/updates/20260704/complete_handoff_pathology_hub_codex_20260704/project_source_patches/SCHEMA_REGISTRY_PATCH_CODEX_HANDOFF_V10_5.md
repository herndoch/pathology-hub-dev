# Schema Registry Patch — Governed Tags and Future Tag Runtime

## Live/current
- `evidence_search_response.v1.5.8` remains the current live response family.
- Governed metadata fields may exist in backend-consumed JSONL records: `primary_tag_governed`, `tag_governance_status`, `tag_governance_basis`.

## Proposed/not live
- `pathology_hub_approved_curriculum_tag_index.v11`
- `searchEvidence.tagaware_request.v1_7_0`
- `tag_auto`, `tag_exact`, `tag_prefix`, `tag_browse`
- `tag_candidates`, `tag_results`, `tag_facets`

Do not update GPT Builder to a tag-aware schema until deployed and audited.
