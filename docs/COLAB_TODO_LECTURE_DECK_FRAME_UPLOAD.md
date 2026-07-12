# Colab: Heme SH lecture frames → pathology-hub-0 slide images

**Drive source:** `3-Resources/Heme/Heme_SH_Lectures`  
**GCS dest (legacy-consistent — canonical):**

`gs://pathology-hub-0/_asset_library/lectures/<CanonicalStem>/<CanonicalStem>_slide_NNNN.jpg`

Example:

`gs://pathology-hub-0/_asset_library/lectures/Heme_SH_Aggressive_B_Cell/Heme_SH_Aggressive_B_Cell_slide_0000.jpg`

Same layout as existing lectures (`BST_Lecture_1_Grossing/BST_Lecture_1_Grossing_slide_0000.jpg`).  
Use **canonical** `Heme_SH_*` stems — not legacy `Other_Heme_*`.

**Also optional:** upload canonical MP4s to

`gs://pathology-hub-0/source_videos/<CanonicalName>.mp4`

Deck sidecar `frames.jsonl` rows already point at these `_asset_library` paths via `image_path` / `asset_gcs_uri`.

---

## Cell 1 — auth + mounts

```python
from google.colab import auth, drive
auth.authenticate_user()
drive.mount("/content/drive")

from google.cloud import storage
import json, re
from datetime import datetime, timezone
from pathlib import Path

PROJECT = "pathology-annotation-project"
HUB_BUCKET = "pathology_hub"          # audits only
VIDEO_BUCKET = "pathology-hub-0"      # MP4s + slide images
ASSET_PREFIX = "_asset_library/lectures/"

DRIVE_ROOT_CANDIDATES = [
    Path("/content/drive/MyDrive/3-Resources/Heme/Heme_SH_Lectures"),
    Path("/content/drive/MyDrive/3-Resources/Heme/Heme_SH_Lectures".replace("3-Resources", "3 - Resources")),
]

client = storage.Client(project=PROJECT)
hub = client.bucket(HUB_BUCKET)
assets = client.bucket(VIDEO_BUCKET)
videos = assets  # same bucket

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "lecture"

def legacy_slide_name(lecture_stem: str, frame_index: int) -> str:
    return f"{lecture_stem}_slide_{int(frame_index):04d}.jpg"

def legacy_asset_key(lecture_stem: str, frame_index: int) -> str:
    fname = legacy_slide_name(lecture_stem, frame_index)
    return f"{ASSET_PREFIX}{lecture_stem}/{fname}"

DRIVE_ROOT = next((p for p in DRIVE_ROOT_CANDIDATES if p.is_dir()), None)
assert DRIVE_ROOT is not None, f"Drive folder not found. Tried: {DRIVE_ROOT_CANDIDATES}"
print("DRIVE_ROOT =", DRIVE_ROOT)
```

---

## Cell 2 — discover chatgpt_readable packages on Drive

```python
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

def find_packages(root: Path):
    found = []
    for index_path in root.rglob("lecture_index.json"):
        pkg_dir = index_path.parent
        frames_dir = pkg_dir / "frames"
        if not frames_dir.is_dir():
            alt = list(pkg_dir.glob("**/frames"))
            frames_dir = alt[0] if alt else None
        if frames_dir is None or not frames_dir.is_dir():
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        video_file = Path(str(index.get("video_file") or pkg_dir.name)).name
        if not video_file.endswith(".mp4"):
            stem = re.sub(r"_(extracted|chatgpt_readable_package|package).*$", "", pkg_dir.name, flags=re.I)
            stem = re.sub(r"_(extracted|chatgpt_readable_package|package).*$", "", pkg_dir.parent.name, flags=re.I) or stem
            video_file = f"{stem}.mp4" if stem else video_file
        canonical = video_file if video_file.endswith(".mp4") else f"{video_file}.mp4"
        lecture_stem = Path(canonical).stem
        package_id = f"{slugify(lecture_stem)}_v0_1"

        # Map original frame filename -> frame index from lecture_index
        frame_entries = index.get("frames") or []
        by_file = {}
        for fr in frame_entries:
            rel = str(fr.get("file") or "").replace("\\", "/")
            if rel.startswith("frames/"):
                rel = rel.split("frames/", 1)[1]
            by_file[rel] = int(fr.get("index", 0))
            by_file[f"frames/{rel}"] = int(fr.get("index", 0))

        uploads = []
        for fp in sorted(frames_dir.iterdir()):
            if not fp.is_file() or fp.suffix.lower() not in IMG_EXT:
                continue
            idx = by_file.get(fp.name)
            if idx is None:
                # fallback: parse frame_NNNN from filename
                m = re.search(r"frame_(\d+)", fp.name)
                idx = int(m.group(1)) if m else len(uploads)
            uploads.append({
                "local_path": fp,
                "frame_index": idx,
                "dest_key": legacy_asset_key(lecture_stem, idx),
                "dest_name": legacy_slide_name(lecture_stem, idx),
            })

        found.append({
            "pkg_dir": pkg_dir,
            "lecture_stem": lecture_stem,
            "canonical_mp4": canonical,
            "package_id": package_id,
            "frame_count_index": len(frame_entries),
            "uploads": uploads,
        })

    best = {}
    for row in found:
        prev = best.get(row["package_id"])
        if prev is None or len(row["uploads"]) > len(prev["uploads"]):
            best[row["package_id"]] = row
    return list(best.values())

packages = find_packages(DRIVE_ROOT)
print(f"found {len(packages)} packages")
for p in packages:
    print(f"  {p['lecture_stem']:35s}  slides={len(p['uploads']):4d}  mp4={p['canonical_mp4']}")
```

---

## Cell 3 — upload frames to `_asset_library/lectures/` (legacy slide path)

```python
DRY_RUN = False   # True = rehearsal
SKIP_EXISTING = True

upload_rows = []
for pkg in packages:
    lecture_stem = pkg["lecture_stem"]
    uploaded = 0
    skipped = 0
    for item in pkg["uploads"]:
        dest_key = item["dest_key"]
        blob = assets.blob(dest_key)
        if SKIP_EXISTING and blob.exists():
            skipped += 1
            continue
        if DRY_RUN:
            print("DRY", dest_key)
        else:
            blob.upload_from_filename(
                str(item["local_path"]),
                content_type="image/jpeg",
            )
        uploaded += 1
    upload_rows.append({
        "package_id": pkg["package_id"],
        "lecture_stem": lecture_stem,
        "canonical_mp4": pkg["canonical_mp4"],
        "drive_pkg_dir": str(pkg["pkg_dir"]),
        "gcs_asset_prefix": f"gs://{VIDEO_BUCKET}/{ASSET_PREFIX}{lecture_stem}/",
        "frames_on_disk": len(pkg["uploads"]),
        "uploaded": uploaded,
        "skipped_existing": skipped,
    })
    print(lecture_stem, "uploaded", uploaded, "skipped", skipped)

upload_rows
```

---

## Cell 4 — optional: upload canonical MP4s

```python
UPLOAD_MP4S = True
DRY_RUN_MP4 = False

mp4_rows = []
mp4s = sorted(DRIVE_ROOT.glob("Heme_SH_*.mp4"))
print(f"top-level mp4s: {len(mp4s)}")

for mp4 in mp4s:
    dest_key = f"source_videos/{mp4.name}"
    blob = videos.blob(dest_key)
    if blob.exists():
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

## Cell 5 — audit JSON

```python
audit = {
    "schema_version": "lecture_deck_frame_upload_audit.v0_1",
    "created_at_utc": utc_now(),
    "input_paths": [str(DRIVE_ROOT)],
    "output_paths": [
        f"gs://{VIDEO_BUCKET}/{ASSET_PREFIX}<CanonicalStem>/<CanonicalStem>_slide_NNNN.jpg",
        f"gs://{VIDEO_BUCKET}/source_videos/Heme_SH_*.mp4",
    ],
    "counts": {
        "packages": len(upload_rows),
        "slides_uploaded": sum(r["uploaded"] for r in upload_rows),
        "slides_skipped_existing": sum(r["skipped_existing"] for r in upload_rows),
        "mp4_rows": len(mp4_rows),
    },
    "packages": upload_rows,
    "mp4s": mp4_rows,
    "known_limitations": [
        "Renames chatgpt_readable frame_NNNN_timestamp.jpg → legacy <stem>_slide_NNNN.jpg by frame index.",
        "Change-detected frames are not identical to old slide exports, but path layout matches legacy _asset_library.",
        "Does not rebuild FAISS/docstore or claim API exposure.",
    ],
}

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
audit_key = f"06_audits/lectures/deck_packages/frame_upload_{stamp}/audit.json"
hub.blob(audit_key).upload_from_string(json.dumps(audit, indent=2) + "\n", content_type="application/json")
print("audit =>", f"gs://{HUB_BUCKET}/{audit_key}")
```

---

## Mapping cheat sheet

| Drive | GCS (legacy-consistent) |
|-------|-------------------------|
| `.../frames/frame_0003_00-00-38.jpg` | `gs://pathology-hub-0/_asset_library/lectures/Heme_SH_Spleen/Heme_SH_Spleen_slide_0003.jpg` |
| `Heme_SH_*.mp4` | `gs://pathology-hub-0/source_videos/Heme_SH_*.mp4` |
| deck sidecar `frames.jsonl` | `image_path` = `<stem>/<stem>_slide_NNNN.jpg` |

If a lecture only has an MP4 and no `chatgpt_readable_package/frames`, run extraction first (your Aggressive B-Cell Colab pattern).
