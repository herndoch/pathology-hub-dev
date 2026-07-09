const DEFAULT_SOURCES = ["textbooks", "pathout", "who"];
const NOTES_STORAGE_KEY = "pathology_hub_teaching_session_notes";
const LEGACY_NOTES_STORAGE_KEY = "pathology_hub_experiment_notes";

const SOURCE_LABELS = {
  who: "WHO Classification",
  textbooks: "Textbooks",
  pathout: "Pathology Outlines",
  journals: "Journals",
  lectures: "Lectures",
  videos: "Videos",
  curriculum: "Curriculum map",
};

const LINK_LABELS = {
  source_url: "Open source page",
  source_page_url: "Open reference page",
  page_image_url: "View textbook page",
  figure_url: "View figure",
  image_url: "View image",
  video_time_url: "Jump to lecture timestamp",
  html_url: "Open teaching page",
};

const MODE_HINTS = {
  gpt_like: "Default: grounded summary with inline citations from selected sources.",
  search_only: "Returns evidence cards only — no OpenAI synthesis.",
  compare_sources: "Answer is sectioned by source family (Textbooks, WHO, PathOut, …).",
  visual: "Retrieval includes figures; thumbnails appear below citations.",
  html_teaching: "Generates a hosted HTML teaching page — link appears above citations.",
};

const STOPWORDS = new Set([
  "the", "a", "an", "of", "in", "for", "and", "or", "with", "is", "are", "to", "on", "at", "by",
]);

const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const modeSelect = document.getElementById("mode-select");
const modeHint = document.getElementById("mode-hint");
const maxResultsInput = document.getElementById("max-results");
const debugToggle = document.getElementById("debug-toggle");
const healthStatus = document.getElementById("health-status");
const sourceCheckboxes = document.getElementById("source-checkboxes");
const sessionNotes = document.getElementById("session-notes");
const copyNotesBtn = document.getElementById("copy-notes-btn");
const exportNotesBtn = document.getElementById("export-notes-btn");
const notesStatus = document.getElementById("notes-status");
const mediaModal = document.getElementById("media-modal");
const mediaModalImg = document.getElementById("media-modal-img");
const mediaModalCaption = document.getElementById("media-modal-caption");
const mediaModalOpen = document.getElementById("media-modal-open");

let supportedSources = [];
let notesSaveTimer = null;

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source;
}

function cardTitle(card) {
  return card.title || card.name || card.heading || card.primary_tag || "(untitled hit)";
}

function cardText(card) {
  return [
    card.title,
    card.name,
    card.heading,
    card.primary_tag,
    card.text_excerpt,
    card.excerpt,
    card.header,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function queryTerms(query) {
  return query
    .toLowerCase()
    .split(/\W+/)
    .filter((word) => word.length >= 3 && !STOPWORDS.has(word));
}

function collectCardLinks(card) {
  const keys = [
    "source_url",
    "source_page_url",
    "page_image_url",
    "figure_url",
    "image_url",
    "video_time_url",
    "html_url",
  ];
  const links = [];
  for (const key of keys) {
    const val = card[key];
    if (typeof val === "string" && val.startsWith("http")) {
      links.push({ key, label: LINK_LABELS[key] || key, href: val });
    }
  }
  return links;
}

function previewUrl(card) {
  for (const key of ["page_image_url", "figure_url", "image_url"]) {
    const val = card[key];
    if (typeof val === "string" && val.startsWith("http")) return val;
  }
  return null;
}

function topCardPerSource(cards) {
  const seen = new Map();
  for (const card of cards || []) {
    const src = card.source || "unknown";
    if (!seen.has(src)) seen.set(src, card);
  }
  return seen;
}

function assessRelevance(query, cards) {
  const tokens = queryTerms(query);
  if (!tokens.length || !cards?.length) {
    return { weak: [], partial: [] };
  }

  const weak = [];
  const partial = [];
  for (const [src, card] of topCardPerSource(cards)) {
    const hay = cardText(card);
    const matched = tokens.filter((term) => hay.includes(term));
    if (matched.length === 0) {
      weak.push({ source: src, title: cardTitle(card) });
    } else if (matched.length < tokens.length) {
      partial.push({
        source: src,
        title: cardTitle(card),
        missing: tokens.filter((term) => !hay.includes(term)),
      });
    }
  }
  return { weak, partial };
}

function renderRelevanceWarning(query, cards) {
  const { weak, partial } = assessRelevance(query, cards);
  if (!weak.length && !partial.length) return "";

  let html = '<div class="relevance-warn" role="status">';
  html += "<strong>Review retrieval relevance</strong>";
  html += "<ul>";
  for (const item of weak) {
    html += `<li><span class="source-badge">${escapeHtml(sourceLabel(item.source))}</span> top hit <em>${escapeHtml(item.title)}</em> may not match your query terms.</li>`;
  }
  for (const item of partial) {
    html += `<li><span class="source-badge">${escapeHtml(sourceLabel(item.source))}</span> top hit missing terms: ${escapeHtml(item.missing.join(", "))}.</li>`;
  }
  html += "</ul><p class=\"hint\">Scroll citations below — stronger hits may appear further down.</p></div>";
  return html;
}

function renderMarkdown(text) {
  if (!text) return "";

  const blocks = String(text).split(/\n{2,}/);
  const htmlBlocks = blocks.map((block) => {
    const lines = block.split("\n");
    const isList = lines.every((line) => /^\s*[-*]\s+/.test(line) || line.trim() === "");
    if (isList && lines.some((line) => /^\s*[-*]\s+/.test(line))) {
      const items = lines
        .filter((line) => /^\s*[-*]\s+/.test(line))
        .map((line) => `<li>${inlineMarkdown(line.replace(/^\s*[-*]\s+/, ""))}</li>`)
        .join("");
      return `<ul class="answer-list">${items}</ul>`;
    }

    if (/^#{1,3}\s+/.test(block)) {
      const level = block.match(/^(#{1,3})\s+/)[1].length;
      const tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      const content = block.replace(/^#{1,3}\s+/, "");
      return `<${tag} class="answer-heading">${inlineMarkdown(content)}</${tag}>`;
    }

    return `<p>${inlineMarkdown(block.replace(/\n/g, "<br />"))}</p>`;
  });

  return `<div class="answer-md">${htmlBlocks.join("")}</div>`;
}

function inlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "<em>$1</em>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");
  return html;
}

function renderHtmlTeachingBanner(evidence) {
  const htmlResult = evidence?.html_result;
  if (!htmlResult?.html_url) return "";

  return `<div class="teaching-banner">
    <strong>Teaching page ready</strong>
    <p>${escapeHtml(String(htmlResult.evidence_count || 0))} evidence items, ${escapeHtml(String(htmlResult.figure_count || 0))} figures</p>
    <a href="${escapeAttr(htmlResult.html_url)}" target="_blank" rel="noopener" class="teaching-link">Open HTML teaching page</a>
  </div>`;
}

function renderCitationLinks(links) {
  if (!links.length) return "";
  let html = '<div class="citation-links">';
  for (const link of links) {
    const previewable = ["page_image_url", "figure_url", "image_url"].includes(link.key);
    if (previewable) {
      html += `<button type="button" class="link-btn preview-btn" data-preview-url="${escapeAttr(link.href)}" data-preview-caption="${escapeAttr(link.label)}">${escapeHtml(link.label)}</button>`;
    } else {
      html += `<a href="${escapeAttr(link.href)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>`;
    }
  }
  html += "</div>";
  return html;
}

function renderCitations(cards, figures) {
  if (!cards?.length && !figures?.length) {
    return '<p class="hint">No citation cards returned for this query.</p>';
  }

  let html = '<details class="citations" open><summary>Sources &amp; citations</summary><ul class="citation-list">';
  for (const card of cards || []) {
    const title = cardTitle(card);
    const source = card.source || card._result_key || "unknown";
    const excerpt = (card.text_excerpt || card.excerpt || "").slice(0, 280);
    const links = collectCardLinks(card);
    const thumb = previewUrl(card);
    const { weak, partial } = assessRelevance(
      queryInput.dataset.lastQuery || "",
      [card],
    );
    const relevanceClass =
      weak.length > 0 ? " citation-weak" : partial.length > 0 ? " citation-partial" : "";

    html += `<li class="citation-item${relevanceClass}">`;
    html += `<div class="citation-head"><strong>${escapeHtml(title)}</strong>`;
    html += `<span class="source-badge">${escapeHtml(sourceLabel(source))}</span></div>`;
    if (excerpt) html += `<div class="citation-excerpt">${escapeHtml(excerpt)}</div>`;
    if (thumb) {
      html += `<button type="button" class="citation-thumb-btn" data-preview-url="${escapeAttr(thumb)}" data-preview-caption="${escapeAttr(title)}">`;
      html += `<img src="${escapeAttr(thumb)}" alt="" class="citation-thumb" loading="lazy" />`;
      html += `<span>Preview image</span></button>`;
    }
    html += renderCitationLinks(links);
    html += "</li>";
  }
  html += "</ul>";

  if (figures?.length) {
    html += '<div class="figures-grid">';
    for (const fig of figures) {
      const url = fig.figure_url || fig.image_url || fig.url;
      if (url) {
        const caption = fig.caption || fig.title || "figure";
        html += `<figure><button type="button" class="figure-preview-btn" data-preview-url="${escapeAttr(url)}" data-preview-caption="${escapeAttr(caption)}">`;
        html += `<img src="${escapeAttr(url)}" alt="${escapeAttr(caption)}" loading="lazy" /></button>`;
        html += `<figcaption>${escapeHtml(caption)}</figcaption></figure>`;
      }
    }
    html += "</div>";
  }

  html += "</details>";
  return html;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/'/g, "&#39;");
}

function selectedSources() {
  return [...sourceCheckboxes.querySelectorAll("input:checked")].map((el) => el.value);
}

function buildPayload(query) {
  return {
    query,
    mode: modeSelect.value,
    sources: selectedSources(),
    max_results: Number(maxResultsInput.value) || 5,
    include_figures: modeSelect.value === "visual",
    max_figures: modeSelect.value === "visual" ? 5 : 0,
    compact: true,
    excerpt_char_limit: 900,
    render_html: modeSelect.value === "html_teaching",
  };
}

function openMediaPreview(url, caption) {
  mediaModalImg.src = url;
  mediaModalImg.alt = caption || "Preview";
  mediaModalImg.hidden = false;
  mediaModalCaption.textContent = caption || "";
  mediaModalOpen.href = url;
  mediaModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeMediaPreview() {
  mediaModal.classList.add("hidden");
  mediaModalImg.src = "";
  mediaModalImg.hidden = true;
  document.body.classList.remove("modal-open");
}

function bindPreviewHandlers(root) {
  root.querySelectorAll("[data-preview-url]").forEach((el) => {
    el.addEventListener("click", () => {
      openMediaPreview(el.dataset.previewUrl, el.dataset.previewCaption || "");
    });
  });
}

async function refreshHealth() {
  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    supportedSources = data.supported_sources || [];
    renderSourceCheckboxes();

    const hubKey = data.secrets?.pathology_hub?.present;
    const openaiKey = data.secrets?.openai?.present;
    const backendOk = data.backend?.ok;
    healthStatus.className = "status";
    if (backendOk && hubKey) {
      healthStatus.classList.add("ok");
      healthStatus.textContent = openaiKey ? "Ready" : "Ready (search-only)";
    } else if (!hubKey) {
      healthStatus.classList.add("warn");
      healthStatus.textContent = "API key missing";
    } else {
      healthStatus.classList.add("warn");
      healthStatus.textContent = "Backend unreachable";
    }
  } catch (err) {
    healthStatus.className = "status error";
    healthStatus.textContent = "Health check failed";
  }
}

function renderSourceCheckboxes() {
  if (!supportedSources.length || sourceCheckboxes.childElementCount) return;
  for (const src of supportedSources) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = src;
    input.checked = DEFAULT_SOURCES.includes(src);
    label.appendChild(input);
    label.appendChild(document.createTextNode(sourceLabel(src)));
    sourceCheckboxes.appendChild(label);
  }
}

function updateModeHint() {
  modeHint.textContent = MODE_HINTS[modeSelect.value] || "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  queryInput.dataset.lastQuery = query;
  appendMessage("user", escapeHtml(query));
  queryInput.value = "";
  sendBtn.disabled = true;

  const thinking = appendMessage("assistant", "<em>Searching evidence…</em>");

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload(query)),
    });
    const data = await resp.json();
    let body = "";

    if (!data.ok) {
      body = `<p class="error-text">${escapeHtml(data.error || data.answer_error || "Request failed")}</p>`;
    } else {
      body += renderRelevanceWarning(query, data.cards);
      body += renderHtmlTeachingBanner(data.evidence);

      if (data.answer) {
        body += renderMarkdown(data.answer);
        if (data.model) body += `<p class="hint">Model: ${escapeHtml(data.model)}</p>`;
      } else if (data.answer_note) {
        body += `<p class="hint">${escapeHtml(data.answer_note)}</p>`;
      } else {
        body += '<p class="hint">Evidence retrieved (search-only).</p>';
      }
    }

    body += renderCitations(data.cards, data.figures);

    if (debugToggle.checked && data.debug) {
      body += `<details class="debug-block"><summary>Debug</summary><pre>${escapeHtml(JSON.stringify(data.debug, null, 2))}</pre></details>`;
      if (data.evidence?.source_status) {
        body += `<details class="debug-block"><summary>source_status</summary><pre>${escapeHtml(JSON.stringify(data.evidence.source_status, null, 2))}</pre></details>`;
      }
    }

    const bodyEl = thinking.querySelector(".body");
    bodyEl.innerHTML = body;
    bindPreviewHandlers(bodyEl);
  } catch (err) {
    thinking.querySelector(".body").innerHTML = `<p class="error-text">${escapeHtml(String(err))}</p>`;
  } finally {
    sendBtn.disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
});

function loadSessionNotes() {
  try {
    let saved = localStorage.getItem(NOTES_STORAGE_KEY);
    if (saved == null) {
      saved = localStorage.getItem(LEGACY_NOTES_STORAGE_KEY);
    }
    if (saved != null) sessionNotes.value = saved;
  } catch (err) {
    notesStatus.textContent = "Could not load saved notes.";
  }
}

function saveSessionNotes() {
  try {
    localStorage.setItem(NOTES_STORAGE_KEY, sessionNotes.value);
    notesStatus.textContent = "Saved locally.";
  } catch (err) {
    notesStatus.textContent = "Could not save notes.";
  }
}

function scheduleNotesSave() {
  clearTimeout(notesSaveTimer);
  notesSaveTimer = setTimeout(saveSessionNotes, 300);
}

function notesMarkdownExport() {
  const body = sessionNotes.value.trim();
  const stamp = new Date().toISOString();
  return `# Pathology Hub teaching session notes\n\nExported: ${stamp}\n\n---\n\n${body}\n`;
}

async function copySessionNotes() {
  const text = sessionNotes.value;
  if (!text.trim()) {
    notesStatus.textContent = "Nothing to copy.";
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    notesStatus.textContent = "Copied to clipboard.";
  } catch (err) {
    notesStatus.textContent = "Copy failed — select and copy manually.";
  }
}

function exportSessionNotes() {
  const md = notesMarkdownExport();
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  anchor.href = url;
  anchor.download = `pathology_hub_teaching_session_${stamp}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
  notesStatus.textContent = "Markdown file downloaded.";
}

function appendMessage(role, html) {
  const tpl = document.getElementById("message-template");
  const node = tpl.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".role").textContent = role === "user" ? "You" : "Assistant";
  node.querySelector(".body").innerHTML = html;
  messagesEl.appendChild(node);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return node;
}

mediaModal.querySelectorAll("[data-modal-close]").forEach((el) => {
  el.addEventListener("click", closeMediaPreview);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !mediaModal.classList.contains("hidden")) {
    closeMediaPreview();
  }
});

modeSelect.addEventListener("change", updateModeHint);
sessionNotes.addEventListener("input", scheduleNotesSave);
copyNotesBtn.addEventListener("click", copySessionNotes);
exportNotesBtn.addEventListener("click", exportSessionNotes);

loadSessionNotes();
updateModeHint();
refreshHealth();
