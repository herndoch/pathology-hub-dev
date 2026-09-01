(() => {
  const DATA_URL = "data/video_oncotree_index_v0_1.json";

  const treeEl = document.getElementById("tree");
  const statsEl = document.getElementById("stats");
  const filterEl = document.getElementById("filter");
  const expandAllEl = document.getElementById("expand-all");
  const emptyEl = document.getElementById("empty");
  const detailEl = document.getElementById("detail");
  const detailTitle = document.getElementById("detail-title");
  const detailPath = document.getElementById("detail-path");
  const clipListEl = document.getElementById("clip-list");
  const player = document.getElementById("player");
  const nowPlaying = document.getElementById("now-playing");
  const limitationsEl = document.getElementById("limitations");

  let index = null;
  let activeNodePath = null;
  let activeClipId = null;
  let clipEndSec = null;

  function fmtTime(sec) {
    const s = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, "0")}`;
  }

  function collectClips(node) {
    const out = [...(node.clips || [])];
    for (const child of node.children || []) {
      out.push(...collectClips(child));
    }
    // de-dupe by chunk_id
    const seen = new Set();
    return out.filter((c) => {
      const key = c.chunk_id || `${c.video_url}|${c.start_sec}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function nodeMatches(node, q) {
    if (!q) return true;
    const hay = `${node.label} ${node.path}`.toLowerCase();
    if (hay.includes(q)) return true;
    for (const clip of collectClips(node)) {
      const cHay = `${clip.title || ""} ${clip.entity_name || ""} ${clip.video_id || ""}`.toLowerCase();
      if (cHay.includes(q)) return true;
    }
    return (node.children || []).some((child) => nodeMatches(child, q));
  }

  function renderStats(counts) {
    const items = [
      ["Clips", counts.clips],
      ["Lectures", counts.videos],
      ["Topics", counts.tagged_leaves],
      ["Roots", counts.roots],
    ];
    statsEl.innerHTML = items
      .map(
        ([k, v]) =>
          `<div class="stat"><span class="k">${k}</span><span class="v">${Number(v).toLocaleString()}</span></div>`,
      )
      .join("");
  }

  function renderTree(roots, q, expandAll) {
    const frag = document.createDocumentFragment();
    const wrap = document.createElement("div");

    function renderNode(node, depth) {
      if (!nodeMatches(node, q)) return null;

      const hasKids = (node.children || []).length > 0;
      if (!hasKids) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "leaf-btn" + (node.path === activeNodePath ? " active" : "");
        btn.dataset.path = node.path;
        btn.innerHTML = `<span class="label">${escapeHtml(node.label)}</span><span class="count">${node.clip_count}</span>`;
        btn.addEventListener("click", () => selectNode(node));
        return btn;
      }

      const details = document.createElement("details");
      details.open = expandAll || depth < 1 || Boolean(q);
      const summary = document.createElement("summary");
      summary.innerHTML = `<span class="caret">▸</span><span class="label">${escapeHtml(node.label)}</span><span class="count">${node.clip_count}</span>`;
      summary.addEventListener("click", (ev) => {
        // clicking label area also selects aggregated clips for this branch
        if (ev.target.closest(".count") || ev.target.closest(".caret")) return;
      });
      summary.addEventListener("dblclick", (ev) => {
        ev.preventDefault();
        selectNode(node);
      });
      // single click on summary label (not just toggle): also show clips
      summary.addEventListener("click", () => {
        // defer so open/close still works
        setTimeout(() => selectNode(node), 0);
      });
      details.appendChild(summary);
      for (const child of node.children || []) {
        const el = renderNode(child, depth + 1);
        if (el) details.appendChild(el);
      }
      return details;
    }

    for (const root of roots) {
      const el = renderNode(root, 0);
      if (el) wrap.appendChild(el);
    }
    if (!wrap.children.length) {
      wrap.textContent = "No topics match that filter.";
    }
    treeEl.innerHTML = "";
    treeEl.appendChild(wrap);
  }

  function selectNode(node) {
    activeNodePath = node.path;
    const clips = collectClips(node);
    emptyEl.classList.add("hidden");
    detailEl.classList.remove("hidden");
    detailTitle.textContent = node.label;
    detailPath.textContent = `${node.path} · ${clips.length} clip${clips.length === 1 ? "" : "s"}`;
    clipListEl.innerHTML = "";
    clips.forEach((clip) => {
      const li = document.createElement("li");
      li.className = "clip";
      li.innerHTML = `
        <div class="title">${escapeHtml(clip.title || "Lecture")}</div>
        <div class="meta">${fmtTime(clip.start_sec)}–${fmtTime(clip.end_sec)} · ${escapeHtml(clip.entity_name || "")}</div>
        <div class="excerpt">${escapeHtml(clip.excerpt || "")}</div>
      `;
      li.addEventListener("click", () => playClip(clip, li));
      clipListEl.appendChild(li);
    });
    document.querySelectorAll(".leaf-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.path === activeNodePath);
    });
    if (clips[0]) playClip(clips[0], clipListEl.querySelector(".clip"));
  }

  function playClip(clip, liEl) {
    activeClipId = clip.chunk_id;
    clipEndSec = clip.end_sec;
    document.querySelectorAll(".clip").forEach((el) => el.classList.remove("active"));
    if (liEl) liEl.classList.add("active");

    const base = clip.video_url || (clip.video_time_url || "").split("#")[0];
    if (!base) {
      nowPlaying.textContent = "No playable URL on this clip.";
      return;
    }
    const start = Number(clip.start_sec) || 0;
    // Setting src with media fragment helps first paint; also seek on loadedmetadata.
    if (player.dataset.base !== base) {
      player.dataset.base = base;
      player.src = `${base}#t=${start}`;
    }
    const seek = () => {
      try {
        player.currentTime = start;
      } catch (_) {
        /* ignore */
      }
      player.play().catch(() => {});
    };
    if (player.readyState >= 1) seek();
    else player.addEventListener("loadedmetadata", seek, { once: true });

    nowPlaying.textContent = `Now playing: ${clip.title} · ${fmtTime(clip.start_sec)}–${fmtTime(clip.end_sec)}`;
  }

  player.addEventListener("timeupdate", () => {
    if (clipEndSec != null && player.currentTime >= clipEndSec) {
      player.pause();
    }
  });

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function rerender() {
    if (!index) return;
    renderTree(index.roots, (filterEl.value || "").trim().toLowerCase(), expandAllEl.checked);
  }

  filterEl.addEventListener("input", rerender);
  expandAllEl.addEventListener("change", rerender);

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
      rerender();
    })
    .catch((err) => {
      treeEl.textContent = String(err);
    });
})();
