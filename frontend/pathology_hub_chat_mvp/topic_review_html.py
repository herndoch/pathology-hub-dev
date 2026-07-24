"""Render prebuilt topic-page sidecars as standalone review HTML."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

try:
    import markdown as _markdown

    def _md_to_html(text: str) -> str:
        return _markdown.markdown(
            text or "",
            extensions=["tables", "fenced_code", "sane_lists"],
        )
except Exception:

    def _md_to_html(text: str) -> str:
        esc = html.escape(text or "")
        parts = [p.strip() for p in re.split(r"\n\s*\n", esc) if p.strip()]
        return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in parts)


def slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", slug)


def render_topic_review_html(page: dict[str, Any], *, note: str = "") -> str:
  label = (page.get("label") or page.get("tag") or "Topic").replace("_", " ")
  tag = page.get("tag") or ""
  category = page.get("category_context") or ""
  model = page.get("model") or ""
  generated = page.get("generated_at") or ""
  cards = page.get("cards") or []
  figures = page.get("figures") or []
  srcs = Counter(c.get("source") for c in cards if isinstance(c, dict))
  src_summary = ", ".join(f"{k} {v}" for k, v in sorted(srcs.items()))

  cards_html: list[str] = []
  for card in cards[:14]:
      if not isinstance(card, dict):
          continue
      title = card.get("title") or card.get("heading") or "Evidence"
      excerpt = (card.get("text_excerpt") or card.get("excerpt") or "")[:420]
      url = (
          card.get("source_url")
          or card.get("source_page_url")
          or card.get("video_time_url")
          or ""
      )
      source = str(card.get("source") or "")
      if url:
          link = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(source)}</a>'
      else:
          link = html.escape(source)
      cards_html.append(
          f"<li><strong>{html.escape(str(title)[:120])}</strong> ({link})"
          f'<br><span class="excerpt">{html.escape(excerpt)}</span></li>'
      )

  fig_html = ""
  if figures:
      blocks = []
      for i, fig in enumerate(figures[:10], 1):
          if not isinstance(fig, dict):
              continue
          url = fig.get("figure_url") or fig.get("url") or fig.get("image_url") or ""
          caption = fig.get("caption") or fig.get("title") or f"Figure {i}"
          if url:
              blocks.append(
                  f'<figure><img src="{html.escape(url)}" alt="{html.escape(str(caption)[:120])}"/>'
                  f"<figcaption>{i}. {html.escape(str(caption)[:240])}</figcaption></figure>"
              )
      if blocks:
          fig_html = (
              f'<section class="figures"><h2>Figures ({len(figures)})</h2>'
              f'<div class="gallery">{"".join(blocks)}</div></section>'
          )

  note_html = f'<div class="note">{html.escape(note)}</div>' if note else ""

  critic_html = ""
  critic = page.get("critic") or {}
  critic_json = critic.get("critic_json") or {}
  issue_labels = {
      "missing_essentials": "Missing essential facts",
      "redundant": "Redundant content",
      "confusing": "Confusing/unclear",
      "entity_conflation": "Entity conflation",
      "off_organ_or_offtopic": "Off-organ/off-topic",
      "missing_ddx_entities": "Missing DDx entities",
      "figure_issues": "Figure issues",
  }
  issue_blocks = []
  for key, label in issue_labels.items():
      items = critic_json.get(key) or []
      if items:
          li = "".join(f"<li>{html.escape(str(x))}</li>" for x in items)
          issue_blocks.append(f"<li><strong>{html.escape(label)}:</strong><ul>{li}</ul></li>")
  if critic_json:
      verdict = str(critic_json.get("verdict") or "unknown")
      revision_applied = critic.get("revision_applied")
      badge_color = "#c0392b" if verdict == "revise" else "#2e7d4f"
      critic_html = f"""
      <section class="critic">
        <h2>Critic pass (pathologist-attending review persona)</h2>
        <p class="meta">
          verdict: <strong style="color:{badge_color}">{html.escape(verdict)}</strong>
          · revision applied: <strong>{html.escape(str(revision_applied))}</strong>
        </p>
        {f'<ul>{"".join(issue_blocks)}</ul>' if issue_blocks else '<p class="meta">No issues found.</p>'}
      </section>
      """

  return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(label)} — Pathology Hub topic review</title>
<style>
  body {{
    font-family: Georgia, "Iowan Old Style", serif;
    max-width: 920px;
    margin: 2rem auto;
    padding: 0 1.2rem;
    color: #152019;
    line-height: 1.5;
  }}
  .eyebrow {{
    font: 600 11px/1.2 system-ui, sans-serif;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #3f6b55;
  }}
  h1 {{ font-size: 2rem; margin: 0.2rem 0 1rem; }}
  .meta {{
    font: 13px/1.4 system-ui, sans-serif;
    color: #555;
    background: #f3f6f4;
    padding: 0.8rem 1rem;
    border-radius: 8px;
  }}
  .stats {{
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 1rem 0;
    font: 14px system-ui, sans-serif;
  }}
  .note {{
    background: #fff8e8;
    border: 1px solid #ecd9a8;
    padding: 0.7rem 1rem;
    border-radius: 8px;
    font: 14px system-ui, sans-serif;
    margin: 1rem 0;
  }}
  .answer h2 {{
    margin-top: 1.2rem;
    border-bottom: 1px solid #d9e3dc;
    padding-bottom: 0.2rem;
  }}
  .evidence h2, .figures h2 {{ margin-top: 2rem; }}
  .evidence li {{ margin: 0.8rem 0; }}
  .excerpt {{ font-size: 13px; color: #444; }}
  .gallery {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.8rem;
  }}
  figure {{ margin: 0; }}
  figure img {{
    width: 100%;
    max-height: 220px;
    object-fit: contain;
    background: #eef2ef;
    border: 1px solid #d0d8d2;
  }}
  figcaption {{ font: 12px/1.3 system-ui, sans-serif; margin-top: 0.25rem; }}
  .back {{
    display: inline-block;
    margin-bottom: 1rem;
    font: 14px system-ui, sans-serif;
    color: #1a5f3a;
  }}
</style>
</head>
<body>
  <a class="back" href="/review">← All review pages</a>
  <p class="eyebrow">Pathology Hub · Topic page review</p>
  <h1>{html.escape(label)}</h1>
  <p class="meta">
    tag: <code>{html.escape(tag)}</code><br/>
    browse: {html.escape(category)} · model: {html.escape(str(model))}<br/>
    generated: {html.escape(str(generated))}
  </p>
  <div class="stats">
    <span>cards: <b>{len(cards)}</b> ({html.escape(src_summary or "none")})</span>
    <span>figures: <b>{len(figures)}</b></span>
  </div>
  {note_html}
  <section class="answer">{_md_to_html(page.get("answer_markdown") or "")}</section>
  {fig_html}
  {critic_html}
  <section class="evidence">
    <h2>Evidence cards (sample)</h2>
    <ol>{"".join(cards_html) or "<li>No cards in sidecar.</li>"}</ol>
  </section>
</body>
</html>"""


def render_review_index_html(items: list[dict[str, str]]) -> str:
    rows = []
    for item in items:
        rows.append(
            f'<li><a href="{html.escape(item["href"])}">{html.escape(item["label"])}</a>'
            f' <span class="meta">{html.escape(item.get("meta") or "")}</span></li>'
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Pathology Hub — topic review index</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ font-size: 1.5rem; }}
li {{ margin: 0.7rem 0; }}
a {{ color: #1a5f3a; font-weight: 600; }}
.meta {{ color: #666; font-weight: 400; font-size: 0.92rem; }}
</style></head><body>
<h1>Topic page review</h1>
<p>Click a topic to open the HTML review page in your browser.</p>
<ul>{"".join(rows)}</ul>
</body></html>"""


def load_page_json(pages_dir: Path, tag: str) -> Optional[dict[str, Any]]:
    path = pages_dir / f"{slugify_tag(tag)}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
