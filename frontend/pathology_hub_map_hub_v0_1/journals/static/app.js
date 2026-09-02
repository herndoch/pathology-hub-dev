(() => {
  const DATA_URL = "data/journals_who_pathout_map_v0_1.json";
  const ONCOTREE_BASE_ROW_HEIGHT = 30;
  const ONCOTREE_BASE_COL_WIDTH = 300;
  const ONCOTREE_ZOOM_STEPS = [0.6, 0.8, 1, 1.2, 1.5];
  const ROOT_COLORS = [
    "#0f6a6a", "#1d4f91", "#8a4b08", "#5b2c6f", "#1a7a4c",
    "#9b2c2c", "#0e7490", "#a16207", "#3730a3", "#be123c",
    "#047857", "#0369a1", "#b45309", "#6d28d9", "#0f766e",
  ];

  const treeEl = document.getElementById("tree");
  const toolbarEl = document.getElementById("oncotree-toolbar");
  const statsEl = document.getElementById("stats");
  const filterEl = document.getElementById("filter");
  const sourceEl = document.getElementById("source-filter");
  const emptyEl = document.getElementById("empty");
  const detailEl = document.getElementById("detail");
  const detailTitle = document.getElementById("detail-title");
  const detailMeta = document.getElementById("detail-meta");
  const openChat = document.getElementById("open-chat");
  const limitationsEl = document.getElementById("limitations");

  let index = null;
  let treeRoots = [];
  let pathToNode = new Map();
  let expanded = new Set();
  let zoomIdx = ONCOTREE_ZOOM_STEPS.indexOf(1);
  let activePath = null;
  let sourceMode = "all";

  function zoom() { return ONCOTREE_ZOOM_STEPS[zoomIdx] ?? 1; }
  function escapeHtml(v) {
    return String(v || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }
  function escapeAttr(v) { return escapeHtml(v).replace(/'/g, "&#39;"); }
  function rootColor(id, i) {
    let h = 0;
    for (let c = 0; c < String(id||"").length; c += 1) h = (h * 31 + id.charCodeAt(c)) >>> 0;
    return ROOT_COLORS[h % ROOT_COLORS.length];
  }

  function leafOk(leaf) {
    const p = (leaf.provenance || "").toLowerCase();
    if (sourceMode === "all") return true;
    if (sourceMode === "who") return p === "who" || p.includes("who");
    if (sourceMode === "pathout") return p === "pathout" || p.includes("pathout");
    return true;
  }

  function filterModel(roots) {
    function walk(node) {
      if (node.kind === "leaf") return leafOk(node) ? { ...node } : null;
      const kids = (node.children || []).map(walk).filter(Boolean);
      if (!kids.length && node.kind !== "root") return null;
      const copy = { ...node, children: kids };
      copy.leaf_count = kids.reduce((n, c) => n + (c.kind === "leaf" ? 1 : c.leaf_count || 0), 0);
      if (node.kind === "root" && !kids.length) return null;
      return copy;
    }
    return roots.map(walk).filter(Boolean);
  }

  function nodeMatches(node, q) {
    if (!q) return true;
    const hay = `${node.label} ${node.path} ${node.tag || ""} ${node.query || ""}`.toLowerCase();
    if (hay.includes(q)) return true;
    return (node.children || []).some((c) => nodeMatches(c, q));
  }

  function filterTree(roots, q) {
    if (!q) return roots;
    function walk(node) {
      if (!nodeMatches(node, q)) return null;
      return { ...node, children: (node.children || []).map(walk).filter(Boolean) };
    }
    return roots.map(walk).filter(Boolean);
  }

  function indexPaths(roots) {
    pathToNode = new Map();
    function walk(node) {
      pathToNode.set(node.path, node);
      for (const c of node.children || []) walk(c);
    }
    for (const r of roots) walk(r);
  }

  function autoExpand(roots, q) {
    if (!q) return;
    function walk(node) {
      const kids = node.children || [];
      if (kids.some((c) => nodeMatches(c, q))) expanded.add(node.path);
      kids.forEach(walk);
    }
    roots.forEach(walk);
  }

  function buildLayout(roots) {
    const rowH = ONCOTREE_BASE_ROW_HEIGHT * zoom();
    const colW = ONCOTREE_BASE_COL_WIDTH * zoom();
    const nodes = [];
    const links = [];
    const pairs = [];
    let rowCursor = 0;

    function visit(node, depth, color, path) {
      const kids = node.children || [];
      const isLeaf = kids.length === 0;
      const isExpanded = !isLeaf && expanded.has(path);
      let midRow;
      if (isLeaf || !isExpanded) {
        midRow = rowCursor;
        rowCursor += 1;
      } else {
        const mids = [];
        kids.forEach((child) => {
          pairs.push({ parentPath: path, childPath: child.path, color });
          mids.push(visit(child, depth + 1, color, child.path));
        });
        midRow = mids.reduce((a, b) => a + b, 0) / mids.length;
      }
      nodes.push({
        kind: node.kind === "root" ? "root" : isLeaf ? "leaf" : "branch",
        path, depth, x: depth * colW, y: midRow * rowH, color,
        label: node.label, hasChildren: !isLeaf, expanded: isExpanded,
        leafCount: node.leaf_count, source: node,
      });
      return midRow;
    }

    const rootMids = [];
    const colors = [];
    roots.forEach((root, i) => {
      const color = rootColor(root.id, i);
      colors.push(color);
      rootMids.push(visit(root, 1, color, root.path));
    });
    if (rootMids.length) {
      const superMid = rootMids.reduce((a, b) => a + b, 0) / rootMids.length;
      nodes.push({ kind: "super", path: "__all__", depth: 0, x: 0, y: superMid * rowH, color: "#4a4a4a", label: "Journals", hasChildren: false });
      roots.forEach((root, i) => pairs.push({ parentPath: "__all__", childPath: root.path, color: colors[i] }));
    }
    const byPath = new Map(nodes.map((n) => [n.path, n]));
    for (const p of pairs) {
      const from = byPath.get(p.parentPath);
      const to = byPath.get(p.childPath);
      if (from && to) links.push({ x1: from.x, y1: from.y, x2: to.x, y2: to.y, color: p.color });
    }
    return { nodes, links, totalRows: rowCursor, rowH, colW };
  }

  function renderToolbar() {
    const canZoomOut = zoomIdx > 0;
    const canZoomIn = zoomIdx < ONCOTREE_ZOOM_STEPS.length - 1;
    toolbarEl.innerHTML = `
      <button type="button" class="btn-secondary" id="ot-expand">${expanded.size ? "Collapse all" : "Expand specialties"}</button>
      <span class="oncotree-zoom-group">
        <button type="button" class="btn-secondary" id="ot-zoom-out" ${canZoomOut ? "" : "disabled"}>−</button>
        <span class="oncotree-zoom-label">${Math.round(zoom() * 100)}%</span>
        <button type="button" class="btn-secondary" id="ot-zoom-in" ${canZoomIn ? "" : "disabled"}>+</button>
      </span>`;
    document.getElementById("ot-expand")?.addEventListener("click", () => {
      if (expanded.size) expanded.clear();
      else treeRoots.forEach((r) => expanded.add(r.path));
      render();
    });
    document.getElementById("ot-zoom-out")?.addEventListener("click", () => { zoomIdx = Math.max(0, zoomIdx - 1); render(); });
    document.getElementById("ot-zoom-in")?.addEventListener("click", () => { zoomIdx = Math.min(ONCOTREE_ZOOM_STEPS.length - 1, zoomIdx + 1); render(); });
  }

  function renderOncotree(roots) {
    const { nodes, links, totalRows, rowH, colW } = buildLayout(roots);
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
    let html = "";
    const q = (filterEl.value || "").trim().toLowerCase();
    for (const n of nodes) {
      if (n.kind === "super") {
        html += `<div class="oncotree-node oncotree-super" style="top:${n.y}px;left:${n.x}px;font-size:${13 * zoom()}px;"><span class="oncotree-dot" style="width:${dotSize}px;height:${dotSize}px;background:${n.color};border-color:${n.color};"></span><span class="oncotree-label">${escapeHtml(n.label)}</span></div>`;
        continue;
      }
      const classes = ["oncotree-node"];
      if (n.kind === "leaf") classes.push("oncotree-leaf");
      if (n.kind === "branch" || n.kind === "root") classes.push("oncotree-branch");
      if (n.path === activePath) classes.push("oncotree-active");
      if (q && `${n.label} ${n.path}`.toLowerCase().includes(q)) classes.push("oncotree-match");
      const caret = n.hasChildren ? `<span class="oncotree-caret">${n.expanded ? "▾" : "▸"}</span>` : "";
      const count = n.leafCount != null ? `<span class="oncotree-count">${n.leafCount}</span>` : "";
      const dotClass = n.hasChildren ? "oncotree-dot oncotree-dot-branch" : "oncotree-dot";
      html += `<button type="button" class="${classes.join(" ")}" data-path="${escapeAttr(n.path)}" style="top:${n.y}px;left:${n.x}px;height:${rowH}px;font-size:${13 * zoom()}px;max-width:${colW - 24}px;">
        <span class="${dotClass}" style="width:${dotSize}px;height:${dotSize}px;border-color:${n.color};background:${n.hasChildren ? "transparent" : n.color};"></span>
        <span class="oncotree-label">${escapeHtml(n.label)}</span>${count}${caret}
      </button>`;
    }
    treeEl.innerHTML = `<div class="oncotree-container"><div class="oncotree-canvas" style="width:${width}px;height:${height}px;">${svg}${html}</div></div>`;
    treeEl.querySelectorAll(".oncotree-node[data-path]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const path = btn.getAttribute("data-path");
        const src = pathToNode.get(path);
        if (!src) return;
        if ((src.children || []).length) {
          if (expanded.has(path)) expanded.delete(path);
          else expanded.add(path);
        }
        activePath = path;
        if (src.kind === "leaf") selectLeaf(src);
        render();
      });
    });
  }

  function selectLeaf(leaf) {
    emptyEl.classList.add("hidden");
    detailEl.classList.remove("hidden");
    const prov = (leaf.provenance || "topic").toLowerCase();
    const badge = prov.includes("pathout")
      ? `<span class="badge badge-pathout">PathOut</span>`
      : `<span class="badge badge-who">WHO</span>`;
    detailTitle.innerHTML = `${escapeHtml(leaf.label)} ${badge}`;
    detailMeta.textContent = leaf.tag || leaf.path;
    const q = encodeURIComponent(leaf.query || leaf.label || "");
    const chatBase = (index && index.chat_url) || "https://chat.pathologynotebook.com";
    openChat.href = `${chatBase}/?q=${q}`;
    openChat.textContent = "Open in Chat";
  }

  function renderStats(counts) {
    statsEl.innerHTML = [
      ["Topics", counts.leaves],
      ["WHO leaves", counts.who_leaves],
      ["Combined", counts.combined_leaves],
      ["Specialties", counts.roots],
    ].map(([k, v]) => `<div class="stat"><span class="k">${k}</span><span class="v">${Number(v || 0).toLocaleString()}</span></div>`).join("");
  }

  function render() {
    if (!index) return;
    const q = (filterEl.value || "").trim().toLowerCase();
    treeRoots = filterModel(index.roots || []);
    indexPaths(treeRoots);
    if (q) autoExpand(treeRoots, q);
    renderToolbar();
    renderOncotree(filterTree(treeRoots, q));
  }

  filterEl.addEventListener("input", render);
  sourceEl.addEventListener("change", () => {
    sourceMode = sourceEl.value;
    render();
  });

  fetch(DATA_URL)
    .then((r) => { if (!r.ok) throw new Error(`Failed ${DATA_URL}`); return r.json(); })
    .then((data) => {
      index = data;
      document.title = data.title || document.title;
      renderStats(data.counts || {});
      if (Array.isArray(data.known_limitations)) limitationsEl.textContent = "Note: " + data.known_limitations.join(" ");
      filterModel(data.roots || []).slice(0, 2).forEach((r) => expanded.add(r.path));
      render();
    })
    .catch((err) => { treeEl.textContent = String(err); });
})();
