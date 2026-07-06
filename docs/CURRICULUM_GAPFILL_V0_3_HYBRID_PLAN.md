# Curriculum Gap Fill v0.3 Hybrid Plan

## Scope

Workstream: Curriculum Gap Fill v0.3 - cross-source hybrid ABPath tagging.

This revision changes lecture gap-fill from SQL-only lexical matching to cross-source hybrid tagging. ABPath remains the ontology source only. WHO, PathOut, textbooks, existing approved curriculum records, and existing lecture tags provide tag meaning evidence.

## Non-goals

- No deploy.
- No GPT Builder update.
- No GCS upload.
- No mutation of raw lecture chunks, textbook chunks, vector docstores, FAISS indexes, or Curriculum Map v0.2 outputs.
- No textbook gap-fill processing.
- No final/live sidecar.
- No OpenAI embedding calls without explicit approval.

## Inputs

- `outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3.jsonl`
- `outputs/curriculum_map_v0_2/curriculum_records_v0_2.jsonl`
- `outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_approved_v0_3_HIGHCONF.jsonl`
- `data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl`
- Local vector docstore samples, if present, are audited only. Full vector similarity is marked unavailable unless usable local vectors are found.

## Seed Profile Construction

For each ABPath tag present in the bounded lecture candidate set:

1. Normalize the tag into root, organ/site, category, and entity phrase.
2. Collect visible v0.2 curriculum records already associated with that tag.
3. Prefer source evidence in this order: WHO, PathOut, textbooks, lectures.
4. Extract source-specific terms and phrases:
   - entity names and aliases
   - morphology phrases
   - IHC marker terms
   - molecular terms
   - diagnostic criteria phrases
   - differential-relevant phrases
5. Remove generic terms such as tumor, neoplasm, malignant, benign, lesion, disease, pathology, diagnosis, other, and miscellaneous.
6. Build sibling negatives from tags sharing the same root but different site/category.

## Hybrid Rescoring

For each existing lecture candidate:

- Start with the prior FTS score.
- Add evidence for exact entity phrase matches.
- Add weighted source support from WHO, PathOut, textbook, and lecture terms.
- Add root/site agreement using existing lecture tag context.
- Use vector similarity only if local vectors are available; otherwise write `vector_status = unavailable`.
- Subtract for sibling/cross-root conflict.
- Subtract for generic-only matches.
- Reject forbidden/generated patterns.

## Decision Classes

- `approved_hybrid_high`: exact/entity support plus cross-source support, or strong FTS plus WHO/PathOut/textbook support, with no sibling conflict.
- `review_hybrid`: plausible but ambiguous, medium confidence, cross-site ambiguity, or lexical/vector disagreement.
- `rejected_hybrid`: generic-only, wrong-root or sibling conflict, forbidden/generated pattern, or weak evidence.

## Outputs

- `outputs/curriculum_gapfill_v0_3/cross_source_tag_seed_profiles_v0_3.jsonl`
- `outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_candidates_v0_3_HYBRID_RESCORED.jsonl`
- `outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_hybrid_review_sample_150.csv`
- `outputs/curriculum_gapfill_v0_3/lecture_abpath_gapfill_hybrid_audit_v0_3.json`
- `outputs/curriculum_gapfill_v0_3/README_HYBRID_GAPFILL_V0_3.md`

## Review Gate

The hybrid output is local review material only. It is not a final approved sidecar, not live, not indexed, not API-exposed, and not uploaded.
