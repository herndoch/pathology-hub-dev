# Lecture Video OncoTree index — handoff v0_1

**Ask (2026-09-01):** Mentor Vivian liked timestamped lecture videos; want an
OncoTree-style page of **just the video index**, runnable as a local site to
toggle through, then shareable with edu leadership (static HTML folder).

## Delivered

- Builder: `scripts/build_lecture_video_oncotree_index_v0_1.py`
- Site: `frontend/lecture_video_oncotree_v0_1/`
- Index snapshot from live deck vector docstore (~915 clips / ~137 lectures /
  ~430 tagged leaves / 20 roots at build time)

## How to demo

```bash
cd frontend/lecture_video_oncotree_v0_1 && python3 -m http.server 8765
# open http://127.0.0.1:8765/
```

## Next (optional)

- Deploy folder to a public GCS website bucket or attach under Chat MVP `/static`
- Add frame thumbnails from deck `frames.jsonl`
- Filter to Heme-only (or Society of ’67 subset) for a shorter leadership tour
