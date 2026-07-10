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

/** Static organ-system taxonomy for the "Browse by organ system" quick-start
 * panel. Grounded in the real root categories used by the curriculum map
 * (Skin, HN, BST, GI, Breast, GYN::*, GU::*, Heme, Endo, Neuro, etc.) — this
 * is a UI-only convenience for building good starter queries, not a claim
 * that any of these are separately indexed/exposed. Every click still goes
 * through the single existing evidence search call. */
const ORGAN_SYSTEMS = [
  { id: "breast", label: "Breast", topics: ["LCIS", "DCIS", "Invasive ductal carcinoma", "Fibroadenoma", "Phyllodes tumor"] },
  { id: "gyn_cervix", label: "Gyn — Cervix", topics: ["CIN2", "CIN3 / HSIL", "Cervical adenocarcinoma", "Endocervical polyp"] },
  { id: "gyn_uterus", label: "Gyn — Uterus", topics: ["Endometrial hyperplasia", "Endometrioid carcinoma", "Leiomyoma", "Leiomyosarcoma uterus"] },
  { id: "gyn_ovary", label: "Gyn — Ovary", topics: ["Serous borderline tumor", "High-grade serous carcinoma", "Mature cystic teratoma", "Granulosa cell tumor"] },
  { id: "gi", label: "GI / Colon", topics: ["Tubular adenoma colon", "Sessile serrated lesion", "Colorectal adenocarcinoma", "Ulcerative colitis"] },
  { id: "gu", label: "GU — Prostate/Bladder/Kidney", topics: ["Prostatic adenocarcinoma Gleason", "High-grade urothelial carcinoma", "Clear cell renal cell carcinoma", "Papillary renal cell carcinoma"] },
  { id: "skin", label: "Skin", topics: ["Basal cell carcinoma", "Squamous cell carcinoma skin", "Melanoma", "Seborrheic keratosis"] },
  { id: "hn", label: "Head & Neck", topics: ["Squamous cell carcinoma oral cavity", "Pleomorphic adenoma", "Warthin tumor", "Mucoepidermoid carcinoma"] },
  { id: "bst", label: "Bone & Soft Tissue", topics: ["Osteosarcoma", "Giant cell tumor of bone", "Liposarcoma", "Leiomyosarcoma soft tissue"] },
  { id: "heme", label: "Heme / Lymph node", topics: ["Diffuse large B-cell lymphoma", "Follicular lymphoma", "Hodgkin lymphoma", "Reactive lymphoid hyperplasia"] },
  { id: "endo", label: "Endocrine", topics: ["Papillary thyroid carcinoma", "Follicular adenoma thyroid", "Medullary thyroid carcinoma", "Parathyroid adenoma"] },
  { id: "neuro", label: "Neuro", topics: ["Glioblastoma", "Meningioma", "Pilocytic astrocytoma", "Schwannoma"] },
  { id: "thorax", label: "Thorax / Mediastinum", topics: ["Lung adenocarcinoma", "Squamous cell carcinoma lung", "Thymoma", "Mesothelioma"] },
  { id: "cyto", label: "Cytology", topics: ["Thyroid FNA Bethesda", "Pap smear HSIL", "Pancreatic FNA adenocarcinoma", "Effusion cytology adenocarcinoma"] },
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
const organChipsEl = document.getElementById("organ-chips");
const topicChipsEl = document.getElementById("topic-chips");

let supportedSources = [];
let notesSaveTimer = null;
let activeOrganSystem = null;

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

/** Maps every literal URL found on a card/figure to that item's rich preview
 * payload, so inline answer citations can open the same modal preview
 * (page image / figure) as the citation cards, instead of blind navigation. */
function buildUrlPreviewIndex(cards, figures) {
  const index = new Map();
  const addUrl = (url, payload) => {
    if (typeof url === "string" && url.startsWith("http") && !index.has(url)) {
      index.set(url, payload);
    }
  };

  for (const card of cards || []) {
    if (!card || typeof card !== "object") continue;
    const presentation = cardPresentation(card);
    if (!presentation.previewUrl) continue;
    const payload = {
      previewUrl: presentation.previewUrl,
      caption: presentation.caption,
      modalLinks: presentation.modalLinks,
    };
    for (const field of [
      "source_url",
      "source_page_url",
      "source_pdf_url",
      "figure_url",
      "page_image_url",
      "image_url",
      "video_time_url",
    ]) {
      addUrl(card[field], payload);
    }
  }

  for (const fig of figures || []) {
    if (!fig || typeof fig !== "object") continue;
    const url = pickHttp(fig.figure_url) || pickHttp(fig.image_url) || pickHttp(fig.url);
    if (!url) continue;
    const payload = {
      previewUrl: url,
      caption: fig.caption || fig.title || "Figure",
      modalLinks: {
        figure: url,
        pageImage: pickHttp(fig.page_image_url),
        source: pickHttp(fig.source_url),
        reference: pickHttp(fig.source_page_url),
      },
    };
    for (const field of ["figure_url", "image_url", "url", "page_image_url", "source_url", "source_page_url"]) {
      addUrl(fig[field], payload);
    }
  }

  return index;
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

/** Best-effort strip of a trailing "Sources:"/"References:" link-dump block.
 * Inline citations already carry every URL; a closing roundup is redundant
 * and the prompt forbids it, but models occasionally slip and add one anyway. */
function stripTrailingLinkDump(text) {
  const blocks = text.split(/\n{2,}/);
  while (blocks.length > 1) {
    const last = blocks[blocks.length - 1].trim();
    const isDumpHeading = /^(\*\*)?(sources|references|evidence used|evidence base|links)(\*\*)?:?\s*$/im.test(
      last.split("\n")[0].trim(),
    );
    const linesAfterHeading = last.split("\n").slice(1);
    const restIsLinksOnly =
      linesAfterHeading.length > 0 &&
      linesAfterHeading.every((line) => {
        const t = line.trim();
        return !t || /^[-*]?\s*\[[^\]]+\]\(https?:[^)\s]+\)\s*$/.test(t);
      });
    if (isDumpHeading && restIsLinksOnly) {
      blocks.pop();
      continue;
    }
    break;
  }
  return blocks.join("\n\n");
}

function renderMarkdown(text, previewIndex) {
  const normalized = stripTrailingLinkDump(normalizeAnswerText(text));
  if (!normalized.trim()) return "";

  const blocks = normalized.split(/\n{2,}/);
  const htmlBlocks = blocks.map((block) => {
    const trimmed = block.replace(/^\n+|\n+$/g, "");
    if (!trimmed.trim()) return "";

    if (isMarkdownTable(trimmed)) {
      return renderMarkdownTable(trimmed);
    }

    const lines = trimmed.split("\n");
    const isList = lines.every((line) => /^\s*[-*]\s+/.test(line) || line.trim() === "");
    if (isList && lines.some((line) => /^\s*[-*]\s+/.test(line))) {
      return renderNestedList(lines.filter((line) => line.trim()), previewIndex);
    }

    if (/^#{1,3}\s+/.test(trimmed)) {
      const level = trimmed.match(/^(#{1,3})\s+/)[1].length;
      const tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      const content = trimmed.replace(/^#{1,3}\s+/, "");
      return `<${tag} class="answer-heading">${inlineMarkdown(content, previewIndex)}</${tag}>`;
    }

    if (lines.length > 1 && lines.every((line) => line.trim())) {
      return lines.map((line) => `<p class="answer-line">${inlineMarkdown(line, previewIndex)}</p>`).join("");
    }

    return `<p class="answer-line">${inlineMarkdown(trimmed, previewIndex)}</p>`;
  });

  return `<div class="answer-md">${htmlBlocks.join("")}</div>`;
}

/** Indentation-aware bullet list renderer. Every 2 (or 1-4) leading spaces
 * of extra indent relative to the first bullet opens one nested <ul> level. */
function renderNestedList(lines, previewIndex) {
  const indentOf = (line) => line.match(/^\s*/)[0].replace(/\t/g, "  ").length;
  const baseIndent = indentOf(lines[0]);
  const stepGuess = Math.max(
    1,
    ...lines.slice(1).map((line) => indentOf(line) - baseIndent).filter((delta) => delta > 0),
  );

  const root = { children: [], depth: -1 };
  const stack = [root];

  for (const line of lines) {
    const depth = Math.max(0, Math.round((indentOf(line) - baseIndent) / stepGuess));
    const content = line.replace(/^\s*[-*]\s+/, "");
    const node = { html: inlineMarkdown(content, previewIndex), children: [] };

    while (stack.length - 1 > depth) stack.pop();
    while (stack.length - 1 < depth) {
      const parent = stack[stack.length - 1];
      const lastChild = parent.children[parent.children.length - 1];
      const holder = lastChild || { html: "", children: [] };
      if (!lastChild) parent.children.push(holder);
      stack.push(holder);
    }
    stack[stack.length - 1].children.push(node);
  }

  const renderChildren = (nodes) => {
    if (!nodes.length) return "";
    const items = nodes
      .map((n) => `<li>${n.html}${renderChildren(n.children)}</li>`)
      .join("");
    return `<ul class="answer-list">${items}</ul>`;
  };

  return renderChildren(root.children);
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

function inlineMarkdown(text, previewIndex) {
  const tokens = [];
  const stash = (html) => {
    const token = `__MDTOK${tokens.length}__`;
    tokens.push(html);
    return token;
  };

  // Image syntax first: ![caption](url) -> inline preview-capable thumbnail.
  let scratch = String(text).replace(/!\[([^\]]*)\]\((https?:[^)\s]+)\)/g, (_, alt, url) => {
    return stash(renderInlineImage(alt, url, previewIndex));
  });

  // Plain links: [label](url) -> preview-aware link when we recognize the URL,
  // otherwise a normal external link.
  scratch = scratch.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (_, label, url) => {
    return stash(renderInlineLink(label, url, previewIndex));
  });

  let html = escapeHtml(scratch);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "<em>$1</em>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");

  tokens.forEach((tokenHtml, index) => {
    html = html.replace(`__MDTOK${index}__`, tokenHtml);
  });

  return html;
}

function renderInlineLink(label, url, previewIndex) {
  const preview = previewIndex?.get(url);
  const safeHref = escapeAttr(url);
  const safeLabel = escapeHtml(label);
  if (preview?.previewUrl) {
    const payload = escapeAttr(JSON.stringify(preview));
    return `<a href="${safeHref}" target="_blank" rel="noopener" class="inline-cite-link" data-preview="${payload}">${safeLabel}</a>`;
  }
  return `<a href="${safeHref}" target="_blank" rel="noopener">${safeLabel}</a>`;
}

function renderInlineImage(alt, url, previewIndex) {
  const preview = previewIndex?.get(url) || { previewUrl: url, caption: alt, modalLinks: { figure: url } };
  const payload = escapeAttr(JSON.stringify(preview));
  const safeAlt = escapeAttr(alt || "Figure");
  return (
    `<button type="button" class="inline-figure-btn" data-preview="${payload}">` +
    `<img src="${escapeAttr(url)}" alt="${safeAlt}" loading="lazy" class="inline-figure-img" />` +
    `<span class="inline-figure-caption">${escapeHtml(alt || "View figure")}</span></button>`
  );
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
    el.addEventListener("click", (event) => {
      // Preview-aware <a> tags keep their href so ctrl/cmd/middle-click still
      // opens the raw source in a new tab; a plain click shows the rich preview.
      const isModifiedClick =
        el.tagName === "A" && (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1);
      if (isModifiedClick) return;
      try {
        if (el.tagName === "A") event.preventDefault();
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

function renderOrganChips() {
  if (!organChipsEl || organChipsEl.childElementCount) return;
  for (const system of ORGAN_SYSTEMS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.textContent = system.label;
    btn.dataset.organId = system.id;
    btn.addEventListener("click", () => selectOrganSystem(system.id));
    organChipsEl.appendChild(btn);
  }
}

function selectOrganSystem(systemId) {
  activeOrganSystem = systemId === activeOrganSystem ? null : systemId;

  organChipsEl.querySelectorAll(".chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.organId === activeOrganSystem);
  });

  topicChipsEl.innerHTML = "";
  const system = ORGAN_SYSTEMS.find((s) => s.id === activeOrganSystem);
  if (!system) return;

  for (const topic of system.topics) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip topic-chip";
    btn.textContent = topic;
    btn.addEventListener("click", () => runOrganTopicQuery(topic));
    topicChipsEl.appendChild(btn);
  }
}

function runOrganTopicQuery(topic) {
  queryInput.value = topic;
  form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true }));
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
      const previewIndex = buildUrlPreviewIndex(data.cards || [], data.figures || []);

      body += renderHtmlTeachingBanner(data.evidence);
      body += renderFiguresStrip(data.figures, query);

      if (data.answer) {
        body += renderMarkdown(data.answer, previewIndex);
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
renderOrganChips();
refreshHealth();
