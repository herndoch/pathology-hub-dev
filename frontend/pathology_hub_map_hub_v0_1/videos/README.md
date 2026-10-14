# /videos/ — Pathology Video Index

This folder is served at `/videos/`. `index.html` here is a placeholder shell.

To ship the index, copy the built page over it:

    cp <claude_joint_work>/VIDEO_INDEX_<date>.html frontend/pathology_hub_map_hub_v0_1/videos/index.html

The built page is self-contained (data embedded as JSON) and already uses the same
design tokens as `/static/tokens.css`. Add the three lines below inside its `<head>`, before the page's own `<style>`, so it
picks up the shared tokens and site navigation:

    <link rel="stylesheet" href="/static/tokens.css">
    <link rel="stylesheet" href="/static/navigation.css">
    <script src="/static/navigation.js?v=20261014.1" defer></script>

The page's own `:root` block should not repeat the palette or font variables that `tokens.css`
provides, and it should accept `?q=TERM` to pre-fill the search box (the front page submits to it).

Rebuild instructions for the page itself live with its build script
(`build_video_index_page_<date>.py`), not in this repository.
