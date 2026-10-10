# Hosting: map.pathologynotebook.com

Date: 2026-09-02  
Service: `pathology-hub-map`  
Package: `frontend/pathology_hub_map_hub_v0_1/`

## Decision

One hub hostname for shareable education maps:

- `map.pathologynotebook.com/` — Content (textbooks+WHO+PathOut) / Lectures / Chat
- `map.pathologynotebook.com/content/` — unified tree (one Cytopathology root)
- `map.pathologynotebook.com/lectures/`
- `/textbooks/` and `/journals/` remain as source-split views
- Chat remains `chat.pathologynotebook.com`

## Why the `*.run.app` URL exists

Cloud Run always issues a default HTTPS URL. Custom `map.pathologynotebook.com` works only after DNS CNAME `map` → `ghs.googlehosted.com.` is added at the domain registrar. Same service either way — the run.app link is not a second product.

## Why not separate lecture-map / textbook-map hosts

One DNS record, one deploy, one place to send non-tech education leadership.

## DNS

CNAME `map` → `ghs.googlehosted.com.`

## Cost

Cloud Run **min instances = 0**. Idle ≈ $0. Textbook JSON is ~20MB (under Cloud Run response limits).
