# Pathology Notebook — Maps hub

Unified navigable HTML maps for education leadership.

## Preferred URL

`https://map.pathologynotebook.com`

Until DNS is set, use the Cloud Run `*.run.app` URL for the same service (same content).

| Path | Map |
|------|-----|
| `/` | Hub (Content · Lectures · Chat) |
| `/content/` | **Textbooks + WHO + PathOut** in one tree (one Cytopathology root) |
| `/lectures/` | Lecture → topics tree |
| `/textbooks/` | Textbooks-only OncoTree (legacy split) |
| `/journals/` | WHO + PathOut only (legacy split) |
| Chat | https://chat.pathologynotebook.com |

## Rebuild unified content JSON

```bash
python3 scripts/build_unified_content_map_v0_1.py
```

## DNS (one record)

| Host | Type | Value |
|------|------|-------|
| `map` | CNAME | `ghs.googlehosted.com.` |

## Deploy

```bash
cd frontend/pathology_hub_map_hub_v0_1
MAP_DOMAIN=1 ./scripts/deploy_cloud_run_https_v0_1.sh
```

Service: `pathology-hub-map` · **min instances 0** (idle ≈ $0)

## Local

```bash
cd frontend/pathology_hub_map_hub_v0_1
python3 -m http.server 8770
# open http://127.0.0.1:8770/content/
```
