# API Contract Addendum — Pathology Hub Evidence Search

## Live endpoint

```text
POST https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/evidence/search
Header: X-API-Key: <secret>
```

## Minimal journal probe payload

```json
{
  "query": "exact known article title or DOI",
  "sources": ["journals"],
  "max_results": 5,
  "compact": true,
  "excerpt_char_limit": 1200
}
```

## Journal proof requirements

Do not rely only on HTTP 200. Inspect:

- `source_status.journals == "ok"`
- `journal_results` not empty
- at least one result has expected `journal` / `source_name`
- `retrieval_mode`, `vector_rank`, `fts_rank`

## Auth naming

Colab secrets used:

- `HUB_API`
- `X-API-Key`

Local env vars:

- `PATHOLOGY_HUB_API_KEY`
- `HUB_API`
- `X_API_KEY`
