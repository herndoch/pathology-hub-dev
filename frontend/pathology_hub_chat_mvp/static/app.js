const DEFAULT_SOURCES = ["textbooks", "pathout", "who"];
/** Most-recently-rendered chat/topic-page result, for the "Export current
 * page as JSON" button — replaces the old teaching-session-notes panel. */
let lastExportableResult = null;
/** From /api/health — drives cache skip + status badge. */
let healthFlags = {
  iterative: true,
  liveLiterature: true,
  streamEndpoint: true,
};
/** Topic pages are meant to be comprehensive, so they always request every
 * supported source regardless of the sidebar checkbox state — this mirrors
 * (and is redundant with) the server-side enforcement in app.py, kept here
 * too so the debug panel shows the sources that are actually used, not a
 * misleadingly narrow sidebar selection. Excludes `curriculum`, which is
 * navigation-only and never treated as citable evidence. */
const TOPIC_PAGE_SOURCES = ["textbooks", "who", "pathout", "videos"];

const SOURCE_LABELS = {
  who: "WHO Classification",
  textbooks: "Textbooks",
  pathout: "Pathoutlines",
  journals: "Journals (retired)",
  literature: "Live literature",
  lectures: "Lectures",
  videos: "Videos",
  curriculum: "Curriculum map",
};

/** Pretty names for textbook source_id tails (after root prefix is stripped). */
const TEXTBOOK_ALIASES = {
  gnepp: "Gnepp",
  atlas: "Atlas",
  cardesa: "Cardesa",
  vasef: "Vasef",
  faq: "FAQ",
};

/** Normalize inline markdown link labels baked into prebuild/synthesis text. */
const INLINE_LINK_LABEL_ALIASES = {
  pathout: "Pathoutlines",
  "path out": "Pathoutlines",
  "hn atlas": "Atlas",
  "hn_gnepp": "Gnepp",
  "hn gnepp": "Gnepp",
};

const MODE_HINTS = {
  gpt_like: "Bullet summary with inline source links. Figures auto-included when you ask to show something.",
  search_only: "Raw evidence cards only — no OpenAI synthesis.",
  compare_sources: "Markdown table comparing sources, plus brief agreement bullets.",
  visual: "Figures retrieved and shown above the answer.",
  html_teaching: "Hosted HTML teaching page — link appears above citations.",
  topic_page: "ExpertPath-style reference page with iterative retrieval (broad → gap-fill → literature deepen), live Elsevier/PubMed/OncoKB, and visible round-by-round progress. Also reachable via the Browse tab.",
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

/** Static, self-contained pathology taxonomy for the "Browse" tree (home tile
 * grid -> subcategory list -> leaf entity list). Curated editorially — real,
 * clinically-correct sub-classification and diagnosis names — NOT sourced
 * from any live index, and NOT read from the separate curriculum provenance
 * browser's SQLite (different workstream). This is a navigation aid only;
 * every leaf click still triggers exactly one fresh POST /evidence/search
 * via /api/chat (mode: "topic_page") — no caching, no claim that any of this
 * is "indexed" or measured. */
const BROWSE_TAXONOMY = [
  {
    id: "breast",
    label: "Breast",
    glyph: "BR",
    gradient: "linear-gradient(135deg, #d1477a, #6b2142)",
    subcategories: [
      { id: "benign", label: "Benign Changes", entities: ["Fibroadenoma", "Fibrocystic change", "Sclerosing adenosis", "Intraductal papilloma"] },
      { id: "in_situ", label: "In Situ Lesions", entities: ["Ductal carcinoma in situ (DCIS)", "Lobular carcinoma in situ (LCIS)", "Pleomorphic LCIS", "Atypical lobular hyperplasia (ALH)", "Flat epithelial atypia"] },
      { id: "invasive", label: "Invasive Carcinomas", entities: ["Invasive ductal carcinoma", "Invasive lobular carcinoma", "Mucinous carcinoma of breast", "Tubular carcinoma of breast"] },
      { id: "inflammatory", label: "Inflammatory Lesions", entities: ["Granulomatous mastitis", "Duct ectasia", "Fat necrosis"] },
      { id: "other", label: "Other Malignancies", entities: ["Phyllodes tumor", "Angiosarcoma of breast"] },
    ],
  },
  {
    id: "gyn_cervix",
    label: "Gyn — Cervix, Vulva & Vagina",
    glyph: "CX",
    gradient: "linear-gradient(135deg, #b23a6b, #5c1f42)",
    subcategories: [
      { id: "squamous", label: "Squamous Lesions", entities: ["CIN1 / LSIL", "CIN2", "CIN3 / HSIL", "Squamous cell carcinoma of cervix"] },
      { id: "glandular", label: "Glandular Lesions", entities: ["Endocervical adenocarcinoma in situ", "Cervical adenocarcinoma, usual type"] },
      { id: "benign", label: "Benign / Reactive", entities: ["Endocervical polyp", "Microglandular hyperplasia"] },
      { id: "vulvovaginal", label: "Vulva & Vagina", entities: ["Vulvar intraepithelial neoplasia (VIN/HSIL)", "Squamous cell carcinoma of vulva", "Extramammary Paget disease", "Vaginal clear cell adenocarcinoma"] },
    ],
  },
  {
    id: "gyn_uterus",
    label: "Gyn — Uterus",
    glyph: "UT",
    gradient: "linear-gradient(135deg, #a84a9c, #4a2159)",
    subcategories: [
      { id: "hyperplasia", label: "Hyperplasia & Precursors", entities: ["Endometrial hyperplasia without atypia", "Atypical hyperplasia / EIN"] },
      { id: "carcinoma", label: "Carcinomas", entities: ["Endometrioid carcinoma", "Serous carcinoma of endometrium", "Clear cell carcinoma of endometrium", "Carcinosarcoma"] },
      { id: "mesenchymal", label: "Mesenchymal Tumors", entities: ["Leiomyoma", "Leiomyosarcoma", "Endometrial stromal sarcoma"] },
    ],
  },
  {
    id: "gyn_ovary",
    label: "Gyn — Ovary",
    glyph: "OV",
    gradient: "linear-gradient(135deg, #8a4fc9, #3c2166)",
    subcategories: [
      { id: "epithelial", label: "Epithelial Tumors", entities: ["Serous borderline tumor", "High-grade serous carcinoma", "Mucinous cystadenoma", "Endometrioid carcinoma of ovary"] },
      { id: "germ_cell", label: "Germ Cell Tumors", entities: ["Mature cystic teratoma", "Dysgerminoma", "Yolk sac tumor"] },
      { id: "sex_cord", label: "Sex Cord-Stromal Tumors", entities: ["Granulosa cell tumor", "Sertoli-Leydig cell tumor", "Fibrothecoma"] },
    ],
  },
  {
    id: "gi",
    label: "GI / Gastrointestinal",
    glyph: "GI",
    gradient: "linear-gradient(135deg, #c98a3f, #6b4416)",
    subcategories: [
      { id: "polyps", label: "Polyps & Precursors", entities: ["Tubular adenoma", "Sessile serrated lesion", "Traditional serrated adenoma", "Hyperplastic polyp"] },
      { id: "carcinoma", label: "Carcinomas", entities: ["Colorectal adenocarcinoma", "Gastric adenocarcinoma", "Esophageal adenocarcinoma (Barrett-associated)"] },
      { id: "inflammatory", label: "Inflammatory Conditions", entities: ["Ulcerative colitis", "Crohn disease", "Celiac disease"] },
      { id: "other", label: "Neuroendocrine & Stromal", entities: ["Well-differentiated neuroendocrine tumor", "Gastrointestinal stromal tumor (GIST)"] },
    ],
  },
  {
    id: "hepatobiliary",
    label: "Hepatobiliary & Pancreatic",
    glyph: "HP",
    gradient: "linear-gradient(135deg, #b5722f, #5e3813)",
    subcategories: [
      { id: "liver", label: "Liver", entities: ["Hepatocellular carcinoma", "Focal nodular hyperplasia", "Hepatic adenoma"] },
      { id: "pancreas", label: "Pancreas", entities: ["Pancreatic ductal adenocarcinoma", "Intraductal papillary mucinous neoplasm (IPMN)", "Pancreatic neuroendocrine tumor"] },
    ],
  },
  {
    id: "gu_prostate_bladder",
    label: "GU — Prostate & Bladder",
    glyph: "PB",
    gradient: "linear-gradient(135deg, #3f8fc9, #1c3f66)",
    subcategories: [
      { id: "prostate", label: "Prostate", entities: ["Prostatic adenocarcinoma (Gleason grading)", "High-grade prostatic intraepithelial neoplasia (HGPIN)", "Atypical adenomatous hyperplasia (adenosis)", "Benign prostatic hyperplasia"] },
      { id: "bladder", label: "Bladder", entities: ["High-grade urothelial carcinoma", "Low-grade papillary urothelial carcinoma", "Urothelial carcinoma in situ", "Urothelial papilloma"] },
    ],
  },
  {
    id: "gu_kidney_testis",
    label: "GU — Kidney & Testis",
    glyph: "KT",
    gradient: "linear-gradient(135deg, #4aa3a3, #1f4d4d)",
    subcategories: [
      { id: "kidney", label: "Kidney", entities: ["Clear cell renal cell carcinoma", "Papillary renal cell carcinoma", "Chromophobe renal cell carcinoma", "Angiomyolipoma", "Oncocytoma"] },
      { id: "testis", label: "Testis", entities: ["Seminoma", "Embryonal carcinoma", "Yolk sac tumor of testis", "Leydig cell tumor"] },
    ],
  },
  {
    id: "skin",
    label: "Skin / Dermatopathology",
    glyph: "SK",
    gradient: "linear-gradient(135deg, #d9a066, #6e4a29)",
    subcategories: [
      { id: "melanocytic", label: "Melanocytic Lesions", entities: ["Melanoma", "Dysplastic nevus", "BAP1-inactivated melanocytoma", "Spitz nevus"] },
      { id: "epithelial", label: "Epithelial Lesions", entities: ["Basal cell carcinoma", "Squamous cell carcinoma of skin", "Seborrheic keratosis", "Actinic keratosis"] },
      { id: "inflammatory", label: "Inflammatory Dermatoses", entities: ["Psoriasis", "Lichen planus", "Spongiotic dermatitis"] },
    ],
  },
  {
    id: "head_neck",
    label: "Head & Neck",
    glyph: "HN",
    gradient: "linear-gradient(135deg, #5f9ea0, #2b4a4b)",
    subcategories: [
      { id: "mucosal", label: "Mucosal / Squamous", entities: ["Squamous cell carcinoma of oral cavity", "Nasopharyngeal carcinoma", "Laryngeal squamous cell carcinoma"] },
      { id: "salivary", label: "Salivary Gland", entities: ["Pleomorphic adenoma", "Warthin tumor", "Mucoepidermoid carcinoma", "Adenoid cystic carcinoma", "Epithelial-myoepithelial carcinoma", "Myoepithelial carcinoma", "Basal cell adenocarcinoma", "Acinic cell carcinoma"] },
    ],
  },
  {
    id: "bone_soft_tissue",
    label: "Bone & Soft Tissue",
    glyph: "BS",
    gradient: "linear-gradient(135deg, #9a9a9a, #4a4a4a)",
    subcategories: [
      { id: "bone", label: "Bone Tumors", entities: ["Osteosarcoma", "Giant cell tumor of bone", "Chondrosarcoma", "Ewing sarcoma", "Chordoma"] },
      { id: "soft_tissue", label: "Soft Tissue Tumors", entities: ["Liposarcoma", "Leiomyosarcoma of soft tissue", "Synovial sarcoma", "Nodular fasciitis", "Meningioma"] },
    ],
  },
  {
    id: "heme",
    label: "Hematopathology / Lymph Nodes",
    glyph: "HM",
    gradient: "linear-gradient(135deg, #c94f4f, #6b2323)",
    subcategories: [
      { id: "b_cell", label: "B-Cell Lymphomas", entities: ["Diffuse large B-cell lymphoma", "Follicular lymphoma", "Mantle cell lymphoma", "Chronic lymphocytic leukemia / SLL"] },
      { id: "hodgkin", label: "Hodgkin & Related", entities: ["Classic Hodgkin lymphoma", "Nodular lymphocyte predominant Hodgkin lymphoma"] },
      { id: "reactive", label: "Reactive / Benign", entities: ["Reactive lymphoid hyperplasia", "Necrotizing lymphadenitis (Kikuchi disease)"] },
    ],
  },
  {
    id: "endocrine",
    label: "Endocrine",
    glyph: "EN",
    gradient: "linear-gradient(135deg, #5fb87d, #245c38)",
    subcategories: [
      { id: "thyroid", label: "Thyroid", entities: ["Papillary thyroid carcinoma", "Follicular adenoma of thyroid", "Medullary thyroid carcinoma", "Hashimoto thyroiditis"] },
      { id: "other_endocrine", label: "Parathyroid & Adrenal", entities: ["Parathyroid adenoma", "Adrenal cortical adenoma", "Pheochromocytoma"] },
    ],
  },
  {
    id: "neuro",
    label: "Neuropathology",
    glyph: "NP",
    gradient: "linear-gradient(135deg, #7a5fc9, #382a6b)",
    subcategories: [
      { id: "tumors", label: "CNS Tumors", entities: ["Glioblastoma", "Meningioma", "Pilocytic astrocytoma", "Schwannoma"] },
      { id: "other", label: "Other", entities: ["Metastatic carcinoma to brain"] },
    ],
  },
  {
    id: "thorax",
    label: "Thorax / Mediastinum",
    glyph: "TX",
    gradient: "linear-gradient(135deg, #4d79c9, #24356b)",
    subcategories: [
      { id: "lung", label: "Lung", entities: ["Lung adenocarcinoma", "Squamous cell carcinoma of lung", "Small cell lung carcinoma"] },
      { id: "mediastinum", label: "Mediastinum & Pleura", entities: ["Thymoma", "Mesothelioma"] },
    ],
  },
  {
    id: "cyto",
    label: "Cytopathology",
    glyph: "CY",
    gradient: "linear-gradient(135deg, #4fc9b8, #1f6b5f)",
    subcategories: [
      { id: "cyto_topics", label: "Common FNA / Exfoliative Cytology", entities: ["Thyroid FNA (Bethesda system)", "Pap smear HSIL", "Pancreatic FNA, adenocarcinoma", "Effusion cytology, adenocarcinoma"] },
    ],
  },
  {
    id: "peds",
    label: "Pediatric",
    glyph: "PD",
    gradient: "linear-gradient(135deg, #e0b84f, #7a5f1f)",
    subcategories: [
      { id: "peds_tumors", label: "Pediatric Tumors", entities: ["Wilms tumor", "Neuroblastoma", "Hepatoblastoma", "Rhabdomyosarcoma"] },
    ],
  },
];

function countLeaves(category) {
  return category.subcategories.reduce((sum, sub) => sum + sub.entities.length, 0);
}

/** Topic-page prepop pilot (v0_1): generated WHO + ABPath Browse
 * tag index, fetched once at startup from the static build artifact. See
 * docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md. Null until loaded (or if the
 * fetch fails), in which case Browse falls back to the curated-only
 * BROWSE_TAXONOMY above so the tree is never blank. */
let browseIndex = null;

/** Locked browse-nav policy: accepted topic tags come from ABPath and/or WHO
 * only (PathOut is a citation source, not a nav tag source). Mirrors
 * `dedupe_rules` in browse_tag_index_v0_2. */
const ACCEPTED_NAV_PROVENANCES = new Set(["abpath", "who", "both"]);
const NAV_PROVENANCE_LABELS = {
  abpath: "ABPath board curriculum",
  who: "WHO classification map",
  both: "ABPath board + WHO",
  curated: "Curated starter (not board-mapped)",
};

function formatNavProvenanceLabel(provenance) {
  const key = String(provenance || "").toLowerCase();
  return NAV_PROVENANCE_LABELS[key] || null;
}

/** Normalize label/query text for matching starter leaves → full ABPath/WHO tags. */
function normalizeTopicMatchKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/**
 * When Browse opens a curated starter leaf (`tag: null`), try to attach the
 * real ABPath/WHO hierarchical tag from the full browse index so the topic
 * page can show board/curricular location instead of a blank tag header.
 */
function resolveBoardMappedLeaf(leafRef) {
  if (!leafRef) return leafRef;
  if (leafRef.tag) return leafRef;
  if (!browseIndex) return leafRef;
  const keys = new Set(
    [leafRef.label, leafRef.query]
      .map(normalizeTopicMatchKey)
      .filter(Boolean),
  );
  if (!keys.size) return leafRef;

  let best = null;
  let bestScore = -1;
  for (const row of collectLeavesFromRoots(getBrowseNavRootsFull() || [])) {
    const leaf = row.leaf;
    if (!leaf?.tag) continue;
    const leafKeys = [leaf.label, leaf.query].map(normalizeTopicMatchKey);
    let score = 0;
    for (const k of keys) {
      for (const lk of leafKeys) {
        if (!lk) continue;
        if (lk === k) score = Math.max(score, 100);
        else if (lk.includes(k) || k.includes(lk)) score = Math.max(score, 60);
      }
    }
    // Prefer ABPath / both over WHO-only; prefer same organ root when known.
    const prov = String(leaf.provenance || "").toLowerCase();
    if (prov === "abpath" || prov === "both") score += 5;
    if (leafRef.categoryId && row.root?.id === leafRef.categoryId) score += 8;
    if (score > bestScore) {
      bestScore = score;
      best = { row, leaf };
    }
  }
  if (!best || bestScore < 60) return leafRef;
  return {
    ...leafRef,
    tag: best.leaf.tag,
    provenance: best.leaf.provenance || leafRef.provenance || null,
    label: leafRef.label || best.leaf.label,
    query: leafRef.query || best.leaf.query || best.leaf.label,
    categoryId: leafRef.categoryId || best.row.root?.id || null,
    subcategoryId: leafRef.subcategoryId || best.row.sub?.id || null,
    boardResolvedFrom: "browse_tag_index",
  };
}

/** Known-root glyph/gradient styling, keyed by the generated index's root
 * `id`s (see build_browse_tag_index_v0_1.py). Any root not listed here
 * (e.g. small PathOut-only residual roots) gets a neutral default look —
 * never a hard failure. */
const BROWSE_ROOT_STYLE = {
  cyto: { glyph: "CY", gradient: "linear-gradient(135deg, #4fc9b8, #1f6b5f)" },
  breast: { glyph: "BR", gradient: "linear-gradient(135deg, #d1477a, #6b2142)" },
  gyn: { glyph: "GY", gradient: "linear-gradient(135deg, #a84a9c, #4a2159)" },
  gi: { glyph: "GI", gradient: "linear-gradient(135deg, #c98a3f, #6b4416)" },
  gu: { glyph: "GU", gradient: "linear-gradient(135deg, #3f8fc9, #1c3f66)" },
  skin: { glyph: "SK", gradient: "linear-gradient(135deg, #d9a066, #6e4a29)" },
  hn: { glyph: "HN", gradient: "linear-gradient(135deg, #5f9ea0, #2b4a4b)" },
  bst: { glyph: "BS", gradient: "linear-gradient(135deg, #9a9a9a, #4a4a4a)" },
  heme: { glyph: "HM", gradient: "linear-gradient(135deg, #c94f4f, #6b2323)" },
  endo: { glyph: "EN", gradient: "linear-gradient(135deg, #5fb87d, #245c38)" },
  neuro: { glyph: "NP", gradient: "linear-gradient(135deg, #7a5fc9, #382a6b)" },
  thorax_mediastinum: { glyph: "TX", gradient: "linear-gradient(135deg, #4d79c9, #24356b)" },
  peds: { glyph: "PD", gradient: "linear-gradient(135deg, #e0b84f, #7a5f1f)" },
  molecular: { glyph: "MO", gradient: "linear-gradient(135deg, #6b8fb8, #2e4a66)" },
  eye_orbit: { glyph: "EY", gradient: "linear-gradient(135deg, #8fae5f, #3f4f24)" },
  eye: { glyph: "EY", gradient: "linear-gradient(135deg, #8fae5f, #3f4f24)" },
  general_pathology: { glyph: "GP", gradient: "linear-gradient(135deg, #8a8a8a, #3a3a3a)" },
};
const DEFAULT_ROOT_STYLE = { glyph: "PA", gradient: "linear-gradient(135deg, #7a7a7a, #3a3a3a)" };

function rootTileStyle(rootId, label) {
  const known = BROWSE_ROOT_STYLE[rootId];
  if (known) return known;
  const glyph = String(label || rootId || "??").replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase() || "PA";
  return { glyph, gradient: DEFAULT_ROOT_STYLE.gradient };
}

/** Converts the hand-curated BROWSE_TAXONOMY into the same {roots ->
 * subcategories -> leaves} shape as the generated index, so every render
 * function below can operate on one unified model regardless of whether the
 * real combined index loaded. Curated leaves have no real taxonomy `tag`
 * (`tag: null`) — loadLeafTopicPage() treats that as "always live, never try
 * prebuild". */
function curatedFallbackRoots() {
  return BROWSE_TAXONOMY.map((cat) => ({
    id: cat.id,
    label: cat.label,
    kind: "curated",
    leaf_count: countLeaves(cat),
    subcategories: cat.subcategories.map((sub) => ({
      id: sub.id,
      label: sub.label,
      leaf_count: sub.entities.length,
      leaves: sub.entities.map((entity) => ({
        tag: null,
        label: entity,
        provenance: "curated",
        query: entity,
      })),
    })),
  }));
}

const BROWSE_PROVENANCE_RANK = { abpath: 0, both: 1, who: 2 };
const BROWSE_NAV_MODE_KEY = "ph_browse_nav_mode_v0_2";
const BROWSE_LEAF_PREVIEW_CAP = 48;
const BROWSE_NAV_THINNING = {
  abpath_primary: false,
  hide_cyto_surgical_dupes: true,
  drop_cyto_pattern: true,
};

let browseNavMode = "full";
let browseFilterQuery = "";

function readBrowseNavMode() {
  try {
    const stored = localStorage.getItem(BROWSE_NAV_MODE_KEY);
    return stored === "full" ? "full" : "starter";
  } catch (_err) {
    return "starter";
  }
}

function writeBrowseNavMode(mode) {
  browseNavMode = mode === "full" ? "full" : "starter";
  try {
    localStorage.setItem(BROWSE_NAV_MODE_KEY, browseNavMode);
  } catch (_err) {
    // ignore quota / private-mode failures
  }
}

browseNavMode = readBrowseNavMode();

function getBrowseNavRootsFull() {
  if (browseIndex && Array.isArray(browseIndex.nav_roots_full) && browseIndex.nav_roots_full.length) {
    return browseIndex.nav_roots_full;
  }
  return null;
}

/** Collapse redundant nav leaves: one clickable topic per root + display label.
 * Prefers ABPath over WHO-only when the same entity name appears under multiple
 * subcategories (common with WHO overlay). */
function compactBrowseRoots(roots, options = {}) {
  const thinning = { ...BROWSE_NAV_THINNING, ...options };
  let before = 0;
  let after = 0;
  let skippedWhoOnly = 0;
  let skippedCytoPattern = 0;
  const compactedRoots = [];
  for (const root of roots || []) {
    const winners = new Map();
    for (const sub of root.subcategories || []) {
      for (const leaf of sub.leaves || []) {
        before += 1;
        const provenance = String(leaf.provenance || "").toLowerCase();
        if (thinning.abpath_primary && provenance === "who") {
          skippedWhoOnly += 1;
          continue;
        }
        if (thinning.drop_cyto_pattern && root.id === "cyto" && String(leaf.tag || "").includes("::Pattern::")) {
          skippedCytoPattern += 1;
          continue;
        }
        const labelKey = String(leaf.label || "").trim().toLowerCase();
        if (!labelKey) continue;
        const dedupeKey = `${root.id}::${labelKey}`;
        const rank = BROWSE_PROVENANCE_RANK[provenance] ?? 9;
        const depth = String(leaf.tag || "").split("::").length;
        const prev = winners.get(dedupeKey);
        if (!prev) {
          winners.set(dedupeKey, { leaf, rank, depth, subId: sub.id, subLabel: sub.label });
          continue;
        }
        const better =
          rank < prev.rank
          || (rank === prev.rank && depth > prev.depth)
          || (rank === prev.rank && depth === prev.depth && String(leaf.tag || "") < String(prev.leaf.tag || ""));
        if (better) {
          winners.set(dedupeKey, { leaf, rank, depth, subId: sub.id, subLabel: sub.label });
        }
      }
    }
    const subBuckets = new Map();
    for (const { leaf, subId, subLabel } of winners.values()) {
      after += 1;
      if (!subBuckets.has(subId)) {
        subBuckets.set(subId, { id: subId, label: subLabel, leaves: [] });
      }
      subBuckets.get(subId).leaves.push(leaf);
    }
    const subcategories = [...subBuckets.values()]
      .map((sub) => {
        sub.leaves = sub.leaves.sort((a, b) => String(a.label).localeCompare(String(b.label)));
        sub.leaf_count = sub.leaves.length;
        return sub;
      })
      .filter((sub) => sub.leaf_count > 0)
      .sort((a, b) => String(a.label).localeCompare(String(b.label)));
    const leafCount = subcategories.reduce((sum, sub) => sum + sub.leaf_count, 0);
    if (!leafCount) continue;
    compactedRoots.push({
      ...root,
      leaf_count: leafCount,
      subcategories,
    });
  }

  let cytoAliasRemoved = 0;
  if (!thinning.hide_cyto_surgical_dupes) {
    return {
      roots: compactedRoots,
      before,
      after,
      removed: Math.max(0, before - after),
      skippedWhoOnly,
      skippedCytoPattern,
      cytoAliasRemoved,
    };
  }

  const nonCytoLabels = new Set();
  for (const root of compactedRoots) {
    if (root.id === "cyto") continue;
    for (const sub of root.subcategories || []) {
      for (const leaf of sub.leaves || []) {
        const labelKey = String(leaf.label || "").trim().toLowerCase();
        if (labelKey) nonCytoLabels.add(labelKey);
      }
    }
  }

  const thinnedRoots = [];
  for (const root of compactedRoots) {
    if (root.id !== "cyto") {
      thinnedRoots.push(root);
      continue;
    }
    const subcategories = [];
    for (const sub of root.subcategories || []) {
      const leaves = (sub.leaves || []).filter((leaf) => {
        const labelKey = String(leaf.label || "").trim().toLowerCase();
        if (!labelKey || !nonCytoLabels.has(labelKey)) return true;
        cytoAliasRemoved += 1;
        return false;
      });
      if (!leaves.length) continue;
      subcategories.push({
        ...sub,
        leaves,
        leaf_count: leaves.length,
      });
    }
    const leafCount = subcategories.reduce((sum, sub) => sum + sub.leaf_count, 0);
    if (!leafCount) continue;
    thinnedRoots.push({
      ...root,
      leaf_count: leafCount,
      subcategories,
    });
  }

  const finalAfter = thinnedRoots.reduce((sum, root) => sum + root.leaf_count, 0);
  return {
    roots: thinnedRoots,
    before,
    after: finalAfter,
    removed: Math.max(0, before - finalAfter),
    skippedWhoOnly,
    skippedCytoPattern,
    cytoAliasRemoved,
  };
}

function getBrowseRoots() {
  if (browseNavMode === "full") {
    const full = getBrowseNavRootsFull();
    if (full) return full;
  }
  if (browseIndex) {
    return curatedFallbackRoots();
  }
  return curatedFallbackRoots();
}

function normalizeBrowseFilterText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function leafMatchesBrowseFilter(leaf, filterText) {
  const q = normalizeBrowseFilterText(filterText);
  if (!q) return true;
  const hay = normalizeBrowseFilterText(
    `${formatDisplayLabel(leaf.label)} ${leaf.query || ""} ${leaf.tag || ""}`,
  );
  return q.split(/\s+/).every((token) => hay.includes(token));
}

function collectLeavesFromRoots(roots) {
  const rows = [];
  for (const root of roots || []) {
    for (const sub of root.subcategories || []) {
      for (const leaf of sub.leaves || []) {
        rows.push({
          root,
          sub,
          leaf,
          displayLabel: formatDisplayLabel(leaf.label),
        });
      }
    }
  }
  return rows;
}

function browseSearchBarHtml(placeholder, value = "") {
  return `<div class="browse-search-row">
    <input type="search" class="browse-search-input" id="browse-filter-input" placeholder="${escapeAttr(placeholder)}" value="${escapeAttr(value)}" autocomplete="off" />
    ${value ? '<button type="button" class="btn-secondary browse-search-clear" id="browse-filter-clear">Clear</button>' : ""}
  </div>`;
}

function bindBrowseSearchHandlers(onChange) {
  const input = document.getElementById("browse-filter-input");
  const clearBtn = document.getElementById("browse-filter-clear");
  if (!input) return;
  input.addEventListener("input", () => {
    browseFilterQuery = input.value;
    onChange();
  });
  clearBtn?.addEventListener("click", () => {
    browseFilterQuery = "";
    onChange();
  });
  input.focus();
}

/** Fetches the generated combined-tag Browse index once at startup. Never
 * throws — on any failure (missing file, empty roots, bad JSON) leaves
 * `browseIndex` as null so Browse keeps working from the curated fallback,
 * per the plan's "thin fallback, do not silently claim the old list is the
 * index" requirement (the home view labels which mode is active). */
async function loadBrowseIndex() {
  try {
    const resp = await fetch("/static/browse_tag_index_v0_1.json");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!data || !Array.isArray(data.roots) || !data.roots.length) {
      throw new Error("Empty or malformed browse_tag_index_v0_1.json");
    }
    const rules = data.dedupe_rules || {};
    const navSources = Array.isArray(rules.nav_sources) ? rules.nav_sources : [];
    if (
      !navSources.includes("abpath")
      || !navSources.includes("who")
      || rules.pathout_nav !== false
    ) {
      throw new Error("Browse index nav_sources are not WHO + ABPath only");
    }
    browseIndex = data;
    const compact = compactBrowseRoots(browseIndex.roots);
    browseIndex.nav_roots_full = compact.roots;
    browseIndex.counts = {
      ...(browseIndex.counts || {}),
      leaves_total_raw: browseIndex.counts?.leaves_total ?? compact.before,
      leaves_total: compact.after,
      leaves_removed_label_dedupe: compact.removed,
      leaves_removed_who_only_nav: compact.skippedWhoOnly,
      leaves_removed_cyto_pattern_nav: compact.skippedCytoPattern,
      leaves_removed_cyto_surgical_alias: compact.cytoAliasRemoved,
    };
    browseIndex.dedupe_rules = {
      ...(browseIndex.dedupe_rules || {}),
      label_dedupe_within_root: "one leaf per root+display_label; prefer abpath > both > who",
      nav_thinning: {
        abpath_primary: BROWSE_NAV_THINNING.abpath_primary,
        hide_cyto_surgical_dupes: BROWSE_NAV_THINNING.hide_cyto_surgical_dupes,
        drop_cyto_pattern: BROWSE_NAV_THINNING.drop_cyto_pattern,
        default_nav_mode: "full",
      },
    };
  } catch (err) {
    browseIndex = null;
    // eslint-disable-next-line no-console
    console.warn("Browse tag index unavailable; using curated fallback taxonomy.", err);
  }
  TAXONOMY_LEAF_INDEX = buildLeafIndex();
}

/** Common pathology abbreviations expanded to full phrases before token
 * comparison, so a DDx bullet spelled out in full (e.g. "Pleomorphic Lobular
 * Carcinoma In Situ") still matches a taxonomy leaf stored as a shorthand
 * (e.g. "Pleomorphic LCIS"), and vice versa. */
const ENTITY_ABBREVIATION_EXPANSIONS = {
  lcis: "lobular carcinoma in situ",
  dcis: "ductal carcinoma in situ",
  plcis: "pleomorphic lobular carcinoma in situ",
  alh: "atypical lobular hyperplasia",
  adh: "atypical ductal hyperplasia",
  cin: "cervical intraepithelial neoplasia",
  hsil: "high grade squamous intraepithelial lesion",
  lsil: "low grade squamous intraepithelial lesion",
  vin: "vulvar intraepithelial neoplasia",
  hgpin: "high grade prostatic intraepithelial neoplasia",
  gist: "gastrointestinal stromal tumor",
  ipmn: "intraductal papillary mucinous neoplasm",
  dlbcl: "diffuse large b cell lymphoma",
  sll: "small lymphocytic lymphoma",
  cll: "chronic lymphocytic leukemia",
};

function normalizeEntityName(name) {
  const base = String(name || "")
    .toLowerCase()
    .replace(/\([^)]*\)/g, " ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return base
    .split(" ")
    .map((token) => ENTITY_ABBREVIATION_EXPANSIONS[token] || token)
    .join(" ");
}

/** Built from the thinned full index when available (curated fallback until
 * loadBrowseIndex() resolves). Mutable (`let`), not a one-time IIFE const,
 * because the underlying roots can change once at startup when the generated
 * index finishes loading. */
function buildLeafIndex() {
  const list = [];
  const roots = getBrowseNavRootsFull() || getBrowseRoots();
  for (const root of roots) {
    for (const sub of root.subcategories) {
      for (const leaf of sub.leaves) {
        const displayName = formatDisplayLabel(leaf.label);
        list.push({
          categoryId: root.id,
          subcategoryId: sub.id,
          tag: leaf.tag,
          label: leaf.label,
          query: leaf.query,
          entityName: displayName,
          normalized: normalizeEntityName(displayName),
        });
      }
    }
  }
  return list;
}

let TAXONOMY_LEAF_INDEX = buildLeafIndex();

function leafRefFrom(leaf) {
  return { categoryId: leaf.categoryId, subcategoryId: leaf.subcategoryId, tag: leaf.tag, label: leaf.label, query: leaf.query };
}

/** Page-context for DDx / cross-mention nav: prefer same organ root over the
 * first alphabetical index hit (e.g. HN Salivary ACC, not Cyto Breast ACC). */
function pageContextFromBrowseState() {
  if (!browseState || browseState.level !== "leaf") return null;
  return {
    categoryId: browseState.categoryId || null,
    subcategoryId: browseState.subcategoryId || null,
    tag: browseState.tag || null,
  };
}

function pageContextFromEntryMeta(entryMeta) {
  if (!entryMeta) return pageContextFromBrowseState();
  return {
    categoryId: entryMeta.categoryId || browseState?.categoryId || null,
    subcategoryId: entryMeta.subcategoryId || browseState?.subcategoryId || null,
    tag: entryMeta.tag || browseState?.tag || null,
  };
}

function leafTagRoot(leaf) {
  const tag = leaf?.tag;
  if (typeof tag === "string" && tag.includes("::")) {
    return tag.split("::", 1)[0].toLowerCase();
  }
  return String(leaf?.categoryId || "").toLowerCase();
}

function pageTagRoot(pageContext) {
  const tag = pageContext?.tag;
  if (typeof tag === "string" && tag.includes("::")) {
    return tag.split("::", 1)[0].toLowerCase();
  }
  return String(pageContext?.categoryId || "").toLowerCase();
}

function subcategoryAffinity(leafSubId, pageSubId) {
  if (!leafSubId || !pageSubId) return 0;
  const a = String(leafSubId).toLowerCase().replace(/_/g, "");
  const b = String(pageSubId).toLowerCase().replace(/_/g, "");
  if (a === b) return 3;
  if (a.includes(b) || b.includes(a)) return 2;
  // Salivary ↔ Salivary_Gland / Cyto_Salivary family tokens
  const tokens = (s) => new Set(s.split(/(?=[A-Z])|_| /).join(" ").toLowerCase().split(/\s+/).filter((t) => t.length > 3));
  const ta = tokens(String(leafSubId));
  const tb = tokens(String(pageSubId));
  let overlap = 0;
  for (const t of ta) if (tb.has(t)) overlap += 1;
  return overlap > 0 ? 1 : 0;
}

/** Rank candidate leaves for navigation. Higher is better. */
function scoreLeafForPageContext(leaf, pageContext) {
  if (!pageContext) {
    // No page context: prefer surgical roots over cyto modality overlays.
    return leaf.categoryId === "cyto" ? 0 : 10;
  }
  let score = 0;
  const pageCat = pageContext.categoryId;
  const pageRoot = pageTagRoot(pageContext);
  const leafRoot = leafTagRoot(leaf);

  if (pageCat && leaf.categoryId === pageCat) score += 100;
  if (pageRoot && leafRoot && pageRoot === leafRoot) score += 80;

  // Prefer related cyto family when page is surgical (HN → Cyto_Salivary)
  // over unrelated cyto (Cyto_Breast).
  score += subcategoryAffinity(leaf.subcategoryId, pageContext.subcategoryId) * 25;

  if (pageCat && pageCat !== "cyto" && leaf.categoryId === "cyto") {
    score -= 40;
  }
  if (pageCat === "cyto" && leaf.categoryId !== "cyto") {
    // On a cyto page, still allow surgical siblings, but prefer cyto.
    score -= 10;
  }
  return score;
}

function pickBestLeaf(candidates, pageContext) {
  if (!candidates?.length) return null;
  let best = candidates[0];
  let bestScore = scoreLeafForPageContext(best, pageContext);
  for (let i = 1; i < candidates.length; i += 1) {
    const leaf = candidates[i];
    const score = scoreLeafForPageContext(leaf, pageContext);
    if (score > bestScore) {
      best = leaf;
      bestScore = score;
    }
  }
  return best;
}

/** Fuzzy-match a Differential Diagnosis bullet's entity name against the
 * taxonomy leaves (curated or generated index, whichever is active), so we
 * only cross-link when reasonably confident — false negatives (no link) are
 * far safer here than false positives (a wrong link), so the overlap
 * threshold below is deliberately conservative.
 *
 * When multiple leaves share the same display name (Adenoid Cystic Carcinoma
 * in Breast, HN Salivary, Cyto Breast, etc.), prefer the leaf in the same
 * organ/root as the current topic page. */
function findTaxonomyMatch(rawName, pageContext = null) {
  const norm = normalizeEntityName(rawName);
  if (!norm) return null;
  const ctx = pageContext || pageContextFromBrowseState();
  const normTokens = new Set(norm.split(" ").filter((t) => t.length > 2));

  const exactMatches = [];
  const fuzzyByScore = new Map(); // score -> leaves[]

  for (const leaf of TAXONOMY_LEAF_INDEX) {
    if (leaf.normalized === norm) {
      exactMatches.push(leaf);
      continue;
    }
    let score = 0;
    if (norm.includes(leaf.normalized) || leaf.normalized.includes(norm)) {
      score = Math.min(leaf.normalized.length, norm.length) / Math.max(leaf.normalized.length, norm.length);
    } else {
      const leafTokens = new Set(leaf.normalized.split(" ").filter((t) => t.length > 2));
      if (!leafTokens.size) continue;
      let overlap = 0;
      for (const t of normTokens) {
        if (leafTokens.has(t)) overlap += 1;
      }
      score = overlap / Math.max(leafTokens.size, normTokens.size, 1);
    }
    if (score < 0.5) continue;
    if (!fuzzyByScore.has(score)) fuzzyByScore.set(score, []);
    fuzzyByScore.get(score).push(leaf);
  }

  if (exactMatches.length) {
    return leafRefFrom(pickBestLeaf(exactMatches, ctx));
  }

  if (fuzzyByScore.size) {
    const topScore = Math.max(...fuzzyByScore.keys());
    if (topScore >= 0.5) {
      return leafRefFrom(pickBestLeaf(fuzzyByScore.get(topScore), ctx));
    }
  }
  return null;
}

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
const exportPageBtn = document.getElementById("export-page-btn");
const exportStatus = document.getElementById("export-status");
const mediaModal = document.getElementById("media-modal");
const mediaModalImg = document.getElementById("media-modal-img");
const mediaModalCaption = document.getElementById("media-modal-caption");
const mediaModalFigure = document.getElementById("media-modal-figure");
const mediaModalPage = document.getElementById("media-modal-page");
const mediaModalSource = document.getElementById("media-modal-source");
const mediaModalTimestamp = document.getElementById("media-modal-timestamp");
const mediaModalReference = document.getElementById("media-modal-reference");
const mediaModalPrev = document.getElementById("media-modal-prev");
const mediaModalNext = document.getElementById("media-modal-next");
const compareTrayEl = document.getElementById("compare-tray");
const compareTrayCountEl = document.getElementById("compare-tray-count");
const compareRunBtn = document.getElementById("compare-run-btn");
const compareClearBtn = document.getElementById("compare-clear-btn");
const flagModal = document.getElementById("flag-modal");
const flagCommentEl = document.getElementById("flag-comment");
const flagSendBtn = document.getElementById("flag-send-btn");
const flagStatusEl = document.getElementById("flag-status");

/** Active lightbox gallery — ordered preview payloads + current index (C10). */
let currentGallery = { items: [], index: 0 };

const MAX_COMPARE = 4;
let compareSet = [];
let flagContext = null;
const viewTabs = document.querySelectorAll(".view-tab");
const browseViewEl = document.getElementById("browse-view");
const askViewEl = document.getElementById("ask-view");
const browseBreadcrumbsEl = document.getElementById("browse-breadcrumbs");
const browseContentEl = document.getElementById("browse-content");

let supportedSources = [];
let browseState = { level: "home" };
let browseRequestSeq = 0;

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source;
}

/** Strip the organ-root prefix from textbook source_id (e.g. hn_gnepp → Gnepp). */
function textbookLabel(sourceId) {
  if (!sourceId) return "Textbook";
  const parts = String(sourceId).split("_");
  if (parts.length < 2) return formatDisplayLabel(sourceId);
  parts.shift();
  const bookKey = parts.join("_");
  const alias = TEXTBOOK_ALIASES[bookKey.toLowerCase()];
  if (alias) return alias;
  return formatDisplayLabel(bookKey);
}

/** Per-card citation badge / "Open …" label — source-aware (B9). */
function citationSourceLabel(card) {
  const source = card.source || card._result_key || "";
  if (source === "journals") {
    return card.journal || card.source_name || "Journal";
  }
  if (source === "textbooks") {
    return textbookLabel(card.source_id);
  }
  return sourceLabel(source);
}

function cardTitle(card) {
  return card.title || card.name || card.heading || card.primary_tag || "(untitled hit)";
}

/** Cards sometimes carry `primary_tag` or `candidate_tags` — surface the
 * first real one as a small badge, but never fabricate a tag: skip entirely
 * if missing, blank, or the literal placeholder `__UNMAPPED__`. */
function cardTagLabel(card) {
  let tag = card.primary_tag;
  if (!tag && Array.isArray(card.candidate_tags) && card.candidate_tags.length) {
    tag = card.candidate_tags[0];
  }
  if (typeof tag !== "string") return null;
  const trimmed = tag.trim();
  if (!trimmed || trimmed === "__UNMAPPED__") return null;
  return trimmed;
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
    item.entity_name,
    item.text_excerpt,
    item.excerpt,
    item.text,
    item.snippet,
    item.header,
    item.source_id,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

const WEAK_SINGLE_TERMS = new Set([
  "cyst",
  "cysts",
  "tumor",
  "tumour",
  "mass",
  "lesion",
  "nodule",
  "benign",
  "malignant",
  "neoplasm",
]);

function termMatchesHaystack(term, haystack) {
  if (!term || !haystack) return false;
  if (term.length <= 5) {
    const re = new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    return re.test(haystack);
  }
  return haystack.includes(term);
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
  const hits = terms.filter((term) => termMatchesHaystack(term, hay));
  if (!hits.length) return 0;
  return hits.length / terms.length;
}

function videoRelevanceScore(query, item) {
  const terms = queryMatchTerms(query);
  if (!terms.length) return 1;
  const hay = itemHaystack(item);
  if (hasTopicConflict(terms, hay)) return -1;
  const hits = terms.filter((term) => termMatchesHaystack(term, hay));
  if (!hits.length) return 0;
  const strongHits = hits.filter((term) => !WEAK_SINGLE_TERMS.has(term));
  if (terms.length >= 2) {
    const rareHit = hits.some((term) => term.length >= 6);
    const ratio = hits.length / terms.length;
    if (!rareHit && ratio < 0.5) return 0;
    if (!rareHit && strongHits.length === 0) return 0;
  } else if (terms.length === 1 && WEAK_SINGLE_TERMS.has(terms[0]) && strongHits.length === 0) {
    return 0;
  }
  return hits.length / terms.length;
}

function filterVideoCardsByRelevance(query, cards, { maxShown = 6 } = {}) {
  const videos = (cards || []).filter(isVideoCard);
  if (!videos.length) {
    return { shown: [], hidden: [], note: "" };
  }
  const scored = videos.map((item) => ({ item, score: videoRelevanceScore(query, item) }));
  const relevant = scored.filter((row) => row.score > 0).sort((a, b) => b.score - a.score);
  const conflicts = scored.filter((row) => row.score < 0);
  const irrelevant = scored.filter((row) => row.score === 0);
  if (relevant.length) {
    // Collapse to one best segment per distinct LECTURE (not per raw chunk)
    // before applying `maxShown`, so e.g. 5 timestamped segments of the same
    // lecture never eat up the display cap as if they were 5 different
    // lectures — see bestVideoCardPerLecture for identity/tiebreak rules.
    const collapsed = bestVideoCardPerLecture(relevant);
    const shown = collapsed.slice(0, maxShown);
    const hiddenCount = conflicts.length + irrelevant.length + Math.max(0, collapsed.length - maxShown);
    const note =
      hiddenCount > 0
        ? `${hiddenCount} off-topic lecture segment${hiddenCount === 1 ? "" : "s"} hidden for this query.`
        : "";
    return { shown, hidden: [...conflicts, ...irrelevant].map((row) => row.item), note };
  }
  if (conflicts.length) {
    return {
      shown: [],
      hidden: videos,
      note: `${conflicts.length} lecture segment${conflicts.length === 1 ? "" : "s"} matched the wrong topic.`,
    };
  }
  return { shown: [], hidden: videos, note: "No lecture segments matched this topic closely." };
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
    // Split "actually off-topic" from "relevant but past the display cap" —
    // lumping both under one "off-topic" note made it look like retrieval
    // found little of value, when often most of it was on-topic and simply
    // not rendered.
    const offTopicCount = conflicts.length + irrelevant.length;
    const overflowCount = Math.max(0, relevant.length - maxShown);
    const notes = [];
    if (offTopicCount > 0) {
      notes.push(`${offTopicCount} off-topic hit${offTopicCount === 1 ? "" : "s"} hidden for this query.`);
    }
    if (overflowCount > 0) {
      notes.push(
        `${overflowCount} more relevant result${overflowCount === 1 ? "" : "s"} retrieved but not shown here (display cap).`,
      );
    }
    return { shown, hidden: [...conflicts, ...irrelevant].map((row) => row.item), note: notes.join(" ") };
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
  const srcLabel = citationSourceLabel(card);

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

/** Human-readable label for Browse nav and breadcrumbs. Underlying tag/id keys
 * used for API calls stay unchanged — only user-visible strings are formatted. */
function formatDisplayLabel(text) {
  return String(text || "").replace(/_/g, " ").trim();
}

/** Subcategory display normalization (A6): plain Genetics → Molecular Genetics. */
function formatSubcategoryLabel(text) {
  const normalized = formatDisplayLabel(text);
  if (/^genetics$/i.test(normalized)) return "Molecular Genetics";
  return normalized;
}

/** Strip textbook-style figure number callouts from rendered prose, e.g.
 * "(Fig. 2.29)", "(Figs. 7.17, 7.18, 7.19)", or standalone "Fig. 2.29". */
function stripFigureReferences(text) {
  let s = String(text || "");
  s = s.replace(/\(\s*Figs?\.\s*[\d][\d.,\s]*\s*\)/gi, "");
  s = s.replace(/\(\s*Figs?\s+[\d][\d.,\s]*\s*\)/gi, "");
  s = s.replace(/\bFigs?\.\s*[\d][\d.,\s]*/gi, "");
  s = s.replace(/\bFigs?\s+[\d][\d.,\s]*/gi, "");
  s = s.replace(/\(\s*\)/g, "");
  s = s.replace(/\b(?:see|refer to)\s+(?=[,.;]|$)/gi, "");
  s = s.replace(/\bto\s+for\b/gi, "for");
  s = s.replace(/\s+([,.;:])/g, "$1");
  s = s.replace(/([,.;])\s*([,.;])/g, "$1");
  s = s.replace(/\s{2,}/g, " ");
  return s.trim();
}

/** Best-effort strip of a trailing "Sources:"/"References:" link-dump block.
 * Inline citations already carry every URL; a closing roundup is redundant
 * and the prompt forbids it, but models occasionally slip and add one anyway. */
/** Unwrap ```markdown / ```md fences so pipe tables inside fences render as HTML. */
function unwrapFencedMarkdownBlocks(text) {
  return String(text || "").replace(/```([a-zA-Z0-9_-]*)\s*\n([\s\S]*?)```/g, (_match, lang, inner) => {
    const body = inner.trim();
    if (!body) return "";
    if (isMarkdownTable(body)) return body;
    if (!lang || /^(markdown|md|text)$/i.test(lang)) return body;
    return `\n\`\`\`${lang}\n${body}\n\`\`\`\n`;
  });
}

function normalizeInlineLinkLabel(label) {
  const raw = String(label || "").trim();
  if (!raw) return raw;
  const lower = raw.toLowerCase();
  if (INLINE_LINK_LABEL_ALIASES[lower]) return INLINE_LINK_LABEL_ALIASES[lower];
  if (/^path\s*out$/i.test(raw)) return "Pathoutlines";
  if (/^hn[_\s]+atlas$/i.test(raw)) return "Atlas";
  if (/^hn[_\s]+gnepp$/i.test(raw)) return "Gnepp";
  const stripped = raw.replace(
    /^(HN|Cyto|GU|Gyn|Breast|Soft|Bone|Pulm|Cardio|Hemat|Hemat_Lymph|Derm|Endo|GI|Neuro|Pediatric|Transplant|Forensic|Molecular)_/i,
    "",
  );
  if (stripped !== raw) {
    const alias = TEXTBOOK_ALIASES[stripped.toLowerCase().replace(/_/g, "")];
    if (alias) return alias;
    return formatDisplayLabel(stripped);
  }
  return raw;
}

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

function isMarkdownImageOnlyLine(line) {
  return /^\s*!\[[^\]]*\]\(https?:[^)\s]+\)\s*$/.test(line || "");
}

function isMarkdownImageOnlyBlock(block) {
  const lines = String(block || "")
    .split("\n")
    .filter((line) => line.trim());
  return lines.length > 0 && lines.every(isMarkdownImageOnlyLine);
}

function renderImageRowFromBlock(block, previewIndex) {
  const imgs = String(block || "")
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      const match = line.trim().match(/^!\[([^\]]*)\]\((https?:[^)\s]+)\)/);
      return match ? renderInlineImage(match[1], match[2], previewIndex) : "";
    })
    .join("");
  return `<div class="inline-figure-row">${imgs}</div>`;
}

function renderMarkdown(text, previewIndex) {
  const normalized = stripTrailingLinkDump(normalizeAnswerText(unwrapFencedMarkdownBlocks(text)));
  if (!normalized.trim()) return "";

  const blocks = normalized.split(/\n{2,}/);
  const htmlBlocks = [];
  let imageBuffer = [];

  const flushImages = () => {
    if (!imageBuffer.length) return;
    htmlBlocks.push(renderImageRowFromBlock(imageBuffer.join("\n"), previewIndex));
    imageBuffer = [];
  };

  for (const block of blocks) {
    const trimmed = block.replace(/^\n+|\n+$/g, "");
    if (!trimmed.trim()) continue;

    // Coalesce consecutive image-only blocks (common model output with blank
    // lines between figures) into one horizontal row instead of a column of <p>s.
    if (isMarkdownImageOnlyBlock(trimmed)) {
      imageBuffer.push(
        ...trimmed
          .split("\n")
          .filter((line) => line.trim()),
      );
      continue;
    }
    flushImages();

    if (isMarkdownTable(trimmed)) {
      htmlBlocks.push(renderMarkdownTable(trimmed));
      continue;
    }

    const lines = trimmed.split("\n");

    // A "## Header" line glued (no blank line) to bullets/prose right after it is common
    // model output — render the header alone, then process the rest of the block normally,
    // instead of swallowing everything into one heading tag.
    if (/^#{1,3}\s+/.test(lines[0])) {
      const level = lines[0].match(/^(#{1,3})\s+/)[1].length;
      const tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      const headingContent = lines[0].replace(/^#{1,3}\s+/, "");
      const headingHtml = `<${tag} class="answer-heading">${inlineMarkdown(headingContent, previewIndex)}</${tag}>`;
      const restLines = lines.slice(1).filter((line) => line.trim());
      if (!restLines.length) {
        htmlBlocks.push(headingHtml);
        continue;
      }
      if (restLines.every(isMarkdownImageOnlyLine)) {
        htmlBlocks.push(headingHtml + renderImageRowFromBlock(restLines.join("\n"), previewIndex));
        continue;
      }
      if (restLines.every((line) => /^\s*[-*]\s+/.test(line))) {
        htmlBlocks.push(headingHtml + renderNestedList(restLines, previewIndex));
        continue;
      }
      htmlBlocks.push(
        headingHtml +
          restLines.map((line) => `<p class="answer-line">${inlineMarkdown(line, previewIndex)}</p>`).join(""),
      );
      continue;
    }

    const isList = lines.every((line) => /^\s*[-*]\s+/.test(line) || line.trim() === "");
    if (isList && lines.some((line) => /^\s*[-*]\s+/.test(line))) {
      htmlBlocks.push(renderNestedList(lines.filter((line) => line.trim()), previewIndex));
      continue;
    }

    if (lines.length > 1 && lines.every((line) => line.trim())) {
      // Mixed block: keep prose as paragraphs, but group consecutive image-only
      // lines into a horizontal row.
      let chunk = "";
      const imgChunk = [];
      const flushImgChunk = () => {
        if (!imgChunk.length) return;
        chunk += renderImageRowFromBlock(imgChunk.join("\n"), previewIndex);
        imgChunk.length = 0;
      };
      for (const line of lines) {
        if (isMarkdownImageOnlyLine(line)) {
          imgChunk.push(line);
        } else {
          flushImgChunk();
          chunk += `<p class="answer-line">${inlineMarkdown(line, previewIndex)}</p>`;
        }
      }
      flushImgChunk();
      htmlBlocks.push(chunk);
      continue;
    }

    htmlBlocks.push(`<p class="answer-line">${inlineMarkdown(trimmed, previewIndex)}</p>`);
  }
  flushImages();

  return `<div class="answer-md">${groupAdjacentFigureButtons(htmlBlocks.join(""))}</div>`;
}

/** Wrap runs of figure-only paragraphs / bare figure buttons into a horizontal
 * `.inline-figure-row`. Catches model output that puts each `![...](url)` in its
 * own blank-line block (rendered as `<p class="answer-line">`) — the common case
 * that still looked like a vertical column. */
function groupAdjacentFigureButtons(html) {
  if (!html || !html.includes("inline-figure-btn")) return html;
  const figureOnlyP =
    /(?:<p class="answer-line">\s*)?(<button\b[^>]*class="[^"]*\binline-figure-btn\b[^"]*"[^>]*>[\s\S]*?<\/button>)\s*(?:<\/p>)?/g;
  // Collapse consecutive figure-only units into one row.
  return html.replace(
    /(?:(?:<p class="answer-line">\s*)?<button\b[^>]*class="[^"]*\binline-figure-btn\b[^"]*"[^>]*>[\s\S]*?<\/button>\s*(?:<\/p>)?\s*){2,}/g,
    (run) => {
      const buttons = [];
      let m;
      const re = new RegExp(figureOnlyP.source, "g");
      while ((m = re.exec(run)) !== null) buttons.push(m[1]);
      if (buttons.length < 2) return run;
      return `<div class="inline-figure-row">${buttons.join("")}</div>`;
    },
  );
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
  text = stripFigureReferences(text);
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
    return stash(renderInlineLink(normalizeInlineLinkLabel(label), url, previewIndex));
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

  const displayCards = collapseVideoCardsForCitations(cards);

  let html = '<details class="citations"><summary>Sources &amp; citations</summary><ul class="citation-list">';
  for (const card of displayCards) {
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

    const tag = cardTagLabel(card);

    html += '<li class="citation-item">';
    html += `<div class="citation-head"><strong>${escapeHtml(presentation.caption)}</strong>`;
    html += `<span class="source-badge">${escapeHtml(citationSourceLabel(card))}</span>`;
    if (tag) html += `<span class="tag-chip" title="${escapeAttr(tag)}">${escapeHtml(tag)}</span>`;
    html += "</div>";
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

function buildPayload(query, modeOverride, options = {}) {
  const mode = modeOverride || modeSelect.value;
  const visual = wantsVisual(query, mode) || mode === "topic_page";
  const sources = mode === "topic_page" ? TOPIC_PAGE_SOURCES : selectedSources();
  const payload = {
    query,
    mode,
    sources: sources.length ? sources : DEFAULT_SOURCES,
    max_results: Number(maxResultsInput.value) || 5,
    // Figures default ON regardless of query wording — a plain factual
    // question shouldn't need "show me a picture" phrasing to surface pics
    // that the pulled sources actually have. Explicitly visual queries and
    // topic pages just get a bigger figure budget.
    include_figures: true,
    max_figures: mode === "topic_page" ? 8 : visual ? 8 : 4,
    compact: true,
    excerpt_char_limit: 900,
    render_html: mode === "html_teaching",
  };
  if (mode === "topic_page" && options.categoryContext) {
    payload.category_context = options.categoryContext;
  }
  if (mode === "topic_page" && options.pageTag) {
    payload.page_tag = options.pageTag;
  }
  if (options.rebuild) {
    payload.rebuild = true;
  }
  return payload;
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

function renderMediaModalPayload(payload) {
  if (!payload?.previewUrl) return;
  mediaModalImg.src = payload.previewUrl;
  mediaModalImg.alt = payload.caption || "Preview";
  mediaModalCaption.textContent = payload.caption || "";

  const links = payload.modalLinks || {};
  setModalAction(mediaModalFigure, links.figure, "Open figure");
  setModalAction(mediaModalPage, links.pageImage, "Open page image");
  setModalAction(mediaModalSource, links.source, "Open source");
  setModalAction(mediaModalTimestamp, links.video, "Open timestamp");
  setModalAction(mediaModalReference, links.reference, "Open reference page");
}

function updateMediaModalNav() {
  const showNav = currentGallery.items.length > 1;
  if (mediaModalPrev) mediaModalPrev.hidden = !showNav;
  if (mediaModalNext) mediaModalNext.hidden = !showNav;
}

function showGalleryAt(index) {
  const n = currentGallery.items.length;
  if (!n) return;
  currentGallery.index = ((index % n) + n) % n;
  renderMediaModalPayload(currentGallery.items[currentGallery.index]);
  updateMediaModalNav();
}

function showPrevGallery() {
  showGalleryAt(currentGallery.index - 1);
}

function showNextGallery() {
  showGalleryAt(currentGallery.index + 1);
}

function openMediaPreview(itemsOrPayload, startIndex = 0) {
  const items = Array.isArray(itemsOrPayload) ? itemsOrPayload : [itemsOrPayload];
  currentGallery = {
    items: items.filter((item) => item?.previewUrl),
    index: startIndex,
  };
  if (!currentGallery.items.length) return;
  showGalleryAt(startIndex);
  mediaModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeMediaPreview() {
  mediaModal.classList.add("hidden");
  mediaModalImg.src = "";
  currentGallery = { items: [], index: 0 };
  updateMediaModalNav();
  document.body.classList.remove("modal-open");
}

// Tiny inline SVG placeholder — no extra network request, so it can never
// itself 404. Defensive fallback for known-bad figure families (e.g. the
// cyto_comprehensive_part_two fixed-crop bug) and for any other dead/broken
// image URL, since a reliable join key against the offline
// curriculum_figure_image_quality_flags_v0_1.jsonl sidecar was not available
// from evidence-card fields alone this session (see
// docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md, figure-quality section).
const BROKEN_IMAGE_PLACEHOLDER =
  "data:image/svg+xml;charset=UTF-8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200">' +
      '<rect width="100%" height="100%" fill="#f1f3f4"/>' +
      '<text x="50%" y="46%" dominant-baseline="middle" text-anchor="middle" ' +
      'font-family="sans-serif" font-size="14" fill="#5f6368">Image unavailable</text>' +
      '<text x="50%" y="62%" dominant-baseline="middle" text-anchor="middle" ' +
      'font-family="sans-serif" font-size="11" fill="#80868b">Known extraction defect or dead link</text>' +
      "</svg>",
  );

// Mirrors figure_quality_filter.TINY_DIM / near-black thresholds (Python unit-tested).
const TINY_IMAGE_DIM = 120;
const NEAR_BLACK_CHANNEL_MAX = 16;
const NEAR_BLACK_FRACTION_STRICT = 0.85;
const NEAR_BLACK_MEAN_LUMINANCE_MAX = 35;
const NEAR_BLACK_FRACTION_LOOSE = 0.3;

function markDefectiveImage(img, reason) {
  if (!img || img.dataset.brokenHandled) return;
  img.dataset.brokenHandled = "true";
  if (reason) img.dataset.defectReason = reason;
  img.src = BROKEN_IMAGE_PLACEHOLDER;
  img.classList.add("img-broken");
  // Hide gallery / figure chrome so solid-black stubs do not occupy a slot or
  // open a black modal. Prefer outer <figure> so figcaptions disappear too.
  // Modal <img> has none of these ancestors, so the placeholder stays visible.
  const chrome =
    img.closest("figure") ||
    img.closest(".topic-gallery-thumb, .figure-preview-btn, .citation-thumb-btn");
  if (chrome) {
    chrome.hidden = true;
    chrome.classList.add("img-defect-hidden");
  }
}

function sampleLooksNearBlack(img) {
  // naturalWidth/Height need no CORS. Canvas sampling does, and may fail for
  // cross-origin proxy URLs — tiny-dim check still catches the 90x90 stubs.
  const w = img.naturalWidth || 0;
  const h = img.naturalHeight || 0;
  if (w > 0 && h > 0 && (w < TINY_IMAGE_DIM || h < TINY_IMAGE_DIM)) {
    return "tiny_image";
  }
  try {
    const sw = Math.min(w, 64);
    const sh = Math.min(h, 64);
    if (sw < 1 || sh < 1) return null;
    const canvas = document.createElement("canvas");
    canvas.width = sw;
    canvas.height = sh;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, sw, sh);
    const data = ctx.getImageData(0, 0, sw, sh).data;
    const n = sw * sh;
    let nearBlack = 0;
    let sumL = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      sumL += 0.2126 * r + 0.7152 * g + 0.0722 * b;
      if (r < NEAR_BLACK_CHANNEL_MAX && g < NEAR_BLACK_CHANNEL_MAX && b < NEAR_BLACK_CHANNEL_MAX) {
        nearBlack += 1;
      }
    }
    const meanL = sumL / n;
    const frac = nearBlack / n;
    if (frac >= NEAR_BLACK_FRACTION_STRICT || (meanL < NEAR_BLACK_MEAN_LUMINANCE_MAX && frac >= NEAR_BLACK_FRACTION_LOOSE)) {
      return "near_black";
    }
  } catch (err) {
    /* tainted canvas / CORS — dimension check above still applies */
  }
  return null;
}

/** Delegated, capture-phase `error` listener (image `error` events don't
 * bubble, but a capturing ancestor listener still sees them) — catches every
 * broken figure/page/citation-thumbnail/modal image anywhere in the app in
 * one place, instead of wiring an `onerror` attribute into every template
 * string that renders an `<img>`. Swaps in a local placeholder so a dead URL
 * (known-bad family or otherwise) never renders an empty broken-image box.
 * `data-broken-handled` guards against a retry loop if the placeholder data
 * URI itself somehow failed to decode. */
document.addEventListener(
  "error",
  (event) => {
    const img = event.target;
    if (!img || img.tagName !== "IMG" || img.dataset.brokenHandled) return;
    markDefectiveImage(img, "load_error");
  },
  true,
);

/** HTTP 200 near-black / tiny extraction stubs never fire `error` — sample
 * after decode and hide them the same way as broken links. */
document.addEventListener(
  "load",
  (event) => {
    const img = event.target;
    if (!img || img.tagName !== "IMG" || img.dataset.brokenHandled) return;
    if ((img.getAttribute("src") || "").startsWith("data:")) return;
    const reason = sampleLooksNearBlack(img);
    if (reason) markDefectiveImage(img, reason);
  },
  true,
);

function scrubDefectiveImages(root) {
  if (!root) return;
  root.querySelectorAll("img").forEach((img) => {
    if (img.dataset.brokenHandled) return;
    if ((img.getAttribute("src") || "").startsWith("data:")) return;
    // Cached images may have already fired `load` before this HTML was bound.
    if (img.complete && img.naturalWidth > 0) {
      const reason = sampleLooksNearBlack(img);
      if (reason) markDefectiveImage(img, reason);
    }
  });
}

function bindPreviewHandlers(root) {
  scrubDefectiveImages(root);
  root.querySelectorAll("[data-preview]").forEach((el) => {
    el.addEventListener("click", (event) => {
      // Preview-aware <a> tags keep their href so ctrl/cmd/middle-click still
      // opens the raw source in a new tab; a plain click shows the rich preview.
      const isModifiedClick =
        el.tagName === "A" && (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1);
      if (isModifiedClick) return;
      // Skip thumbs already hidden as defective extraction stubs.
      if (el.hidden || el.classList.contains("img-defect-hidden")) return;
      try {
        if (el.tagName === "A") event.preventDefault();
        const payload = JSON.parse(el.dataset.preview);
        const compareCol = el.closest(".compare-column");
        // `.topic-section-body`/`.topic-key-facts` come before the narrower
        // `.topic-gallery-grid` etc. here so inline figures embedded in a
        // topic-page section (Microscopic, Gross Features, ...) become a
        // scrollable (arrow-key) gallery of every image in that section,
        // not just the ones in the same consecutive image row.
        const gallery = compareCol
          ? compareCol.querySelector(".compare-gallery-grid, .topic-gallery-grid")
          : el.closest(
              ".topic-section-body, .topic-key-facts, .topic-gallery-grid, .figures-grid, .figures-grid-prominent",
            );
        let items = [payload];
        let index = 0;
        if (gallery) {
          const siblings = [];
          gallery.querySelectorAll("[data-preview]").forEach((sib) => {
            if (sib.hidden || sib.classList.contains("img-defect-hidden")) return;
            try {
              siblings.push(JSON.parse(sib.dataset.preview));
            } catch (err) {
              /* skip malformed sibling */
            }
          });
          if (siblings.length) {
            items = siblings;
            const matchIdx = siblings.findIndex((item) => item.previewUrl === payload.previewUrl);
            index = matchIdx >= 0 ? matchIdx : 0;
          }
        }
        openMediaPreview(items, index);
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
    // Prefer ui_sources (journals retired from checkboxes). Fall back to
    // supported_sources filtered client-side for older servers.
    const raw = data.ui_sources || data.supported_sources || [];
    supportedSources = raw.filter((s) => s !== "journals");
    renderSourceCheckboxes();

    healthFlags.iterative = data.topic_page_iterative !== false;
    healthFlags.liveLiterature = data.topic_page_live_literature !== false;
    // Older servers lack these fields — treat missing iterative flag as "not this build".
    healthFlags.streamEndpoint = typeof data.topic_page_iterative === "boolean";

    const hubKey = data.secrets?.pathology_hub?.present;
    const openaiKey = data.secrets?.openai?.present;
    const backendOk = data.backend?.ok;
    healthStatus.className = "status";
    if (backendOk && hubKey) {
      healthStatus.classList.add("ok");
      const bits = [openaiKey ? "Ready" : "Ready (search-only)"];
      if (healthFlags.streamEndpoint && healthFlags.iterative) bits.push("live thinking");
      if (healthFlags.liveLiterature) bits.push("literature");
      healthStatus.textContent = bits.join(" · ");
      healthStatus.title = healthFlags.streamEndpoint
        ? "Iterative SSE build active — topic pages stream round progress."
        : "Server build may be outdated (no topic_page_iterative flag). Checkout cursor/topic-iterative-sse-layout-9231 and restart.";
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
    if (src === "journals") continue; // retired local FAISS corpus — live literature is separate
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

function setActiveView(view) {
  viewTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  browseViewEl.classList.toggle("hidden", view !== "browse");
  askViewEl.classList.toggle("hidden", view !== "ask");
}

function findCategory(categoryId) {
  return getBrowseRoots().find((r) => r.id === categoryId) || null;
}

function findSubcategory(category, subcategoryId) {
  return (category && category.subcategories.find((s) => s.id === subcategoryId)) || null;
}

function renderBrowseBreadcrumbs() {
  const parts = [
    {
      label: "Home",
      onClick: () => {
        browseFilterQuery = "";
        browseState = { level: "home" };
        renderBrowseView();
      },
    },
  ];

  const category = browseState.categoryId ? findCategory(browseState.categoryId) : null;
  if (category && browseState.level !== "home") {
    parts.push({
      label: formatDisplayLabel(category.label),
      onClick: () => {
        browseFilterQuery = "";
        browseState = { level: "category", categoryId: category.id };
        renderBrowseView();
      },
    });
  }

  const subcategory =
    category && browseState.subcategoryId ? findSubcategory(category, browseState.subcategoryId) : null;
  if (subcategory && (browseState.level === "subcategory" || browseState.level === "leaf")) {
    parts.push({
      label: formatSubcategoryLabel(subcategory.label),
      onClick: () => {
        browseFilterQuery = "";
        browseState = { level: "subcategory", categoryId: category.id, subcategoryId: subcategory.id };
        renderBrowseView();
      },
    });
  }

  if (browseState.level === "leaf" && browseState.label) {
    parts.push({ label: formatDisplayLabel(browseState.label), onClick: null });
  }

  browseBreadcrumbsEl.innerHTML = "";
  parts.forEach((part, idx) => {
    if (idx > 0) browseBreadcrumbsEl.appendChild(document.createTextNode(" \u203a "));
    if (part.onClick) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "breadcrumb-link";
      btn.textContent = part.label;
      btn.addEventListener("click", part.onClick);
      browseBreadcrumbsEl.appendChild(btn);
    } else {
      const span = document.createElement("span");
      span.className = "breadcrumb-current";
      span.textContent = part.label;
      browseBreadcrumbsEl.appendChild(span);
    }
  });
}

function compareEntityKey(entity) {
  return entity.tag || `${entity.label}::${entity.query}`;
}

function comparePayloadFromNav(navTarget) {
  const category = findCategory(navTarget.categoryId);
  const sub = findSubcategory(category, navTarget.subcategoryId);
  return {
    tag: navTarget.tag,
    label: navTarget.label,
    query: navTarget.query || navTarget.label,
    categoryId: navTarget.categoryId,
    subcategoryId: navTarget.subcategoryId,
    categoryContext: category && sub ? `${category.label} > ${sub.label}` : null,
  };
}

function comparePayloadFromLeaf(categoryId, subcategoryId, leaf) {
  const category = findCategory(categoryId);
  const sub = findSubcategory(category, subcategoryId);
  return {
    tag: leaf.tag,
    label: leaf.label,
    query: leaf.query || leaf.label,
    categoryId,
    subcategoryId,
    categoryContext: category && sub ? `${category.label} > ${sub.label}` : null,
  };
}

function isInCompareSet(entity) {
  const key = compareEntityKey(entity);
  return compareSet.some((e) => compareEntityKey(e) === key);
}

function renderCompareTray() {
  if (!compareTrayEl) return;
  const n = compareSet.length;
  compareTrayEl.classList.toggle("hidden", n === 0);
  if (compareTrayCountEl) {
    compareTrayCountEl.textContent = n === 1 ? "1 selected" : `${n} selected`;
  }
  if (compareRunBtn) compareRunBtn.disabled = n < 2;
}

function addToCompare(entity) {
  if (!entity?.label) return;
  if (isInCompareSet(entity)) return;
  if (compareSet.length >= MAX_COMPARE) {
    compareSet.shift();
  }
  compareSet.push(entity);
  renderCompareTray();
  document.querySelectorAll(".vs-btn").forEach((btn) => {
    try {
      const ent = JSON.parse(btn.dataset.compare || "{}");
      btn.classList.toggle("in-compare", isInCompareSet(ent));
    } catch (err) {
      /* ignore */
    }
  });
}

function removeFromCompare(entity) {
  const key = compareEntityKey(entity);
  compareSet = compareSet.filter((e) => compareEntityKey(e) !== key);
  renderCompareTray();
}

function clearCompareSet() {
  compareSet = [];
  renderCompareTray();
  document.querySelectorAll(".vs-btn.in-compare").forEach((btn) => btn.classList.remove("in-compare"));
}

function renderVsButton(entity, extraClass = "") {
  const payload = escapeAttr(JSON.stringify(entity));
  const active = isInCompareSet(entity) ? " in-compare" : "";
  return `<button type="button" class="vs-btn${extraClass}${active}" data-compare="${payload}" title="Add to comparison">VS</button>`;
}

function bindVsButtons(root) {
  root.querySelectorAll(".vs-btn").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      try {
        addToCompare(JSON.parse(btn.dataset.compare));
      } catch (err) {
        /* ignore */
      }
    });
  });
}

function openFlagModal(context) {
  flagContext = context;
  if (flagCommentEl) flagCommentEl.value = "";
  if (flagStatusEl) flagStatusEl.textContent = "";
  flagModal?.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeFlagModal() {
  flagModal?.classList.add("hidden");
  document.body.classList.remove("modal-open");
  flagContext = null;
}

async function submitFlag() {
  if (!flagContext || !flagCommentEl) return;
  const comment = flagCommentEl.value.trim();
  if (!comment) {
    if (flagStatusEl) flagStatusEl.textContent = "Please enter a comment.";
    return;
  }
  if (flagStatusEl) flagStatusEl.textContent = "Sending…";
  try {
    const resp = await fetch("/api/flag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tag: flagContext.tag || null,
        label: flagContext.label || "",
        query: flagContext.query || "",
        comment,
        page_kind: flagContext.page_kind || "topic_page",
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      if (flagStatusEl) flagStatusEl.textContent = data.error || "Failed to send feedback.";
      return;
    }
    if (flagStatusEl) flagStatusEl.textContent = "Thanks — feedback recorded.";
    setTimeout(closeFlagModal, 900);
  } catch (err) {
    if (flagStatusEl) flagStatusEl.textContent = String(err);
  }
}

function renderCompareColumn(column, colIndex) {
  const query = column.query || column.label || "";
  const figFilter = filterByQueryRelevance(query, column.figures || [], { maxShown: 10 });
  const shownFigures = figFilter.shown.length ? figFilter.shown : column.figures || [];
  const tabId = `compare-col-${colIndex}`;
  let html = `<div class="compare-column" data-col="${colIndex}">`;
  html += `<div class="compare-column-title">${escapeHtml(formatDisplayLabel(column.label))}</div>`;
  html += '<div class="compare-tab-bar">';
  html += `<button type="button" class="compare-tab-btn active" data-col-tab="images" data-col="${colIndex}">Images</button>`;
  html += `<button type="button" class="compare-tab-btn" data-col-tab="text" data-col="${colIndex}">Text</button>`;
  html += "</div>";
  html += `<div class="compare-col-panel" id="${tabId}-images">`;
  html += `<div class="topic-panel-title">Selected Images</div>${renderTopicGallery(shownFigures, { compareCol: colIndex })}`;
  if (figFilter.note) html += `<p class="hint">${escapeHtml(figFilter.note)}</p>`;
  html += "</div>";
  html += `<div class="compare-col-panel hidden" id="${tabId}-text">`;
  html += `<div class="topic-section-body">${renderMarkdown(column.text_summary || "", new Map())}</div>`;
  html += "</div></div>";
  return html;
}

function bindCompareColumnTabs(root) {
  root.querySelectorAll(".compare-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const col = btn.dataset.col;
      const tab = btn.dataset.colTab;
      root.querySelectorAll(`.compare-column[data-col="${col}"] .compare-tab-btn`).forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      root.querySelectorAll(`.compare-column[data-col="${col}"] .compare-col-panel`).forEach((panel) => {
        panel.classList.toggle("hidden", !panel.id.endsWith(`-${tab}`));
      });
    });
  });
}

async function loadCompareView() {
  if (compareSet.length < 2) return;
  browseContentEl.innerHTML = '<p class="hint">Generating comparison — retrieving evidence for each diagnosis…</p>';
  try {
    const resp = await fetch("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        entities: compareSet.map((e) => ({
          tag: e.tag || null,
          label: e.label,
          query: e.query || e.label,
          category_context: e.categoryContext || null,
        })),
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      browseContentEl.innerHTML = `<p class="error-text">${escapeHtml(data.error || data.comparison_error || "Compare failed")}</p>`;
      return;
    }
    let html = '<div class="compare-view-header">';
    html += `<h2 class="browse-heading">Compare Diagnoses (${data.columns.length})</h2>`;
    html += '<button type="button" class="btn-secondary" id="compare-back-btn">Back</button>';
    html += '<button type="button" class="btn-secondary" id="compare-remove-all-btn">Remove all diagnoses</button>';
    html += "</div>";
    html += '<div class="compare-columns">';
    for (let i = 0; i < data.columns.length; i += 1) {
      html += renderCompareColumn(data.columns[i], i);
    }
    html += "</div>";
    html += '<div class="compare-analysis"><h3>AI Comparison Analysis</h3>';
    if (data.comparison) {
      html += renderMarkdown(data.comparison, new Map());
    } else {
      html += `<p class="error-text">${escapeHtml(data.comparison_error || "Comparison synthesis failed")}</p>`;
    }
    html += "</div>";
    browseContentEl.innerHTML = html;
    bindPreviewHandlers(browseContentEl);
    bindCompareColumnTabs(browseContentEl);
    document.getElementById("compare-back-btn")?.addEventListener("click", () => {
      browseState = { level: "home" };
      renderBrowseView();
    });
    document.getElementById("compare-remove-all-btn")?.addEventListener("click", () => {
      clearCompareSet();
      browseState = { level: "home" };
      renderBrowseView();
    });
  } catch (err) {
    browseContentEl.innerHTML = `<p class="error-text">${escapeHtml(String(err))}</p>`;
  }
}

function renderBrowseView() {
  renderBrowseBreadcrumbs();
  if (browseState.level === "compare") {
    loadCompareView();
  } else if (browseState.level === "category") {
    renderBrowseCategory(browseState.categoryId);
  } else if (browseState.level === "subcategory") {
    renderBrowseSubcategory(browseState.categoryId, browseState.subcategoryId);
  } else if (browseState.level === "leaf") {
    loadLeafTopicPage(browseState);
  } else {
    renderBrowseHome();
  }
}

function renderBrowseHome() {
  const usingIndex = Boolean(browseIndex);
  const starterRoots = curatedFallbackRoots();
  const fullRoots = getBrowseNavRootsFull();
  const showingFull = usingIndex && browseNavMode === "full" && fullRoots;
  const roots = showingFull ? fullRoots : starterRoots;
  const starterTotal = starterRoots.reduce((sum, r) => sum + r.leaf_count, 0);
  const fullTotal = fullRoots
    ? fullRoots.reduce((sum, r) => sum + r.leaf_count, 0)
    : browseIndex?.counts?.leaves_total ?? 0;
  const leavesRaw = usingIndex ? browseIndex.counts?.leaves_total_raw : null;
  const leavesRemoved = usingIndex ? browseIndex.counts?.leaves_removed_label_dedupe : 0;

  let html = "";
  if (usingIndex) {
    html += '<div class="browse-nav-toggle" role="group" aria-label="Browse navigation mode">';
    html += `<button type="button" class="browse-nav-mode-btn${browseNavMode === "starter" ? " active" : ""}" data-browse-mode="starter">Starter topics (${starterTotal})</button>`;
    html += `<button type="button" class="browse-nav-mode-btn${browseNavMode === "full" ? " active" : ""}" data-browse-mode="full">Full index (${fullTotal})</button>`;
    html += "</div>";
  }

  if (showingFull) {
    const abpathCount = browseIndex.counts?.leaves_abpath_only;
    const whoOnlyCount = browseIndex.counts?.leaves_who_only;
    const bothCount = browseIndex.counts?.leaves_both;
    const provenanceNote =
      abpathCount != null && whoOnlyCount != null
        ? ` Built from ABPath curriculum tags (${abpathCount} ABPath, ${bothCount ?? 0} overlap, ${whoOnlyCount} WHO-only additions).`
        : "";
    const dedupeNote =
      leavesRemoved > 0 ? ` ${leavesRaw} raw tag paths collapsed to ${fullTotal} nav topics (duplicate labels per organ merged; ABPath spelling wins on overlap).` : "";
    html += `<p class="hint">WHO + ABPath browse index only — no PathOut nav tags.${provenanceNote}${dedupeNote} Cyto cytology-only entries stay when no surgical twin exists. Use search on long lists; first topic open builds live, then caches.</p>`;
    html += browseSearchBarHtml("Filter topics (e.g. adenoid cystic, LCIS, GIST)…", browseFilterQuery);
  } else if (usingIndex) {
    html += `<p class="hint">Starter browse — ${starterTotal} high-yield topics. Switch to <strong>Full index</strong> for the complete WHO + ABPath tree (${fullTotal} topics).</p>`;
  } else {
    html += '<p class="hint">Browse tag index unavailable — showing the curated starter taxonomy fallback instead. Not a claim about what is indexed.</p>';
  }

  if (showingFull && browseFilterQuery.trim()) {
    const matches = collectLeavesFromRoots(roots).filter((row) => leafMatchesBrowseFilter(row.leaf, browseFilterQuery));
    html += `<p class="hint">${matches.length} topic${matches.length === 1 ? "" : "s"} matching "${escapeHtml(browseFilterQuery.trim())}".</p>`;
    html += '<div class="chevron-list">';
    for (const row of matches.slice(0, 120)) {
      const leafPayload = escapeAttr(
        JSON.stringify({
          tag: row.leaf.tag,
          label: row.leaf.label,
          query: row.leaf.query,
          provenance: row.leaf.provenance || null,
          categoryId: row.root.id,
          subcategoryId: row.sub.id,
        }),
      );
      html += `<button type="button" class="chevron-item browse-search-hit" data-leaf="${leafPayload}"><span>${escapeHtml(row.displayLabel)} <span class="chevron-count">(${escapeHtml(formatDisplayLabel(row.root.label))})</span></span><span class="chevron">\u203a</span></button>`;
    }
    html += "</div>";
    if (matches.length > 120) {
      html += `<p class="hint">Showing first 120 matches — refine your search to narrow further.</p>`;
    }
    browseContentEl.innerHTML = html;
    browseContentEl.querySelectorAll("[data-browse-mode]").forEach((el) => {
      el.addEventListener("click", () => {
        writeBrowseNavMode(el.dataset.browseMode);
        browseFilterQuery = "";
        browseState = { level: "home" };
        renderBrowseView();
      });
    });
    bindBrowseSearchHandlers(() => renderBrowseHome());
    browseContentEl.querySelectorAll(".browse-search-hit").forEach((el) => {
      el.addEventListener("click", () => {
        const leaf = JSON.parse(el.dataset.leaf);
        browseFilterQuery = "";
        browseState = {
          level: "leaf",
          categoryId: leaf.categoryId,
          subcategoryId: leaf.subcategoryId,
          tag: leaf.tag,
          label: leaf.label,
          query: leaf.query,
          provenance: leaf.provenance || null,
        };
        renderBrowseView();
      });
    });
    return;
  }

  html += '<div class="browse-tile-grid">';
  for (const root of roots) {
    const style = rootTileStyle(root.id, root.label);
    const countLabel = usingIndex
      ? (showingFull ? `${root.leaf_count} topic tags` : `${root.leaf_count} starter topics`)
      : `${root.leaf_count} starter topics`;
    html += `<button type="button" class="browse-tile" data-category-id="${escapeAttr(root.id)}" style="background:${style.gradient}">`;
    html += `<span class="browse-tile-glyph">${escapeHtml(style.glyph)}</span>`;
    html += `<span class="browse-tile-banner"><span class="browse-tile-label">${escapeHtml(formatDisplayLabel(root.label))}</span><span class="browse-tile-count">${countLabel}</span></span>`;
    html += "</button>";
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
  browseContentEl.querySelectorAll("[data-browse-mode]").forEach((el) => {
    el.addEventListener("click", () => {
      writeBrowseNavMode(el.dataset.browseMode);
      browseFilterQuery = "";
      browseState = { level: "home" };
      renderBrowseView();
    });
  });
  if (showingFull) {
    bindBrowseSearchHandlers(() => renderBrowseHome());
  }
  browseContentEl.querySelectorAll(".browse-tile").forEach((el) => {
    el.addEventListener("click", () => {
      browseFilterQuery = "";
      browseState = { level: "category", categoryId: el.dataset.categoryId };
      renderBrowseView();
    });
  });
}

function renderBrowseCategory(categoryId) {
  const cat = findCategory(categoryId);
  if (!cat) {
    browseState = { level: "home" };
    renderBrowseView();
    return;
  }
  const showingFull = Boolean(browseIndex && browseNavMode === "full");
  let html = `<h2 class="browse-heading">${escapeHtml(formatDisplayLabel(cat.label))}</h2>`;
  html += showingFull
    ? '<p class="hint">WHO + ABPath tags for this root. Pick a subcategory, then a topic — or filter on the next screen when lists are long.</p>'
    : '<p class="hint">Starter topic list for navigation — not a claim about what is indexed. Pick a subcategory, then a specific diagnosis.</p>';
  if (showingFull) {
    html += browseSearchBarHtml(`Search within ${formatDisplayLabel(cat.label)}…`, browseFilterQuery);
  }
  const subs = (cat.subcategories || []).filter((sub) => {
    if (!browseFilterQuery.trim()) return true;
    return (sub.leaves || []).some((leaf) => leafMatchesBrowseFilter(leaf, browseFilterQuery));
  });
  if (showingFull && browseFilterQuery.trim()) {
    html += `<p class="hint">${subs.length} subcategor${subs.length === 1 ? "y" : "ies"} with matches.</p>`;
  }
  html += '<div class="chevron-list">';
  for (const sub of subs) {
    const matchCount = browseFilterQuery.trim()
      ? (sub.leaves || []).filter((leaf) => leafMatchesBrowseFilter(leaf, browseFilterQuery)).length
      : sub.leaf_count;
    html += `<button type="button" class="chevron-item" data-sub-id="${escapeAttr(sub.id)}"><span>${escapeHtml(formatSubcategoryLabel(sub.label))}${showingFull ? ` <span class="chevron-count">(${matchCount})</span>` : ""}</span><span class="chevron">\u203a</span></button>`;
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
  if (showingFull) {
    bindBrowseSearchHandlers(() => renderBrowseCategory(categoryId));
  }
  browseContentEl.querySelectorAll(".chevron-item").forEach((el) => {
    el.addEventListener("click", () => {
      browseState = { level: "subcategory", categoryId, subcategoryId: el.dataset.subId };
      renderBrowseView();
    });
  });
}

function renderBrowseSubcategory(categoryId, subcategoryId) {
  const cat = findCategory(categoryId);
  const sub = findSubcategory(cat, subcategoryId);
  if (!cat || !sub) {
    browseState = { level: "home" };
    renderBrowseView();
    return;
  }
  const showingFull = Boolean(browseIndex && browseNavMode === "full");
  const allLeaves = sub.leaves || [];
  const filteredLeaves = allLeaves.filter((leaf) => leafMatchesBrowseFilter(leaf, browseFilterQuery));
  const hasFilter = Boolean(browseFilterQuery.trim());
  const visibleLeaves = hasFilter ? filteredLeaves : filteredLeaves.slice(0, BROWSE_LEAF_PREVIEW_CAP);
  const hiddenCount = hasFilter ? 0 : Math.max(0, filteredLeaves.length - visibleLeaves.length);

  let html = `<h2 class="browse-heading">${escapeHtml(formatDisplayLabel(cat.label))} — ${escapeHtml(formatSubcategoryLabel(sub.label))}</h2>`;
  html += showingFull
    ? '<p class="hint">Pick a topic to load a grounded topic page. Long lists are capped until you search.</p>'
    : '<p class="hint">Pick a diagnosis to load a live, grounded topic page from current evidence.</p>';
  if (showingFull || allLeaves.length > BROWSE_LEAF_PREVIEW_CAP) {
    html += browseSearchBarHtml("Filter topics in this list…", browseFilterQuery);
  }
  if (hiddenCount > 0) {
    html += `<p class="hint">Showing ${visibleLeaves.length} of ${filteredLeaves.length} topics — type to search the full list.</p>`;
  } else if (hasFilter) {
    html += `<p class="hint">${visibleLeaves.length} match${visibleLeaves.length === 1 ? "" : "es"}.</p>`;
  }
  html += '<div class="chevron-list">';
  for (const leaf of visibleLeaves) {
    const displayLabel = formatDisplayLabel(leaf.label);
    const leafPayload = escapeAttr(
      JSON.stringify({ tag: leaf.tag, label: leaf.label, query: leaf.query, provenance: leaf.provenance || null }),
    );
    const compareEntity = comparePayloadFromLeaf(categoryId, subcategoryId, leaf);
    const comparePayload = escapeAttr(JSON.stringify(compareEntity));
    html += '<div class="browse-leaf-row">';
    html += `<button type="button" class="chevron-item" data-leaf="${leafPayload}"><span>${escapeHtml(displayLabel)}</span><span class="chevron">\u203a</span></button>`;
    html += `<button type="button" class="vs-btn${isInCompareSet(compareEntity) ? " in-compare" : ""}" data-compare="${comparePayload}" title="Add to comparison">VS</button>`;
    html += "</div>";
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
  if (showingFull || allLeaves.length > BROWSE_LEAF_PREVIEW_CAP) {
    bindBrowseSearchHandlers(() => renderBrowseSubcategory(categoryId, subcategoryId));
  }
  browseContentEl.querySelectorAll(".chevron-item").forEach((el) => {
    el.addEventListener("click", () => {
      const leaf = JSON.parse(el.dataset.leaf);
      browseState = {
        level: "leaf",
        categoryId,
        subcategoryId,
        tag: leaf.tag,
        label: leaf.label,
        query: leaf.query,
        provenance: leaf.provenance || null,
      };
      renderBrowseView();
    });
  });
  bindVsButtons(browseContentEl);
}

const TOPIC_PAGE_SECTION_ORDER = [
  "Key Facts",
  "Terminology",
  "Etiology/Pathogenesis",
  "Clinical Issues",
  "Imaging Features",
  "Gross Features",
  "Microscopic",
  "Ancillary Tests",
  "Molecular / Therapeutic",
  "Differential Diagnosis",
  "Key Literature",
];

function normalizeHeaderKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z]+/g, "");
}

/** Splits a topic_page answer into { headerText: content } by its own
 * "## Header" lines — separate from the general-purpose renderMarkdown,
 * but section bodies are still rendered with renderMarkdown/inlineMarkdown
 * below so nested bullets, tables, and inline previews keep working. */
function parseTopicPageSections(text) {
  const normalized = stripTrailingLinkDump(normalizeAnswerText(text || ""));
  const sections = {};
  let current = null;
  let buffer = [];
  const flush = () => {
    if (current != null) sections[current] = buffer.join("\n").trim();
    buffer = [];
  };
  for (const line of normalized.split("\n")) {
    const m = line.match(/^#{1,3}\s+(.+?)\s*$/);
    if (m) {
      flush();
      current = m[1].trim();
      continue;
    }
    if (current != null) buffer.push(line);
  }
  flush();
  return sections;
}

function findSectionContent(sections, wantedName) {
  const wanted = normalizeHeaderKey(wantedName);
  for (const key of Object.keys(sections)) {
    if (normalizeHeaderKey(key) === wanted) return sections[key];
  }
  return "";
}

const NOT_COVERED_RE =
  /^(?:[-*]\s*)?not covered in retrieved evidence\.?$/i;

function sectionHasContent(content) {
  const text = String(content || "").trim();
  if (!text) return false;
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return false;
  return !lines.every((line) => NOT_COVERED_RE.test(line));
}

function extractInlineFiguresFromMarkdown(text) {
  const figs = [];
  const re = /!\[([^\]]*)\]\((https?:[^)\s]+)\)/g;
  let match;
  while ((match = re.exec(String(text || ""))) !== null) {
    figs.push({
      caption: match[1] || "Figure",
      figure_url: match[2],
      url: match[2],
      source_kind: "inline_markdown",
    });
  }
  return figs;
}

function collectInlineFiguresFromSections(sections) {
  const out = [];
  for (const name of TOPIC_PAGE_SECTION_ORDER) {
    if (name === "Key Facts") continue;
    out.push(...extractInlineFiguresFromMarkdown(findSectionContent(sections, name)));
  }
  return out;
}

function figureGalleryUrl(fig) {
  return pickHttp(fig.figure_url) || pickHttp(fig.image_url) || pickHttp(fig.url);
}

function mergeTopicGalleryFigures(retrievedFigures, inlineFigures, lectureItems, { maxShown = 16 } = {}) {
  const merged = [];
  const seen = new Set();
  const add = (fig) => {
    const url = figureGalleryUrl(fig);
    if (!url || seen.has(url)) return;
    seen.add(url);
    merged.push(fig);
  };
  for (const fig of retrievedFigures || []) add(fig);
  for (const fig of inlineFigures || []) add(fig);
  for (const item of lectureItems || []) {
    if (!item?.previewUrl) continue;
    add({
      caption: item.caption,
      figure_url: item.previewUrl,
      url: item.previewUrl,
      source_kind: "lecture_frame",
    });
  }
  return merged.slice(0, maxShown);
}

/** Map figure modality → topic-page section that should own its gallery. */
const FIGURE_MODALITY_SECTION = {
  imaging: "Imaging Features",
  gross: "Gross Features",
  microscopic: "Microscopic",
  ihc: "Ancillary Tests",
};

/** Classify a retrieved/inline figure into imaging / gross / microscopic / ihc / other. */
function classifyFigureModality(fig) {
  const blob = [
    fig?.caption,
    fig?.title,
    fig?.alt,
    fig?.section,
    fig?.chunk_type,
    fig?.source_id,
    fig?.figure_url,
    fig?.image_url,
    fig?.url,
  ]
    .map((x) => String(x || "").toLowerCase())
    .join(" ");

  if (
    /\b(mammog|ultrasound|sonograph|\bmri\b|magnetic resonance|\bct\b|radiograph|x-?ray|pet[- ]?ct|fluoroscop|imaging|radiolog)\b/.test(
      blob,
    )
  ) {
    return "imaging";
  }
  if (/\b(gross|macroscopic|cut[- ]surface|specimen|fresh tissue|resection specimen|excised)\b/.test(blob)) {
    return "gross";
  }
  if (
    /\b(ihc|immuno[- ]?histochem|immunostain|immuno stain|her2|er\/pr|ki-?67|cd\d{1,3}|cytokeratin|stain for)\b/.test(
      blob,
    )
  ) {
    return "ihc";
  }
  if (
    /\b(h&amp;e|h&e|h\/e|histolog|microscop|photomicro|cytolog|nuclear|cytoplasm|architecture|ductal|lobular|acin)\b/.test(
      blob,
    )
  ) {
    return "microscopic";
  }
  // PathOutlines / textbook figures without a caption cue are usually micro.
  const src = String(fig?.source || "").toLowerCase();
  if (src === "pathout" || src === "textbooks" || src === "who") return "microscopic";
  return "other";
}

/**
 * Bucket figures into section galleries. Prefer the section that already
 * inlined the image in markdown; otherwise classify by caption/URL heuristics.
 */
function bucketFiguresBySection(retrievedFigures, sections) {
  const buckets = {
    "Imaging Features": [],
    "Gross Features": [],
    Microscopic: [],
    "Ancillary Tests": [],
    other: [],
  };
  const used = new Set();
  const push = (sectionKey, fig) => {
    const url = figureGalleryUrl(fig);
    if (!url || used.has(url)) return;
    used.add(url);
    buckets[sectionKey].push(fig);
  };

  for (const name of Object.keys(buckets)) {
    if (name === "other") continue;
    for (const fig of extractInlineFiguresFromMarkdown(findSectionContent(sections, name))) {
      push(name, fig);
    }
  }

  for (const fig of retrievedFigures || []) {
    const url = figureGalleryUrl(fig);
    if (!url || used.has(url)) continue;
    const modality = classifyFigureModality(fig);
    const section = FIGURE_MODALITY_SECTION[modality] || "other";
    push(section, { ...fig, _modality: modality });
  }
  return buckets;
}

function renderSectionGallery(sectionName, figures, { maxItems = 24 } = {}) {
  if (!figures || !figures.length) return "";
  const title = `${sectionName} gallery`;
  return (
    `<div class="section-gallery" data-section-gallery="${escapeAttr(sectionName)}">` +
    `<div class="section-gallery-title">${escapeHtml(title)}</div>` +
    renderTopicGallery(figures, { maxItems }) +
    "</div>"
  );
}

/** Drop markdown images from prose when a dedicated section gallery will show them. */
function stripMarkdownImages(text) {
  return String(text || "")
    .replace(/!\[[^\]]*\]\(https?:[^)\s]+\)\s*/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function lectureFramePlaceholderDataUrl(card) {
  const title = cardTitle(card).slice(0, 48);
  const ts = formatVideoTimestamp(card) || "Lecture segment";
  const tag = cardTagLabel(card);
  const tagLine = tag ? formatDisplayLabel(tag).slice(0, 56) : "";
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">' +
    '<rect width="100%" height="100%" fill="#1a1a1d"/>' +
    '<rect x="24" y="24" width="592" height="312" rx="8" fill="#2b2b30" stroke="#5f6368" stroke-width="2"/>' +
    '<text x="50%" y="42%" dominant-baseline="middle" text-anchor="middle" fill="#e8eaed" font-family="sans-serif" font-size="22" font-weight="700">' +
    escapeHtml(title) +
    "</text>" +
    '<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#9aa0a6" font-family="sans-serif" font-size="16">' +
    escapeHtml(ts) +
    "</text>" +
    (tagLine
      ? '<text x="50%" y="66%" dominant-baseline="middle" text-anchor="middle" fill="#8ab4f8" font-family="sans-serif" font-size="14">' +
        escapeHtml(tagLine) +
        "</text>"
      : "") +
    '<text x="50%" y="82%" dominant-baseline="middle" text-anchor="middle" fill="#80868b" font-family="sans-serif" font-size="12">Click for description · Open timestamp from modal</text>' +
    "</svg>";
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function lectureCardPresentation(card) {
  const figure = pickHttp(card.figure_url) || pickHttp(card.image_url) || pickHttp(card.page_image_url);
  const video = pickHttp(card.video_time_url) || pickHttp(card.video_url);
  const previewUrl = figure || lectureFramePlaceholderDataUrl(card);
  const excerpt = String(card.excerpt || card.text || "").trim();
  const ts = formatVideoTimestamp(card);
  const caption = [cardTitle(card), ts, excerpt ? excerpt.slice(0, 280) : ""].filter(Boolean).join(" — ");
  return {
    previewUrl,
    caption,
    modalLinks: {
      figure: figure || undefined,
      video,
      source: pickHttp(card.source_url),
    },
    kind: "lecture",
  };
}

function renderTopicGallery(figures, options = {}) {
  if (!figures || !figures.length) {
    return '<p class="hint">No figures returned for this query.</p>';
  }
  const gridClass =
    options.compareCol != null
      ? "topic-gallery-grid compare-gallery-grid"
      : "topic-gallery-grid";
  const gridAttrs =
    options.compareCol != null
      ? ` class="${gridClass}" data-compare-col="${options.compareCol}"`
      : ` class="${gridClass}"`;
  let html = `<div${gridAttrs}>`;
  const maxItems = options.maxItems ?? 40;
  for (const fig of figures.slice(0, maxItems)) {
    const url = pickHttp(fig.figure_url) || pickHttp(fig.image_url) || pickHttp(fig.url);
    if (!url) continue;
    const caption = fig.caption || fig.title || "Figure";
    const payload = escapeAttr(
      JSON.stringify({
        previewUrl: url,
        caption,
        modalLinks: {
          figure: url,
          pageImage: pickHttp(fig.page_image_url),
          source: pickHttp(fig.source_url),
          reference: pickHttp(fig.source_page_url),
        },
      }),
    );
    html += `<button type="button" class="topic-gallery-thumb" data-preview="${payload}"><img src="${escapeAttr(url)}" alt="${escapeAttr(caption)}" loading="lazy" /></button>`;
  }
  html += "</div>";
  return html;
}

/** Differential Diagnosis bullets look like "- **Entity Name** — detail".
 * When the leading bold entity fuzzy-matches a taxonomy leaf, render it as a
 * clickable internal nav button that loads that entity's own fresh topic
 * page; otherwise leave it as plain text (never fabricate a link). */
function renderDifferentialSection(content, previewIndex, pageContext = null) {
  const text = String(content || "").trim();
  if (!text) return '<p class="hint">Not covered in retrieved evidence.</p>';
  const ctx = pageContext || pageContextFromBrowseState();

  const items = [];
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const match = line.match(/^[-*]\s*\*\*(.+?)\*\*\s*[-\u2014:]*\s*(.*)$/);
    if (!match) {
      // A stray bare citation link (no bullet, no bold entity name) is a trailing
      // reference the model shouldn't have added here — drop it rather than
      // rendering a phantom Differential Diagnosis entry.
      const isBareLink = /^[-*]?\s*\[[^\]]+\]\(https?:[^)\s]+\)\s*$/.test(line);
      if (isBareLink) continue;
      items.push(`<li>${inlineMarkdown(line.replace(/^[-*]\s*/, ""), previewIndex)}</li>`);
      continue;
    }
    const entityName = match[1].trim();
    const rest = match[2].trim();
    const navTarget = findTaxonomyMatch(entityName, ctx);
    if (navTarget) {
      const payload = escapeAttr(JSON.stringify(navTarget));
      const compareEnt = comparePayloadFromNav(navTarget);
      items.push(
        `<li class="ddx-row"><button type="button" class="ddx-link-btn" data-ddx-nav="${payload}">${escapeHtml(formatDisplayLabel(entityName))}</button>` +
          renderVsButton(compareEnt, " vs-btn-inline") +
          (rest ? ` \u2014 ${inlineMarkdown(rest, previewIndex)}` : "") +
          "</li>",
      );
    } else {
      items.push(
        `<li><strong>${escapeHtml(formatDisplayLabel(entityName))}</strong>${rest ? ` \u2014 ${inlineMarkdown(rest, previewIndex)}` : ""}</li>`,
      );
    }
  }
  return `<ul class="answer-list ddx-list">${items.join("")}</ul>`;
}

function renderWhoCrossMentions(mentions, pageContext = null) {
  if (!mentions?.length) return "";
  const ctx = pageContext || pageContextFromBrowseState();
  const items = [];
  for (const mention of mentions) {
    const leaf = mention.matched_leaf;
    if (!leaf) continue;
    const navTarget = findTaxonomyMatch(leaf, ctx);
    const sourceEntity = mention.source_entity || "WHO";
    const sourceSection = mention.source_section || "";
    const meta = sourceSection
      ? ` <span class="who-mention-meta">(from ${escapeHtml(sourceEntity)}, ${escapeHtml(sourceSection)})</span>`
      : ` <span class="who-mention-meta">(from ${escapeHtml(sourceEntity)})</span>`;
    if (navTarget) {
      const payload = escapeAttr(JSON.stringify(navTarget));
      const compareEnt = comparePayloadFromNav(navTarget);
      items.push(
        `<li class="ddx-row"><button type="button" class="ddx-link-btn" data-ddx-nav="${payload}">${escapeHtml(formatDisplayLabel(leaf))}</button>${renderVsButton(compareEnt, " vs-btn-inline")}${meta}</li>`,
      );
    } else {
      items.push(`<li><strong>${escapeHtml(formatDisplayLabel(leaf))}</strong>${meta}</li>`);
    }
  }
  if (!items.length) return "";
  return `<div class="topic-who-mentions"><div class="topic-panel-title">Cross-referenced Entities</div><ul class="answer-list ddx-list">${items.join("")}</ul></div>`;
}

function isVideoCard(card) {
  const source = card?.source || card?._result_key || "";
  return source === "videos" || source === "lectures" || Boolean(card?.video_id);
}

function videoCardKey(card) {
  const chunk = String(card?.chunk_id || "").trim();
  if (chunk) return chunk;
  const videoId = String(card?.video_id || "").trim();
  const start = card?.start_sec ?? card?.start_time_sec;
  if (videoId && start != null) return `${videoId}::${start}`;
  // Live STRICT_CYTO_v9 docstore collapsed many lectures into one fake path-derived
  // video_id (`gcs_gs_pathology_hub_02_normalized_lectures_lecture_chunks`). Prefer
  // title for dedupe when the id looks like that blob, so distinct lectures don't
  // all collapse incorrectly if titles differ.
  const looksLikePathBlob =
    !videoId ||
    /^gcs_gs_/i.test(videoId) ||
    /lecture_chunks$/i.test(videoId) ||
    videoId.includes("/");
  if (!looksLikePathBlob) return videoId;
  const title = String(card?.title || "").trim();
  if (title) return `title:${title}`;
  return String(card?.chunk_id || videoId || "").trim();
}

function dedupeVideoCards(cards) {
  const seen = new Set();
  const result = [];
  for (const card of cards || []) {
    if (!isVideoCard(card)) continue;
    const key = videoCardKey(card);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(card);
  }
  return result;
}

/**
 * LECTURE-level identity for a video/lecture card — same video_id/title
 * fallback rules as backend `video_card_key` (pathology_backend.py), but
 * deliberately WITHOUT the chunk_id shortcut that `videoCardKey` above uses
 * first. `videoCardKey` is chunk/segment-level (each timestamped segment of
 * a lecture has its own chunk_id, so it never collapses segments of the
 * same lecture — that's intentional for `dedupeVideoCards`, which only
 * exists to drop literal duplicate chunks). Here we want the coarser
 * "which single underlying lecture is this from" identity, so that e.g. 5
 * timestamped segments of one "BST Lecture 3 SoftTissue2" video are
 * recognized as ONE lecture instead of 5. `source_id` is not usable for
 * this (documented corpus-wide-constant limitation), so identity is
 * video_id when it isn't a path-blob placeholder, else the lecture title.
 */
function videoLectureKey(card) {
  const videoId = String(card?.video_id || "").trim();
  const looksLikePathBlob =
    !videoId ||
    /^gcs_gs_/i.test(videoId) ||
    /lecture_chunks$/i.test(videoId) ||
    videoId.includes("/");
  if (!looksLikePathBlob) return videoId;
  const title = String(card?.title || "").trim();
  if (title) return `title:${title}`;
  const chunk = String(card?.chunk_id || "").trim();
  return videoId || chunk || null;
}

function videoSegmentDurationSec(card) {
  const start = card?.start_sec ?? card?.start_time_sec;
  const end = card?.end_sec ?? card?.end_time_sec;
  if (typeof start === "number" && typeof end === "number" && end > start) {
    return end - start;
  }
  return 0;
}

/**
 * Collapse a list of already-relevance-sorted `{ item, score }` rows down to
 * one row per distinct lecture (via `videoLectureKey`), keeping the single
 * "best" row per lecture. Per the user's own "best/longest match" wording:
 * relevance score is the primary tiebreak (it already governs display order
 * everywhere else on the topic page), and segment duration (end - start) is
 * the secondary tiebreak when scores are equal. Distinct lectures are never
 * dropped here — only redundant same-lecture segments are — so a topic with
 * N genuinely different lectures still surfaces up to N entries.
 */
function bestVideoCardPerLecture(rows) {
  const winners = new Map();
  const order = [];
  for (const row of rows || []) {
    const key = videoLectureKey(row.item) || `chunk:${row.item?.chunk_id || order.length}`;
    const current = winners.get(key);
    if (!current) {
      winners.set(key, row);
      order.push(key);
      continue;
    }
    const currentDuration = videoSegmentDurationSec(current.item);
    const candidateDuration = videoSegmentDurationSec(row.item);
    if (row.score > current.score || (row.score === current.score && candidateDuration > currentDuration)) {
      winners.set(key, row);
    }
  }
  return order.map((key) => winners.get(key).item);
}

function collapseVideoCardsForCitations(cards) {
  const videoSeen = new Set();
  return (cards || []).filter((card) => {
    if (!isVideoCard(card)) return true;
    const key = videoCardKey(card);
    if (!key || videoSeen.has(key)) return false;
    videoSeen.add(key);
    return true;
  });
}

function formatVideoTimestamp(card) {
  const start = card.start_sec ?? card.start_time_sec;
  const end = card.end_sec ?? card.end_time_sec;
  if (typeof start === "number" && typeof end === "number") {
    return `${formatVideoSec(start)}–${formatVideoSec(end)}`;
  }
  if (typeof start === "number") return `at ${formatVideoSec(start)}`;
  return "";
}

function formatVideoSec(seconds) {
  const m = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function renderTopicLectureGallery(cards) {
  const videos = dedupeVideoCards(cards);
  if (!videos.length) return "";
  let html =
    '<div class="topic-videos"><div class="topic-panel-title">Lecture segments</div><div class="topic-lecture-gallery">';
  for (const card of videos) {
    const presentation = lectureCardPresentation(card);
    if (!presentation.previewUrl) continue;
    const payload = escapeAttr(JSON.stringify(presentation));
    const label = cardTitle(card);
    html +=
      `<button type="button" class="topic-lecture-thumb" data-preview="${payload}">` +
      `<img src="${escapeAttr(presentation.previewUrl)}" alt="${escapeAttr(label)}" loading="lazy" />` +
      `<span class="topic-lecture-thumb-caption">${escapeHtml(label)}</span>` +
      (formatVideoTimestamp(card)
        ? `<span class="topic-lecture-thumb-ts">${escapeHtml(formatVideoTimestamp(card))}</span>`
        : "") +
      "</button>";
  }
  html += "</div></div>";
  return html;
}

/** Text/link strip for lecture cards (honest when video_url is null). */
function renderTopicVideos(cards) {
  const videos = dedupeVideoCards(cards);
  if (!videos.length) return "";
  let html = '<div class="topic-videos"><div class="topic-panel-title">Videos</div><ul class="topic-video-list">';
  for (const card of videos) {
    const title = cardTitle(card);
    const url = pickHttp(card.video_time_url) || pickHttp(card.video_url);
    const ts = formatVideoTimestamp(card);
    html += '<li class="topic-video-item">';
    if (url) {
      html += `<a class="topic-video-link" href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>`;
    } else {
      html += `<span class="topic-video-title">${escapeHtml(title)}</span>`;
      html += '<span class="topic-video-unavailable"> — timestamp link not available</span>';
    }
    if (ts) html += `<span class="topic-video-ts">${escapeHtml(ts)}</span>`;
    html += "</li>";
  }
  html += "</ul></div>";
  return html;
}

function renderTopicPage(sections, previewIndex, figures, whoCrossMentions, videoCards, pageContext = null) {
  const keyFacts = findSectionContent(sections, "Key Facts");
  const ctx = pageContext || pageContextFromBrowseState();
  // figures = retrieved pool; bucket into Imaging / Gross / Micro / IHC galleries
  // instead of one dump "Selected Images" box beside Key Facts.
  const buckets = bucketFiguresBySection(figures || [], sections);
  const gallerySections = new Set([
    "Imaging Features",
    "Gross Features",
    "Microscopic",
    "Ancillary Tests",
  ]);

  let html = '<div class="topic-page">';
  if (sectionHasContent(keyFacts)) {
    html += '<div class="topic-page-top topic-page-top-facts-only">';
    html += `<div class="topic-key-facts"><div class="topic-panel-title">Key Facts</div>${renderMarkdown(keyFacts, previewIndex)}</div>`;
    html += "</div>";
  }

  // Frame thumbs when available; always keep the honest link/unavailable list.
  html += renderTopicLectureGallery(videoCards);
  html += renderTopicVideos(videoCards);

  html += renderWhoCrossMentions(whoCrossMentions, ctx);

  html += '<div class="topic-sections">';
  for (const name of TOPIC_PAGE_SECTION_ORDER) {
    if (name === "Key Facts") continue;
    const content = findSectionContent(sections, name);
    const sectionFigs = gallerySections.has(name) ? buckets[name] || [] : [];
    if (!sectionHasContent(content) && !sectionFigs.length) continue;
    html += `<div class="topic-section" data-topic-section="${escapeAttr(name)}">`;
    html += `<div class="topic-section-header">${escapeHtml(name.toUpperCase())}</div>`;
    html += '<div class="topic-section-body">';
    if (sectionHasContent(content)) {
      if (name === "Differential Diagnosis") {
        html += renderDifferentialSection(content, previewIndex, ctx);
      } else {
        // Prefer one gallery under the section over duplicating the same
        // images as both inline markdown thumbs and a gallery grid.
        const prose = sectionFigs.length ? stripMarkdownImages(content) : content;
        if (sectionHasContent(prose)) {
          html += renderMarkdown(prose, previewIndex);
        }
      }
    } else if (sectionFigs.length) {
      html +=
        '<p class="hint">No prose for this section in the synthesized page — showing figures matched from retrieved evidence.</p>';
    }
    if (sectionFigs.length) {
      html += renderSectionGallery(name, sectionFigs);
    }
    html += "</div></div>";
  }
  if (buckets.other.length) {
    html += '<div class="topic-section" data-topic-section="Additional Images">';
    html += '<div class="topic-section-header">ADDITIONAL IMAGES</div>';
    html += '<div class="topic-section-body">';
    html +=
      '<p class="hint">Figures that could not be confidently placed under Imaging, Gross, Microscopic, or Ancillary Tests.</p>';
    html += renderSectionGallery("Additional images", buckets.other);
    html += "</div></div>";
  }
  html += "</div></div>";
  return html;
}

function renderDebugBlock(data) {
  if (!debugToggle.checked || !data.debug) return "";
  let html = `<details class="debug-block"><summary>Debug</summary><pre>${escapeHtml(JSON.stringify(data.debug, null, 2))}</pre></details>`;
  if (data.evidence?.source_status) {
    html += `<details class="debug-block"><summary>source_status</summary><pre>${escapeHtml(JSON.stringify(data.evidence.source_status, null, 2))}</pre></details>`;
  }
  return html;
}

function countItemsBySource(items) {
  const counts = {};
  for (const item of items || []) {
    const src = String(item?.source || "unknown").toLowerCase();
    counts[src] = (counts[src] || 0) + 1;
  }
  return counts;
}

function formatSourceCountLabel(sourceKey, count) {
  const label = SOURCE_LABELS[sourceKey] || sourceKey;
  return `${label} ${count}`;
}

/** Always-visible retrieval breakdown for topic pages (works on cache hits too). */
function renderTopicSourceSummary(data, entryMeta = null) {
  const cardCounts = countItemsBySource(data.cards || []);
  const figureCounts = countItemsBySource(data.figures || []);
  const parts = Object.entries(cardCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([src, n]) => formatSourceCountLabel(src, n));
  if (!parts.length) {
    return '<p class="hint topic-source-summary">No evidence cards on this page — try Rebuild.</p>';
  }

  const debug = data?.debug;
  const pageRoot = debug?.page_root || (entryMeta?.tag?.includes("::") ? entryMeta.tag.split("::", 1)[0] : null);
  let html = '<div class="topic-source-summary">';
  html += `<p class="hint"><strong>Evidence used:</strong> ${escapeHtml(parts.join(" · "))}`;
  const figTotal = (data.figures || []).length;
  if (figTotal) {
    html += ` · ${figTotal} figure${figTotal === 1 ? "" : "s"}`;
  }
  const litCount =
    (data.literature || []).length ||
    (data.cards || []).filter((c) => (c.source || "") === "literature").length;
  if (litCount) {
    html += ` · <strong>${litCount} live literature</strong> (Elsevier/PubMed/OncoKB)`;
  } else if (data.debug && data.debug.live_literature_enabled === false) {
    html += " · live literature off";
  } else if (data.debug && data.mode === "topic_page") {
    html += " · live literature: none returned";
  }
  html += ".</p>";

  if (pageRoot) {
    const narrow = debug?.root_narrow_enabled;
    const before = debug?.cards_before_root_filter;
    const after = debug?.cards_after_root_filter;
    if (narrow === true && typeof before === "number" && typeof after === "number" && before !== after) {
      html += `<p class="hint">Organ filter <strong>${escapeHtml(formatDisplayLabel(pageRoot))}</strong>: ${after} cards kept (${before - after} off-root textbooks/pathout/videos dropped; WHO kept).</p>`;
    } else if (narrow === true) {
      html += `<p class="hint">Organ filter <strong>${escapeHtml(formatDisplayLabel(pageRoot))}</strong> active for textbooks, Pathoutlines, and lecture segments.</p>`;
    }
  }

  if (debug?.iterative && Array.isArray(debug.round_summaries) && debug.round_summaries.length) {
    const rounds = debug.round_summaries
      .map((r) => {
        const bits = [`R${r.round} ${r.label || ""}`.trim()];
        if (typeof r.cards === "number") bits.push(`${r.cards} cards`);
        if (typeof r.literature_total === "number") bits.push(`${r.literature_total} lit`);
        if (typeof r.cards_added === "number" && r.cards_added) bits.push(`+${r.cards_added}`);
        return bits.join(" · ");
      })
      .join(" → ");
    html += `<p class="hint"><strong>Iterative retrieval:</strong> ${escapeHtml(rounds)}</p>`;
  }

  if (debug?.cards_by_source_before_cap && debug?.cards_by_source_after_cap) {
    const before = Object.entries(debug.cards_by_source_before_cap)
      .map(([src, n]) => `${SOURCE_LABELS[src] || src} ${n}`)
      .join(", ");
    const after = Object.entries(debug.cards_by_source_after_cap)
      .map(([src, n]) => `${SOURCE_LABELS[src] || src} ${n}`)
      .join(", ");
    if (before !== after) {
      html += `<p class="hint">Retrieved ${escapeHtml(before)} → capped to ${escapeHtml(after)} for synthesis.</p>`;
    }
  }

  const status = data.evidence?.source_status;
  if (status && typeof status === "object") {
    const bad = Object.entries(status).filter(([, v]) => v && v !== "ok" && v !== "not_requested");
    if (bad.length) {
      html += `<p class="hint">Source status: ${escapeHtml(bad.map(([k, v]) => `${SOURCE_LABELS[k] || k}: ${v}`).join("; "))}</p>`;
    }
  }

  const lectureCards = (data.cards || []).filter(isVideoCard);
  const withFrames = lectureCards.filter((c) => pickHttp(c.figure_url) || pickHttp(c.image_url)).length;
  if (lectureCards.length && !withFrames) {
    html += '<p class="hint">Lecture hits have timestamps but the API is not returning slide frame URLs yet — thumbnails show placeholders until backend maps <code>image_path</code> from the lecture index.</p>';
  }

  html += '<p class="hint">Topic pages always query all sources (sidebar checkboxes do not apply). Per-source minimum is automatic; user-controlled source weighting is not built yet — use Ask/search for a single-source deep dive.</p>';
  html += "</div>";
  return html;
}

function topicPageFanoutHint(data) {
  const debug = data?.debug;
  if (!debug?.multi_query) return "";
  const variantCount = debug.query_variants?.length || "?";
  const callCount = debug.call_count || "?";
  const capped = debug.cards_capped;
  const capLimit = debug.cards_cap_limit;
  let text = debug.iterative
    ? `Iterative retrieval across ${debug.iterative_rounds || "?"} rounds · ${variantCount} hub queries (${callCount} source calls).`
    : `Retrieval used ${variantCount} parallel query variants (${callCount} total source calls) for broader coverage.`;
  if (typeof capped === "number" && typeof capLimit === "number") {
    text += ` ${capped} unique cards (cap ${capLimit}) sent to synthesis.`;
  }
  if (typeof debug.literature_count === "number") {
    text += ` ${debug.literature_count} live literature cards.`;
  }
  return `<p class="hint topic-fanout-hint">${escapeHtml(text)}</p>`;
}

function renderTopicExportBar() {
  return (
    '<div class="topic-export-bar">' +
    '<button type="button" class="btn-secondary topic-export-btn">Export page as JSON</button>' +
    '<p class="hint">Full raw response (answer, cards, figures, literature, debug).</p>' +
    "</div>"
  );
}

/** Build HTML for the live SSE thinking / progress panel. */
function renderThinkingPanel(steps, { live = false } = {}) {
  const liveClass = live ? " thinking-live" : "";
  if (!steps?.length) {
    return (
      `<div class="thinking-panel${liveClass}" data-thinking-panel>` +
      '<div class="thinking-panel-title">Working…</div>' +
      '<ul class="thinking-steps"></ul></div>'
    );
  }
  let html =
    `<div class="thinking-panel${liveClass}" data-thinking-panel>` +
    '<div class="thinking-panel-title">Building evidence</div><ul class="thinking-steps">';
  for (const step of steps) {
    const status = step.status || "running";
    html += `<li class="thinking-step ${escapeAttr(status)}">`;
    html += '<span class="thinking-mark" aria-hidden="true"></span>';
    html += "<div>";
    html += `<div class="thinking-label">${escapeHtml(step.label || step.phase || "…")}</div>`;
    if (step.detail) {
      html += `<div class="thinking-detail">${escapeHtml(step.detail)}</div>`;
    }
    if (Array.isArray(step.queries) && step.queries.length) {
      html += '<ul class="thinking-queries">';
      for (const q of step.queries.slice(0, 6)) {
        html += `<li>${escapeHtml(q)}</li>`;
      }
      html += "</ul>";
    }
    html += "</div></li>";
  }
  html += "</ul></div>";
  return html;
}

function thinkingStepKey(ev) {
  if (ev.phase === "round" || ev.phase === "literature") {
    return `${ev.phase}-${ev.round || 0}-${ev.label || ""}`;
  }
  return `${ev.phase || "step"}-${ev.label || ""}`;
}

function upsertThinkingStep(steps, ev) {
  const key = thinkingStepKey(ev);
  const next = {
    key,
    phase: ev.phase,
    round: ev.round,
    status: ev.status || "running",
    label: ev.label || ev.phase || "Working…",
    detail: ev.detail || "",
    queries: ev.queries || null,
  };
  const idx = steps.findIndex((s) => s.key === key);
  if (idx >= 0) {
    steps[idx] = { ...steps[idx], ...next };
  } else {
    steps.push(next);
  }
  return steps;
}

function yieldToBrowserPaint() {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => resolve());
    } else {
      setTimeout(resolve, 0);
    }
  });
}

/**
 * Real SSE client for POST /api/chat/stream — yields progress events live
 * (not a post-hoc replay). Returns the final `result` payload.
 *
 * Awaits onProgress and yields to the browser between events so the thinking
 * panel can paint even when chunks arrive in a burst.
 */
async function streamChat(payload, { onProgress } = {}) {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const errBody = await resp.json();
      detail = errBody.error || detail;
    } catch (_) {
      /* ignore */
    }
    if (resp.status === 404) {
      detail =
        "No /api/chat/stream on this server — checkout cursor/topic-iterative-sse-layout-9231, restart ./scripts/run_local.sh, hard-refresh.";
    }
    throw new Error(detail);
  }
  if (!resp.body || typeof resp.body.getReader !== "function") {
    // Extremely old environments — fall back to blocking chat.
    const fallback = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return fallback.json();
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let resultPayload = null;

  const flushBlock = async (block) => {
    const lines = block.split(/\r?\n/);
    let eventName = "message";
    const dataLines = [];
    for (const line of lines) {
      if (!line || line.startsWith(":")) continue; // SSE comments / flush pads
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    let data;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch (_) {
      return;
    }
    if (eventName === "progress") {
      if (onProgress) await onProgress(data);
      await yieldToBrowserPaint();
    } else if (eventName === "result") {
      resultPayload = data;
    } else if (eventName === "error") {
      throw new Error(data.error || "Stream error");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    // Split on blank line; tolerate padded comment frames between events.
    while ((sep = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const block = buffer.slice(0, sep);
      const match = buffer.slice(sep).match(/^\r?\n\r?\n/);
      buffer = buffer.slice(sep + (match ? match[0].length : 2));
      if (block.trim()) await flushBlock(block);
    }
  }
  if (buffer.trim()) await flushBlock(buffer);
  if (!resultPayload) {
    throw new Error("Stream ended without a result event.");
  }
  return resultPayload;
}

/** Splits a raw "Root::Sub::Leaf" tag into human-readable breadcrumb
 * segments, resolving the root segment against the loaded Browse taxonomy's
 * display label when possible (e.g. tag root "HN" -> taxonomy root label)
 * so the page shows where this sits in the curriculum, not just a raw tag
 * string with literal "::" separators. */
function tagBreadcrumbSegments(tag) {
  const parts = String(tag || "")
    .split("::")
    .map((p) => p.trim())
    .filter(Boolean);
  if (!parts.length) return [];
  const rootSlug = parts[0]
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const matchedRoot = (getBrowseRoots() || []).find((r) => r.id === rootSlug);
  return parts.map((part, i) => {
    if (i === 0) return matchedRoot ? formatDisplayLabel(matchedRoot.label) : formatDisplayLabel(part);
    if (i === parts.length - 1) return formatDisplayLabel(part);
    return formatSubcategoryLabel(part);
  });
}

function browsePathSegments(entryMeta) {
  const segments = [];
  const category = entryMeta?.categoryId ? findCategory(entryMeta.categoryId) : null;
  const subcategory = category ? findSubcategory(category, entryMeta.subcategoryId) : null;
  if (category?.label) segments.push(formatDisplayLabel(category.label));
  if (subcategory?.label) segments.push(formatSubcategoryLabel(subcategory.label));
  const leafLabel = entryMeta?.label || entryMeta?.query;
  if (leafLabel) segments.push(formatDisplayLabel(leafLabel));
  return segments;
}

/** Board / hierarchical curriculum panel — always shown on topic pages when
 * we have either a formal ABPath/WHO tag or a Browse path. */
function renderEntryTagsHeader(tag, provenance, entryMeta = null) {
  const tagSegments = tag ? tagBreadcrumbSegments(tag) : [];
  const pathSegments = browsePathSegments(entryMeta || {});
  const segments = tagSegments.length ? tagSegments : pathSegments;
  if (!segments.length && !tag && !provenance) return "";

  const provenanceLabel =
    formatNavProvenanceLabel(provenance) ||
    (tag ? null : "Browse path only — open from Full index for ABPath board tags");

  let html = '<div class="topic-tags-header curriculum-board-panel">';
  html += '<div class="curriculum-board-title">Board / curriculum map</div>';
  html += '<div class="curriculum-board-row">';
  html += '<span class="topic-tags-label">Hierarchy:</span>';
  html += `<span class="tag-chip topic-entry-tag" title="${escapeAttr(tag || segments.join(" › "))}">`;
  html += segments
    .map((seg) => escapeHtml(seg))
    .join(' <span class="tag-breadcrumb-sep">\u203a</span> ');
  html += "</span>";
  if (provenanceLabel) {
    html += `<span class="source-badge provenance-badge">${escapeHtml(provenanceLabel)}</span>`;
  }
  html += "</div>";
  if (tag) {
    html += `<div class="curriculum-board-tagline"><span class="topic-tags-label">Tag path:</span> <code class="curriculum-tag-path">${escapeHtml(tag)}</code></div>`;
  } else {
    html +=
      '<p class="hint curriculum-board-hint">No ABPath/WHO tag on this leaf yet — switch Browse to <strong>Full index</strong> (or Rebuild after pull) to attach board curricular tags like <code>Breast::Neoplastic::…::Lobular_Carcinoma_In_Situ_LCIS</code>.</p>';
  }
  html += "</div>";
  return html;
}

function renderLiteratureProviderStatus(debug) {
  const providers = debug?.literature_providers;
  if (!providers || typeof providers !== "object") return "";
  const parts = [];
  for (const [name, meta] of Object.entries(providers)) {
    if (!meta || typeof meta !== "object") continue;
    const label =
      name === "scopus" || name.includes("scopus")
        ? "Elsevier Scopus"
        : name === "pubmed" || name.includes("pubmed")
          ? "PubMed"
          : name === "oncokb" || name.includes("oncokb")
            ? "OncoKB"
            : name;
    if (meta.ok) {
      const n = typeof meta.returned === "number" ? meta.returned : "?";
      const total = meta.total != null ? ` / ${meta.total} total` : "";
      const skipped = meta.skipped ? ` (${meta.skipped})` : "";
      parts.push(`${label}: ok (${n}${total})${skipped}`);
    } else {
      parts.push(`${label}: failed (${meta.error || "unknown"})`);
    }
  }
  const warnings = Array.isArray(debug?.literature_warnings) ? debug.literature_warnings : [];
  if (!parts.length && !warnings.length) return "";
  let html = '<div class="literature-status">';
  if (parts.length) {
    html += `<p class="hint"><strong>Literature APIs:</strong> ${escapeHtml(parts.join(" · "))}</p>`;
  }
  if (warnings.length) {
    html += `<p class="hint literature-warning">${escapeHtml(warnings.join("; "))}</p>`;
  }
  html += "</div>";
  return html;
}

function renderLiteratureStrip(cards, debug = null) {
  const lit =
    (cards || []).filter((c) => (c.source || "").toLowerCase() === "literature") ||
    [];
  const statusHtml = renderLiteratureProviderStatus(debug);
  if (!lit.length) {
    if (!statusHtml) return "";
    return (
      '<div class="literature-strip"><div class="topic-panel-title">Live literature (Elsevier / PubMed / OncoKB)</div>' +
      statusHtml +
      '<p class="hint">No literature cards returned for this page.</p></div>'
    );
  }
  let html =
    '<div class="literature-strip"><div class="topic-panel-title">Live literature (Elsevier / PubMed / OncoKB)</div>';
  html += statusHtml;
  html += '<ul class="literature-list">';
  for (const card of lit.slice(0, 10)) {
    const title = card.title || "Untitled";
    const journal = card.journal || card.source_name || "";
    const year = card.year || "";
    const mode = card.retrieval_mode || "";
    const url = card.source_url || card.url || (card.doi ? `https://doi.org/${card.doi}` : "");
    const snip = (card.excerpt || card.text || "").replace(/\s+/g, " ").trim().slice(0, 220);
    const link = url
      ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>`
      : escapeHtml(title);
    html += `<li><div class="literature-title">${link}</div>`;
    html += `<div class="literature-meta">${escapeHtml([journal, year, mode].filter(Boolean).join(" · "))}</div>`;
    if (snip) html += `<div class="literature-snip">${escapeHtml(snip)}${snip.length >= 220 ? "…" : ""}</div>`;
    html += "</li>";
  }
  html += "</ul></div>";
  return html;
}

function renderTopicPageResult(data, query, entryMeta = null) {
  // Display caps mirror the actual backend retrieval caps (TOPIC_PAGE_MAX_CARDS=120,
  // TOPIC_PAGE_MAX_FIGURES=40 in pathology_backend.py) — these used to be
  // much smaller (20/16) than what was actually retrieved and sent to
  // synthesis, so the page looked far shallower than the real evidence base.
  const cardFilter = filterByQueryRelevance(query, data.cards || [], { maxShown: 80 });
  const sortedCards = cardFilter.shown.length ? cardFilter.shown : data.cards || [];
  const literatureCards = data.literature || sortedCards.filter((c) => (c.source || "") === "literature");
  const videoFilter = filterVideoCardsByRelevance(query, sortedCards, { maxShown: 6 });
  const lectureCards = videoFilter.shown;
  const figFilter = filterByQueryRelevance(query, data.figures || [], { maxShown: 40 });
  const shownFigures = figFilter.shown.length ? figFilter.shown : data.figures || [];
  const sections = parseTopicPageSections(data.answer || "");
  const inlineFigures = collectInlineFiguresFromSections(sections);
  // Pass retrieved figures (plus any inline-only URLs) into section bucketing —
  // renderTopicPage places them under Imaging / Gross / Micro / Ancillary galleries.
  const sectionFigurePool = mergeTopicGalleryFigures(shownFigures, inlineFigures, [], { maxShown: 40 });
  const previewIndex = buildUrlPreviewIndex(data.cards || [], [...shownFigures, ...inlineFigures]);
  for (const card of lectureCards) {
    const presentation = lectureCardPresentation(card);
    if (presentation.previewUrl && !previewIndex.has(presentation.previewUrl)) {
      previewIndex.set(presentation.previewUrl, presentation);
    }
  }
  const pageContext = pageContextFromEntryMeta(entryMeta);
  const tag = entryMeta?.tag || null;
  const provenance = entryMeta?.provenance || null;

  // Board/curriculum hierarchy at the top (ABPath/WHO tag path when known).
  let html = renderEntryTagsHeader(tag, provenance, entryMeta);
  html += renderTopicPage(
    sections,
    previewIndex,
    sectionFigurePool,
    data.who_cross_mentions || [],
    lectureCards,
    pageContext,
  );
  html += renderLiteratureStrip(literatureCards, data.debug || null);
  if (figFilter.note) html += `<p class="hint">${escapeHtml(figFilter.note)}</p>`;
  if (videoFilter.note) html += `<p class="hint">${escapeHtml(videoFilter.note)}</p>`;
  if (cardFilter.note) html += `<p class="hint">${escapeHtml(cardFilter.note)}</p>`;
  html += renderCitations(sortedCards);
  html += renderTopicSourceSummary(data, entryMeta);
  html += topicPageFanoutHint(data);
  html += renderDebugBlock(data);
  html += renderTopicExportBar();
  return html;
}

function bindDdxLinks(root) {
  root.querySelectorAll("[data-ddx-nav]").forEach((el) => {
    el.addEventListener("click", () => {
      try {
        const nav = JSON.parse(el.dataset.ddxNav);
        browseState = {
          level: "leaf",
          categoryId: nav.categoryId,
          subcategoryId: nav.subcategoryId,
          tag: nav.tag,
          label: nav.label,
          query: nav.query,
        };
        setActiveView("browse");
        renderBrowseView();
      } catch (err) {
        /* ignore malformed nav payload */
      }
    });
  });
}

/** Read-only lookup of a cached topic page (on-demand cache or legacy pilot). */
async function fetchCachedTopicPage(tag) {
  if (!tag) return null;
  try {
    const resp = await fetch(`/api/topic_prebuild?tag=${encodeURIComponent(tag)}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    if (!data || !data.found || !data.ok || !data.answer_markdown) return null;
    return data;
  } catch (err) {
    return null;
  }
}

function topicPageCacheHint(data, cachedMeta) {
  if (data?.cache_hit || cachedMeta) {
    const when = data?.cached_at || cachedMeta?.generated_at || "";
    const src = data?.cache_source || cachedMeta?.cache_source || "cache";
    const model = data?.model || cachedMeta?.model || "";
    const parts = ["Cached topic page — instant reuse from a prior open."];
    if (when) parts.push(`Saved ${when}.`);
    if (model) parts.push(`Model: ${model}.`);
    if (src === "pilot_prebuild") parts.push("(legacy pilot prebuild)");
    parts.push("Use Rebuild for a fresh live query.");
    return `<p class="hint topic-cache-hint">${escapeHtml(parts.join(" "))}</p>`;
  }
  if (data?.cache_saved) {
    return `<p class="hint topic-cache-hint">Saved this page for the next visitor.</p>`;
  }
  return "";
}

function bindTopicPageChrome(root, leafRef, displayLabel, query) {
  root.querySelector(".flag-page-btn")?.addEventListener("click", () => {
    openFlagModal({
      tag: leafRef.tag,
      label: displayLabel,
      query,
      page_kind: "topic_page",
    });
  });
  root.querySelector(".rebuild-page-btn")?.addEventListener("click", () => {
    loadLeafTopicPage(leafRef, { rebuild: true });
  });
  root.querySelectorAll(".topic-export-btn").forEach((btn) => {
    btn.addEventListener("click", exportCurrentPageAsJson);
  });
  bindPreviewHandlers(root);
  bindDdxLinks(root);
  bindVsButtons(root);
}

function renderTopicPageShell(leafRef, displayLabel, query, { bodyHtml = "", thinkingHtml = "" } = {}) {
  const compareEnt = comparePayloadFromLeaf(leafRef.categoryId, leafRef.subcategoryId, {
    tag: leafRef.tag,
    label: leafRef.label,
    query,
  });
  let html = '<div class="topic-page-actions">';
  html += `<button type="button" class="btn-secondary flag-page-btn">Flag</button>`;
  if (leafRef.tag) {
    html += `<button type="button" class="btn-secondary rebuild-page-btn">Rebuild</button>`;
  }
  html += renderVsButton(compareEnt);
  html += "</div>";
  html += thinkingHtml;
  html += bodyHtml;
  return html;
}

/** Loads a Browse leaf's topic page via SSE so round progress is visible.
 * Skips the silent prebuild cache when iterative retrieval is on (otherwise
 * cache hits hide all thinking). Rebuild always forces a live stream. */
async function loadLeafTopicPage(leafRefIn, { rebuild = false } = {}) {
  // Attach ABPath/WHO hierarchical tag when a starter leaf had tag:null.
  const leafRef = resolveBoardMappedLeaf(leafRefIn) || leafRefIn;
  // Keep Browse state in sync so breadcrumbs / rebuild / export see the tag.
  if (leafRef.tag && browseState?.level === "leaf") {
    browseState = {
      ...browseState,
      tag: leafRef.tag,
      provenance: leafRef.provenance || browseState.provenance || null,
      categoryId: leafRef.categoryId || browseState.categoryId || null,
      subcategoryId: leafRef.subcategoryId || browseState.subcategoryId || null,
    };
  }
  const seq = ++browseRequestSeq;
  const displayLabel = formatDisplayLabel(leafRef.label || leafRef.query);
  browseContentEl.innerHTML = renderTopicPageShell(leafRef, displayLabel, leafRef.query || displayLabel, {
    thinkingHtml: renderThinkingPanel(
      [{ status: "running", label: "Starting live retrieval…", detail: displayLabel }],
      { live: true },
    ),
  });
  bindTopicPageChrome(browseContentEl, leafRef, displayLabel, leafRef.query || displayLabel);

  const category = findCategory(leafRef.categoryId);
  const subcategory = category ? findSubcategory(category, leafRef.subcategoryId) : null;
  const categoryContext =
    category && subcategory ? `${category.label} > ${subcategory.label}` : category?.label || null;
  const query = leafRef.query || displayLabel;

  try {
    // Silent cache skips thinking entirely — only use it when iterative/SSE
    // is off (older server) and the user did not ask to Rebuild.
    let cachedMeta = null;
    const allowCache = !rebuild && !healthFlags.iterative && Boolean(leafRef.tag);
    if (allowCache) {
      cachedMeta = await fetchCachedTopicPage(leafRef.tag);
    }
    if (seq !== browseRequestSeq) return;

    let data;
    let steps = [];
    if (cachedMeta && allowCache) {
      data = {
        ok: true,
        mode: "topic_page",
        answer: cachedMeta.answer_markdown,
        cards: cachedMeta.cards || [],
        figures: cachedMeta.figures || [],
        literature: (cachedMeta.cards || []).filter((c) => (c.source || "") === "literature"),
        who_cross_mentions: cachedMeta.who_cross_mentions || [],
        cache_hit: true,
        cache_source: cachedMeta.cache_source,
        cached_at: cachedMeta.generated_at,
        model: cachedMeta.model,
        debug: null,
      };
    } else {
      const paintThinking = () => {
        if (seq !== browseRequestSeq) return;
        browseContentEl.innerHTML = renderTopicPageShell(leafRef, displayLabel, query, {
          thinkingHtml: renderThinkingPanel(steps, { live: true }),
        });
        bindTopicPageChrome(browseContentEl, leafRef, displayLabel, query);
      };
      paintThinking();
      data = await streamChat(
        buildPayload(query, "topic_page", {
          categoryContext,
          pageTag: leafRef.tag,
          rebuild,
        }),
        {
          onProgress: async (ev) => {
            upsertThinkingStep(steps, ev);
            paintThinking();
          },
        },
      );
      // Mark any still-running steps done for the retained summary.
      steps = steps.map((s) => (s.status === "running" ? { ...s, status: "done" } : s));
    }
    if (seq !== browseRequestSeq) return;

    if (!data.ok) {
      browseContentEl.innerHTML = `<p class="error-text">${escapeHtml(data.error || data.answer_error || "Request failed")}</p>`;
      return;
    }

    setLastExportableResult({
      source: "topic_page",
      query,
      tag: leafRef.tag || null,
      label: displayLabel || leafRef.label || null,
      data,
    });

    // Always surface a retrieval transcript: live SSE steps when present,
    // otherwise rebuild a summary from debug.round_summaries so the user
    // still sees that iterative work happened.
    let thinkingHtml = steps.length ? renderThinkingPanel(steps) : "";
    if (!thinkingHtml && data.debug?.round_summaries?.length) {
      thinkingHtml = renderThinkingPanel(
        data.debug.round_summaries.map((r) => ({
          status: "done",
          label: `Round ${r.round} — ${r.label || "retrieval"}`,
          detail: [
            typeof r.cards === "number" ? `${r.cards} cards` : null,
            typeof r.figures === "number" ? `${r.figures} figures` : null,
            typeof r.literature_total === "number" ? `${r.literature_total} literature` : null,
            typeof r.cards_added === "number" && r.cards_added ? `+${r.cards_added}` : null,
          ]
            .filter(Boolean)
            .join(" · "),
          queries: r.queries || null,
        })),
      );
    }
    let html = renderTopicPageShell(leafRef, displayLabel, query, {
      thinkingHtml,
      bodyHtml:
        topicPageCacheHint(data, cachedMeta) +
        renderTopicPageResult(data, query, {
          tag: leafRef.tag,
          provenance: leafRef.provenance || null,
          categoryId: leafRef.categoryId || browseState.categoryId || null,
          subcategoryId: leafRef.subcategoryId || browseState.subcategoryId || null,
        }),
    });
    browseContentEl.innerHTML = html;
    bindTopicPageChrome(browseContentEl, leafRef, displayLabel, query);
  } catch (err) {
    if (seq !== browseRequestSeq) return;
    browseContentEl.innerHTML = `<p class="error-text">${escapeHtml(String(err))}</p>`;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  setActiveView("ask");
  appendMessage("user", escapeHtml(query));
  queryInput.value = "";
  sendBtn.disabled = true;

  const steps = [];
  const thinking = appendMessage("assistant", renderThinkingPanel(steps));
  const bodyEl = thinking.querySelector(".body");
  const paintThinking = () => {
    bodyEl.innerHTML = renderThinkingPanel(steps);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  try {
    const data = await streamChat(buildPayload(query), {
      onProgress: async (ev) => {
        upsertThinkingStep(steps, ev);
        paintThinking();
      },
    });
    let body = "";
    const doneSteps = steps.map((s) => (s.status === "running" ? { ...s, status: "done" } : s));
    if (doneSteps.length) {
      body += renderThinkingPanel(doneSteps);
    }

    if (data.ok) {
      setLastExportableResult({ source: data.mode || "chat", query, data });
    }

    if (!data.ok) {
      body = `<p class="error-text">${escapeHtml(data.error || data.answer_error || "Request failed")}</p>`;
    } else if (data.mode === "topic_page") {
      body += renderTopicPageResult(data, query);
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

    if (data.ok && data.mode !== "topic_page") {
      body += renderDebugBlock(data);
    }
    if (data.ok && data.mode === "topic_page") {
      /* export bar already included in renderTopicPageResult */
    } else if (data.ok) {
      body += renderTopicExportBar();
    }

    bodyEl.innerHTML = body;
    bodyEl.querySelectorAll(".topic-export-btn").forEach((btn) => {
      btn.addEventListener("click", exportCurrentPageAsJson);
    });
    bindPreviewHandlers(bodyEl);
    if (data.mode === "topic_page") {
      bindDdxLinks(bodyEl);
    }
  } catch (err) {
    bodyEl.innerHTML = `<p class="error-text">${escapeHtml(String(err))}</p>`;
  } finally {
    sendBtn.disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
});

/** Tracks whatever was last rendered (topic page or Ask-tab chat answer) so
 * the sidebar "Export current page as JSON" button always has something real
 * to download — the full raw API response, not just what got rendered. */
function setLastExportableResult(meta) {
  lastExportableResult = { ...meta, exported_at: null };
  exportPageBtn.disabled = false;
  exportStatus.textContent = "";
}

function slugForFilename(text) {
  return (
    String(text || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 60) || "page"
  );
}

function exportCurrentPageAsJson() {
  if (!lastExportableResult) {
    exportStatus.textContent = "Nothing to export yet — ask a question or open a topic page first.";
    return;
  }
  const payload = { ...lastExportableResult, exported_at: new Date().toISOString() };
  const json = JSON.stringify(payload, null, 2);
  const blob = new Blob([json], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  const slug = slugForFilename(payload.tag || payload.query || payload.source);
  anchor.href = url;
  anchor.download = `pathology_hub_${slug}_${stamp}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  exportStatus.textContent = "JSON file downloaded.";
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
if (mediaModalPrev) mediaModalPrev.addEventListener("click", showPrevGallery);
if (mediaModalNext) mediaModalNext.addEventListener("click", showNextGallery);

document.addEventListener("keydown", (event) => {
  if (mediaModal.classList.contains("hidden")) return;
  if (event.key === "Escape") {
    closeMediaPreview();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    showPrevGallery();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    showNextGallery();
  }
});

modeSelect.addEventListener("change", updateModeHint);
exportPageBtn.addEventListener("click", exportCurrentPageAsJson);

viewTabs.forEach((tab) => {
  tab.addEventListener("click", () => setActiveView(tab.dataset.view));
});

compareRunBtn?.addEventListener("click", () => {
  if (compareSet.length < 2) return;
  browseState = { level: "compare" };
  setActiveView("browse");
  renderBrowseView();
});
compareClearBtn?.addEventListener("click", clearCompareSet);
flagModal?.querySelectorAll("[data-flag-close]").forEach((el) => {
  el.addEventListener("click", closeFlagModal);
});
flagSendBtn?.addEventListener("click", submitFlag);

updateModeHint();
setActiveView("browse");
browseContentEl.innerHTML = '<p class="hint">Loading Browse topic index…</p>';
loadBrowseIndex().then(() => {
  renderBrowseView();
});
refreshHealth();
