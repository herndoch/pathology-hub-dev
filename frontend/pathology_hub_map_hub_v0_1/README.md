# Pathology Knowledge Hub: shareable front door

Open https://map.pathologynotebook.com/ for the reference library, teaching topics, lecture clips and the separate assistant preview.

## Run locally

From the repository root, with Python 3.11 or later:

```sh
python3 frontend/pathology_hub_map_hub_v0_1/serve.py
```

Open http://127.0.0.1:8770/. No packages or credentials are needed for map browsing. Recordings, figures and the hosted reference app need network access and retain their own access requirements.

## Share a selection

Select a teaching topic and use **Copy topic link**. In Lecture clips, choose a lecture or clip and use **Copy lecture link**. The URL preserves the selection, filter and clip timestamp. Reloading restores it without autoplay.

The reference-library link opens a matching saved topic or prepares a topic search in the existing hosted app. It does not promise a specific WHO or PathOutlines result. The assistant preview remains a separate existing service mode.

## One maintained map implementation

| Route | Content |
|---|---|
| `/` | Front door, videos first |
| `/videos/` | Pathology Video Index (self-contained page; see `videos/README.md`) |
| `/content/` | Textbook, WHO and PathOutlines topic tree |
| `/lectures/` | Lecture topics and timestamped clips |
| `/textbooks/` | Redirect to the textbook filter |
| `/journals/` | Redirect to the WHO/PathOutlines filter |
| `/app/` | Redirect to the hosted reference library |

Older standalone map folders are preserved as historical inputs, not deployed as competing views. The lecture builder now targets this hub. Rebuild the content tree with `python3 scripts/build_unified_content_map_v0_1.py`; its audit records inputs, hashes, counts and limits. Rebuilding lectures requires the original configured source docstore.

## Package and check

```sh
python3 -m unittest discover -s tests -p test_map_release.py -v
python3 scripts/package_hub_maps.py --output /tmp/pathology-hub-maps.zip
```

The ZIP contains the same launcher and static files, plus a SHA-256 manifest. Extract it and run `python serve.py` (Windows: `py serve.py`). It links to the hosted application; it does not bundle its backend or source library.

## One visual system

All pages load `static/tokens.css` and the shared navigation bar from `static/navigation.js`. The tokens (palette, type, radii, shadows, search bar, pill and card classes) are copied from the reference library at chat.pathologynotebook.com (its `landing_ui.css`), so the hub reads as the same product; when that site's look changes, update `tokens.css` to match. There is no dark mode, to match the reference library. The front page and the video index share the same six source labels: Full, Partial, Video not yet checked, Pathology Outlines, Webpage, No free source yet. Keep those names and the dated "playable as of" line consistent across pages.

## Hosting

Cloud Run service: `pathology-hub-map`, project `pathology-annotation-project`, region `us-central1`. The Dockerfile serves the same canonical folders. See [release notes](../../docs/HUB_RELEASE_20261010.md) for review findings, validation and the application boundary.
