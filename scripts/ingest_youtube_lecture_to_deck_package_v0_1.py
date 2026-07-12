#!/usr/bin/env python3
"""Ingest a YouTube lecture into a Pathology Hub deck package (playback = YouTube).

Pipeline (approach B):
  1. yt-dlp: metadata + audio (+ optional low-res video for frames)
     OR use operator-supplied --audio / --video / --meta-json when cloud IPs
     are bot-blocked
  2. OpenAI Whisper API: timed transcript segments
  3. Optional ffmpeg frame sampling → package frames/
  4. Write deck sidecar (segments/frames/manifest) with YouTube video_url
     and YouTube timestamp links (&t=NNNs) as video_time_url
  5. Optional: BST/GI/… semantic gate + upload

YouTube bot-checks often block cloud IPs. Options:
  - Pass --cookies cookies.txt (Netscape export from a logged-in browser)
  - Or download locally and pass --audio / --video (see docs handoff)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from google.cloud.storage import Client
from openai import OpenAI


SCHEMA_VERSION = "lecture_deck_package.v0_1"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "lecture"


def extract_youtube_id(url: str) -> str:
    u = urlparse(url)
    if u.netloc in {"youtu.be"}:
        return u.path.strip("/").split("/")[0]
    qs = parse_qs(u.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]
    m = re.search(r"(?:embed|shorts|live)/([A-Za-z0-9_-]{6,})", url)
    if m:
        return m.group(1)
    raise ValueError(f"Could not parse YouTube id from {url}")


def youtube_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def make_youtube_time_url(video_id: str, start: Any, end: Any = None) -> Optional[str]:
    """YouTube deep link. End is ignored (YT only seeks to start)."""
    try:
        s = int(float(start))
    except (TypeError, ValueError):
        return None
    if s < 0:
        s = 0
    return f"https://www.youtube.com/watch?v={video_id}&t={s}s"


def run(cmd: list[str], *, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, capture_output=True, text=True)


def yt_dlp_base(cookies: Optional[Path]) -> list[str]:
    cmd = ["yt-dlp", "--no-playlist", "--js-runtimes", "node"]
    if cookies and cookies.is_file():
        cmd.extend(["--cookies", str(cookies)])
    # Prefer clients that sometimes bypass bot walls
    cmd.extend(["--extractor-args", "youtube:player_client=android,ios,tv,web"])
    return cmd


def fetch_oembed(url: str) -> dict[str, Any]:
    endpoint = f"https://www.youtube.com/oembed?url={url}&format=json"
    with urllib.request.urlopen(endpoint, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_metadata(url: str, cookies: Optional[Path], meta_json: Optional[Path]) -> dict[str, Any]:
    if meta_json and meta_json.is_file():
        return json.loads(meta_json.read_text())
    cmd = yt_dlp_base(cookies) + ["--dump-single-json", "--skip-download", url]
    try:
        proc = run(cmd)
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or "")[-2000:]
        print("WARN yt-dlp metadata failed; trying oEmbed fallback:", err[-400:], flush=True)
        try:
            oe = fetch_oembed(url)
            return {
                "id": extract_youtube_id(url),
                "title": oe.get("title"),
                "uploader": oe.get("author_name"),
                "channel": oe.get("author_name"),
                "duration": None,
                "thumbnail": oe.get("thumbnail_url"),
                "_meta_source": "oembed_fallback",
            }
        except Exception as oe_exc:
            raise RuntimeError(
                "yt-dlp metadata failed (often YouTube bot-check on cloud IPs). "
                "Export browser cookies to cookies.txt and pass --cookies, "
                "or pass --audio (and optional --meta-json) from a local download.\n"
                f"yt-dlp: {err}\noembed: {oe_exc}"
            ) from exc


def download_audio(url: str, out_dir: Path, cookies: Optional[Path]) -> Path:
    out_tmpl = str(out_dir / "audio.%(ext)s")
    cmd = yt_dlp_base(cookies) + [
        "-f",
        "bestaudio[ext=m4a]/bestaudio/best",
        "-o",
        out_tmpl,
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        url,
    ]
    try:
        run(cmd)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Audio download failed (YouTube bot-check). "
            "Pass --cookies cookies.txt or --audio /path/to/audio.mp3\n"
            + (exc.stderr or "")[-2000:]
        ) from exc
    for p in out_dir.glob("audio.*"):
        if p.suffix.lower() in {".mp3", ".m4a", ".webm", ".opus", ".wav"}:
            return p
    raise FileNotFoundError(f"No audio downloaded under {out_dir}")


def download_video_lowres(url: str, out_dir: Path, cookies: Optional[Path]) -> Optional[Path]:
    out_tmpl = str(out_dir / "video.%(ext)s")
    cmd = yt_dlp_base(cookies) + [
        "-f",
        "bv*[height<=480]+ba/b[height<=480]/worst",
        "-o",
        out_tmpl,
        "--merge-output-format",
        "mp4",
        url,
    ]
    try:
        run(cmd)
    except subprocess.CalledProcessError as exc:
        print("WARN video download failed; continuing audio-only:", (exc.stderr or "")[-500:], flush=True)
        return None
    for p in out_dir.glob("video.*"):
        if p.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            return p
    return None


def whisper_transcribe(client: OpenAI, audio_path: Path) -> list[dict[str, Any]]:
    """Return list of {id,start,end,text} using OpenAI whisper-1 verbose_json."""
    size_mb = audio_path.stat().st_size / 1e6
    print(f"Whisper transcribe {audio_path.name} ({size_mb:.1f} MB)", flush=True)
    if size_mb > 24.5:
        raise RuntimeError(
            f"Audio {audio_path} is {size_mb:.1f} MB; Whisper API limit is ~25 MB. "
            "Re-encode smaller (e.g. ffmpeg -i in.mp3 -b:a 64k out.mp3) and pass --audio."
        )
    with audio_path.open("rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    segs = data.get("segments") or []
    out = []
    for i, s in enumerate(segs):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "id": i,
                "start": float(s.get("start") or 0.0),
                "end": float(s.get("end") or s.get("start") or 0.0),
                "text": text,
            }
        )
    return out


def extract_frames(video_path: Path, frames_dir: Path, *, every_sec: float = 12.0) -> list[dict[str, Any]]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    fps = 1.0 / max(every_sec, 1.0)
    pattern = str(frames_dir / "slide_%04d.jpg")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        "-q:v",
        "3",
        pattern,
    ]
    try:
        run(cmd)
    except subprocess.CalledProcessError as exc:
        print("WARN ffmpeg frames failed:", (exc.stderr or "")[-500:], flush=True)
        return []
    rows = []
    for i, path in enumerate(sorted(frames_dir.glob("slide_*.jpg"))):
        start_sec = i * every_sec
        rows.append(
            {
                "frame_index": i,
                "start_sec": start_sec,
                "file": path.name,
                "local_path": path,
            }
        )
    return rows


def probe_duration_sec(media: Path) -> Optional[float]:
    try:
        proc = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media),
            ]
        )
        return float(proc.stdout.strip())
    except Exception as exc:
        print("WARN duration probe failed:", exc, flush=True)
        return None


def build_package_dir(
    *,
    work: Path,
    package_id: str,
    title: str,
    root: str,
    video_id: str,
    duration: Optional[float],
    segments: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    youtube_url: str,
    source_url: str,
) -> Path:
    out = work / package_id
    out.mkdir(parents=True, exist_ok=True)
    video_url = youtube_watch_url(video_id)

    seg_rows = []
    for s in segments:
        start = float(s["start"])
        end = float(s["end"])
        seg_rows.append(
            {
                "schema_version": "lecture_deck_segment.v0_1",
                "package_id": package_id,
                "segment_id": f"{package_id}::seg_{int(s['id']):05d}",
                "start_sec": start,
                "end_sec": end,
                "text": s["text"],
                "language": "en",
                "video_id": video_id,
                "video_url": video_url,
                "video_time_url": make_youtube_time_url(video_id, start, end),
                "raw_source_gcs_uri": None,
                "raw_source_join_basis": "youtube_watch_url",
                "youtube_url": youtube_url,
                "primary_tag": None,
                "tag_status": "untagged",
                "root": root,
                "indexable": False,
                "source_format": "youtube_whisper_v0",
            }
        )

    frame_rows = []
    for fr in frames:
        start = float(fr["start_sec"])
        frame_rows.append(
            {
                "schema_version": "lecture_deck_frame.v0_1",
                "package_id": package_id,
                "frame_index": fr["frame_index"],
                "start_sec": start,
                "file": f"frames/{fr['file']}",
                "local_frame_path": str(fr.get("local_path") or ""),
                "transcript_context": None,
                "video_id": video_id,
                "video_url": video_url,
                "video_time_url": make_youtube_time_url(video_id, start),
                "raw_source_join_basis": "youtube_watch_url",
                "youtube_url": youtube_url,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "title": title,
        "root": root,
        "source_format": "youtube_ingest_v0_1",
        "youtube_url": youtube_url,
        "youtube_video_id": video_id,
        "video_file_declared": None,
        "duration_seconds": duration,
        "video_id": video_id,
        "raw_source_gcs_uri": None,
        "video_url": video_url,
        "raw_source_join_basis": "youtube_watch_url",
        "playback": "youtube",
        "counts": {
            "segments": len(seg_rows),
            "frames": len(frame_rows),
            "segments_with_video_time_url": sum(1 for s in seg_rows if s.get("video_time_url")),
            "frames_with_video_time_url": sum(1 for f in frame_rows if f.get("video_time_url")),
            "canonical_mp4_present": False,
        },
        "created_at_utc": utc_now(),
        "known_limitations": [
            "Playback is YouTube watch URL + &t= seconds (not GCS MP4 #t=).",
            "YouTube ignores end time in deep links.",
            "Cloud yt-dlp often needs --cookies or local --audio due to bot checks.",
            "Sidecar only until semantic gate + vector rebuild.",
        ],
        "source_url": source_url,
    }

    audit = {
        "schema_version": "lecture_deck_youtube_ingest_audit.v0_1",
        "created_at_utc": utc_now(),
        "package_id": package_id,
        "input_paths": [source_url],
        "output_paths": [
            str(out / "manifest.json"),
            str(out / "segments.jsonl"),
            str(out / "frames.jsonl"),
            str(out / "audit.json"),
        ],
        "counts": manifest["counts"],
        "join": {
            "video_url": video_url,
            "raw_source_join_basis": "youtube_watch_url",
            "youtube_video_id": video_id,
        },
        "known_limitations": manifest["known_limitations"],
    }

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (out / "segments.jsonl").open("w") as f:
        for row in seg_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "frames.jsonl").open("w") as f:
        for row in frame_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (out / "segments_indexable.jsonl").write_text("")
    (out / "chunks_indexable.jsonl").write_text("")

    if frames:
        dest_frames = out / "frames"
        dest_frames.mkdir(exist_ok=True)
        for fr in frames:
            src = fr.get("local_path")
            if src and Path(src).is_file():
                shutil.copy2(src, dest_frames / fr["file"])

    return out


def upload_package(client: Client, local_dir: Path, package_id: str, *, upload_frames: bool) -> list[str]:
    hub = client.bucket("pathology_hub")
    hub0 = client.bucket("pathology-hub-0")
    uploaded = []
    for name in (
        "manifest.json",
        "segments.jsonl",
        "frames.jsonl",
        "audit.json",
        "segments_indexable.jsonl",
        "chunks_indexable.jsonl",
    ):
        path = local_dir / name
        if not path.is_file():
            continue
        dest = f"02_normalized/lectures/deck_packages/{package_id}/{name}"
        hub.blob(dest).upload_from_filename(str(path))
        uploaded.append(f"gs://pathology_hub/{dest}")

    if upload_frames:
        frames_dir = local_dir / "frames"
        if frames_dir.is_dir():
            stem = package_id.replace("_v0_1", "")
            asset_stem = re.sub(r"[^A-Za-z0-9_]+", "_", stem)
            for jpg in sorted(frames_dir.glob("*.jpg")):
                m = re.search(r"(\d+)", jpg.stem)
                idx = int(m.group(1)) if m else 0
                key = f"_asset_library/lectures/{asset_stem}/{asset_stem}_slide_{idx:04d}.jpg"
                hub0.blob(key).upload_from_filename(str(jpg))
                uploaded.append(f"gs://pathology-hub-0/{key}")
    return uploaded


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    p.add_argument("--root", default="BST", help="Browse root for later gating")
    p.add_argument("--package-id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--cookies", type=Path, default=None, help="Netscape cookies.txt for yt-dlp")
    p.add_argument("--audio", type=Path, default=None, help="Pre-downloaded audio (skip yt-dlp audio)")
    p.add_argument("--video", type=Path, default=None, help="Pre-downloaded video for frames")
    p.add_argument("--meta-json", type=Path, default=None, help="yt-dlp --dump-single-json output")
    p.add_argument("--out-root", type=Path, default=Path("outputs/lecture_deck_packages_v0_1"))
    p.add_argument("--work-dir", type=Path, default=None)
    p.add_argument("--frame-every-sec", type=float, default=15.0)
    p.add_argument("--skip-frames", action="store_true")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--upload-frames", action="store_true")
    p.add_argument("--gate", action="store_true", help="Run semantic gated chunker after build")
    p.add_argument("--leaf-dir", type=Path, default=Path("outputs/bst_browse_leaf_embeddings_v0_1"))
    args = p.parse_args()

    video_id = extract_youtube_id(args.url)
    youtube_url = youtube_watch_url(video_id)
    work = Path(tempfile.mkdtemp(prefix="yt_ingest_")) if args.work_dir is None else args.work_dir
    work.mkdir(parents=True, exist_ok=True)
    print("work", work, flush=True)

    meta = fetch_metadata(args.url, args.cookies, args.meta_json)
    title = args.title or meta.get("title") or f"YouTube {video_id}"
    duration = meta.get("duration")
    uploader = meta.get("uploader") or meta.get("channel") or ""
    print(
        json.dumps(
            {
                "id": video_id,
                "title": title,
                "duration": duration,
                "uploader": uploader,
                "meta_source": meta.get("_meta_source") or "yt_dlp_or_json",
            },
            indent=2,
        ),
        flush=True,
    )

    package_id = args.package_id or f"yt_{slugify(uploader)[:24]}_{slugify(title)[:48]}_{video_id.lower()}_v0_1"
    if len(package_id) > 90:
        package_id = f"yt_{video_id.lower()}_v0_1"

    if args.audio and args.audio.is_file():
        audio = args.audio
        print(f"using local audio {audio}", flush=True)
    else:
        audio = download_audio(args.url, work, args.cookies)

    if duration is None:
        duration = probe_duration_sec(audio)

    client = OpenAI()
    segments = whisper_transcribe(client, audio)
    print(f"segments={len(segments)}", flush=True)

    frames: list[dict[str, Any]] = []
    if not args.skip_frames:
        video: Optional[Path] = None
        if args.video and args.video.is_file():
            video = args.video
            print(f"using local video {video}", flush=True)
        else:
            video = download_video_lowres(args.url, work, args.cookies)
        if video:
            frames = extract_frames(video, work / "frame_imgs", every_sec=args.frame_every_sec)
            print(f"frames={len(frames)}", flush=True)

    pkg_dir = build_package_dir(
        work=args.out_root,
        package_id=package_id,
        title=title if not uploader else f"{title} ({uploader})",
        root=args.root,
        video_id=video_id,
        duration=float(duration) if duration is not None else None,
        segments=segments,
        frames=frames,
        youtube_url=youtube_url,
        source_url=args.url,
    )
    print("package", pkg_dir, flush=True)

    uploaded: list[str] = []
    if args.upload:
        gcs = Client()
        uploaded = upload_package(gcs, pkg_dir, package_id, upload_frames=args.upload_frames)
        print(json.dumps({"uploaded": len(uploaded)}, indent=2), flush=True)

    if args.gate:
        import sys

        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parent / "build_lecture_deck_semantic_indexable_chunks_v0_2.py"),
            "--package-dir",
            str(pkg_dir),
            "--leaf-dir",
            str(args.leaf_dir),
            "--root",
            args.root,
        ]
        print("+", " ".join(cmd), flush=True)
        subprocess.check_call(cmd)
        if args.upload:
            gcs = Client()
            for name in ("chunks_indexable.jsonl", "chunk_audit.json", "manifest.json", "segments.jsonl"):
                path = pkg_dir / name
                if path.is_file():
                    dest = f"02_normalized/lectures/deck_packages/{package_id}/{name}"
                    gcs.bucket("pathology_hub").blob(dest).upload_from_filename(str(path))
                    uploaded.append(f"gs://pathology_hub/{dest}")

    print(
        json.dumps(
            {
                "ok": True,
                "package_id": package_id,
                "package_dir": str(pkg_dir),
                "youtube_url": youtube_url,
                "segments": len(segments),
                "frames": len(frames),
                "uploaded": uploaded[:10],
                "upload_count": len(uploaded),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
