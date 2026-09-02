# Hosting: map.pathologynotebook.com

Date: 2026-09-02  
Service: `pathology-hub-map`  
Package: `frontend/pathology_hub_map_hub_v0_1/`

## Decision

One hub hostname for shareable education maps:

- `map.pathologynotebook.com/` — choose Lectures / Textbooks / Journals (WHO+PathOut) / Chat
- `map.pathologynotebook.com/lectures/`
- `map.pathologynotebook.com/textbooks/`
- `map.pathologynotebook.com/journals/`
- Chat remains `chat.pathologynotebook.com`

## Why not separate lecture-map / textbook-map hosts

One DNS record, one deploy, one place to send non-tech education leadership.

## DNS

CNAME `map` → `ghs.googlehosted.com.`

## Cost

Cloud Run **min instances = 0**. Idle ≈ $0. Textbook JSON is ~20MB (under Cloud Run response limits).
