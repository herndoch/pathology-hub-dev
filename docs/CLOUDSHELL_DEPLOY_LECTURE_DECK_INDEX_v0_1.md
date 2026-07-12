# Cloud Shell: deploy lecture-index refresh (candidate → verify → traffic)

**Why:** `gcloud run services update … LECTURE_MANIFEST_REFRESH_TS` alone keeps serving
revision `00029-rnt` with the old **42069** lecture FAISS baked under `/tmp`.
GCS already has the **718**-chunk deck index. You need a **source deploy** that
includes the force-redownload patch.

**Source:** `backend/pathology_hub_v04_live_recovered/` on branch
`cursor/pathology-hub-chat-mvp` (PR #14).

Ignore the Gaia / Regional Access Boundary noise if deploy still says `Done.`

---

## 0) Get the patched code in Cloud Shell

```bash
cd ~
git clone https://github.com/herndoch/pathology-hub-dev.git
cd pathology-hub-dev
git fetch origin cursor/pathology-hub-chat-mvp
git checkout cursor/pathology-hub-chat-mvp
```

(Or `git pull` if you already have the repo.)

Confirm patch:

```bash
grep -n "LECTURE_MANIFEST_REFRESH_TS forces" backend/pathology_hub_v04_live_recovered/app.py
```

---

## 1) Deploy **0% traffic** candidate (safe)

```bash
cd ~/pathology-hub-dev

gcloud run deploy pathology-hub-v04 \
  --source=backend/pathology_hub_v04_live_recovered \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --no-traffic \
  --tag=lecture-deck-v01 \
  --cpu=4 --memory=12Gi \
  --timeout=300 --concurrency=160 --max-instances=10 \
  --min-instances=1 \
  --env-vars-file=audits/prod_deploy_20260712_lecture_refresh/prod_env_vars.yaml \
  --set-secrets="PATHOLOGY_HUB_API_KEY=pathology-hub-api-key:latest,OPENAI_API_KEY=OPEN_AI_KEY_01:latest,FIGURE_PROXY_SECRET=pathology-hub-api-key:latest"
```

Wait until it finishes. Note the new revision name (should be **00030+**, not 00029).

Tagged URL form:

`https://lecture-deck-v01---pathology-hub-v04-830130787988.us-central1.run.app/health`

(If your project uses the `vorn5q2kga` host form, use that instead — Cloud Shell will print the tagged URL.)

---

## 2) Verify candidate before any traffic shift

```bash
# replace URL with the tagged URL printed by deploy
curl -sS "https://lecture-deck-v01---pathology-hub-v04-830130787988.us-central1.run.app/health" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); m=d.get('lecture_vector_manifest_summary') or {}; print('records', m.get('record_count') or d.get('lecture_vector_records')); print('schema', m.get('schema_version')); print('faiss_bytes', d.get('lecture_faiss_size_bytes'))"
```

**Pass:** `records` ≈ **718**, `schema` contains `deck_packages`, `faiss_bytes` ≈ **4.4e6** (not ~258e6).

---

## 3) Only if step 2 passes — shift production traffic

```bash
# replace NEW_REV with the revision from step 1, e.g. pathology-hub-v04-00030-xxx
gcloud run services update-traffic pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --to-revisions=NEW_REV=100
```

Then check public `/health` the same way — expect **718**.

---

## Rollback

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --to-revisions=pathology-hub-v04-00029-rnt=100
```
