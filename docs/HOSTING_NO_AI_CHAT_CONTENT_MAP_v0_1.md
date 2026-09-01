# Hosting recommendation: Chat no-AI content map

Date: 2026-09-01  
Package: `frontend/chat_no_ai_content_map_v0_1/`  
Related: `docs/DEPLOY_CHAT_MVP_HTTPS_CLOUD_RUN_v0_1.md`

## Decision

**Preferred public URL:** `https://no-ai-chat.pathologynotebook.com`

### Why this over path-on-chat

- Chat MVP (`chat.pathologynotebook.com`) is a **FastAPI Cloud Run** service with
  secrets, backend API calls, and its own deploy/scale lifecycle.
- The no-AI map is a **static** prebuild inventory. Hosting it under
  `chat.…/no-ai` either bloats the chat service or requires a shared path-aware
  front door (LB / Cloudflare / Firebase rewrites) that does not exist yet.
- Subdomain mapping matches how `chat.` already works: hostname → one host,
  managed cert, no path coupling.

### Options considered

| URL | Use? |
|-----|------|
| `no-ai-chat.pathologynotebook.com` | **Yes** — default |
| `chat.pathologynotebook.com/no-ai` | No for now |
| `pathologynotebook.com/chat-no-ai` | Later redirect only, after apex path routing exists |

### Suggested deploy shape (when ready)

1. Host static files from `frontend/chat_no_ai_content_map_v0_1/` (GCS website,
   Firebase Hosting, Cloudflare Pages, or a tiny nginx Cloud Run service).
2. Map custom domain `no-ai-chat.pathologynotebook.com` + managed cert.
3. Optional later: apex rewrite/redirect
   `pathologynotebook.com/chat-no-ai` → `https://no-ai-chat.pathologynotebook.com/`.

Do not claim the hostname is live until DNS + mapping are verified.
