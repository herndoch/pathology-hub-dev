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

const MODE_HINTS = {
  gpt_like: "Bullet summary with inline source links. Figures auto-included when you ask to show something.",
  search_only: "Raw evidence cards only — no OpenAI synthesis.",
  compare_sources: "Markdown table comparing sources, plus brief agreement bullets.",
  visual: "Figures retrieved and shown above the answer.",
  html_teaching: "Hosted HTML teaching page — link appears above citations.",
};

const VISUAL_QUERY_RE =
  /\b(show\s+me|show|picture|pictures|photo|photos|image|images|figure|figures|histology|histologic|microscopic|microscopy|gross|what\s+does|look\s+like|demonstrate|illustrate|visual)\b/i;

const QUERY_STOPWORDS = new Set([
  "the", "a", "an", "of", "in", "for", "and", "or", "with", "is", "are", "to", "on", "at", "by", "me", "my",
]);

/** Expand common pathology shorthand for client-side relevance checks. */
const TERM_EXPANSIONS = {
  cin1: ["cin", "cervical", "cervix", "intraepithelial", "squamous", "sil", "lsil"],
  cin2: ["cin", "cervical", "cervix", "intraepithelial", "squamous", "sil", "hsil"],
  cin3: ["cin", "cervical", "cervix", "intraepithelial", "squamous", "sil", "hsil"],
  cin: ["cervical", "cervix", "intraepithelial", "squamous", "sil"],
  lsil: ["squamous", "intraepithelial", "cervical", "cervix", "sil"],
  hsil: ["squamous", "intraepithelial", "cervical", "cervix", "sil"],
  lcis: ["lobular", "breast", "in", "situ"],
  dcis: ["ductal", "breast", "in", "situ"],
  ssl: ["serrated", "colon", "sessile"],
  crc: ["colorectal", "colon", "carcinoma"],
};

/** Hard mismatches — if query implies A, block content clearly about B. */
const TOPIC_CONFLICTS = [
  {
    query: ["cervical", "cervix", "cin", "lsil", "hsil", "endocervical", "colposcopy"],
    block: ["salivary", "myoepithelial", "parotid", "submandibular", "myoepithelioma"],
  },
  {
    query: ["breast", "lcis", "dcis", "mammary"],
    block: ["salivary", "myoepithelial", "colon", "cervical", "cervix"],
  },
  {
    query: ["colon", "colorectal", "rectal", "adenoma"],
    block: ["salivary", "breast", "cervical", "cervix"],
  },
];

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
const mediaModalFigure = document.getElementById("media-modal-figure");
const mediaModalPage = document.getElementById("media-modal-page");
const mediaModalSource = document.getElementById("media-modal-source");
const mediaModalReference = document.getElementById("media-modal-reference");

let supportedSources = [];
let notesSaveTimer = null;

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source;
}

function cardTitle(card) {
  return card.title || card.name || card.heading || card.primary_tag || "(untitled hit)";
}

function pickHttp(value) {
  return typeof value === "string" && value.startsWith("http") ? value : null;
}

function wantsVisual(query, mode) {
  return mode === "visual" || VISUAL_QUERY_RE.test(query || "");
}

function queryMatchTerms(query) {
  const stripped = String(query || "")
    .toLowerCase()
    .replace(VISUAL_QUERY_RE, " ")
    .replace(/[^\w\s]/g, " ");
  const raw = stripped.split(/\s+/).filter((t) => t.length >= 2 && !QUERY_STOPWORDS.has(t));
  const terms = new Set(raw);
  for (const token of raw) {
    for (const extra of TERM_EXPANSIONS[token] || []) {
      terms.add(extra);
    }
  }
  return [...terms];
}

function itemHaystack(item) {
  return [
    item.caption,
    item.title,
    item.name,
    item.heading,
    item.primary_tag,
    item.text_excerpt,
    item.excerpt,
    item.header,
    item.source_id,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function hasTopicConflict(queryTerms, haystack) {
  for (const rule of TOPIC_CONFLICTS) {
    const queryHit = rule.query.some((term) => queryTerms.includes(term));
    if (!queryHit) continue;
    if (rule.block.some((term) => haystack.includes(term))) {
      return true;
    }
  }
  return false;
}

function relevanceScore(query, item) {
  const terms = queryMatchTerms(query);
  if (!terms.length) return 1;
  const hay = itemHaystack(item);
  if (hasTopicConflict(terms, hay)) return -1;
  const hits = terms.filter((term) => hay.includes(term));
  if (!hits.length) return 0;
  return hits.length / terms.length;
}

function filterByQueryRelevance(query, items, { maxShown = 8 } = {}) {
  const list = items || [];
  if (!list.length) {
    return { shown: [], hidden: [], note: "" };
  }

  const scored = list.map((item) => ({ item, score: relevanceScore(query, item) }));
  const relevant = scored.filter((row) => row.score > 0).sort((a, b) => b.score - a.score);
  const conflicts = scored.filter((row) => row.score < 0);
  const irrelevant = scored.filter((row) => row.score === 0);

  if (relevant.length) {
    const shown = relevant.slice(0, maxShown).map((row) => row.item);
    const hiddenCount = conflicts.length + irrelevant.length + Math.max(0, relevant.length - maxShown);
    const note =
      hiddenCount > 0
        ? `${hiddenCount} off-topic hit${hiddenCount === 1 ? "" : "s"} hidden for this query.`
        : "";
    return { shown, hidden: [...conflicts, ...irrelevant].map((row) => row.item), note };
  }

  if (conflicts.length) {
    return {
      shown: [],
      hidden: list,
      note: `${conflicts.length} retrieved figure${conflicts.length === 1 ? "" : "s"} matched the wrong organ/topic (e.g. salivary vs cervical). Try unchecking WHO or use Search only.`,
    };
  }

  return {
    shown: list.slice(0, maxShown),
    hidden: list.slice(maxShown),
    note: "",
  };
}

function cardPresentation(card) {
  const figure = pickHttp(card.figure_url) || pickHttp(card.image_url);
  const pageImage = pickHttp(card.page_image_url);
  const source = pickHttp(card.source_url);
  const reference = pickHttp(card.source_page_url);
  const video = pickHttp(card.video_time_url);
  const previewUrl = figure || pageImage;
  const srcLabel = sourceLabel(card.source || "");

  const displayLinks = [];
  const seen = new Set();
  const primary = source || reference || video;
  if (primary) {
    let label = "Open source";
    if (source && primary === source) label = `Open ${srcLabel}`;
    else if (video && primary === video) label = "Video timestamp";
    else if (reference && primary === reference) label = "Reference page";
    displayLinks.push({ label, href: primary });
    seen.add(primary);
  }
  if (reference && !seen.has(reference)) {
    displayLinks.push({ label: "Reference page", href: reference });
    seen.add(reference);
  }

  return {
    previewUrl,
    caption: cardTitle(card),
    modalLinks: { figure, pageImage, source, reference, video },
    displayLinks,
  };
}

function normalizeAnswerText(text) {
  return String(text || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\r\n/g, "\n");
}

function renderMarkdown(text) {
  const normalized = normalizeAnswerText(text);
  if (!normalized.trim()) return "";

  const blocks = normalized.split(/\n{2,}/);
  const htmlBlocks = blocks.map((block) => {
    const trimmed = block.trim();
    if (!trimmed) return "";

    if (isMarkdownTable(trimmed)) {
      return renderMarkdownTable(trimmed);
    }

    const lines = trimmed.split("\n");
    const isList = lines.every((line) => /^\s*[-*]\s+/.test(line) || line.trim() === "");
    if (isList && lines.some((line) => /^\s*[-*]\s+/.test(line))) {
      const items = lines
        .filter((line) => /^\s*[-*]\s+/.test(line))
        .map((line) => `<li>${inlineMarkdown(line.replace(/^\s*[-*]\s+/, ""))}</li>`)
        .join("");
      return `<ul class="answer-list">${items}</ul>`;
    }

    if (/^#{1,3}\s+/.test(trimmed)) {
      const level = trimmed.match(/^(#{1,3})\s+/)[1].length;
      const tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      const content = trimmed.replace(/^#{1,3}\s+/, "");
      return `<${tag} class="answer-heading">${inlineMarkdown(content)}</${tag}>`;
    }

    if (lines.length > 1 && lines.every((line) => line.trim())) {
      return lines.map((line) => `<p class="answer-line">${inlineMarkdown(line)}</p>`).join("");
    }

    return `<p class="answer-line">${inlineMarkdown(trimmed)}</p>`;
  });

  return `<div class="answer-md">${htmlBlocks.join("")}</div>`;
}

function isMarkdownTable(block) {
  const lines = block.split("\n").filter((line) => line.trim());
  if (lines.length < 2) return false;
  return lines.every((line) => line.includes("|"));
}

function renderMarkdownTable(block) {
  const lines = block.split("\n").filter((line) => line.trim() && !/^\|[\s\-:|]+\|$/.test(line.trim()));
  if (!lines.length) return "";

  const rows = lines.map((line) =>
    line
      .split("|")
      .map((cell) => cell.trim())
      .filter((cell, idx, arr) => !(idx === 0 && cell === "") && !(idx === arr.length - 1 && cell === "")),
  );

  const [header, ...body] = rows;
  if (!header?.length) return "";

  let html = '<table class="answer-table"><thead><tr>';
  for (const cell of header) {
    html += `<th>${inlineMarkdown(cell)}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of body) {
    html += "<tr>";
    for (let i = 0; i < header.length; i += 1) {
      html += `<td>${inlineMarkdown(row[i] || "—")}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return html;
}

function inlineMarkdown(text) {
  const links = [];
  let scratch = String(text).replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (_, label, url) => {
    const token = `__MDLINK${links.length}__`;
    links.push({ label, url });
    return token;
  });

  let html = escapeHtml(scratch);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "<em>$1</em>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");

  links.forEach((link, index) => {
    html = html.replace(
      `__MDLINK${index}__`,
      `<a href="${escapeAttr(link.url)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>`,
    );
  });

  return html;
}

function renderHtmlTeachingBanner(evidence) {
  const htmlResult = evidence?.html_result;
  if (!htmlResult?.html_url) return "";

  return `<div class="teaching-banner">
    <strong>Teaching page ready</strong>
    <p>${escapeHtml(String(htmlResult.evidence_count || 0))} evidence · ${escapeHtml(String(htmlResult.figure_count || 0))} figures</p>
    <a href="${escapeAttr(htmlResult.html_url)}" target="_blank" rel="noopener" class="teaching-link">Open HTML teaching page</a>
  </div>`;
}

function renderFiguresStrip(figures, query) {
  const { shown, note } = filterByQueryRelevance(query, figures, { maxShown: 6 });
  if (!shown.length) {
    if (note) return `<p class="hint figures-note">${escapeHtml(note)}</p>`;
    return "";
  }

  let html = '<div class="figures-strip"><div class="figures-strip-title">Figures matching your query</div>';
  if (note) html += `<p class="hint figures-note">${escapeHtml(note)}</p>`;
  html += '<div class="figures-grid figures-grid-prominent">';
  for (const fig of shown) {
    const url = fig.figure_url || fig.image_url || fig.url;
    if (!url) continue;
    const caption = fig.caption || fig.title || "Figure";
    const payload = escapeAttr(
      JSON.stringify({
        previewUrl: url,
        caption,
        modalLinks: {
          figure: pickHttp(fig.figure_url) || pickHttp(fig.image_url) || pickHttp(fig.url),
          pageImage: pickHttp(fig.page_image_url),
          source: pickHttp(fig.source_url),
          reference: pickHttp(fig.source_page_url),
        },
      }),
    );
    html += `<figure><button type="button" class="figure-preview-btn" data-preview="${payload}">`;
    html += `<img src="${escapeAttr(url)}" alt="${escapeAttr(caption)}" loading="lazy" /></button>`;
    html += `<figcaption>${escapeHtml(caption)}</figcaption></figure>`;
  }
  html += "</div></div>";
  return html;
}

function renderCitationLinks(presentation) {
  if (!presentation.displayLinks.length) return "";
  let html = '<div class="citation-links">';
  for (const link of presentation.displayLinks) {
    html += `<a href="${escapeAttr(link.href)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>`;
  }
  html += "</div>";
  return html;
}

function renderCitations(cards) {
  if (!cards?.length) {
    return '<p class="hint">No citation cards returned for this query.</p>';
  }

  let html = '<details class="citations"><summary>Sources &amp; citations</summary><ul class="citation-list">';
  for (const card of cards) {
    const source = card.source || card._result_key || "unknown";
    const excerpt = (card.text_excerpt || card.excerpt || "").slice(0, 220);
    const presentation = cardPresentation(card);
    const previewPayload = presentation.previewUrl
      ? escapeAttr(
          JSON.stringify({
            previewUrl: presentation.previewUrl,
            caption: presentation.caption,
            modalLinks: presentation.modalLinks,
          }),
        )
      : "";

    html += '<li class="citation-item">';
    html += `<div class="citation-head"><strong>${escapeHtml(presentation.caption)}</strong>`;
    html += `<span class="source-badge">${escapeHtml(sourceLabel(source))}</span></div>`;
    if (excerpt) html += `<div class="citation-excerpt">${escapeHtml(excerpt)}</div>`;
    if (previewPayload) {
      html += `<button type="button" class="citation-thumb-btn" data-preview="${previewPayload}">`;
      html += `<img src="${escapeAttr(presentation.previewUrl)}" alt="" class="citation-thumb" loading="lazy" />`;
      html += `<span>Open preview</span></button>`;
    }
    html += renderCitationLinks(presentation);
    html += "</li>";
  }
  html += "</ul></details>";
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
  const mode = modeSelect.value;
  const visual = wantsVisual(query, mode);
  return {
    query,
    mode,
    sources: selectedSources(),
    max_results: Number(maxResultsInput.value) || 5,
    include_figures: visual,
    max_figures: visual ? 5 : 0,
    compact: true,
    excerpt_char_limit: 900,
    render_html: mode === "html_teaching",
  };
}

function setModalAction(el, url, label) {
  if (url) {
    el.href = url;
    el.textContent = label;
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

function openMediaPreview(payload) {
  if (!payload?.previewUrl) return;

  mediaModalImg.src = payload.previewUrl;
  mediaModalImg.alt = payload.caption || "Preview";
  mediaModalCaption.textContent = payload.caption || "";

  const links = payload.modalLinks || {};
  setModalAction(mediaModalFigure, links.figure, "Open figure");
  setModalAction(mediaModalPage, links.pageImage, "Open page image");
  setModalAction(
    mediaModalSource,
    links.source || links.video,
    links.video && !links.source ? "Open video" : "Open source",
  );
  setModalAction(mediaModalReference, links.reference, "Open reference page");

  mediaModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeMediaPreview() {
  mediaModal.classList.add("hidden");
  mediaModalImg.src = "";
  document.body.classList.remove("modal-open");
}

function bindPreviewHandlers(root) {
  root.querySelectorAll("[data-preview]").forEach((el) => {
    el.addEventListener("click", () => {
      try {
        openMediaPreview(JSON.parse(el.dataset.preview));
      } catch (err) {
        /* ignore malformed preview payload */
      }
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
      const cardFilter = filterByQueryRelevance(query, data.cards || [], { maxShown: 20 });
      const sortedCards = cardFilter.shown.length ? cardFilter.shown : data.cards || [];

      body += renderHtmlTeachingBanner(data.evidence);
      body += renderFiguresStrip(data.figures, query);

      if (data.answer) {
        body += renderMarkdown(data.answer);
      } else if (data.answer_note) {
        body += `<p class="hint">${escapeHtml(data.answer_note)}</p>`;
      } else if (!data.figures?.length) {
        body += '<p class="hint">Evidence retrieved (search-only).</p>';
      }

      if (cardFilter.note) {
        body += `<p class="hint">${escapeHtml(cardFilter.note)}</p>`;
      }

      body += renderCitations(sortedCards);
    }

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
    if (saved == null) saved = localStorage.getItem(LEGACY_NOTES_STORAGE_KEY);
    if (saved != null && saved !== "undefined") sessionNotes.value = saved;
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
