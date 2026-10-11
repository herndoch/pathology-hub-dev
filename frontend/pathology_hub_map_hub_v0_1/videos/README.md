# /videos/ — Pathology Video Index

This folder is served at `/videos/`. `index.html` here is a placeholder shell.

To ship the index, copy the built page over it:

    cp <claude_joint_work>/VIDEO_INDEX_<date>.html frontend/pathology_hub_map_hub_v0_1/videos/index.html

The built page is self-contained (data embedded as JSON) and already uses the same
design tokens as `/static/tokens.css`. Add the two lines below inside its `<head>` so it
picks up the shared site navigation:

    <link rel="stylesheet" href="/static/navigation.css">
    <script src="/static/navigation.js?v=20261011.1" defer></script>

Rebuild instructions for the page itself live with its build script
(`build_video_index_page_<date>.py`), not in this repository.
