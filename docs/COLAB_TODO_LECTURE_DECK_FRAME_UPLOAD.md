# Colab: Heme SH lecture frames → Pathology Hub GCS

**Drive source:** `3-Resources/Heme/Heme_SH_Lectures`  
**GCS dest (canonical for chatgpt_readable frames):**

`gs://pathology_hub/02_normalized/lectures/deck_packages/<package_id>/frames/`

**Also optional:** upload canonical MP4s to

`gs://pathology-hub-0/source_videos/<CanonicalName>.mp4`

Do **not** dump these into legacy `_asset_library/lectures/Other_*` unless you intentionally want that mirror.

---

## Cell 1 — auth + mounts

```python
from google.colab import auth, drive
auth.authenticate_user()
drive.mount("/content/drive")

from google.cloud import storage
import json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path

PROJECT = "pathology-annotation-project"
HUB_BUCKET = "pathology_hub"
VIDEO_BUCKET = "pathology-hub-0"

# Adjust if your Drive layout differs (Shared drive vs My Drive)
DRIVE_ROOT_CANDIDATES = [
    Path("/content/drive/MyDrive/3-Resources/Heme/Heme_SH_Lectures"),
    Path("/content/drive/MyDrive/3-Resources/Heme/Heme_SH_Lectures".replace("3-Resources", "3 - Resources")),
]

client = storage.Client(project=PROJECT)
hub = client.bucket(HUB_BUCKET)
videos = client.bucket(VIDEO_BUCKET)

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "lecture"

DRIVE_ROOT = next((p for p in DRIVE_ROOT_CANDIDATES if p.is_dir()), None)
assert DRIVE_ROOT is not None, f"Drive folder not found. Tried: {DRIVE_ROOT_CANDIDATES}"
print("DRIVE_ROOT =", DRIVE_ROOT)
```

---

## Cell 2 — discover chatgpt_readable packages on Drive

Looks for any folder that has both `lecture_index.json` and a `frames/` dir (matches your nested `.../chatgpt_readable_package/` layout and `*_extracted` trees).

```python
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

def find_packages(root: Path):
    found = []
    for index_path in root.rglob("lecture_index.json"):
        pkg_dir = index_path.parent
        frames_dir = pkg_dir / "frames"
        if not frames_dir.is_dir():
            # sometimes frames sit beside a nested chatgpt_readable_package
            alt = list(pkg_dir.glob("**/frames"))
            frames_dir = alt[0] if alt else None
        if frames_dir is None or not frames_dir.is_dir():
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        video_file = Path(str(index.get("video_file") or pkg_dir.name)).name
        if not video_file.endswith(".mp4"):
            # recover from parent names like Heme_SH_PT_LPD_extracted
            stem = re.sub(r"_(extracted|chatgpt_readable_package|package).*$", "", pkg_dir.name, flags=re.I)
            stem = re.sub(r"_(extracted|chatgpt_readable_package|package).*$", "", pkg_dir.parent.name, flags=re.I) or stem
            video_file = f"{stem}.mp4" if stem else video_file
        canonical = video_file if video_file.endswith(".mp4") else f"{video_file}.mp4"
        package_id = f"{slugify(Path(canonical).stem)}_v0_1"
        frame_files = sorted(
            p for p in frames_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMG_EXT
        )
        found.append({
            "pkg_dir": pkg_dir,
            "index_path": index_path,
            "frames_dir": frames_dir,
            "canonical_mp4": canonical,
            "package_id": package_id,
            "duration_seconds": index.get("duration_seconds"),
            "frame_count_index": len(index.get("frames") or []),
            "frame_files": frame_files,
        })
    # de-dupe by package_id (prefer more frames)
    best = {}
    for row in found:
        prev = best.get(row["package_id"])
        if prev is None or len(row["frame_files"]) > len(prev["frame_files"]):
            best[row["package_id"]] = row
    return list(best.values())

packages = find_packages(DRIVE_ROOT)
print(f"found {len(packages)} packages")
for p in packages:
    print(f"  {p['package_id']:40s}  frames={len(p['frame_files']):4d}  mp4={p['canonical_mp4']}  src={p['pkg_dir']}")
```

---

## Cell 3 — upload frames to deck_packages (the right spot)

```python
DRY_RUN = False  # set True first if you want a rehearsal
SKIP_EXISTING = True

upload_rows = []
for pkg in packages:
    package_id = pkg["package_id"]
    uploaded = 0
    skipped = 0
    for fp in pkg["frame_files"]:
        dest_key = f"02_normalized/lectures/deck_packages/{package_id}/frames/{fp.name}"
        blob = hub.blob(dest_key)
        if SKIP_EXISTING and blob.exists():
            skipped += 1
            continue
        if DRY_RUN:
            print("DRY", dest_key)
        else:
            blob.upload_from_filename(str(fp), content_type="image/jpeg" if fp.suffix.lower() in {".jpg", ".jpeg"} else None)
        uploaded += 1
    upload_rows.append({
        "package_id": package_id,
        "canonical_mp4": pkg["canonical_mp4"],
        "drive_pkg_dir": str(pkg["pkg_dir"]),
        "gcs_frames_prefix": f"gs://{HUB_BUCKET}/02_normalized/lectures/deck_packages/{package_id}/frames/",
        "frames_on_disk": len(pkg["frame_files"]),
        "uploaded": uploaded,
        "skipped_existing": skipped,
    })
    print(package_id, "uploaded", uploaded, "skipped", skipped)

upload_rows
```

---

## Cell 4 — optional: upload canonical MP4s (pending-name policy)

Only uploads if missing. Uses the **canonical** lecture name (e.g. `Heme_SH_Aggressive_B_Cell.mp4`), never `Other_Heme_*`.

```python
UPLOAD_MP4S = True
DRY_RUN_MP4 = False

mp4_rows = []
# Prefer top-level MP4s in Heme_SH_Lectures
mp4s = sorted(DRIVE_ROOT.glob("Heme_SH_*.mp4"))
print(f"top-level mp4s: {len(mp4s)}")

for mp4 in mp4s:
    dest_key = f"source_videos/{mp4.name}"
    blob = videos.blob(dest_key)
    exists = blob.exists()
    if exists:
        mp4_rows.append({"file": mp4.name, "status": "already_present", "gcs": f"gs://{VIDEO_BUCKET}/{dest_key}"})
        continue
    if not UPLOAD_MP4S:
        mp4_rows.append({"file": mp4.name, "status": "missing_skipped", "gcs": f"gs://{VIDEO_BUCKET}/{dest_key}"})
        continue
    if DRY_RUN_MP4:
        print("DRY MP4", dest_key)
        status = "dry_run"
    else:
        print("uploading MP4", mp4.name, f"({mp4.stat().st_size/1e6:.1f} MB) …")
        blob.upload_from_filename(str(mp4), content_type="video/mp4")
        status = "uploaded"
    mp4_rows.append({"file": mp4.name, "status": status, "gcs": f"gs://{VIDEO_BUCKET}/{dest_key}"})

mp4_rows
```

---

## Cell 5 — write audit JSON to GCS

```python
audit = {
    "schema_version": "lecture_deck_frame_upload_audit.v0_1",
    "created_at_utc": utc_now(),
    "input_paths": [str(DRIVE_ROOT)],
    "output_paths": [
        f"gs://{HUB_BUCKET}/02_normalized/lectures/deck_packages/*/frames/",
        f"gs://{VIDEO_BUCKET}/source_videos/Heme_SH_*.mp4",
    ],
    "counts": {
        "packages": len(upload_rows),
        "frames_uploaded": sum(r["uploaded"] for r in upload_rows),
        "frames_skipped_existing": sum(r["skipped_existing"] for r in upload_rows),
        "mp4_rows": len(mp4_rows),
    },
    "packages": upload_rows,
    "mp4s": mp4_rows,
    "known_limitations": [
        "Uploads chatgpt_readable change-detected frames only — not legacy _asset_library slide exports.",
        "Does not rebuild FAISS/docstore or claim API exposure.",
        "package_id uses slug(canonical_stem)_v0_1; keep in sync with deck sidecar converter.",
    ],
}

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
audit_key = f"06_audits/lectures/deck_packages/frame_upload_{stamp}/audit.json"
hub.blob(audit_key).upload_from_string(
    json.dumps(audit, indent=2) + "\n",
    content_type="application/json",
)
print("audit =>", f"gs://{HUB_BUCKET}/{audit_key}")
```

---

## Mapping cheat sheet

| Drive | GCS |
|-------|-----|
| `.../chatgpt_readable_package/frames/*.jpg` | `gs://pathology_hub/02_normalized/lectures/deck_packages/<slug>_v0_1/frames/` |
| `Heme_SH_*.mp4` | `gs://pathology-hub-0/source_videos/Heme_SH_*.mp4` |
| zip already on bucket root | converter/batch script (separate); frames can still come from Drive or zip |

If a lecture only has an MP4 in Drive and **no** `chatgpt_readable_package/frames` yet, this notebook will not invent frames — run your extraction Colab first (same pattern as `Heme_SH_Aggressive_B_Cell_Extraction_Colab_Drive_Outp...`).
