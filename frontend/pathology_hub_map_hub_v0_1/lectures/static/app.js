(() => {
  const DATA_URL = "data/lecture_to_topics_index_v0_1.json";
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
  const confidenceEl = document.getElementById("confidence-filter");
  const exportLinksEl = document.getElementById("export-links");
  const emptyEl = document.getElementById("empty");
  const detailEl = document.getElementById("detail");
  const detailTitle = document.getElementById("detail-title");
  const detailMeta = document.getElementById("detail-meta");
  const topicListEl = document.getElementById("topic-list");
  const segmentListEl = document.getElementById("segment-list");
  const segHeading = document.getElementById("seg-heading");
  const player = document.getElementById("player");
  const nowPlaying = document.getElementById("now-playing");
  const limitationsEl = document.getElementById("limitations");

  let index = null;
  let treeRoots = [];
  let pathToNode = new Map();
  let expanded = new Set();
  let zoomIdx = ONCOTREE_ZOOM_STEPS.indexOf(1);
  let activePath = null;
  let activeLectureId = null;
  let activeTag = null;
  let activeChunkId = null;
  /** @type {'high'|'high_medium'|'all'} */
  let confidenceMode = "high";

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

  function rootColor(rootId, i) {
    if (!rootId) return ROOT_COLORS[i % ROOT_COLORS.length];
    let h = 0;
    for (let c = 0; c < rootId.length; c += 1) h = (h * 31 + rootId.charCodeAt(c)) >>> 0;
    return ROOT_COLORS[h % ROOT_COLORS.length];
  }

  function allowedTiers() {
    if (confidenceMode === "all") return new Set(["high", "medium", "low"]);
    if (confidenceMode === "high_medium") return new Set(["high", "medium"]);
    return new Set(["high"]);
  }

  function filterSegments(segments) {
    const allow = allowedTiers();
    return (segments || []).filter((s) => allow.has(s.confidence || "low"));
  }

  function visibleTopics(lec) {
    return (lec.topics || [])
      .map((t) => ({ ...t, segments: filterSegments(t.segments) }))
      .filter((t) => t.segments.length);
  }

  function lectureVisibleCount(lec) {
    return visibleTopics(lec).reduce((n, t) => n + t.segments.length, 0);
  }

  function pretty(text) {
    return String(text || "").replace(/_/g, " ").replace(/\s+/g, " ").trim() || "(untitled)";
  }

  function buildTreeModel(lectures) {
    const byRoot = new Map();
    for (const lec of lectures || []) {
      const topics = visibleTopics(lec);
      if (!topics.length && confidenceMode !== "all") continue;
      if (!topics.length) continue;
      const rootId = lec.root || topics[0]?.root || "Other";
      if (!byRoot.has(rootId)) {
        byRoot.set(rootId, {
          id: rootId,
          label: pretty(rootId),
          path: rootId,
          kind: "root",
          children: [],
          lecture_count: 0,
          clip_count: 0,
        });
      }
      const root = byRoot.get(rootId);
      const lecPath = `${rootId}::lec:${lec.video_id}`;
      const lecNode = {
        id: lec.video_id,
        label: lec.title || pretty(lec.video_id),
        path: lecPath,
        kind: "lecture",
        lecture: lec,
        children: [],
        lecture_count: 1,
        clip_count: topics.reduce((n, t) => n + t.segments.length, 0),
      };
      for (const topic of topics) {
        lecNode.children.push({
          id: topic.primary_tag,
          label: topic.label || pretty(topic.primary_tag),
          path: `${lecPath}::${topic.primary_tag}`,
          kind: "topic",
          lecture: lec,
          topic,
          children: [],
          lecture_count: 0,
          clip_count: topic.segments.length,
        });
      }
      lecNode.children.sort((a, b) => a.label.localeCompare(b.label));
      root.children.push(lecNode);
      root.lecture_count += 1;
      root.clip_count += lecNode.clip_count;
    }
    const roots = [...byRoot.values()].sort((a, b) => a.label.localeCompare(b.label));
    for (const r of roots) r.children.sort((a, b) => a.label.localeCompare(b.label));
    return roots;
  }

  function nodeMatches(node, q) {
    if (!q) return true;
    const hay = `${node.label} ${node.path}`.toLowerCase();
    if (hay.includes(q)) return true;
    if (node.kind === "topic" && (node.topic?.primary_tag || "").toLowerCase().includes(q)) return true;
    if (node.lecture) {
      const lh = `${node.lecture.title || ""} ${node.lecture.video_id || ""}`.toLowerCase();
      if (lh.includes(q)) return true;
    }
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
          const childPath = child.path;
          linkPairs.push({ parentPath: path, childPath, color });
          childMids.push(visit(child, depth + 1, color, childPath));
        });
        midRow = childMids.reduce((sum, m) => sum + m, 0) / childMids.length;
      }

      nodes.push({
        kind: node.kind === "root" ? "root" : isLeaf ? "leaf" : "branch",
        path,
        depth,
        x: depth * colW,
        y: midRow * rowH,
        color,
        label,
        isTall,
        hasChildren: !isLeaf,
        expanded: isExpanded,
        leafCount: node.kind === "root" ? node.lecture_count : node.clip_count,
        source: node,
      });
      return midRow;
    }

    const rootMids = [];
    const rootColors = [];
    roots.forEach((root, i) => {
      const color = rootColor(root.id, i);
      rootColors.push(color);
      rootMids.push(visit(root, 1, color, root.path));
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
        label: "Lectures",
        hasChildren: false,
      });
      roots.forEach((root, i) => {
        linkPairs.push({ parentPath: "__all__", childPath: root.path, color: rootColors[i] });
      });
    }

    const byPath = new Map(nodes.map((n) => [n.path, n]));
    for (const pair of linkPairs) {
      const from = byPath.get(pair.parentPath);
      const to = byPath.get(pair.childPath);
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
      <button type="button" class="btn-secondary" id="ot-expand">${anyExpanded ? "Collapse all" : "Expand specialties"}</button>
      <span class="oncotree-zoom-group" role="group" aria-label="Zoom">
        <button type="button" class="btn-secondary" id="ot-zoom-out" ${canZoomOut ? "" : "disabled"}>−</button>
        <span class="oncotree-zoom-label">${Math.round(zoom() * 100)}%</span>
        <button type="button" class="btn-secondary" id="ot-zoom-in" ${canZoomIn ? "" : "disabled"}>+</button>
      </span>
    `;
    document.getElementById("ot-expand")?.addEventListener("click", () => {
      if (expanded.size) expanded.clear();
      else for (const r of treeRoots) expanded.add(r.path);
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
        const src = pathToNode.get(path);
        if (!src) return;
        if ((src.children || []).length) {
          if (expanded.has(path)) expanded.delete(path);
          else expanded.add(path);
        }
        activePath = path;
        if (src.kind === "lecture" || src.kind === "topic") {
          selectLecture(src.lecture, src.kind === "topic" ? src.topic.primary_tag : null);
        }
        render();
      });
    });
  }

  function confidenceBadge(tier) {
    const t = tier || "low";
    return `<span class="badge badge-${escapeHtml(t)}">${escapeHtml(t)}</span>`;
  }

  function selectLecture(lec, tagFilter) {
    activeLectureId = lec.video_id;
    activeTag = tagFilter || null;
    activeChunkId = null;
    emptyEl.classList.add("hidden");
    detailEl.classList.remove("hidden");
    detailTitle.textContent = lec.title;
    const topics = visibleTopics(lec);
    const clips = topics.reduce((n, t) => n + t.segments.length, 0);
    detailMeta.textContent = `${pretty(lec.root || "")} · ${topics.length} topics · ${clips} clips shown`;
    player.removeAttribute("src");
    player.load();
    nowPlaying.textContent = "Pick a clip below, then press play.";
    renderTopics(lec, topics);
    renderSegments(lec, topics, activeTag);
  }

  function renderTopics(lec, topics) {
    topicListEl.innerHTML = "";
    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "topic-item" + (activeTag == null ? " active" : "");
    const allCount = topics.reduce((n, t) => n + t.segments.length, 0);
    allBtn.innerHTML = `<div class="title">All topics</div><div class="meta">${allCount} clips</div>`;
    allBtn.addEventListener("click", () => {
      activeTag = null;
      renderTopics(lec, topics);
      renderSegments(lec, topics, null);
    });
    const allLi = document.createElement("li");
    allLi.appendChild(allBtn);
    topicListEl.appendChild(allLi);

    topics.forEach((topic) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "topic-item" + (activeTag === topic.primary_tag ? " active" : "");
      btn.innerHTML = `<div class="title">${escapeHtml(topic.label)}</div><div class="meta">${topic.segments.length} clips</div>`;
      btn.addEventListener("click", () => {
        activeTag = topic.primary_tag;
        renderTopics(lec, topics);
        renderSegments(lec, topics, topic.primary_tag);
      });
      li.appendChild(btn);
      topicListEl.appendChild(li);
    });
  }

  function renderSegments(lec, topics, tagFilter) {
    const segs = [];
    for (const topic of topics) {
      if (tagFilter && topic.primary_tag !== tagFilter) continue;
      for (const seg of topic.segments) segs.push({ topic, seg });
    }
    segs.sort((a, b) => a.seg.start_sec - b.seg.start_sec);
    segHeading.textContent = tagFilter ? `Clips · ${segs[0]?.topic.label || "topic"}` : `Clips (${segs.length})`;
    segmentListEl.innerHTML = "";
    if (!segs.length) {
      segmentListEl.innerHTML = `<li class="meta">No clips at this confidence level.</li>`;
      return;
    }
    segs.forEach(({ topic, seg }) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "segment-item" + (seg.chunk_id === activeChunkId ? " active" : "");
      btn.innerHTML = `
        <div class="title">${escapeHtml(seg.start_label)}–${escapeHtml(seg.end_label)} · ${escapeHtml(topic.label)} ${confidenceBadge(seg.confidence)}</div>
        <div class="excerpt">${escapeHtml(seg.excerpt || "")}</div>
      `;
      btn.addEventListener("click", () => playSegment(lec, topic, seg, btn));
      li.appendChild(btn);
      segmentListEl.appendChild(li);
    });
  }

  function playSegment(lec, topic, seg, btnEl) {
    activeChunkId = seg.chunk_id;
    document.querySelectorAll(".segment-item").forEach((el) => el.classList.remove("active"));
    if (btnEl) btnEl.classList.add("active");
    const url = seg.video_time_url || lec.video_url;
    if (!url) {
      nowPlaying.textContent = "No video link for this clip.";
      return;
    }
    const base = (lec.video_url || url.split("#")[0]).split("#")[0];
    const needLoad = !player.src || !String(player.src).startsWith(base);
    const seek = () => {
      try {
        player.currentTime = Number(seg.start_sec) || 0;
      } catch (_) {
        /* ignore */
      }
      nowPlaying.textContent = `${topic.label} · ${seg.start_label}–${seg.end_label} — press play`;
    };
    if (needLoad) {
      player.src = base;
      player.addEventListener("loadedmetadata", seek, { once: true });
      player.load();
    } else {
      seek();
    }
  }

  function renderStats(counts) {
    const items = [
      ["Lectures", counts.lectures],
      ["High-conf clips", counts.segments_high_confidence],
      ["Topics", counts.unique_topics],
      ["Specialties", counts.unique_roots],
    ];
    statsEl.innerHTML = items
      .map(([k, v]) => `<div class="stat"><span class="k">${k}</span><span class="v">${Number(v).toLocaleString()}</span></div>`)
      .join("");
  }

  function renderExports(exports) {
    if (!exports) {
      exportLinksEl.innerHTML = "";
      return;
    }
    const links = [
      ["CSV · high-conf lectures", exports.lectures_summary_high_confidence_csv],
      ["CSV · high-conf clips", exports.lecture_topic_segments_high_confidence_csv],
      ["CSV · all automated", exports.lecture_topic_segments_all_gated_csv],
    ].filter(([, href]) => href);
    exportLinksEl.innerHTML = links
      .map(([label, href]) => `<a href="${escapeHtml(href)}" download>${escapeHtml(label)}</a>`)
      .join("");
  }

  function render() {
    if (!index) return;
    const q = (filterEl.value || "").trim().toLowerCase();
    treeRoots = buildTreeModel(index.lectures || []);
    indexPaths(treeRoots);
    if (q) autoExpandForFilter(treeRoots, q);
    renderToolbar();
    renderOncotree(filterTree(treeRoots, q));
  }

  filterEl.addEventListener("input", render);
  confidenceEl.addEventListener("change", () => {
    confidenceMode = confidenceEl.value;
    if (activeLectureId && index) {
      const lec = (index.lectures || []).find((L) => L.video_id === activeLectureId);
      if (lec && lectureVisibleCount(lec)) selectLecture(lec, activeTag);
      else {
        emptyEl.classList.remove("hidden");
        detailEl.classList.add("hidden");
        activeLectureId = null;
      }
    }
    render();
  });

  fetch(DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load ${DATA_URL}`);
      return r.json();
    })
    .then((data) => {
      index = data;
      document.title = data.title || document.title;
      confidenceMode = data.default_confidence_filter || "high";
      confidenceEl.value = confidenceMode;
      renderStats(data.counts || {});
      renderExports(data.exports || {});
      if (Array.isArray(data.known_limitations) && data.known_limitations.length) {
        limitationsEl.textContent = "Note: " + data.known_limitations.join(" ");
      }
      for (const r of buildTreeModel(data.lectures || []).slice(0, 3)) expanded.add(r.path);
      render();
    })
    .catch((err) => {
      treeEl.textContent = String(err);
    });
})();
