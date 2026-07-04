# Tag Governance / Curriculum Mapping Handoff

## Current user-approved policy

- PathOut tags are mostly good and should be auto-approved as local curriculum tags unless they are obvious junk/root errors.
- WHO processed tags should fuzzy-map to ABPath and auto-accept score >= 90.
- Lecture/textbook generated tags are the main problem.
- Tags containing `::Lectures::`, `::Textbooks::`, slide/page/file artifacts, or lecture-title-only hierarchy should not become ontology.
- Weak lecture/textbook chunks should inherit the most recent meaningful tag within the same sequence and max distance.
- If no prior meaningful context exists, set governed tag `__UNMAPPED__`; keep vector-searchable but hide from tag browsing/curriculum map.
- Hold off on secondary facets for now.
- Keep PathOut-only local tags and approve them.

## Needed proof before claiming live

A curriculum hardening notebook/package was discussed/generated conceptually. Do not claim it is live unless its run report/audit ZIP is available and promotion is proven.

## What Codex should do if resuming this workstream

1. Read current live tag audits/manifests from GCS.
2. Build a small sample report of lecture/textbook tags still containing junk patterns.
3. Implement inheritance with explicit distance caps and audit inherited distance.
4. Do not expose unapproved generated tags in tag browser/API facets.
5. Keep raw source files; modify governed metadata/index only with backups.
