# Curriculum Map Readiness Audit v0 Review

Generated: 2026-07-04T20:33:05+00:00
Mode: audit

## Safety

- Local script only.
- No gcloud commands are executed by this script.
- No GCS upload, GCS mutation, v11 promotion, deployment, or GPT Builder schema update is performed.

## Inputs

- Input directory: `data/curriculum_map_readiness_v0`
- Files seen: 24

## Summary

- Records parsed: 21463
- Parse errors: 0
- Forbidden visible tag examples: 945
- ABPath terms found for WHO fuzzy audit: 8802

## Review notes

- `who_abpath_fuzzy_audit.csv` contains a limitation row if no local ABPath source was present.
- `pathout_local_tag_review.csv` is a local review aid; it does not approve or promote tags.
- `high_yield_root_examples.csv` is a browsing sanity check, not proof of live API behavior.
