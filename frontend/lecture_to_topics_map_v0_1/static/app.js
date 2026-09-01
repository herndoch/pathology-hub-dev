(() => {
  const DATA_URL = "data/lecture_to_topics_index_v0_1.json";

  const statsEl = document.getElementById("stats");
  const filterEl = document.getElementById("filter");
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

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function lectureMatches(lec, q) {
    if (!q) return true;
    const hay = [
      lec.title,
      lec.video_id,
      lec.root,
      lec.package_id,
      ...(lec.topics || []).flatMap((t) => [
        t.primary_tag,
        t.label,
        ...(t.segments || []).map((s) => s.excerpt || s.transcript || ""),
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
      ["Segments", counts.segments],
      ["Topics", counts.unique_topics],
      ["Roots", counts.unique_roots],
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
      ["CSV · lectures", exports.lectures_summary_csv],
      ["CSV · segments", exports.lecture_topic_segments_csv],
      ["JSON index", "data/lecture_to_topics_index_v0_1.json"],
    ].filter(([, href]) => href);
    exportLinksEl.innerHTML = links
      .map(
        ([label, href]) =>
          `<a href="${escapeHtml(href)}" download>${escapeHtml(label)}</a>`
      )
      .join("");
  }

  function renderLectureList() {
    const q = (filterEl.value || "").trim().toLowerCase();
    const lectures = (index.lectures || []).filter((lec) => lectureMatches(lec, q));
    if (!lectures.length) {
      lectureListEl.innerHTML = `<li class="meta">No lectures match.</li>`;
      return;
    }
    lectureListEl.innerHTML = "";
    lectures.forEach((lec) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lecture-item" + (lec.video_id === activeLectureId ? " active" : "");
      btn.innerHTML = `
        <div class="title">${escapeHtml(lec.title)}</div>
        <div class="meta">${escapeHtml(lec.root || "")} · ${lec.topic_count} topics · ${lec.segment_count} segments</div>
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
    detailMeta.textContent = `${lec.video_id} · ${lec.topic_count} topics · ${lec.segment_count} segments`;
    player.removeAttribute("src");
    player.load();
    nowPlaying.textContent = "Select a segment to load / seek (press play).";
    renderTopics(lec);
    renderSegments(lec, null);
    renderLectureList();
  }

  function renderTopics(lec) {
    topicListEl.innerHTML = "";
    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "topic-item" + (activeTag == null ? " active" : "");
    allBtn.innerHTML = `<div class="title">All topics</div><div class="meta">${lec.segment_count} segments</div>`;
    allBtn.addEventListener("click", () => {
      activeTag = null;
      renderTopics(lec);
      renderSegments(lec, null);
    });
    const allLi = document.createElement("li");
    allLi.appendChild(allBtn);
    topicListEl.appendChild(allLi);

    (lec.topics || []).forEach((topic) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "topic-item" + (activeTag === topic.primary_tag ? " active" : "");
      btn.innerHTML = `
        <div class="title">${escapeHtml(topic.label)}</div>
        <div class="meta">${escapeHtml(topic.root || "")} · ${topic.segment_count} seg · ${escapeHtml(topic.primary_tag)}</div>
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
      for (const seg of topic.segments || []) {
        segs.push({ topic, seg });
      }
    }
    segs.sort((a, b) => a.seg.start_sec - b.seg.start_sec);
    segHeading.textContent = tagFilter
      ? `Segments · ${segs[0]?.topic.label || "topic"}`
      : `Segments · all topics (${segs.length})`;
    segmentListEl.innerHTML = "";
    if (!segs.length) {
      segmentListEl.innerHTML = `<li class="meta">No segments.</li>`;
      return;
    }
    segs.forEach(({ topic, seg }) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "segment-item" + (seg.chunk_id === activeChunkId ? " active" : "");
      btn.innerHTML = `
        <div class="title">${escapeHtml(seg.start_label)}–${escapeHtml(seg.end_label)} · ${escapeHtml(topic.label)}</div>
        <div class="meta">${escapeHtml(seg.entity_name || topic.primary_tag)}</div>
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
    // Load base URL once; seek without relying on autoplay.
    const base = (lec.video_url || url.split("#")[0]).split("#")[0];
    const needLoad = !player.src || !player.src.startsWith(base);
    const seek = () => {
      try {
        player.currentTime = Number(seg.start_sec) || 0;
      } catch (_) {
        /* ignore seek races */
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

  function render() {
    if (!index) return;
    renderLectureList();
  }

  filterEl.addEventListener("input", render);

  fetch(DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load ${DATA_URL}`);
      return r.json();
    })
    .then((data) => {
      index = data;
      document.title = data.title || document.title;
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
