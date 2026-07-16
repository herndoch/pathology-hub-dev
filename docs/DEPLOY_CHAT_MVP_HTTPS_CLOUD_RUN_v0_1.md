# Deploy Chat MVP on HTTPS (Cloud Run) v0_1

Date: 2026-07-16  
Service: `pathology-hub-chat-mvp`  
Project: `pathology-annotation-project`  
Region: `us-central1`

## Why Cloud Run

The Chat MVP is a FastAPI app (not a static site). Cloud Run gives:

- HTTPS on `https://<service>-…run.app` (Google-managed cert)
- Secret Manager injection for API keys
- Same project / region pattern as `pathology-hub-v04`

## One-command deploy

```bash
cd frontend/pathology_hub_chat_mvp
chmod +x scripts/deploy_cloud_run_https_v0_1.sh
./scripts/deploy_cloud_run_https_v0_1.sh
```

Prints the HTTPS URL when finished. Smoke:

```bash
curl -sS "$URL/api/health" | python3 -m json.tool
```

## What it wires

| Item | Value |
|------|--------|
| Dockerfile | `frontend/pathology_hub_chat_mvp/Dockerfile` |
| Listen | `0.0.0.0:$PORT` (8080) |
| Backend API | `PATHOLOGY_HUB_API_URL` → live `pathology-hub-v04` |
| Secrets | `OPENAI_API_KEY` ← secret `OPENAI`; `PATHOLOGY_HUB_API_KEY` ← secret `PATHOLOGY_HUB_API_KEY` |
| Auth | public by default (`ALLOW_UNAUTHENTICATED=1`) |

Private deploy:

```bash
ALLOW_UNAUTHENTICATED=0 ./scripts/deploy_cloud_run_https_v0_1.sh
```

## Known limitations / safety

- Public UI can spend OpenAI + Hub API quota — use private mode or IAP if this is not intentional.
- Custom domain (optional later): Cloud Run domain mapping + managed cert.
- This does **not** replace GPT Builder / Custom GPT; separate workstream.
- Do not deploy on top of `pathology-hub-v04` — keep a separate service name.

## Rollback

```bash
gcloud run services update-traffic pathology-hub-chat-mvp \
  --region=us-central1 \
  --to-revisions=REVISION=100
# or delete the service if the MVP should go offline
gcloud run services delete pathology-hub-chat-mvp --region=us-central1
```
