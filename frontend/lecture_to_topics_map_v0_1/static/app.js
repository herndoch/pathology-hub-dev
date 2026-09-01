(() => {
  const DATA_URL = "data/lecture_to_topics_index_v0_1.json";

  const statsEl = document.getElementById("stats");
  const filterEl = document.getElementById("filter");
  const confidenceEl = document.getElementById("confidence-filter");
  const exportLinksEl = document.getElementById("export-links");
  const lectureListEl = document.getElementById("lecture-list");
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
  let activeLectureId = null;
  let activeTag = null;
  let activeChunkId = null;
  /** @type {'high'|'high_medium'|'all'} */
  let confidenceMode = "high";

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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

  function lectureVisibleSegments(lec) {
    const out = [];
    for (const topic of lec.topics || []) {
      for (const seg of filterSegments(topic.segments)) out.push({ topic, seg });
    }
    return out;
  }

  function lectureMatches(lec, q) {
    const visible = lectureVisibleSegments(lec);
    if (!visible.length && confidenceMode !== "all") {
      // still allow finding lectures that only have low-confidence when searching? hide them.
      if (!q) return false;
    }
    if (!q) return visible.length > 0 || confidenceMode === "all";
    const hay = [
      lec.title,
      lec.video_id,
      lec.root,
      lec.package_id,
      ...visible.flatMap(({ topic, seg }) => [
        topic.primary_tag,
        topic.label,
        seg.excerpt || seg.transcript || "",
      ]),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  }

  function renderStats(counts) {
    const items = [
      ["Lectures", counts.lectures],
      ["High-conf", counts.segments_high_confidence],
      ["All gated", counts.segments],
      ["Topics", counts.unique_topics],
    ];
    statsEl.innerHTML = items
      .map(
        ([k, v]) =>
          `<div class="stat"><span class="k">${k}</span><span class="v">${Number(v).toLocaleString()}</span></div>`
      )
      .join("");
  }

  function renderExports(exports) {
    if (!exports) {
      exportLinksEl.innerHTML = "";
      return;
    }
    const links = [
      ["CSV · high-conf lectures", exports.lectures_summary_high_confidence_csv],
      ["CSV · high-conf segments", exports.lecture_topic_segments_high_confidence_csv],
      ["CSV · all gated (incl. uncertain)", exports.lecture_topic_segments_all_gated_csv],
      ["JSON index", "data/lecture_to_topics_index_v0_1.json"],
    ].filter(([, href]) => href);
    exportLinksEl.innerHTML = links
      .map(([label, href]) => `<a href="${escapeHtml(href)}" download>${escapeHtml(label)}</a>`)
      .join("");
  }

  function confidenceBadge(tier) {
    const t = tier || "low";
    return `<span class="badge badge-${escapeHtml(t)}">${escapeHtml(t)}</span>`;
  }

  function renderLectureList() {
    const q = (filterEl.value || "").trim().toLowerCase();
    const lectures = (index.lectures || []).filter((lec) => lectureMatches(lec, q));
    if (!lectures.length) {
      lectureListEl.innerHTML = `<li class="meta">No lectures match this confidence filter.</li>`;
      return;
    }
    lectureListEl.innerHTML = "";
    lectures.forEach((lec) => {
      const visible = lectureVisibleSegments(lec).length;
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lecture-item" + (lec.video_id === activeLectureId ? " active" : "");
      btn.innerHTML = `
        <div class="title">${escapeHtml(lec.title)}</div>
        <div class="meta">${escapeHtml(lec.root || "")} · ${visible} shown / ${lec.segment_count} gated · ${lec.high_confidence_segment_count} high-conf</div>
      `;
      btn.addEventListener("click", () => selectLecture(lec));
      li.appendChild(btn);
      lectureListEl.appendChild(li);
    });
  }

  function selectLecture(lec) {
    activeLectureId = lec.video_id;
    activeTag = null;
    activeChunkId = null;
    emptyEl.classList.add("hidden");
    detailEl.classList.remove("hidden");
    detailTitle.textContent = lec.title;
    const visible = lectureVisibleSegments(lec).length;
    detailMeta.textContent = `${lec.video_id} · showing ${visible} of ${lec.segment_count} gated segments (${lec.high_confidence_segment_count} high-confidence)`;
    player.removeAttribute("src");
    player.load();
    nowPlaying.textContent = "Select a segment to load / seek (press play).";
    renderTopics(lec);
    renderSegments(lec, null);
    renderLectureList();
  }

  function renderTopics(lec) {
    topicListEl.innerHTML = "";
    const allVisible = lectureVisibleSegments(lec);
    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "topic-item" + (activeTag == null ? " active" : "");
    allBtn.innerHTML = `<div class="title">All topics</div><div class="meta">${allVisible.length} segments shown</div>`;
    allBtn.addEventListener("click", () => {
      activeTag = null;
      renderTopics(lec);
      renderSegments(lec, null);
    });
    const allLi = document.createElement("li");
    allLi.appendChild(allBtn);
    topicListEl.appendChild(allLi);

    (lec.topics || []).forEach((topic) => {
      const segs = filterSegments(topic.segments);
      if (!segs.length) return;
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "topic-item" + (activeTag === topic.primary_tag ? " active" : "");
      btn.innerHTML = `
        <div class="title">${escapeHtml(topic.label)}</div>
        <div class="meta">${escapeHtml(topic.root || "")} · ${segs.length} shown · ${topic.high_confidence_segment_count} high-conf</div>
      `;
      btn.addEventListener("click", () => {
        activeTag = topic.primary_tag;
        renderTopics(lec);
        renderSegments(lec, topic.primary_tag);
      });
      li.appendChild(btn);
      topicListEl.appendChild(li);
    });
  }

  function renderSegments(lec, tagFilter) {
    const segs = [];
    for (const topic of lec.topics || []) {
      if (tagFilter && topic.primary_tag !== tagFilter) continue;
      for (const seg of filterSegments(topic.segments)) segs.push({ topic, seg });
    }
    segs.sort((a, b) => a.seg.start_sec - b.seg.start_sec);
    segHeading.textContent = tagFilter
      ? `Segments · ${segs[0]?.topic.label || "topic"}`
      : `Segments · filtered (${segs.length})`;
    segmentListEl.innerHTML = "";
    if (!segs.length) {
      segmentListEl.innerHTML = `<li class="meta">No segments at this confidence level. Try “High + medium” or “All gated”.</li>`;
      return;
    }
    segs.forEach(({ topic, seg }) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "segment-item" + (seg.chunk_id === activeChunkId ? " active" : "");
      const score = seg.tag_score != null ? Number(seg.tag_score).toFixed(3) : "?";
      const margin = seg.tag_margin != null ? Number(seg.tag_margin).toFixed(3) : "?";
      btn.innerHTML = `
        <div class="title">${escapeHtml(seg.start_label)}–${escapeHtml(seg.end_label)} · ${escapeHtml(topic.label)} ${confidenceBadge(seg.confidence)}</div>
        <div class="meta">score ${escapeHtml(score)} · margin ${escapeHtml(margin)}${seg.tag_runner_up ? ` · runner-up ${escapeHtml(String(seg.tag_runner_up).split("::").pop())}` : ""}</div>
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
      nowPlaying.textContent = "No video URL on this segment.";
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
      nowPlaying.textContent = `${topic.label} · ${seg.start_label}–${seg.end_label} · ${seg.confidence} — press play`;
    };
    if (needLoad) {
      player.src = base;
      player.addEventListener("loadedmetadata", seek, { once: true });
      player.load();
    } else {
      seek();
    }
  }

  function refreshActiveLecture() {
    if (!activeLectureId || !index) return;
    const lec = (index.lectures || []).find((L) => L.video_id === activeLectureId);
    if (!lec) return;
    const visible = lectureVisibleSegments(lec).length;
    detailMeta.textContent = `${lec.video_id} · showing ${visible} of ${lec.segment_count} gated segments (${lec.high_confidence_segment_count} high-confidence)`;
    if (activeTag) {
      const topic = (lec.topics || []).find((t) => t.primary_tag === activeTag);
      if (!topic || !filterSegments(topic.segments).length) activeTag = null;
    }
    renderTopics(lec);
    renderSegments(lec, activeTag);
  }

  function render() {
    if (!index) return;
    renderLectureList();
    refreshActiveLecture();
  }

  filterEl.addEventListener("input", () => {
    renderLectureList();
  });
  confidenceEl.addEventListener("change", () => {
    confidenceMode = confidenceEl.value;
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
        limitationsEl.textContent = "Limitations: " + data.known_limitations.join(" ");
      }
      render();
    })
    .catch((err) => {
      lectureListEl.textContent = String(err);
    });
})();
