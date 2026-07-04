# GPT Builder Update Checklist — v1.5.9 Curriculum Map

Status: FINAL checklist for manual GPT Builder update. Do not redeploy backend from this checklist.

## 1. Production Proof Commands

```bash
PROD_URL="https://pathology-hub-v04-vorn5q2kga-uc.a.run.app"
API_KEY="$(gcloud secrets versions access latest --secret=pathology-hub-api-key --project=pathology-annotation-project)"

curl -s "$PROD_URL/health" | jq '{
  version,
  curriculum_map_enabled,
  curriculum_map_version,
  curriculum_map_build_status,
  curriculum_map_forbidden_visible_tag_count,
  curriculum_map_records_visible,
  curriculum_map_review_queue_count
}'

curl -s -X POST "$PROD_URL/evidence/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"query":"ovary granulosa","sources":["curriculum"],"max_results":5,"compact":true}' \
  | jq '.source_status,.curriculum_status,.curriculum_results[0]'

curl -s -X POST "$PROD_URL/evidence/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"query":"melanoma","sources":["curriculum"],"max_results":10,"compact":true}' \
  | grep -E "::Lectures::|::Textbooks::|::Error|Slide_|Page_|Digital_Pathology_Slide|Pathology_Slide|rejected_generated" || true
```

The forbidden-pattern grep should return no lines.

## 2. OpenAPI File To Paste Into GPT Builder

```text
docs/openapi_pathology_hub_unified_searchEvidence_v1_5_9_curriculum_FINAL.yaml
```

## 3. GPT Instruction File To Paste Into GPT Builder

```text
docs/GPT_INSTRUCTIONS_PATHOLOGY_HUB_V1_5_9_CURRICULUM_UNDER_8K_FINAL.txt
```

## 4. GPT Preview Tests

Run these in GPT Preview after pasting the schema/instructions:

```text
Find the curriculum area for ovarian granulosa cell tumor.
Build me a study map for prostate adenocarcinoma grading.
Now teach me ovarian granulosa cell tumor using evidence.
```

## 5. Expected First Action Call

For the first preview test, the expected first Action call is:

```json
{"query":"ovary granulosa","sources":["curriculum"],"max_results":5,"compact":true}
```

## 6. Expected Second Evidence Action Call

For teaching requests, the second Action call should use evidence sources, for example:

```json
{"query":"ovarian granulosa cell tumor","sources":["who","textbooks","pathout","journals","lectures"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

Source choice may vary by question, but diagnostic teaching should use WHO/textbooks/pathout/journals/lectures as appropriate. Curriculum alone is not diagnostic evidence.

## 7. Pass/Fail Criteria

Pass if:

- `source_status.curriculum == "ok"`.
- `curriculum_status.forbidden_visible_tag_count == 0`.
- `curriculum_results` is non-empty for known queries such as `ovary granulosa` and `GYN::Ovary`.
- Existing evidence sources still work: `who`, `textbooks`, `journals`, `pathout`, `lectures`, `videos`.
- GPT Preview uses one Action only: `searchEvidence`.
- GPT Preview does not invent `curriculumSearch`.
- GPT Preview does not present review_queue, rejected, hidden, generated, or forbidden-pattern tags as curriculum nodes.

Fail if any of those checks fail.

## 8. Rollback Note

If GPT Builder rejects the schema or GPT Preview fails, restore the previous v1.5.8 OpenAPI and GPT instructions. Do not redeploy backend, do not modify GCS, and do not create a second Action.
