# Handoff: pathCast #PATHBOARDS YouTube ingest

## Can the agent scour YouTube?

**Yes for discovery** (playlists, titles, IDs, URLs).  
**No for download** (bot/age gates on cloud IPs) — Colab queue still required.

## Source

- Channel: [pathCast](https://www.youtube.com/@pathCast) (`UCVxosS9hPP3ikMQXAE9Pamw`)
- Playlist: [#PATHBOARDS](https://www.youtube.com/playlist?list=PL4GDLmrdXtfT-w9Q93NlvptjuZ1QYfzYB) — **29** videos
- Inventory: `docs/pathcast_pathboards_inventory_v0_1.json`
- Colab QUEUE (gate-ready subset, **20** rows): `notebooks/YouTube_Lecture_Queue_Colab_v0_1.ipynb`

## Board-review core (#PATHBOARDS branded, gate-ready)

| Root | Video |
|------|-------|
| Breast | High Yield Breast Pathology for Boards |
| Heme | Hematopathology Parts 1–2; Molecular Part 2 (hematolymphoid) |
| GU | High Yield GU; Kidney Parts 1–2 |
| Cyto | High Yield Cytopathology |
| Pulm → Thorax_Mediastinum | High Yield Pulmonary |
| Skin | High Yield Dermpath (**no leaf embeddings yet** — not in Colab QUEUE) |
| Molecular Part 1 / Transfusion | not gate-ready yet |

## Operator loop

1. Open Colab queue notebook (badge in notebook)
2. `INDEX = 0` … bump after each **delete runtime**
3. Paste `PACKAGE_ID` to agent → gate → periodic FAISS promote

## Skipped

- Damron breast (age-restricted, non-pathCast)
- Gardner + Cipriani already live

## Follow-ups

- Expand inventory to other pathCast playlists (`#BREASTPATH`, `#GIPATH`, …) — 40 playlists on channel
- Build Skin / Molecular / BloodBank leaf embeddings to unlock remaining PATHBOARDS titles
