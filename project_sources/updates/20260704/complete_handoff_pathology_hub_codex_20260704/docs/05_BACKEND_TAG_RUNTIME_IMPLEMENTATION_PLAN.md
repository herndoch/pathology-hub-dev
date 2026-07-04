# Backend Tag Runtime Implementation Plan

## Problem

Live API returns evidence and governed `primary_tag` fields, but GPT cannot yet browse by tag or infer tags through a proven backend mode.

## Desired request examples

```json
{"query":"ovarian high grade serous carcinoma p53 BRCA","sources":["who","textbooks","pathout","lectures","journals"],"search_mode":"tag_auto","infer_tags_from_query":true,"return_tag_facets":true,"max_results":5,"compact":true}
```

```json
{"query":"","sources":["textbooks","pathout","lectures"],"search_mode":"tag_prefix","tag_prefixes":["GYN::Ovary"],"max_results":20,"compact":true}
```

## Minimal SQL table

```sql
CREATE TABLE tag_records (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  record_id TEXT,
  source_id TEXT,
  title TEXT,
  url TEXT,
  primary_tag TEXT NOT NULL,
  primary_tag_governed TEXT,
  tag_governance_status TEXT,
  tag_authority TEXT,
  tag_root TEXT,
  tag_path TEXT,
  text_excerpt TEXT,
  source_record_json TEXT,
  normalized_artifact_gcs_uri TEXT,
  raw_source_gcs_uri TEXT,
  created_at_utc TEXT
);
CREATE INDEX idx_tag_records_source ON tag_records(source);
CREATE INDEX idx_tag_records_primary_tag ON tag_records(primary_tag);
CREATE INDEX idx_tag_records_root ON tag_records(tag_root);
CREATE INDEX idx_tag_records_tag_path ON tag_records(tag_path);
```

Use `primary_tag_governed` where available; otherwise use `primary_tag` only if it passes approved policy.

## Approved visible tags

Include gold ABPath, WHO-mapped-to-ABPath, approved PathOut local, manual-approved local, and inherited-context tags. Exclude `__UNMAPPED__`, rejected/generated tags, and lecture/textbook artifact tags.

## Search modes

- default/hybrid: current source-specific retrieval.
- tag_exact: exact governed tag matches.
- tag_prefix: governed tag prefix/root subtree.
- tag_browse: tag tree/facets/counts.
- tag_auto: infer candidate tags from query, then retrieve using those tags plus optional vector/FTS.

## Backward-compatible response additions

```json
{"tag_candidates":[],"tag_facets":[],"tag_results":[],"tag_search_mode":"tag_auto","tag_index_status":{"loaded":true,"record_count":323274}}
```

## Required tests

Legacy requests must still work. Tag modes must respect source filters and never return forbidden tag patterns.
