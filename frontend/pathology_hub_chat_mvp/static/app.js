const DEFAULT_SOURCES = ["textbooks", "pathout", "who"];

const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const modeSelect = document.getElementById("mode-select");
const maxResultsInput = document.getElementById("max-results");
const debugToggle = document.getElementById("debug-toggle");
const healthStatus = document.getElementById("health-status");
const sourceCheckboxes = document.getElementById("source-checkboxes");

let supportedSources = [];

function linkFields(card) {
  const keys = [
    "source_url",
    "source_page_url",
    "page_image_url",
    "figure_url",
    "image_url",
    "video_time_url",
    "html_url",
  ];
  for (const key of keys) {
    const val = card[key];
    if (typeof val === "string" && val.startsWith("http")) return { label: key, href: val };
  }
  return null;
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

function renderCitations(cards, figures) {
  if (!cards?.length && !figures?.length) {
    return "<p class=\"hint\">No citation cards returned for this query.</p>";
  }

  let html = "<details class=\"citations\" open><summary>Sources &amp; citations</summary><ul class=\"citation-list\">";
  for (const card of cards || []) {
    const title = card.title || card.name || card.primary_tag || "(untitled hit)";
    const source = card.source || card._result_key || "unknown";
    const excerpt = (card.text_excerpt || card.excerpt || "").slice(0, 280);
    const link = linkFields(card);
    html += `<li class="citation-item"><strong>${escapeHtml(title)}</strong>`;
    html += `<div class="meta">${escapeHtml(source)}</div>`;
    if (excerpt) html += `<div>${escapeHtml(excerpt)}</div>`;
    if (link) {
      html += `<div><a href="${escapeAttr(link.href)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a></div>`;
    }
    html += "</li>";
  }
  html += "</ul>";

  if (figures?.length) {
    html += "<div class=\"figures-grid\">";
    for (const fig of figures) {
      const url = fig.figure_url || fig.image_url || fig.url;
      if (url) {
        html += `<figure><img src="${escapeAttr(url)}" alt="${escapeAttr(fig.caption || fig.title || "figure")}" /><figcaption>${escapeHtml(fig.caption || fig.title || "")}</figcaption></figure>`;
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
      healthStatus.textContent = openaiKey ? "Backend + keys OK" : "Backend OK (OpenAI optional)";
    } else if (!hubKey) {
      healthStatus.classList.add("warn");
      healthStatus.textContent = "Missing Pathology Hub API key";
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
    label.appendChild(document.createTextNode(src));
    sourceCheckboxes.appendChild(label);
  }
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
    } else if (data.answer) {
      body = `<div>${escapeHtml(data.answer)}</div>`;
      if (data.model) body += `<p class="hint">Model: ${escapeHtml(data.model)}</p>`;
    } else if (data.answer_note) {
      body = `<p class="hint">${escapeHtml(data.answer_note)}</p>`;
    } else {
      body = "<p class=\"hint\">Evidence retrieved (search-only).</p>";
    }

    body += renderCitations(data.cards, data.figures);

    if (debugToggle.checked && data.debug) {
      body += `<details class="debug-block"><summary>Debug</summary><pre>${escapeHtml(JSON.stringify(data.debug, null, 2))}</pre></details>`;
      if (data.evidence?.source_status) {
        body += `<details class="debug-block"><summary>source_status</summary><pre>${escapeHtml(JSON.stringify(data.evidence.source_status, null, 2))}</pre></details>`;
      }
    }

    thinking.querySelector(".body").innerHTML = body;
  } catch (err) {
    thinking.querySelector(".body").innerHTML = `<p class="error-text">${escapeHtml(String(err))}</p>`;
  } finally {
    sendBtn.disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
});

refreshHealth();
