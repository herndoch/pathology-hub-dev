# API Contract — searchEvidence v1.5.9 Curriculum Map v0.2

Version: `1.5.9-curriculum-map-v02`

Endpoint remains:

```text
POST /evidence/search
operationId: searchEvidence
```

No separate `curriculumSearch` Action is introduced.

## Supported Sources

Existing v1.5.8 sources remain supported:

```text
who
textbooks
journals
pathout
lectures
videos
```

v1.5.9 adds:

```text
curriculum
```

Aliases preserved from v1.5.8:

```text
lecture, lectures, video, videos -> lectures
pathology_outlines -> pathout
```

## Curriculum Request Examples

```json
{"query":"GYN::Ovary","sources":["curriculum"],"max_results":5,"compact":true}
```

```json
{"query":"ovary granulosa","sources":["curriculum"],"max_results":5,"compact":true}
```

Supported query patterns:

```text
GYN::Ovary
GU::Prostate
root:GYN::Ovary
tag:Granulosa
ovary granulosa
```

## Curriculum Response Additions

Responses may include:

```text
curriculum_status
curriculum_results
warnings
```

`curriculum_status` includes version, build status, forbidden visible tag count, visible record count, review queue count, rejected/hidden count, HTML URL, and GCS paths used.

`curriculum_results` include approved visible curriculum nodes only. Review queue counts may be reported, but review rows are not mixed into approved results.

## Non-Goals

- No production GPT Builder update in this phase.
- No separate GPT Action.
- No load of the 935 MB uncompressed JSONL at API startup.
- No exposure of rejected/generated/hidden tags as curriculum nodes.
