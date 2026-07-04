# Tag Policy and Governance

## Provenance categories

```text
gold_abpath
who_mapped_to_abpath
approved_pathout_local
manual_approved_local
inherited_context
rejected_generated
excluded_junk
unmapped_no_context
```

## PathOut

Auto-approve PathOut tags as local curriculum tags unless obvious artifacts/root errors.

## WHO

Use `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json`. Fuzzy-match WHO tags to ABPath and auto-accept score >= 90.

## Lectures/textbooks

Do not let them invent ontology. Use exact/strong match, PathOut/ABPath/WHO mapping, sequence inheritance, or governed untagged.

## v11 inheritance limits

```text
Lecture max inheritance: 600 seconds / 12 rows
Textbook max inheritance: 2 pages / 25 rows
```

## Forbidden visible tag patterns

```text
::Lectures::
::Textbooks::
Slide_
Page_
Digital_Pathology_Slide
Pathology_Slide
Benign_Cystic_Neck_Mass_Case_01
::Error
```
