# Colab TODO — upload lecture deck frames / associated pics

**Owner:** operator (you) via Colab  
**Not required for:** convert → tag → consolidate sidecar path

## Why separate

Deck sidecars (`frames.jsonl`) already store timestamps + `video_time_url`.  
Frame JPG bytes can land later without re-chunking.

## Suggested destinations (pick one per package; do not overwrite legacy slide libraries casually)

1. Sidecar asset prefix (preferred for chatgpt_readable frames):

`gs://pathology_hub/02_normalized/lectures/deck_packages/<package_id>/frames/`

2. Legacy-style asset library only if intentionally mirroring old layout:

`gs://pathology-hub-0/_asset_library/lectures/<CanonicalLectureStem>/`

Keep chatgpt_readable change-detected frames distinct from legacy slide exports unless you deliberately unify them.

## Minimal Colab sketch

```python
from google.cloud import storage
import zipfile, tempfile
from pathlib import Path

client = storage.Client(project="pathology-annotation-project")
zip_blob = client.bucket("pathology_hub").blob("Heme_SH_Aggressive_B_Cell_chatgpt_readable_package.zip")
package_id = "heme_sh_aggressive_b_cell_v0_1"

with tempfile.TemporaryDirectory() as tmp:
    zpath = Path(tmp) / "pkg.zip"
    zip_blob.download_to_filename(zpath)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(tmp)
    frames = list(Path(tmp).rglob("frames/*.jpg")) + list(Path(tmp).rglob("frames/*.jpeg"))
    dest_bucket = client.bucket("pathology_hub")
    for fp in frames:
        dest = f"02_normalized/lectures/deck_packages/{package_id}/frames/{fp.name}"
        dest_bucket.blob(dest).upload_from_filename(str(fp))
        print("uploaded", dest)
```

## After upload

Write a tiny audit JSON (`schema_version`, input zip, output prefix, frame count, known limitations) under:

`gs://pathology_hub/06_audits/lectures/deck_packages/`

Do not claim frames are API-exposed until something serves them.
