# Current Master Spine Patch — Governed Tag Cleanup v10.5 and Codex Transition

Pathology Hub now has governed tag cleanup v10.5 promoted to backend-consumed metadata paths and API-proven for standard `searchEvidence` calls. Authenticated test queries for lectures, combined WHO/textbooks/PathOut/journals, and textbooks/PathOut returned HTTP 200 with zero forbidden lecture/textbook artifact primary-tags.

The current live Action remains `searchEvidence` / `POST /evidence/search`. Do not mark explicit tag browsing/search-by-tag modes as live until a backend tag-runtime patch is deployed and audited.

WHO processed tag-bearing rows are confirmed at `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json`. PathOut AP-diagnostic tags are treated as approved local curriculum tags. Lecture/textbook generated artifact tags are excluded from governed visible tag surfaces.
