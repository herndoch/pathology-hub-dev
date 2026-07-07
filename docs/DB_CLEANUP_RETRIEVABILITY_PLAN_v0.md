# Curriculum DB Cleanup + Retrievability Plan (v0)

Local-first, GCS-aware, staging-before-prod. Goal: turn the flattened curriculum
SQLite artifacts into a **query-friendly, provenance-preserving, full-text-searchable**
database, then promote it safely to the live API.

> Authoritative constraints: `AGENTS.md` + `CURRENT_MASTER_SPINE`.
> - Keep source / normalized / chunked / vector / API / frontend workstreams separate.
> - Write sidecars; do not overwrite original normalized records.
> - Produce an `audit.json` (schema_version, input_paths, output_paths, counts, known_limitations) **before** any GCS upload.

---

## 0. Grounded facts (verified 2026-07-06)

Environment:
- `gcloud` authenticated as `herndon.charlie@gmail.com`, project `pathology-annotation-project`. GCS reads work.
- Live Cloud Run API: `https://pathology-hub-830130787988.us-central1.run.app/evidence/search`.
- **Prod curriculum DB currently = v0_2**: `gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_tag_index_v0_2.sqlite`.

Buckets:
- `gs://pathology-hub-0` (legacy/source): `source_videos/` (235 objects), `source_pdfs/` (98), `WHO/WHO_HTML/` (2049), `_asset_library/`, `_content_library/`.
- `gs://pathology_hub` (pipeline): `02_normalized/`, `03_indexes/`, `04_api_artifacts/`, `05_html/`, `06_audits/`, `00_manifests/`.

Local DB artifacts:
- `outputs/curriculum_map_v0_2/curriculum_tag_index_v0_2.sqlite`
- `outputs/curriculum_map_v0_3/curriculum_tag_index_v0_3.sqlite`
- `outputs/curriculum_map_v0_4/curriculum_tag_index_v0_4.sqlite`
- JSONL (provenance source of truth): `outputs/curriculum_map_v0_*/curriculum_records_v*.jsonl`

### The load-bearing problem

The SQLite `curriculum_records` tables are **lossy projections**. Rich provenance
(`raw_source_gcs_uri`, `normalized_artifact_gcs_uri`, `chunk_id`, `page`, `image_path`,
WHO `html_gcs_path`, pathout `url`, `curriculum_unit_id`, `source_id`) exists **only in
the JSONL `original_record`**, not in the DB. There is also **no full-text index**, so the
API can only do tag-prefix / in-memory node scoring.

| Fact | v0_2 | v0_3 | v0_4 |
|---|---|---|---|
| PK on curriculum_records | none | `curriculum_row_key` | `curriculum_row_key` |
| Indexes | 0 | 5 | 2 |
| FK enforcement | off | off | off |
| FTS full-text table | none | none | none |
| Provenance columns | absent | absent | absent |
| Runtime tables `tag_counts`/`review_queue`/`high_yield_examples` | present | **missing** | **missing** |
| Duplicate `record_id` rows | 84,951 | 49,530 | 49,530 |
| Blank `approved_tag` | 40,529 | 0 | 0 |
| Blank `title` | 42,094 | 24,698 | 24,698 |

Runtime dependency (in `backend/pathology_hub_v04_curriculum/app.py`): curriculum search
queries `tag_counts`, `review_queue`, `high_yield_examples`. **v0_3/v0_4 would break/degrade
curriculum search** because those tables are absent there.

### Current SQLite schemas (verified)

```
v0_2 curriculum_records: record_id, source, approved_tag, status, visible, title
v0_3 curriculum_records: curriculum_row_key, record_id, approved_tag, root, source, title,
     input_path, content_source, ontology_source, gapfill_version, decision_status,
     source_family, source_id, chunk_id, row_identity, duplicate_ordinal
v0_4 curriculum_records: curriculum_row_key, record_id, approved_tag, root, source, title,
     input_path, content_source, ontology_source, map_status
```

### Provenance available in JSONL by source family (verified)

- **textbooks**: `raw_source_gcs_uri` (`gs://pathology-hub-0/source_pdfs/*.pdf`), `normalized_artifact_gcs_uri`, `chunk_id`, `page`, `chapter_number`, `section_heading`, `image_path`, `figure_id`, tag arrays.
- **lectures**: `raw_source_gcs_uri` (`gs://pathology-hub-0/source_videos/*.mp4`), `normalized_artifact_gcs_uri`, `chunk_id`, `curriculum_unit_id`, `docstore_row_index`.
- **pathout**: `raw_source_gcs_uri`, `normalized_artifact_gcs_uri`, `pathout_id`, `url`, `page_title`, `figures`.
- **who**: `html_gcs_path` (`gs://pathology-hub-0/WHO/WHO_HTML/...`), `tags[]`, structured clinical prose fields.

---

## Action categories

- **SAFE NOW / READ-ONLY** — local inspection + read-only GCS. No approval needed.
- **LOCAL BUILD** — additive local artifacts (cleaned DB, audits, rejects). Reversible.
- **APPROVAL-GATED PROMOTION** — GCS writes, Cloud Run deploy, live API repoint, GPT Builder. Requires passing audit + explicit go.

---

## Phase 0 — Read-only local + GCS audit  · SAFE NOW · MUST

```bash
mkdir -p audits/db_cleanup_v0/gcs_inventory

# Local schema + integrity snapshot
for v in v0_2 v0_3 v0_4; do
  db="outputs/curriculum_map_${v}/curriculum_tag_index_${v}.sqlite"
  sqlite3 "$db" ".schema"                   > "audits/db_cleanup_v0/schema.${v}.sql"
  sqlite3 "$db" "PRAGMA integrity_check;"   > "audits/db_cleanup_v0/integrity.${v}.txt"
  sqlite3 "$db" "PRAGMA foreign_key_check;" > "audits/db_cleanup_v0/fk_check.${v}.txt"
done

# Read-only GCS inventory of referenced prefixes (bounded; NOT gs://**)
P=pathology-annotation-project
OUT=audits/db_cleanup_v0/gcs_inventory
gcloud storage ls "gs://pathology-hub-0/source_videos/**"    --project=$P > "$OUT/hub0_source_videos.txt"
gcloud storage ls "gs://pathology-hub-0/source_pdfs/**"      --project=$P > "$OUT/hub0_source_pdfs.txt"
gcloud storage ls "gs://pathology-hub-0/WHO/WHO_HTML/**"     --project=$P > "$OUT/hub0_who_html.txt"
gcloud storage ls "gs://pathology-hub-0/_asset_library/**"   --project=$P > "$OUT/hub0_asset_library.txt"
gcloud storage ls "gs://pathology-hub-0/_content_library/**" --project=$P > "$OUT/hub0_content_library.txt"
```

**Pass/fail:** all `integrity.*` = `ok`; inventories non-empty (expect videos≈235, pdfs≈98, WHO≈2049).
**Rollback:** n/a (read-only).

---

## Phase 1 — Canonical schema + runtime compatibility  · LOCAL BUILD · MUST

Create `outputs/curriculum_map_v0_4_cleaned/schema.sql` as the single DDL source of truth.
Keep runtime-facing columns; **rebuild** the runtime trio as real tables (not empty shims);
add provenance child tables + FTS.

```sql
-- schema.sql (abridged; see build script)
CREATE TABLE curriculum_records (
  curriculum_row_key TEXT PRIMARY KEY,
  record_id     TEXT NOT NULL,
  source        TEXT NOT NULL,
  approved_tag  TEXT NOT NULL,
  root          TEXT NOT NULL,
  title         TEXT,
  content_source TEXT, ontology_source TEXT, decision_status TEXT, map_status TEXT,
  source_family TEXT, source_id TEXT, chunk_id TEXT, curriculum_unit_id TEXT,
  -- denormalized retrieval columns (validated against GCS inventory):
  source_gcs_uri TEXT, normalized_artifact_gcs_uri TEXT,
  source_page_url TEXT, page_image_url TEXT, video_url TEXT, video_time_url TEXT,
  provenance_class TEXT
);
CREATE TABLE curriculum_nodes (tag TEXT PRIMARY KEY, root TEXT, record_count INTEGER);
CREATE TABLE tag_counts        (source TEXT, tag TEXT, count INTEGER);
CREATE TABLE review_queue      (record_id TEXT, source TEXT, original_tag TEXT, review_reason TEXT, title TEXT);
CREATE TABLE high_yield_examples (root TEXT, tag TEXT, source TEXT, record_id TEXT, title TEXT);

CREATE TABLE record_sources (curriculum_row_key TEXT, record_id TEXT, source_family TEXT,
  raw_source_gcs_uri TEXT, raw_bucket TEXT, raw_object TEXT,
  normalized_artifact_gcs_uri TEXT, who_html_gcs_path TEXT, pathout_url TEXT,
  raw_uri_valid INT, raw_uri_in_inventory INT, provenance_class TEXT);
CREATE TABLE record_tags   (curriculum_row_key TEXT, tag TEXT, tag_kind TEXT);
CREATE TABLE record_assets (curriculum_row_key TEXT, asset_kind TEXT, gcs_uri TEXT, public_url TEXT, valid INT);
CREATE TABLE record_pages  (curriculum_row_key TEXT, page INTEGER, chapter_number TEXT, section_heading TEXT);
CREATE TABLE record_quality_flags (curriculum_row_key TEXT PRIMARY KEY,
  blank_title INT, blank_tag INT, flattened_tags INT, provenance_missing INT, dup_semantic INT);

CREATE VIRTUAL TABLE curriculum_fts USING fts5(
  record_id UNINDEXED, approved_tag, root, title, source, search_text,
  tokenize = 'unicode61 remove_diacritics 2'
);
```

Indexes (Phase 5) added after load.

**app.py startup guard** (add to `ensure_curriculum_artifacts_v159` path):

```python
REQUIRED = {"curriculum_records","curriculum_nodes","tag_counts","review_queue","high_yield_examples"}
have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
missing = REQUIRED - have
if missing:
    raise RuntimeError(f"Curriculum DB missing required tables: {sorted(missing)}")
```

**Pass/fail:** runtime smokes succeed:
```sql
SELECT COUNT(*) FROM tag_counts;
SELECT COUNT(*) FROM review_queue WHERE original_tag='GYN::Ovary';
SELECT source, record_id, title FROM high_yield_examples LIMIT 3;
SELECT record_id, title FROM curriculum_fts WHERE curriculum_fts MATCH 'ovary granulosa' LIMIT 5;
```
**Rollback:** cleaned DB is a new file; delete it.

---

## Phase 2 — Provenance / GCS pointer repair  · SAFE NOW (audit) + LOCAL BUILD (repair) · MUST

Provenance lives in JSONL, so extraction is a Python pass populating `record_sources`.
Classify every row: `ok_traced | missing_pointer | malformed_uri | wrong_bucket | wrong_path_convention | stale_not_in_inventory | unsupported_source_type`.

Audit SQL (after load):

```sql
-- no usable source pointer
SELECT COUNT(*) FROM record_sources
WHERE COALESCE(TRIM(raw_source_gcs_uri),'')='' AND COALESCE(TRIM(normalized_artifact_gcs_uri),'')=''
  AND COALESCE(TRIM(who_html_gcs_path),'')='' AND COALESCE(TRIM(pathout_url),'')='';

-- malformed / wrong-bucket gs://
SELECT record_id, raw_source_gcs_uri FROM record_sources
WHERE TRIM(raw_source_gcs_uri)<>''
  AND raw_source_gcs_uri NOT LIKE 'gs://pathology_hub/%'
  AND raw_source_gcs_uri NOT LIKE 'gs://pathology-hub-0/%' LIMIT 100;

-- placeholder pointers
SELECT record_id, raw_source_gcs_uri FROM record_sources
WHERE LOWER(COALESCE(raw_source_gcs_uri,'')) IN ('unknown','none','n/a','placeholder','');

-- pointer present but not in GCS inventory (stale)
SELECT record_id, raw_source_gcs_uri FROM record_sources
WHERE raw_uri_valid=1 AND raw_uri_in_inventory=0 LIMIT 100;
```

**Deterministic repairs allowed (LOCAL BUILD):**
- public URL from validated `gs://` URI: `gs://B/obj` → `https://storage.googleapis.com/B/urlquote(obj)`.
- lecture video filename→inventory match (proven pattern in `scripts/repair_lecture_timecoded_docstore_v0_1.py`, e.g. `Breast_Lecture_Epithelial%20Part%201_Chen.mp4`).
- Anything non-deterministic → `rejects/provenance_unresolved.jsonl`. **No guessing.**

**Pass/fail:** 100% of rows carry a non-null `provenance_class`; visible set has 0 malformed/wrong-bucket URIs.

---

## Phase 3 — Malformed / flattened remediation  · LOCAL BUILD · SHOULD

Detect + structure (into child tables) rather than leave blobs:

```sql
SELECT record_id, tags FROM staging_records WHERE TRIM(tags) LIKE '[%' OR TRIM(tags) LIKE '{%' LIMIT 100; -- JSON-ish
SELECT record_id, tags FROM staging_records WHERE tags LIKE '%,%' OR tags LIKE '%|%' OR tags LIKE '%;%' LIMIT 100; -- delimited
SELECT SUM(title IS NULL) null_titles, SUM(TRIM(title)='') blank_titles FROM curriculum_records; -- blank vs null
```

Populate `record_tags`, `record_assets`, `record_pages`, `record_quality_flags`.
Do **not** collapse WHO clinical prose into tags (that's content, not structure).

---

## Phase 4 — Duplicate / null / blank cleanup  · LOCAL BUILD · MUST

`record_id` is legitimately non-unique (one source row → many tags; WHO entities repeat across roots).
Use `curriculum_row_key` (v0_3 pattern) as PK; audit semantic dupes.

```sql
SELECT curriculum_unit_id, approved_tag, source, COUNT(*) n
FROM curriculum_records GROUP BY curriculum_unit_id, approved_tag, source
HAVING n>1 ORDER BY n DESC LIMIT 100;

SELECT COUNT(*) FROM curriculum_records WHERE COALESCE(TRIM(approved_tag),'')=''; -- was 40,529 in v0_2
```

Rules (record in `audit.json`): exact-identity repeats → keep first + `duplicate_ordinal`; blank tag with no recoverable value → `rejects/blank_tag.jsonl`, excluded from visible/API set; blank/NULL title → coalesce to derived title or flag.

**Pass/fail:** duplicate PK groups = 0; visible-set blank tags = 0; every dropped row in a rejects file with a reason.

---

## Phase 5 — Performance / retrievability index tuning  · LOCAL BUILD · SHOULD

```sql
CREATE INDEX idx_cr_tag      ON curriculum_records(approved_tag);
CREATE INDEX idx_cr_source   ON curriculum_records(source);
CREATE INDEX idx_cr_root     ON curriculum_records(root);
CREATE INDEX idx_cr_unit     ON curriculum_records(curriculum_unit_id);
CREATE INDEX idx_rq_orig_tag ON review_queue(original_tag);
CREATE INDEX idx_tc_tag      ON tag_counts(tag);
CREATE INDEX idx_hy_tag      ON high_yield_examples(tag);
CREATE INDEX idx_rs_rowkey   ON record_sources(curriculum_row_key);
ANALYZE;
INSERT INTO curriculum_fts(curriculum_fts) VALUES('optimize');
```

**Pass/fail:** `EXPLAIN QUERY PLAN` for runtime + FTS smokes uses an index/FTS, not `SCAN`.

---

## Phase 6 — Rebuild safety guardrails  · LOCAL BUILD · MUST

Destructive `path.unlink()` before recreate exists in (verified line numbers):
- `scripts/build_curriculum_map_v0_2.py:407`
- `scripts/build_curriculum_map_v0_3.py:168`
- `scripts/curriculum_gapfill_v0_4_stage_with_low_info_gate.py:745`
- `scripts/curriculum_map_readiness_v0.py:377`

Change all four: write to `*.sqlite.tmp`, validate, then `os.replace()` (atomic). Never unlink
the live artifact first. Require `--replace-approved` to overwrite an approved artifact
(default refuse). Write `audit.json` before an artifact is promotion-ready.

---

## Non-destructive migration flow (the build)

New script: `scripts/build_curriculum_db_cleaned_v0.py`.

1. Open source JSONL (`curriculum_records_v0_4.jsonl`) as provenance truth; source DBs read-only.
2. Load Phase 0 GCS inventory sidecars into in-memory sets.
3. Create shadow DB from `schema.sql`.
4. `INSERT ... SELECT` flat columns; Python pass for provenance + flattened fields.
5. Populate child tables + `record_quality_flags`; write `rejects/*.jsonl`.
6. Build FTS rows (`search_text` = title + tags + excerpt).
7. Re-materialize `tag_counts` / `review_queue` / `high_yield_examples` / `curriculum_nodes` / `source_counts` (reuse existing `review_queue_v0_*.csv`, `rejected_tags_v0_*.csv`).
8. Run validation → `validation/*.json`, `audit.json`, `manifest.json`.
9. Atomic rename shadow → cleaned artifact **only if validation passes**.

Artifact layout:
```
outputs/curriculum_map_v0_4_cleaned/
  curriculum_tag_index_v0_4_cleaned.sqlite
  schema.sql  audit.json  manifest.json
  rejects/{blank_tag,provenance_unresolved,malformed_uri}.jsonl
  gcs_inventory/*.txt
  validation/{integrity,schema_drift,duplicates,provenance,runtime_smoke}.json
```

---

## Validation suite (gates promotion)

- `PRAGMA integrity_check`=ok; `PRAGMA foreign_key_check` empty — MUST
- Schema matches `schema.sql`; runtime trio + FTS present — MUST
- Duplicate PK groups = 0; semantic-dup report attached — MUST
- Visible set: 0 blank approved_tag, 0 missing source pointer, 0 malformed/wrong-bucket URI — MUST
- All unresolved rows in `rejects/*.jsonl` with reasons — MUST
- FTS smoke + runtime smokes pass (run in `.venv_curriculum`/`.venv_test`; deps `numpy`/`faiss`/`fastapi` required) — MUST
- Row-count delta old→cleaned explained by rejects + dedupe — MUST

Run smokes via existing harness pointed at cleaned DB:
```bash
source .venv_curriculum/bin/activate
CURRICULUM_SQLITE_GCS=outputs/curriculum_map_v0_4_cleaned/curriculum_tag_index_v0_4_cleaned.sqlite \
  python3 scripts/test_curriculum_loader_local_v1_5_9.py
```

---

## Script-level changes

- `backend/pathology_hub_v04_curriculum/app.py` — add startup DB guard; add FTS-backed branch to `curriculum_search_v159` returning validated source URLs. Don't change ranking defaults. MUST (guard) / SHOULD (FTS).
- `scripts/build_curriculum_map_v0_2.py` — shadow+atomic swap; keep as canonical builder (already emits runtime trio). MUST.
- `scripts/build_curriculum_map_v0_3.py` — shadow+swap; add runtime trio; centralize DDL. MUST.
- `scripts/curriculum_gapfill_v0_4_stage_with_low_info_gate.py` — shadow+swap; add runtime trio; audit before artifact. MUST.
- `scripts/curriculum_map_readiness_v0.py` — shadow+swap; reuse as audit generator. SHOULD.
- `scripts/build_curriculum_db_cleaned_v0.py` — NEW migration flow; reuse URI/public-URL helpers from `repair_lecture_timecoded_docstore_v0_1.py`. MUST.

---

## Prioritized backlog (top 10)

1. Phase 0 snapshot + bounded GCS inventory — SAFE NOW — MUST
2. Runtime-compat audit vs app.py (proves v0_3/v0_4 break curriculum) — SAFE NOW — MUST
3. Provenance extraction JSONL → `record_sources` + classification — LOCAL BUILD — MUST
4. Build FTS + denormalized retrieval columns — LOCAL BUILD — MUST
5. Re-materialize runtime trio in cleaned DB — LOCAL BUILD — MUST
6. Shadow+atomic swap in 4 builders — LOCAL BUILD — MUST
7. Dedupe via row_key + rejects for blank tags — LOCAL BUILD — MUST
8. `record_tags` normalization — LOCAL BUILD — SHOULD
9. app.py startup guard + FTS search branch — LOCAL BUILD — SHOULD
10. Validation suite + audit.json/manifest.json — LOCAL BUILD — MUST

---

## Go / no-go checklist (before any promotion)

- [ ] integrity_check=ok, foreign_key_check empty
- [ ] schema matches schema.sql; runtime trio + FTS present
- [ ] duplicate PK groups = 0; semantic-dup report attached
- [ ] visible set: 0 blank tag, 0 missing pointer, 0 malformed/wrong-bucket URI
- [ ] rejects/*.jsonl complete with reasons
- [ ] FTS + runtime smokes pass in venv
- [ ] row-count delta explained; audit.json + manifest.json written
- [ ] confirmation: no GCS write / deploy / prod repoint done yet

---

## APPROVAL-GATED promotion path (staging before prod)

> Prod curriculum DB is currently v0_2. Do NOT repoint prod until staging smoke passes.

### P1. Upload cleaned package to a NEW candidate GCS path (additive; overwrites nothing)
- Purpose: stage for review. Requires: green go/no-go + audit.json.
```bash
gcloud storage cp -r outputs/curriculum_map_v0_4_cleaned \
  gs://pathology_hub/03_indexes/curriculum/v0_4_cleaned_candidate/ \
  --project=pathology-annotation-project
```
- Rollback: `gcloud storage rm -r gs://pathology_hub/03_indexes/curriculum/v0_4_cleaned_candidate/`.

### P2. Versioned manifest object
- Purpose: provenance of promoted artifact (schema_version, sha256, counts). Rollback: delete manifest.

### P3. Point a STAGING Cloud Run revision at the candidate DB
- Set on the **staging** service only:
  `CURRICULUM_SQLITE_GCS=gs://pathology_hub/03_indexes/curriculum/v0_4_cleaned_candidate/curriculum_tag_index_v0_4_cleaned.sqlite`
- Rollback: restore previous staging env value / route to prior revision.

### P4. Staging smoke
```bash
curl -s -H "X-API-Key: $KEY" https://<staging-url>/health | jq '.curriculum_map_build_status'
curl -s -H "X-API-Key: $KEY" -X POST https://<staging-url>/evidence/search \
  -d '{"query":"ovary granulosa","sources":["curriculum"],"max_results":5}' | jq '.curriculum_results | length'
```
- Pass/fail: health ok, curriculum_results non-empty, no forbidden tags.

### P5. Production promotion (ONLY after staging passes + explicit go)
- Repoint prod `CURRICULUM_SQLITE_GCS` → candidate path; deploy prod revision.
- Rollback: repoint to v0_2 + route to prior revision.

### P6. GPT Builder update (only if API contract changed)
- Rollback: restore prior schema.

Each promotion step requires: exact command, input artifact, destination, audit evidence,
rollback path, and explicit human approval.

---

## One-page execution runbook

```bash
# 0. Baseline + read-only GCS inventory (SAFE NOW)
mkdir -p audits/db_cleanup_v0/gcs_inventory
for v in v0_2 v0_3 v0_4; do
  db=outputs/curriculum_map_${v}/curriculum_tag_index_${v}.sqlite
  sqlite3 "$db" ".schema" > audits/db_cleanup_v0/schema.${v}.sql
  sqlite3 "$db" "PRAGMA integrity_check;" > audits/db_cleanup_v0/integrity.${v}.txt
done
P=pathology-annotation-project; OUT=audits/db_cleanup_v0/gcs_inventory
gcloud storage ls "gs://pathology-hub-0/source_videos/**" --project=$P > $OUT/hub0_source_videos.txt
gcloud storage ls "gs://pathology-hub-0/source_pdfs/**"   --project=$P > $OUT/hub0_source_pdfs.txt
gcloud storage ls "gs://pathology-hub-0/WHO/WHO_HTML/**"  --project=$P > $OUT/hub0_who_html.txt

# 1. Build cleaned, query-friendly DB (LOCAL BUILD) — shadow path + atomic swap
python3 scripts/build_curriculum_db_cleaned_v0.py \
  --source-jsonl outputs/curriculum_map_v0_4/curriculum_records_v0_4.jsonl \
  --review-csv   outputs/curriculum_map_v0_4/../curriculum_map_v0_2/review_queue_v0_2.csv \
  --gcs-inventory-dir audits/db_cleanup_v0/gcs_inventory \
  --out-dir outputs/curriculum_map_v0_4_cleaned

# 2. Validate (LOCAL BUILD) -> validation/*.json + audit.json + manifest.json

# 3. Runtime + FTS smoke in venv (LOCAL BUILD)
source .venv_curriculum/bin/activate
CURRICULUM_SQLITE_GCS=outputs/curriculum_map_v0_4_cleaned/curriculum_tag_index_v0_4_cleaned.sqlite \
  python3 scripts/test_curriculum_loader_local_v1_5_9.py

# 4. Go/no-go — review audit.json + validation/*

# 5. APPROVAL-GATED promotion (staging first, then prod). See promotion section.
```

---

_Status: plan only. No GCS writes, Cloud Run deploys, prod repoint, or GPT Builder changes have been performed. Read-only GCS listing and local SQLite inspection only._
