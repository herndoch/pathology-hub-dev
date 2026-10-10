# Hub maps and application entry point — October 10, 2026

Share https://map.pathologynotebook.com/. It offers three clear choices: the existing reference library, teaching topics and lecture clips. The existing interactive assistant is labeled preview. The map package can also run locally using only Python; see the [launcher and packaging guide](../frontend/pathology_hub_map_hub_v0_1/README.md).

## What this release contains

- The unified maps from PR #51, including its PR #50 ancestry, with reviewed corrections.
- One canonical deployed topic browser for textbooks, WHO and PathOutlines. Old textbook/journal routes redirect to its source filters.
- Stable topic and lecture/clip URLs, copy-link controls, browser reload/back restoration and a shared navigation bar.
- Links that open matching saved reference topics (or prepare a search) in the existing application. Source badges describe mapping provenance, not a guaranteed source-specific retrieval result.
- A standard-library local server, allowlisted ZIP builder and SHA-256 file manifest. Historical split-map source folders remain in Git for provenance.

## Standards review of #51

Pinned proposal: `96a9676582977a28da9d3f497ff4629b7dc24cb1`. The independent standards review found no definite hard AGENTS violation. Three engineering findings were corrected: duplicate branch/leaf browse identifiers, lost dual-source provenance, and duplicate standalone/hub build targets. Node IDs now include kind, source membership is independent, and the lecture builder targets the canonical deployed hub. The originals remain available in Git.

## Spec review of #51

The independent requirements review found three correctness gaps and one stale-detail issue. WHO+PathOutlines records lost PathOutlines membership; two same-path branch/topic pairs obscured data or expansion; source-specific Chat labels promised behavior that the generic query did not supply; changing filters could leave excluded details visible. These were corrected. A release recheck additionally caught branch expansion replacing the selected topic in shared links; selection now remains attached to the displayed leaf.

## Verification

Eight Python tests cover actual input/output counts, dual-source retention, unique browse IDs, collision-topic samples/children, route redirects, HTTP health/HEAD handling, restricted paths and ZIP read-back hashes. JavaScript syntax and Git whitespace checks pass.

Browser checks verified the formerly inaccessible Granulomatous topic and its eight samples; separate SCC branch and leaf controls; WHO+PathOutlines badges; exclusion of a selected topic by source filter; shared topic reload; copying the displayed leaf after branch expansion; and a lecture clip reloading at 1652.96 seconds without autoplay. The home and content page fit a 390-pixel viewport. A live DCIS reference link opened the saved reference page with source sections. These checks do not validate medical content or every external recording/figure.

The rebuilt map contains 5,554 topic leaves, 2,212 with textbook samples, 1,920 with WHO mappings and 2,618 with PathOutlines mappings. Membership overlaps; 540 leaves preserve both WHO and PathOutlines. These are map counts, not validated curriculum coverage or retrieval availability.

## Application and release boundary

This release consolidates navigation around the existing hosted reference application. It does not replace or redeploy the reference/assistant backend, claim to merge every local application experiment, or package the underlying source library. The local conversational/writing-assistant checkout retains its separate changes. A clean clone runs the delivered maps; a full application deployment still requires its configured backend, credentials and reviewed assets.

The public reference application was observed at revision `pathology-hub-chat-mvp-00135-kag`; the assistant-preview traffic tag pointed to `00127-hog`. No generation or writing-model call was made by this release validation. Lecture mappings are automated, with high-confidence clips shown by default; external media retain source access requirements.

## Operations

The maps run on the existing `pathology-hub-map` Cloud Run service in `pathology-annotation-project`, `us-central1`. Deploy a no-traffic candidate, verify its canonical routes and compare the served files to the package, then move traffic to that exact revision. The previous public revision was `pathology-hub-map-00002-flx`; rolling traffic back to it restores the previous maps. The local delivery receipt records the resulting revision, Git commit and HTTP/hash checks.
