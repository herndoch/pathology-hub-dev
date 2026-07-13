# Plan — put Heme Anki builder authority files on GCS (v0_1)

Date: 2026-07-13  
Status: **scaffolding published; TNK + WHO pending your laptop upload**

## Canonical prefix

```text
gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/
```

| Path | Status |
|------|--------|
| `shared/Pathology_Anki_Contextual_Cloze_SOP_v1_1.pdf` | ✅ uploaded |
| `shared/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip` | ❌ pending you |
| `shared/WHO_WHO_JSON_PROCESSED_HEME.json` | ❌ pending you |
| `shared/accepted_tags.json` | ❌ pending (extract from TNK zip) |
| `docs/HANDOFF_*.md` | ✅ uploaded |
| `series_index.json` | ✅ pointers to existing lecture ZIPs + sidecars |
| `audit.json` | ✅ |

Lecture ZIPs / sidecars stay where they already are (not duplicated). `series_index.json` points at them.

## What you run locally (the only missing pieces)

```bash
gsutil cp /path/to/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip \
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/

gsutil cp /path/to/WHO_WHO_JSON_PROCESSED_HEME.json \
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/

# optional but convenient — extract from TNK package first
gsutil cp /path/to/accepted_tags.json \
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/
```

Or:

```bash
python3 scripts/publish_heme_anki_builder_gcs_bundle_v0_1.py \
  --tnk-zip /path/to/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip \
  --who-json /path/to/WHO_WHO_JSON_PROCESSED_HEME.json \
  --accepted-tags /path/to/accepted_tags.json
```

## Why this layout

- Keeps Anki builder inputs separate from Evidence RAG / lecture vector indexes
- Does not overwrite original lecture packages
- One shared style/WHO/SOP set for all 17 series
- Audit required before/after publish (`audit.json` + `06_audits/anki/...`)

## ChatGPT note

GCS URIs help *you* assemble downloads. ChatGPT still needs the files **attached/uploaded** unless you give it a connector that can read that bucket. Putting files on GCS does not automatically make them visible inside ChatGPT.
