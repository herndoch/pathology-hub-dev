(() => {
  const DATA_URL = "data/chat_no_ai_content_map_v0_1.json";

  const ONCOTREE_BASE_ROW_HEIGHT = 30;
  const ONCOTREE_BASE_COL_WIDTH = 300;
  const ONCOTREE_ZOOM_STEPS = [0.6, 0.8, 1, 1.2, 1.5];
  const ONCOTREE_TALL_LABEL_CHARS = 34;
  const ROOT_COLORS = [
    "#0f6a6a", "#1d4f91", "#8a4b08", "#5b2c6f", "#1a7a4c",
    "#9b2c2c", "#0e7490", "#a16207", "#3730a3", "#be123c",
    "#047857", "#0369a1", "#b45309", "#6d28d9", "#0f766e",
    "#b91c1c", "#1e40af", "#854d0e", "#7c3aed", "#155e75",
  ];

  const treeEl = document.getElementById("tree");
  const toolbarEl = document.getElementById("oncotree-toolbar");
  const statsEl = document.getElementById("stats");
  const filterEl = document.getElementById("filter");
  const emptyEl = document.getElementById("empty");
  const detailEl = document.getElementById("detail");
  const detailTitle = document.getElementById("detail-title");
  const detailPath = document.getElementById("detail-path");
  const itemListEl = document.getElementById("item-list");
  const figureImg = document.getElementById("figure-img");
  const figureCaption = document.getElementById("figure-caption");
  const limitationsEl = document.getElementById("limitations");
  const sampleModal = document.getElementById("sample-modal");
  const sampleModalTitle = document.getElementById("sample-modal-title");
  const sampleModalMeta = document.getElementById("sample-modal-meta");
  const sampleModalExcerpt = document.getElementById("sample-modal-excerpt");
  const sampleModalFigureWrap = document.getElementById("sample-modal-figure-wrap");
  const sampleModalFigureImg = document.getElementById("sample-modal-figure-img");
  const sampleModalPageWrap = document.getElementById("sample-modal-page-wrap");
  const sampleModalPageImg = document.getElementById("sample-modal-page-img");
  const sampleModalPdf = document.getElementById("sample-modal-pdf");
  const sampleModalFigureLink = document.getElementById("sample-modal-figure-link");
  const sampleModalPageLink = document.getElementById("sample-modal-page-link");

  let index = null;
  let expanded = new Set();
  let zoomIdx = ONCOTREE_ZOOM_STEPS.indexOf(1);
  let activePath = null;
  let activeItemId = null;
  let pathToSourceNode = new Map();

  function zoom() {
    return ONCOTREE_ZOOM_STEPS[zoomIdx] ?? 1;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/'/g, "&#39;");
  }

  function pickHttp(value) {
    return typeof value === "string" && value.startsWith("http") ? value : null;
  }

  function setAction(el, href, label) {
    if (!el) return;
    if (!href) {
      el.hidden = true;
      el.removeAttribute("href");
      return;
    }
    el.hidden = false;
    el.href = href;
    if (label) el.textContent = label;
  }

  function closeSampleModal() {
    if (!sampleModal) return;
    sampleModal.classList.add("hidden");
    document.body.classList.remove("modal-open");
  }

  function openSampleModal(it) {
    if (!sampleModal) return;
    const kind = it.kind === "figure" ? "Figure" : (it.source_family || "Card");
    const page = it.page != null ? `p.${it.page}` : "";
    sampleModalTitle.textContent = it.title || it.source_name || it.source_id || "Source sample";
    sampleModalMeta.textContent = [kind, page, it.figure_id || it.section || ""].filter(Boolean).join(" · ");
    sampleModalExcerpt.textContent = it.caption || it.excerpt || "";

    const figureUrl = pickHttp(it.figure_url || it.image_url);
    const pageUrl = pickHttp(it.page_image_url);
    const pdfUrl = pickHttp(it.source_page_url) || pickHttp(it.source_pdf_url);
    const sourceUrl = pickHttp(it.source_url);

    if (figureUrl) {
      sampleModalFigureWrap.hidden = false;
      sampleModalFigureImg.src = figureUrl;
    } else {
      sampleModalFigureWrap.hidden = true;
      sampleModalFigureImg.removeAttribute("src");
    }
    if (pageUrl) {
      sampleModalPageWrap.hidden = false;
      sampleModalPageImg.src = pageUrl;
    } else {
      sampleModalPageWrap.hidden = true;
      sampleModalPageImg.removeAttribute("src");
    }

    setAction(sampleModalPdf, pdfUrl || sourceUrl, pdfUrl ? (it.page != null ? `Open page ${it.page} in PDF` : "Open PDF") : (sourceUrl ? "Open source" : "Open PDF"));
    setAction(sampleModalFigureLink, figureUrl, "Open figure");
    setAction(sampleModalPageLink, pageUrl, "Open page image");

    sampleModal.classList.remove("hidden");
    document.body.classList.add("modal-open");
  }

  function rootColor(rootId, i) {
    if (!rootId) return ROOT_COLORS[i % ROOT_COLORS.length];
    let h = 0;
    for (let c = 0; c < rootId.length; c += 1) h = (h * 31 + rootId.charCodeAt(c)) >>> 0;
    return ROOT_COLORS[h % ROOT_COLORS.length];
  }

  function collectItems(node) {
    const out = [...(node.items || [])];
    for (const child of node.children || []) out.push(...collectItems(child));
    const seen = new Set();
    return out.filter((it) => {
      const key = (it.record_id || it.chunk_id) || `${it.source_id}|${it.page}|${it.excerpt?.slice(0, 40)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function nodeMatches(node, q) {
    if (!q) return true;
    const hay = `${node.label} ${node.path}`.toLowerCase();
    if (hay.includes(q)) return true;
    for (const it of collectItems(node)) {
      const cHay = `${it.title || ""} ${it.source_name || ""} ${it.source_family || ""} ${it.excerpt || ""} ${it.caption || ""} ${it.figure_id || ""}`.toLowerCase();
      if (cHay.includes(q)) return true;
    }
    return (node.children || []).some((child) => nodeMatches(child, q));
  }

  function filterRoots(roots, q) {
    if (!q) return roots;
    function filterNode(node) {
      if (!nodeMatches(node, q)) return null;
      const kids = (node.children || []).map(filterNode).filter(Boolean);
      return { ...node, children: kids };
    }
    return roots.map(filterNode).filter(Boolean);
  }

  function indexPaths(roots) {
    pathToSourceNode = new Map();
    function walk(node) {
      pathToSourceNode.set(node.path, node);
      for (const child of node.children || []) walk(child);
    }
    for (const r of roots) walk(r);
  }

  function autoExpandForFilter(roots, q) {
    if (!q) return;
    function walk(node) {
      const kids = node.children || [];
      if (kids.some((c) => nodeMatches(c, q))) expanded.add(node.path);
      for (const child of kids) walk(child);
    }
    for (const r of roots) walk(r);
  }

  function buildOncotreeLayout(roots) {
    const rowH = ONCOTREE_BASE_ROW_HEIGHT * zoom();
    const colW = ONCOTREE_BASE_COL_WIDTH * zoom();
    const nodes = [];
    const links = [];
    const linkPairs = [];
    let rowCursor = 0;

    function visit(node, depth, color, path) {
      const kids = node.children || [];
      const isLeaf = kids.length === 0;
      const isExpanded = !isLeaf && expanded.has(path);
      const label = node.label || path;
      const isTall = isLeaf && label.length > ONCOTREE_TALL_LABEL_CHARS;
      let midRow;

      if (isLeaf || !isExpanded) {
        midRow = rowCursor;
        rowCursor += isTall ? 2 : 1;
      } else {
        const childMids = [];
        kids.forEach((child) => {
          const childPath = child.path || `${path}::${child.id}`;
          linkPairs.push({ parentPath: path, childPath, color });
          childMids.push(visit(child, depth + 1, color, childPath));
        });
        midRow = childMids.reduce((sum, m) => sum + m, 0) / childMids.length;
      }

      nodes.push({
        kind: isLeaf ? "leaf" : depth <= 1 ? "root" : "branch",
        path,
        depth,
        x: depth * colW,
        y: midRow * rowH,
        color,
        label,
        isTall,
        hasChildren: !isLeaf,
        expanded: isExpanded,
        leafCount: node.page_count,
        source: node,
      });
      return midRow;
    }

    const rootMids = [];
    const rootColors = [];
    roots.forEach((root, i) => {
      const color = rootColor(root.id, i);
      rootColors.push(color);
      rootMids.push(visit(root, 1, color, root.path || root.id));
    });

    if (rootMids.length) {
      const superMid = rootMids.reduce((s, m) => s + m, 0) / rootMids.length;
      nodes.push({
        kind: "super",
        path: "__all__",
        depth: 0,
        x: 0,
        y: superMid * rowH,
        color: "#4a4a4a",
        label: "Prebuilds",
        hasChildren: false,
      });
      roots.forEach((root, i) => {
        linkPairs.push({ parentPath: "__all__", childPath: root.path || root.id, color: rootColors[i] });
      });
    }

    const pathToNode = new Map(nodes.map((n) => [n.path, n]));
    for (const pair of linkPairs) {
      const from = pathToNode.get(pair.parentPath);
      const to = pathToNode.get(pair.childPath);
      if (!from || !to) continue;
      links.push({ x1: from.x, y1: from.y, x2: to.x, y2: to.y, color: pair.color });
    }
    return { nodes, links, totalRows: rowCursor, rowH, colW };
  }

  function renderToolbar() {
    const canZoomOut = zoomIdx > 0;
    const canZoomIn = zoomIdx < ONCOTREE_ZOOM_STEPS.length - 1;
    const anyExpanded = expanded.size > 0;
    toolbarEl.innerHTML = `
      <button type="button" class="btn-secondary" id="ot-expand">${anyExpanded ? "Collapse all" : "Expand roots"}</button>
      <span class="oncotree-zoom-group" role="group" aria-label="Zoom">
        <button type="button" class="btn-secondary" id="ot-zoom-out" ${canZoomOut ? "" : "disabled"}>−</button>
        <span class="oncotree-zoom-label">${Math.round(zoom() * 100)}%</span>
        <button type="button" class="btn-secondary" id="ot-zoom-in" ${canZoomIn ? "" : "disabled"}>+</button>
      </span>
    `;
    document.getElementById("ot-expand")?.addEventListener("click", () => {
      if (expanded.size) expanded.clear();
      else if (index) for (const r of index.roots) expanded.add(r.path || r.id);
      render();
    });
    document.getElementById("ot-zoom-out")?.addEventListener("click", () => {
      zoomIdx = Math.max(0, zoomIdx - 1);
      render();
    });
    document.getElementById("ot-zoom-in")?.addEventListener("click", () => {
      zoomIdx = Math.min(ONCOTREE_ZOOM_STEPS.length - 1, zoomIdx + 1);
      render();
    });
  }

  function renderOncotree(roots) {
    const { nodes, links, totalRows, rowH, colW } = buildOncotreeLayout(roots);
    const maxDepth = nodes.reduce((m, n) => Math.max(m, n.depth), 0);
    const width = (maxDepth + 1) * colW + 48;
    const height = Math.max(totalRows * rowH + 24, 220);
    const dotSize = Math.max(8, Math.round(10 * zoom()));

    let svg = `<svg class="oncotree-links" width="${width}" height="${height}" aria-hidden="true">`;
    for (const link of links) {
      const midX = (link.x1 + link.x2) / 2;
      const off = dotSize / 2 + 4;
      svg += `<path d="M ${link.x1 + off} ${link.y1 + off} C ${midX} ${link.y1 + off}, ${midX} ${link.y2 + off}, ${link.x2 + off} ${link.y2 + off}" stroke="${link.color}" stroke-opacity="0.45" fill="none" stroke-width="1.5" />`;
    }
    svg += "</svg>";

    let nodesHtml = "";
    for (const n of nodes) {
      if (n.kind === "super") {
        nodesHtml += `<div class="oncotree-node oncotree-super" style="top:${n.y}px;left:${n.x}px;font-size:${13 * zoom()}px;"><span class="oncotree-dot" style="width:${dotSize}px;height:${dotSize}px;background:${n.color};border-color:${n.color};"></span><span class="oncotree-label">${escapeHtml(n.label)}</span></div>`;
        continue;
      }
      const classes = ["oncotree-node"];
      if (n.kind === "leaf") classes.push("oncotree-leaf");
      if (n.kind === "branch" || n.kind === "root") classes.push("oncotree-branch");
      if (n.path === activePath) classes.push("oncotree-active");
      const q = (filterEl.value || "").trim().toLowerCase();
      if (q && `${n.label} ${n.path}`.toLowerCase().includes(q)) classes.push("oncotree-match");
      const caret = n.hasChildren ? `<span class="oncotree-caret">${n.expanded ? "▾" : "▸"}</span>` : "";
      const count = n.leafCount != null ? `<span class="oncotree-count">${n.leafCount}</span>` : "";
      const dotClass = n.hasChildren ? "oncotree-dot oncotree-dot-branch" : "oncotree-dot";
      const h = n.isTall ? 2 * rowH : rowH;
      nodesHtml += `<button type="button" class="${classes.join(" ")}" data-path="${escapeAttr(n.path)}" style="top:${n.y}px;left:${n.x}px;height:${h}px;font-size:${13 * zoom()}px;max-width:${colW - 24}px;">
        <span class="${dotClass}" style="width:${dotSize}px;height:${dotSize}px;border-color:${n.color};background:${n.hasChildren ? "transparent" : n.color};"></span>
        <span class="oncotree-label">${escapeHtml(n.label)}</span>${count}${caret}
      </button>`;
    }

    treeEl.innerHTML = `<div class="oncotree-container"><div class="oncotree-canvas" style="width:${width}px;height:${height}px;">${svg}${nodesHtml}</div></div>`;
    treeEl.querySelectorAll(".oncotree-node[data-path]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const path = btn.getAttribute("data-path");
        const src = pathToSourceNode.get(path);
        if (!src) return;
        if ((src.children || []).length) {
          if (expanded.has(path)) expanded.delete(path);
          else expanded.add(path);
        }
        selectNode(src);
        render();
      });
    });
  }

  function selectNode(node) {
    activePath = node.path;
    const items = collectItems(node);
    emptyEl.classList.add("hidden");
    detailEl.classList.remove("hidden");
    detailTitle.textContent = node.label;
    detailPath.textContent = `${node.path} · ${node.page_count || 0} prebuild page(s) · ${node.card_count || 0} cards / ${node.figure_count || 0} figures indexed · showing ${items.length} samples`;
    itemListEl.innerHTML = "";
    figureImg.classList.add("hidden");
    figureImg.removeAttribute("src");
    figureCaption.textContent = items.length
      ? "Select a sample to preview text or figure."
      : "No sample excerpts under this node (counts may still exist in the full index).";

    items.forEach((it) => {
      const li = document.createElement("li");
      li.className = "clip" + ((it.record_id || it.chunk_id) === activeItemId ? " active" : "");
      const kind = it.kind === "figure" ? "Figure" : (it.source_family || "Card");
      const page = it.page != null ? `p.${it.page}` : "";
      li.innerHTML = `
        <div class="title">${escapeHtml(it.title || it.source_name || it.source_id || "Source")} · ${kind} ${escapeHtml(page)}</div>
        <div class="meta">${escapeHtml([it.source_family, it.figure_id || it.section || ""].filter(Boolean).join(" · "))}</div>
        <div class="excerpt">${escapeHtml(it.caption || it.excerpt || "")}</div>
      `;
      li.addEventListener("click", () => showItem(it, li));
      itemListEl.appendChild(li);
    });
  }

  function showItem(it, liEl) {
    activeItemId = (it.record_id || it.chunk_id);
    document.querySelectorAll(".clip").forEach((el) => el.classList.remove("active"));
    if (liEl) liEl.classList.add("active");
    if ((it.figure_url || it.image_url)) {
      figureImg.classList.remove("hidden");
      figureImg.src = (it.figure_url || it.image_url);
      figureCaption.textContent = `${it.title || it.source_name || ""} ${it.figure_id || ""} p.${it.page ?? "?"} — open modal for page/PDF`.trim();
    } else if (it.page_image_url) {
      figureImg.classList.remove("hidden");
      figureImg.src = it.page_image_url;
      figureCaption.textContent = `Page image · ${it.title || it.source_name || ""} p.${it.page ?? "?"}`;
    } else {
      figureImg.classList.add("hidden");
      figureImg.removeAttribute("src");
      figureCaption.textContent = it.excerpt
        ? `${it.source_family || "Card"} · ${it.title || it.source_name || ""} p.${it.page ?? "?"}`
        : "No figure URL on this sample.";
    }
    openSampleModal(it);
  }

  function renderStats(counts) {
    const items = [
      ["Pages", counts.prebuild_pages],
      ["Cards", counts.cards_indexed],
      ["Figures", counts.figures_indexed],
      ["Roots", counts.roots],
    ];
    statsEl.innerHTML = items
      .map(([k, v]) => `<div class="stat"><span class="k">${k}</span><span class="v">${Number(v).toLocaleString()}</span></div>`)
      .join("");
  }

  function render() {
    if (!index) return;
    const q = (filterEl.value || "").trim().toLowerCase();
    indexPaths(index.roots);
    if (q) autoExpandForFilter(index.roots, q);
    renderToolbar();
    renderOncotree(filterRoots(index.roots, q));
  }

  filterEl.addEventListener("input", render);

  sampleModal?.querySelectorAll("[data-modal-close]").forEach((el) => {
    el.addEventListener("click", closeSampleModal);
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeSampleModal();
  });

  fetch(DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load ${DATA_URL}`);
      return r.json();
    })
    .then((data) => {
      index = data;
      document.title = data.title || document.title;
      renderStats(data.counts || {});
      if (Array.isArray(data.known_limitations) && data.known_limitations.length) {
        limitationsEl.textContent = "Limitations: " + data.known_limitations.join(" ");
      }
      expanded.clear();
      render();
    })
    .catch((err) => {
      treeEl.textContent = String(err);
    });
})();
