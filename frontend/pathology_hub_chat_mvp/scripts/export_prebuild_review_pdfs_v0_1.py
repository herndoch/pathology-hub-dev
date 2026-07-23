#!/usr/bin/env python3
"""Export prebuilt topic-page sidecars to printable HTML + Chrome PDFs (v0_1).

Reads pages written by prebuild_topic_pages_pilot_v0_1.py and produces a
human-reviewable PDF per leaf (markdown answer + figure gallery + card counts).

Does not call OpenAI or the live hub API — offline render of already-built
sidecars only.

Example:
    python3 scripts/export_prebuild_review_pdfs_v0_1.py \\
        --sample outputs/chat_mvp_topic_prepop_v0_1/review10_sample_v0_1.json \\
        --out-dir /opt/cursor/artifacts/prebuild_review_pdfs
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_SAMPLE = OUTPUT_DIR / "review10_sample_v0_1.json"
DEFAULT_OUT = Path("/opt/cursor/artifacts/prebuild_review_pdfs")


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", slug)


def _md_to_html(text: str) -> str:
    try:
        import markdown  # type: ignore

        return markdown.markdown(
            text or "",
            extensions=["tables", "fenced_code", "sane_lists"],
        )
    except Exception:
        # Minimal fallback: escape + paragraph breaks.
        esc = html.escape(text or "")
        parts = [p.strip() for p in re.split(r"\n\s*\n", esc) if p.strip()]
        return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in parts)


def _fig_url(fig: dict) -> str:
    for key in ("image_url", "url", "thumbnail_url", "proxy_url", "src"):
        val = fig.get(key)
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    return ""


def _cache_figure(url: str, img_dir: Path) -> Path | None:
    """Download figure locally with a short timeout so Chrome never waits on the network."""
    if not url:
        return None
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    # Prefer a stable extension guess.
    ext = ".jpg"
    lower = url.lower().split("?", 1)[0]
    for candidate in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if lower.endswith(candidate):
            ext = candidate
            break
    dest = img_dir / f"{digest}{ext}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PathologyHubPrebuildReview/0.1"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
        if not data:
            return None
        dest.write_bytes(data)
        return dest
    except Exception:
        return None


def _render_page_html(page: dict, img_dir: Path) -> str:
    label = page.get("label") or page.get("tag") or "Topic"
    tag = page.get("tag") or ""
    query = page.get("query") or ""
    cat = page.get("category_context") or ""
    model = page.get("model") or ""
    generated = page.get("generated_at") or ""
    cards = page.get("cards") or []
    figures = page.get("figures") or []
    who = page.get("who_cross_mentions") or []
    dbg = page.get("retrieval_debug_summary") or {}
    answer_html = _md_to_html(page.get("answer_markdown") or "")

    fig_blocks = []
    for i, fig in enumerate(figures[:12], 1):
        url = _fig_url(fig)
        caption = fig.get("caption") or fig.get("title") or fig.get("label") or f"Figure {i}"
        source = fig.get("source") or fig.get("source_family") or ""
        local = _cache_figure(url, img_dir)
        if local is not None:
            img = (
                f'<img src="{html.escape(local.as_uri())}" '
                f'alt="{html.escape(str(caption)[:120])}"/>'
            )
        elif url:
            img = (
                f'<div class="no-img">Image unavailable for PDF '
                f"(source had URL; download timed out/failed)</div>"
            )
        else:
            img = '<div class="no-img">No image URL</div>'
        fig_blocks.append(
            f"""
            <figure>
              {img}
              <figcaption><strong>{i}.</strong> {html.escape(str(caption)[:280])}
              <span class="meta">{html.escape(str(source))}</span></figcaption>
            </figure>
            """
        )

    who_html = ""
    if who:
        items = "".join(f"<li>{html.escape(str(w)[:300])}</li>" for w in who[:12])
        who_html = f"<section><h2>WHO cross-mentions</h2><ul>{items}</ul></section>"

    limitations = page.get("known_limitations") or []
    lim_html = "".join(f"<li>{html.escape(str(x))}</li>" for x in limitations)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{html.escape(str(label))} — prebuild review</title>
<style>
  @page {{ size: letter; margin: 0.55in; }}
  body {{
    font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
    color: #1a1f1c;
    line-height: 1.45;
    font-size: 11pt;
  }}
  h1 {{
    font-size: 22pt;
    margin: 0 0 0.15em;
    letter-spacing: -0.02em;
  }}
  .eyebrow {{
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #3d5a4c;
    margin: 0 0 0.4em;
  }}
  .meta {{
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 8.5pt;
    color: #555;
  }}
  .stats {{
    display: flex;
    gap: 1.2em;
    margin: 0.8em 0 1.2em;
    padding: 0.6em 0;
    border-top: 1px solid #c9d4cc;
    border-bottom: 1px solid #c9d4cc;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 9.5pt;
  }}
  h2 {{
    font-size: 13pt;
    margin: 1.2em 0 0.4em;
    color: #24352c;
    border-bottom: 1px solid #d7e0da;
    padding-bottom: 0.15em;
  }}
  .answer h1, .answer h2, .answer h3 {{
    font-size: 12pt;
    margin-top: 0.9em;
  }}
  .gallery {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.7em;
  }}
  figure {{
    margin: 0;
    break-inside: avoid;
  }}
  figure img {{
    width: 100%;
    max-height: 220px;
    object-fit: contain;
    background: #eef2ef;
    border: 1px solid #d0d8d2;
  }}
  figcaption {{
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 8pt;
    margin-top: 0.25em;
  }}
  .no-img {{
    height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f0f3f1;
    color: #777;
    font-family: "IBM Plex Sans", sans-serif;
    font-size: 9pt;
  }}
  ul {{ padding-left: 1.2em; }}
  code {{ font-size: 8.5pt; }}
</style>
</head>
<body>
  <p class="eyebrow">Pathology Hub · Topic prebuild review</p>
  <h1>{html.escape(str(label).replace('_', ' '))}</h1>
  <p class="meta">
    tag: <code>{html.escape(tag)}</code><br/>
    browse: {html.escape(cat)} · query: {html.escape(query)}<br/>
    model: {html.escape(str(model))} · generated: {html.escape(str(generated))}
  </p>
  <div class="stats">
    <span>ok: <strong>{html.escape(str(page.get('ok')))}</strong></span>
    <span>cards: <strong>{len(cards)}</strong></span>
    <span>figures: <strong>{len(figures)}</strong></span>
    <span>elapsed: <strong>{html.escape(str(dbg.get('elapsed_s') or '?'))}s</strong></span>
    <span>calls: <strong>{html.escape(str(dbg.get('call_count') or '?'))}</strong></span>
  </div>
  <section>
    <h2>Synthesized topic page</h2>
    <div class="answer">{answer_html}</div>
  </section>
  <section>
    <h2>Selected images ({len(figures)})</h2>
    <div class="gallery">
      {''.join(fig_blocks) if fig_blocks else '<p class="meta">No figures in this sidecar.</p>'}
    </div>
  </section>
  {who_html}
  <section>
    <h2>Known limitations</h2>
    <ul>{lim_html or '<li>None listed.</li>'}</ul>
  </section>
</body>
</html>
"""


def _chrome_print(html_path: Path, pdf_path: Path) -> None:
    """Print HTML to PDF. Chrome headless sometimes hangs after writing the PDF;
    accept success if the PDF appears with non-trivial size.
    """
    if pdf_path.exists():
        pdf_path.unlink()
    chrome = "google-chrome"
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-pdf-header-footer",
        "--virtual-time-budget=12000",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        if not (pdf_path.exists() and pdf_path.stat().st_size > 1000):
            raise
    if not (pdf_path.exists() and pdf_path.stat().st_size > 1000):
        raise RuntimeError(f"Chrome did not write a usable PDF at {pdf_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    args = parser.parse_args()

    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    leaves = sample["leaves"]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    html_dir = args.out_dir / "html"
    img_dir = args.out_dir / "images"
    html_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    try:
        import markdown  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "markdown"])

    written = []
    for i, leaf in enumerate(leaves, 1):
        tag = leaf["tag"]
        slug = _slugify_tag(tag)
        json_path = args.pages_dir / f"{slug}.json"
        if not json_path.exists():
            print(f"MISSING sidecar: {json_path}", flush=True)
            continue
        page = json.loads(json_path.read_text(encoding="utf-8"))
        html_path = html_dir / f"{i:02d}_{slug}.html"
        pdf_path = args.out_dir / f"{i:02d}_{slug}.pdf"
        print(f"Rendering {html_path.name} (caching figures)...", flush=True)
        html_path.write_text(_render_page_html(page, img_dir), encoding="utf-8")
        print(f"Printing {pdf_path.name} ...", flush=True)
        _chrome_print(html_path, pdf_path)
        written.append(
            {
                "tag": tag,
                "ok": page.get("ok"),
                "cards": len(page.get("cards") or []),
                "figures": len(page.get("figures") or []),
                "pdf": str(pdf_path),
                "html": str(html_path),
            }
        )

    index = {
        "schema_version": "topic_prepop_review_pdf_index_v0_1",
        "sample": str(args.sample),
        "n_pdfs": len(written),
        "items": written,
    }
    index_path = args.out_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(written)} PDFs → {args.out_dir}")
    print(f"Index: {index_path}")


if __name__ == "__main__":
    main()
