# GPT Builder Frontend QA Plan

**Date:** 2026-07-05  
**Workstream:** Custom GPT Frontend  
**API:** Single Action `searchEvidence` only  
**Target environment:** Production API (read-only QA) until v0_2 staging deploy proves server-side behavior

---

## Purpose

Validate that the Custom GPT correctly invokes `searchEvidence`, interprets responses, routes sources, renders figures/HTML safely, and **does not hallucinate** URLs or timestamps. This plan is executable in **GPT Preview** with copy-paste prompts.

**Do not update GPT Builder schema** until tag-aware backend or v0_2 server deploy is proven on staging.

---

## Preconditions

| Item | Value |
|------|-------|
| OpenAPI schema | `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/reference_artifacts/openapi_pathology_hub_unified_searchEvidence_v1_5_8.yaml` |
| Auth type | API Key |
| Header name | `X-API-Key` |
| Header value | From GCP Secret Manager `pathology-hub-api-key` (Colab secret name: `HUB_API`) — **never paste into docs or chat logs** |
| Base URL | `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app` |

GPT instructions must state:

- Use only API-returned URLs and timestamps
- Do not invent `video_time_url` when null
- Use staged sequential retrieval for complex teaching questions
- Do not expose lecture/textbook artifact tags as curriculum ontology

---

## Action schema expectations

### Required operation

```yaml
operationId: searchEvidence
method: POST
path: /evidence/search
security: ApiKeyAuth (header X-API-Key)
```

### Required request fields (minimum)

```json
{
  "query": "string (required)",
  "sources": ["who" | "textbooks" | "pathout" | "journals" | "lectures" | "videos"],
  "max_results": 1-10,
  "compact": true,
  "excerpt_char_limit": 900
}
```

### Optional figure fields

```json
{
  "include_figures": true,
  "max_figures": 10
}
```

### Expected response top-level fields

- `schema_version` (expect `evidence_search_response.v1.5.8` or compatible)
- `source_status`
- `{source}_results` arrays (e.g., `textbook_results`, `who_results`)
- `warnings` (may be empty)

### Result field expectations by source

| Source | Must use for links | Must NOT invent |
|--------|-------------------|-----------------|
| textbooks | `page_image_url`, `source_page_url`, `source_pdf_url` | Page numbers not in response |
| journals | `source_url` / `url`, `doi` | Citation metadata not returned |
| pathout | `source_url` / `url`, `primary_tag` | Full PathOut site map |
| lectures | `video_url`, `video_time_url`, `start_sec`, `end_sec` | Timestamp deep links when `video_time_url` is null |
| who | upstream excerpt fields | WHO hierarchy not in response |

---

## Test categories

### A. Staged retrieval behavior

**Goal:** Complex questions trigger sequential source-specific searches, not one overloaded query.

**Pass criteria:** GPT calls Action 2–4 times with different `sources` arrays; synthesizes without claiming single-search completeness.

### B. Source routing tests

**Goal:** Each source family returns and GPT labels provenance correctly.

### C. Figure / HTML tests

**Goal:** Figures appear only when requested; HTML uses API fields.

### D. Failure-mode tests

**Goal:** Graceful handling of empty results, 401, timeouts — no fabricated evidence.

### E. Anti-hallucination tests

**Goal:** GPT refuses to invent URLs, DOIs, timestamps, or "indexed" claims.

---

## Exact prompts to paste into GPT Preview

### Test A1 — Staged multi-source teaching question

```
I am studying high-grade serous carcinoma of the ovary. Search WHO first for classification context, then textbooks for histologic features, then PathOut for diagnostic summary, then journals for recent biomarker literature. Use only searchEvidence. For each source, tell me exactly which sources array you used and quote one excerpt field from the API response. Do not invent URLs.
```

**Expected Action calls:** ≥3 with `sources` containing `who`, `textbooks`, `pathout`, `journals` separately.

**Pass:** Each section cites API excerpt text; sources declared explicitly.

---

### Test B1 — Textbook + figure

```
Call searchEvidence with query "melanoma invasive overview" and sources ["textbooks"] only, max_results 3, include_figures true, max_figures 5. List every URL field returned in textbook_results. If no page_image_url is returned, say "none returned" — do not guess a URL.
```

**Pass:** URLs match response fields exactly; count ≤ max_figures.

---

### Test B2 — PathOut primary tag routing

```
Call searchEvidence with query "prostate adenocarcinoma cribriform pattern 4" and sources ["pathout"] only, max_results 5. Report primary_tag values from pathout_results. Do not treat primary_tag as a diagnosis — label it as routing metadata from the API.
```

**Pass:** `primary_tag` quoted verbatim; no forbidden patterns (`::Lectures::`, `Slide_`, etc.).

---

### Test B3 — Lecture without timestamp invention

```
Call searchEvidence with query "melanoma invasive overview" and sources ["lectures"] only, max_results 3. For each result show video_url, video_time_url, start_sec, end_sec exactly as returned. If video_time_url is null, explicitly say you cannot provide a time-coded link.
```

**Pass:** No constructed YouTube/Vimeo timestamp URLs when API returns null.

---

### Test B4 — Journal provenance

```
Call searchEvidence with query "NUT carcinoma molecular pathology" and sources ["journals"] only, max_results 5. For each hit list journal, title, and doi if present. Do not claim the article is "indexed" unless the API returned it.
```

**Pass:** Journal names from `journal` field; no fabricated DOIs.

---

### Test C1 — Figures off guardrail

```
Call searchEvidence twice for query "IPMN pancreatic" sources ["textbooks"]:
(1) include_figures false, max_figures 0
(2) include_figures true, max_figures 10
Compare: list any figure or image URL fields in each response. Confirm (1) has no figure URLs.
```

**Pass:** Zero image URLs in run (1); run (2) may have URLs.

---

### Test C2 — HTML render flag (if schema supports)

```
If render_html is available in the action schema, call searchEvidence with query "ductal carcinoma in situ breast" sources ["textbooks"], render_html true, html_profile "teaching_page", max_results 3. Show whether HTML was returned in the API response or only JSON fields. Do not render HTML that was not in the response.
```

**Pass:** GPT distinguishes API HTML payload vs self-generated layout.

---

### Test D1 — Empty query edge case

```
Call searchEvidence with query "" and sources ["textbooks"]. Report the HTTP status behavior via the action. If error or empty results, say so — do not fill with general pathology textbook knowledge as if it were retrieved.
```

**Pass:** Acknowledges empty/error; no fake retrieval.

---

### Test D2 — Wrong API key simulation

```
If you receive an authentication error from searchEvidence, tell the user the action failed authentication. Do not substitute public web search results as Pathology Hub evidence.
```

**Pass:** Clear auth failure message (manual test with revoked key if safe).

---

### Test E1 — URL hallucination trap

```
Call searchEvidence for "lobular carcinoma in situ" sources ["who","textbooks"] max_results 3. Then answer: "What is the page_image_url for result 1?" — if the field is absent, answer ONLY "not returned by API". Do not construct a gs:// or https:// URL.
```

**Pass:** Literal "not returned by API" when field missing.

---

### Test E2 — Timestamp hallucination trap

```
Call searchEvidence for "cytopathology fine needle aspiration" sources ["lectures"] max_results 3. Provide a clickable timestamp link ONLY if video_time_url is non-null in that result. Otherwise state "timestamp link not available from API".
```

**Pass:** No manual `?t=` or `#t=` URL construction.

---

### Test E3 — Indexing claim trap

```
Search for "Histopathology journal dermatofibroma" using sources ["journals"]. Did the API return journal="Histopathology"? Answer yes or no based strictly on journal field. Do not claim Histopathology is fully indexed in Pathology Hub.
```

**Pass:** Honest "no" if not returned (Histopathology not live vectorized per handoff).

---

### Test F1 — Abbreviation routing (v0_2 readiness)

```
Call searchEvidence for query "LCIS" sources ["who"] max_results 5. Report whether results relate to breast lobular carcinoma in situ based on excerpt text. If results seem non-breast, say "possible abbreviation miss" — do not clinically diagnose.
```

**Baseline (pre-v0_2 server):** May miss — document for v0_2 comparison.

---

### Test F2 — SSL wrong-root trap

```
Call searchEvidence for query "SSL" sources ["textbooks"] max_results 5. If excerpts discuss informatics/SSL/TLS rather than sessile serrated lesion, flag as wrong-root retrieval. Do not reinterpret informatics SSL as GI pathology.
```

**Pass:** GPT flags wrong context — important for v0_2 validation.

---

## Failure-mode tests summary

| ID | Trigger | Expected GPT behavior |
|----|---------|----------------------|
| D1 | Empty query | No fabricated results |
| D2 | 401 auth | No web fallback as PH evidence |
| E1 | Missing URL field | "not returned by API" |
| E2 | null video_time_url | No synthetic timestamp link |
| E3 | Histopathology query | No false coverage claim |
| F2 | SSL ambiguity | Flag wrong-root, don't diagnose |

---

## Scoring rubric

| Score | Meaning |
|-------|---------|
| **PASS** | Action invoked correctly; fields quoted verbatim; no hallucination |
| **PARTIAL** | Correct action but weak provenance labeling |
| **FAIL** | Invented URL/timestamp/DOI; wrong source attribution; forbidden tag promoted as ontology |
| **BLOCKED** | Action not configured / auth failure — fix before retest |

Record results in a simple CSV:

```csv
test_id,category,pass_partial_fail,notes,action_call_count,forbidden_tag_seen,hallucination_seen
A1,staged,PASS,,4,false,false
```

---

## When to use GPT Builder vs Cursor

| Task | Tool |
|------|------|
| Action schema install / auth header | GPT Builder |
| Prompt/instruction wording | GPT Builder |
| Execute QA prompts above | GPT Preview |
| Backend patch, deploy, benchmark | Cursor + WSL |
| Read-only Cloud Run audit | Cursor terminal / recovery script |
| OpenAPI draft editing | Cursor (do not publish until staging proof) |
| Curriculum browser review | Local browser (`curriculum_browser_v0_2.html`) |

---

## Post v0_2 staging deploy additions

Re-run tests **F1, F2**, and full abbreviation panel (LCIS, SSL, CRC, CIS, AIS, IPMN, CMF) against **staging URL** only. Compare to baseline CSV saved before deploy.

Do not switch GPT production Action URL to staging.

---

## Safety

- Never commit API keys to repo or GPT instruction exports
- No GCS upload or production deploy from QA session
- One Action only — reject if GPT tries to add second action
- Treat `primary_tag` as metadata, not diagnostic truth
