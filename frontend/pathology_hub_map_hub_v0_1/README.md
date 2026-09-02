# Pathology Notebook — Maps hub

Unified navigable HTML maps for education leadership.

## Preferred URL

`https://map.pathologynotebook.com`

| Path | Map |
|------|-----|
| `/` | Hub (choose a map or open Chat) |
| `/lectures/` | Lecture → topics tree |
| `/textbooks/` | Textbook OncoTree |
| `/journals/` | WHO + PathologyOutlines tree |
| Chat | https://chat.pathologynotebook.com |

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
# optional: assemble www layout by serving this folder directly
python3 -m http.server 8770
```
