# Decisions Log Patch — Governed Curriculum Tags

1. ABPath tags are gold/source-truth.
2. WHO processed JSON tags should be fuzzy-mapped to ABPath; auto-accept threshold for v11 is score >= 90.
3. PathOut tags are auto-approved local curriculum tags unless they hit obvious junk/root-error rules.
4. Lecture/textbook-generated ontology tags are not approved as curriculum tags merely because they exist.
5. Weak-context lecture/textbook chunks should inherit the most recent meaningful tag within max sequence limits.
6. Chunks with no approved tag and no valid inheritance context remain governed untagged and are excluded from tag browsing/curriculum maps.
7. Secondary curriculum facets are deferred.
8. Raw PDFs/videos are never deleted; only derived metadata/figure-map records may be excluded after audit.
