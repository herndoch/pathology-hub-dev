# Curriculum Mapping Strategy and v11

## User decisions

1. PathOut-only tags: auto-approve as local curriculum tags.
2. WHO fuzzy matches to ABPath: auto-accept at score >= 90.
3. Lecture/textbook weak chunks: use max-distance inheritance.
4. Chunks with no prior meaningful tag: remain vector-searchable but disappear from tag browsing/curriculum maps.
5. Hold off on secondary curriculum facets.
6. Keep PathOut-only local tags rather than forcing every entity into ABPath.

## v11 notebook

Included:

```text
reference_artifacts/pathology_hub_curriculum_tag_hardening_v11_package.zip
notebooks/Pathology_Hub_Curriculum_Tag_Hardening_v11_SINGLE_NOTEBOOK.ipynb
```

Defaults:

```python
PROMOTION_MODE = "backup_replace_live"
RESTART_CLOUD_RUN_AFTER_PROMOTION = True
RUN_API_PROOF = True
WHO_FUZZY_ACCEPT_THRESHOLD = 90
MAX_LECTURE_INHERIT_GAP_SEC = 600
MAX_LECTURE_INHERIT_ROW_GAP = 12
MAX_TEXTBOOK_INHERIT_PAGE_GAP = 2
MAX_TEXTBOOK_INHERIT_ROW_GAP = 25
```

## Status

v11 was generated but not run/proven. Do not mark live until output ZIP/health/API proof is inspected.
