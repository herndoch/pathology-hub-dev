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

1. Deploy static shell: `frontend/chat_no_ai_content_map_v0_1/scripts/deploy_cloud_run_https_v0_1.sh`
   (`MAP_DOMAIN=1` creates the Cloud Run domain mapping).
2. Serve the large index from
   `gs://pathology_hub/api_exposed/chat_no_ai_content_map_v0_1/` (public HTTPS;
   gzip object preferred). Cloud Run HTTP responses are capped ~32MiB, so do
   not serve the uncompressed 37MB JSON through Cloud Run.
3. DNS: CNAME `no-ai-chat` → `ghs.googlehosted.com.` (same as `chat`).
4. Optional later: apex rewrite/redirect
   `pathologynotebook.com/chat-no-ai` → `https://no-ai-chat.pathologynotebook.com/`.

Custom domain is Ready only after DNS + managed cert provision.
Live run.app URL works immediately after deploy.
