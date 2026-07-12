# YouTube ingest handoff — Cipriani BST board review

Target: https://www.youtube.com/watch?v=NOmOHTh-vtY  
Title (oEmbed): Bone & Soft Tissue Board Review 2026-04-23 (Nicole Cipriani)  
Root: `BST` · Playback: YouTube (`&t=NNNs`) · Script: `scripts/ingest_youtube_lecture_to_deck_package_v0_1.py`

## Blocker (cloud agent)

YouTube returns **Sign in to confirm you’re not a bot** for all yt-dlp clients from this cloud IP. oEmbed title works; media + timedtext do not. Chrome on the VM has no YouTube login cookies.

## Unblock (pick one)

### A) Cookies (preferred for full yt-dlp)

1. On your laptop, export Netscape `cookies.txt` while logged into YouTube  
   (see [yt-dlp cookie export](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)).
2. Drop the file into the agent workspace (e.g. `/workspace/cookies.txt`).
3. Re-run:

```bash
source .venv/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS=/home/ubuntu/.config/gcp/cursor-sa.json
python scripts/ingest_youtube_lecture_to_deck_package_v0_1.py \
  --url 'https://www.youtube.com/watch?v=NOmOHTh-vtY' \
  --root BST \
  --cookies /workspace/cookies.txt \
  --leaf-dir outputs/bst_browse_leaf_embeddings_v0_1 \
  --gate --upload --upload-frames
```

### B) Local media handoff (no cookies in cloud)

On a machine that can play the video:

```bash
yt-dlp -f 'bestaudio' -o cipriani_audio.%(ext)s --extract-audio --audio-format mp3 \
  'https://www.youtube.com/watch?v=NOmOHTh-vtY'
# optional frames source
yt-dlp -f 'bv*[height<=480]+ba/b[height<=480]' -o cipriani_video.mp4 --merge-output-format mp4 \
  'https://www.youtube.com/watch?v=NOmOHTh-vtY'
yt-dlp --dump-single-json --skip-download 'https://www.youtube.com/watch?v=NOmOHTh-vtY' > cipriani_meta.json
```

Copy `cipriani_audio.mp3` (+ optional video/meta) into the workspace, then:

```bash
python scripts/ingest_youtube_lecture_to_deck_package_v0_1.py \
  --url 'https://www.youtube.com/watch?v=NOmOHTh-vtY' \
  --root BST \
  --audio /workspace/cipriani_audio.mp3 \
  --video /workspace/cipriani_video.mp4 \
  --meta-json /workspace/cipriani_meta.json \
  --leaf-dir outputs/bst_browse_leaf_embeddings_v0_1 \
  --gate --upload --upload-frames
```

If Whisper rejects size (>25 MB): `ffmpeg -y -i cipriani_audio.mp3 -b:a 64k cipriani_audio_64k.mp3`

## After successful ingest

```bash
python scripts/build_lecture_vector_from_deck_packages_v0_1.py --upload --promote-live
```

Then refresh Cloud Run (operator SA; agent lacks `run.services.update`):

```bash
gcloud run services update pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --update-env-vars=LECTURE_MANIFEST_REFRESH_TS=$(date -u +%Y%m%dT%H%M%SZ)
```

That bumps an env var so new pods re-download lecture FAISS/docstore from GCS (deck index ~712 + new chunks). Without it, warm pods keep the old cached index.

## Gate / URL note

Semantic gate v0_2 now emits YouTube `&t=NNNs` when `video_url` is youtube.com / youtu.be (GCS stays `#t=`).
