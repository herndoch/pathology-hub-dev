const DEFAULT_SOURCES = ["textbooks", "pathout", "who"];
/** Topic pages are meant to be comprehensive, so they always request every
 * supported source regardless of the sidebar checkbox state — this mirrors
 * (and is redundant with) the server-side enforcement in app.py, kept here
 * too so the debug panel shows the sources that are actually used, not a
 * misleadingly narrow sidebar selection. Excludes `curriculum`, which is
 * navigation-only and never treated as citable evidence. */
const TOPIC_PAGE_SOURCES = ["textbooks", "who", "pathout", "journals", "videos"];
const NOTES_STORAGE_KEY = "pathology_hub_teaching_session_notes";
const LEGACY_NOTES_STORAGE_KEY = "pathology_hub_experiment_notes";

const SOURCE_LABELS = {
  who: "WHO Classification",
  textbooks: "Textbooks",
  pathout: "Pathoutlines",
  journals: "Journals",
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

const MODE_HINTS = {
  gpt_like: "Bullet summary with inline source links. Figures auto-included when you ask to show something.",
  search_only: "Raw evidence cards only — no OpenAI synthesis.",
  compare_sources: "Markdown table comparing sources, plus brief agreement bullets.",
  visual: "Figures retrieved and shown above the answer.",
  html_teaching: "Hosted HTML teaching page — link appears above citations.",
  topic_page: "ExpertPath-style reference page: Key Facts box, section headers, figure gallery, and multi-query retrieval (3–4 parallel aspect variants × all sources) for broader coverage. Also reachable via the Browse tab.",
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

function getBrowseRoots() {
  if (browseIndex && Array.isArray(browseIndex.roots) && browseIndex.roots.length) {
    return browseIndex.roots;
  }
  return curatedFallbackRoots();
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
    browseIndex = data;
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

/** Built from getBrowseRoots() (curated fallback until loadBrowseIndex()
 * resolves, then rebuilt from the real combined index). Mutable (`let`), not
 * a one-time IIFE const, because the underlying roots can change once at
 * startup when the generated index finishes loading. */
function buildLeafIndex() {
  const list = [];
  for (const root of getBrowseRoots()) {
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

/** Fuzzy-match a Differential Diagnosis bullet's entity name against the
 * taxonomy leaves (curated or generated index, whichever is active), so we
 * only cross-link when reasonably confident — false negatives (no link) are
 * far safer here than false positives (a wrong link), so the overlap
 * threshold below is deliberately conservative. */
function findTaxonomyMatch(rawName) {
  const norm = normalizeEntityName(rawName);
  if (!norm) return null;
  const normTokens = new Set(norm.split(" ").filter((t) => t.length > 2));
  let best = null;
  let bestScore = 0;
  for (const leaf of TAXONOMY_LEAF_INDEX) {
    if (leaf.normalized === norm) {
      return leafRefFrom(leaf);
    }
    if (norm.includes(leaf.normalized) || leaf.normalized.includes(norm)) {
      const score = Math.min(leaf.normalized.length, norm.length) / Math.max(leaf.normalized.length, norm.length);
      if (score > bestScore) {
        bestScore = score;
        best = leaf;
      }
      continue;
    }
    const leafTokens = new Set(leaf.normalized.split(" ").filter((t) => t.length > 2));
    if (!leafTokens.size) continue;
    let overlap = 0;
    for (const t of normTokens) {
      if (leafTokens.has(t)) overlap += 1;
    }
    const ratio = overlap / Math.max(leafTokens.size, normTokens.size, 1);
    if (ratio > bestScore) {
      bestScore = ratio;
      best = leaf;
    }
  }
  if (best && bestScore >= 0.5) {
    return leafRefFrom(best);
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
const mediaModalPrev = document.getElementById("media-modal-prev");
const mediaModalNext = document.getElementById("media-modal-next");

/** Active lightbox gallery — ordered preview payloads + current index (C10). */
let currentGallery = { items: [], index: 0 };
const viewTabs = document.querySelectorAll(".view-tab");
const browseViewEl = document.getElementById("browse-view");
const askViewEl = document.getElementById("ask-view");
const browseBreadcrumbsEl = document.getElementById("browse-breadcrumbs");
const browseContentEl = document.getElementById("browse-content");

let supportedSources = [];
let notesSaveTimer = null;
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

    // A "## Header" line glued (no blank line) to bullets/prose right after it is common
    // model output — render the header alone, then process the rest of the block normally,
    // instead of swallowing everything into one heading tag.
    if (/^#{1,3}\s+/.test(lines[0])) {
      const level = lines[0].match(/^(#{1,3})\s+/)[1].length;
      const tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      const headingContent = lines[0].replace(/^#{1,3}\s+/, "");
      const headingHtml = `<${tag} class="answer-heading">${inlineMarkdown(headingContent, previewIndex)}</${tag}>`;
      const restLines = lines.slice(1).filter((line) => line.trim());
      if (!restLines.length) return headingHtml;
      if (restLines.every((line) => /^\s*[-*]\s+/.test(line))) {
        return headingHtml + renderNestedList(restLines, previewIndex);
      }
      return (
        headingHtml +
        restLines.map((line) => `<p class="answer-line">${inlineMarkdown(line, previewIndex)}</p>`).join("")
      );
    }

    const isList = lines.every((line) => /^\s*[-*]\s+/.test(line) || line.trim() === "");
    if (isList && lines.some((line) => /^\s*[-*]\s+/.test(line))) {
      return renderNestedList(lines.filter((line) => line.trim()), previewIndex);
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
    include_figures: visual,
    max_figures: mode === "topic_page" ? 8 : visual ? 5 : 0,
    compact: true,
    excerpt_char_limit: 900,
    render_html: mode === "html_teaching",
  };
  if (mode === "topic_page" && options.categoryContext) {
    payload.category_context = options.categoryContext;
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
  setModalAction(
    mediaModalSource,
    links.source || links.video,
    links.video && !links.source ? "Open video" : "Open source",
  );
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
        const gallery = el.closest(".topic-gallery-grid, .figures-grid, .figures-grid-prominent");
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

function renderBrowseView() {
  renderBrowseBreadcrumbs();
  if (browseState.level === "category") {
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
  const roots = getBrowseRoots();
  const usingIndex = Boolean(browseIndex);
  const leavesTotal = usingIndex
    ? browseIndex.counts?.leaves_total ?? roots.reduce((sum, r) => sum + r.leaf_count, 0)
    : roots.reduce((sum, r) => sum + r.leaf_count, 0);

  let html = usingIndex
    ? `<p class="hint">WHO + ABPath topic index — ${leavesTotal} topic tags across ${roots.length} roots (local v0_2 snapshot; pilot prebuild covers a small sample, everything else falls back to a live query). Not a claim about API exposure or vector coverage.</p>`
    : '<p class="hint">Browse tag index unavailable — showing the curated starter taxonomy fallback instead. Not a claim about what is indexed.</p>';

  html += '<div class="browse-tile-grid">';
  for (const root of roots) {
    const style = rootTileStyle(root.id, root.label);
    const countLabel = usingIndex ? `${root.leaf_count} topic tags` : `${root.leaf_count} starter topics`;
    html += `<button type="button" class="browse-tile" data-category-id="${escapeAttr(root.id)}" style="background:${style.gradient}">`;
    html += `<span class="browse-tile-glyph">${escapeHtml(style.glyph)}</span>`;
    html += `<span class="browse-tile-banner"><span class="browse-tile-label">${escapeHtml(formatDisplayLabel(root.label))}</span><span class="browse-tile-count">${countLabel}</span></span>`;
    html += "</button>";
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
  browseContentEl.querySelectorAll(".browse-tile").forEach((el) => {
    el.addEventListener("click", () => {
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
  let html = `<h2 class="browse-heading">${escapeHtml(formatDisplayLabel(cat.label))}</h2>`;
  html += browseIndex
    ? '<p class="hint">WHO + ABPath topic tags for this root. Pick a subcategory, then a topic.</p>'
    : '<p class="hint">Curated starter topic list for navigation — not a claim about what is indexed. Pick a subcategory, then a specific diagnosis.</p>';
  html += '<div class="chevron-list">';
  for (const sub of cat.subcategories) {
    html += `<button type="button" class="chevron-item" data-sub-id="${escapeAttr(sub.id)}"><span>${escapeHtml(formatSubcategoryLabel(sub.label))}${browseIndex ? ` <span class="chevron-count">(${sub.leaf_count})</span>` : ""}</span><span class="chevron">\u203a</span></button>`;
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
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
  let html = `<h2 class="browse-heading">${escapeHtml(formatDisplayLabel(cat.label))} — ${escapeHtml(formatSubcategoryLabel(sub.label))}</h2>`;
  html += browseIndex
    ? '<p class="hint">Pick a topic to load a grounded topic page — prebuilt (pilot) pages load instantly, others run a live query.</p>'
    : '<p class="hint">Pick a diagnosis to load a live, grounded topic page from current evidence.</p>';
  html += '<div class="chevron-list">';
  for (const leaf of sub.leaves) {
    const displayLabel = formatDisplayLabel(leaf.label);
    const payload = escapeAttr(JSON.stringify({ tag: leaf.tag, label: leaf.label, query: leaf.query, provenance: leaf.provenance || null }));
    html += `<button type="button" class="chevron-item" data-leaf="${payload}"><span>${escapeHtml(displayLabel)}</span><span class="chevron">\u203a</span></button>`;
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
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
}

const TOPIC_PAGE_SECTION_ORDER = [
  "Key Facts",
  "Terminology",
  "Etiology/Pathogenesis",
  "Clinical Issues",
  "Microscopic",
  "Ancillary Tests",
  "Differential Diagnosis",
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

function renderTopicGallery(figures) {
  if (!figures || !figures.length) {
    return '<p class="hint">No figures returned for this query.</p>';
  }
  let html = '<div class="topic-gallery-grid">';
  for (const fig of figures.slice(0, 10)) {
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
function renderDifferentialSection(content, previewIndex) {
  const text = String(content || "").trim();
  if (!text) return '<p class="hint">Not covered in retrieved evidence.</p>';

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
    const navTarget = findTaxonomyMatch(entityName);
    if (navTarget) {
      const payload = escapeAttr(JSON.stringify(navTarget));
      items.push(
        `<li><button type="button" class="ddx-link-btn" data-ddx-nav="${payload}">${escapeHtml(formatDisplayLabel(entityName))}</button>` +
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

function renderWhoCrossMentions(mentions) {
  if (!mentions?.length) return "";
  const items = [];
  for (const mention of mentions) {
    const leaf = mention.matched_leaf;
    if (!leaf) continue;
    const navTarget = findTaxonomyMatch(leaf);
    const sourceEntity = mention.source_entity || "WHO";
    const sourceSection = mention.source_section || "";
    const meta = sourceSection
      ? ` <span class="who-mention-meta">(from ${escapeHtml(sourceEntity)}, ${escapeHtml(sourceSection)})</span>`
      : ` <span class="who-mention-meta">(from ${escapeHtml(sourceEntity)})</span>`;
    if (navTarget) {
      const payload = escapeAttr(JSON.stringify(navTarget));
      items.push(
        `<li><button type="button" class="ddx-link-btn" data-ddx-nav="${payload}">${escapeHtml(formatDisplayLabel(leaf))}</button>${meta}</li>`,
      );
    } else {
      items.push(`<li><strong>${escapeHtml(formatDisplayLabel(leaf))}</strong>${meta}</li>`);
    }
  }
  if (!items.length) return "";
  return `<div class="topic-who-mentions"><div class="topic-panel-title">Cross-referenced Entities</div><ul class="answer-list ddx-list">${items.join("")}</ul></div>`;
}

function renderTopicPage(sections, previewIndex, figures, whoCrossMentions) {
  const keyFacts = findSectionContent(sections, "Key Facts");
  const keyFactsHtml = keyFacts.trim()
    ? renderMarkdown(keyFacts, previewIndex)
    : '<p class="hint">Not covered in retrieved evidence.</p>';

  let html = '<div class="topic-page">';
  html += '<div class="topic-page-top">';
  html += `<div class="topic-key-facts"><div class="topic-panel-title">Key Facts</div>${keyFactsHtml}</div>`;
  html += `<div class="topic-gallery"><div class="topic-panel-title">Selected Images</div>${renderTopicGallery(figures)}</div>`;
  html += "</div>";

  html += renderWhoCrossMentions(whoCrossMentions);

  html += '<div class="topic-sections">';
  for (const name of TOPIC_PAGE_SECTION_ORDER) {
    if (name === "Key Facts") continue;
    const content = findSectionContent(sections, name);
    html += '<div class="topic-section">';
    html += `<div class="topic-section-header">${escapeHtml(name.toUpperCase())}</div>`;
    html += '<div class="topic-section-body">';
    if (name === "Differential Diagnosis") {
      html += renderDifferentialSection(content, previewIndex);
    } else {
      html += content.trim()
        ? renderMarkdown(content, previewIndex)
        : '<p class="hint">Not covered in retrieved evidence.</p>';
    }
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

function topicPageFanoutHint(data) {
  const debug = data?.debug;
  if (!debug?.multi_query) return "";
  const variantCount = debug.query_variants?.length || "?";
  const callCount = debug.call_count || "?";
  const capped = debug.cards_capped;
  const capLimit = debug.cards_cap_limit;
  let text = `Retrieval used ${variantCount} parallel query variants (${callCount} total source calls) for broader coverage.`;
  if (typeof capped === "number" && typeof capLimit === "number") {
    text += ` ${capped} unique cards (cap ${capLimit}) sent to synthesis.`;
  }
  return `<p class="hint topic-fanout-hint">${escapeHtml(text)}</p>`;
}

function renderEntryTagsFooter(tag, provenance) {
  if (!tag) return "";
  let html = '<div class="topic-tags-footer">';
  html += '<span class="topic-tags-label">Tags:</span>';
  html += `<span class="tag-chip topic-entry-tag" title="${escapeAttr(tag)}">${escapeHtml(formatDisplayLabel(tag))}</span>`;
  if (provenance && provenance !== "curated") {
    html += `<span class="source-badge provenance-badge">${escapeHtml(provenance)}</span>`;
  }
  html += "</div>";
  return html;
}

function renderTopicPageResult(data, query, entryMeta = null) {
  const cardFilter = filterByQueryRelevance(query, data.cards || [], { maxShown: 20 });
  const sortedCards = cardFilter.shown.length ? cardFilter.shown : data.cards || [];
  const figFilter = filterByQueryRelevance(query, data.figures || [], { maxShown: 10 });
  const shownFigures = figFilter.shown.length ? figFilter.shown : data.figures || [];
  const previewIndex = buildUrlPreviewIndex(data.cards || [], data.figures || []);
  const sections = parseTopicPageSections(data.answer || "");

  let html = topicPageFanoutHint(data);
  html += renderTopicPage(sections, previewIndex, shownFigures, data.who_cross_mentions || []);
  if (figFilter.note) html += `<p class="hint">${escapeHtml(figFilter.note)}</p>`;
  if (cardFilter.note) html += `<p class="hint">${escapeHtml(cardFilter.note)}</p>`;
  html += renderCitations(sortedCards);
  const tag = entryMeta?.tag || null;
  const provenance = entryMeta?.provenance || null;
  html += renderEntryTagsFooter(tag, provenance);
  html += renderDebugBlock(data);
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

/** Best-effort read-only lookup of a topic-page-prepop-pilot sidecar
 * (outputs/chat_mvp_topic_prepop_v0_1/pages/, served via GET
 * /api/topic_prebuild) for a real taxonomy leaf's `tag`. Returns null on any
 * miss/error so the caller falls back to the live path unchanged — never
 * throws, never fabricates content. */
async function fetchPrebuiltTopicPage(tag) {
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

/** Loads a Browse leaf's topic page. `leafRef` is {categoryId,
 * subcategoryId, tag, label, query} (tag is null for curated-fallback
 * leaves, which always go straight to the live path). Tries the pilot
 * prebuild cache first (instant, no OpenAI call) when `tag` is present; on
 * any miss falls back to the existing live POST /api/chat (mode:
 * "topic_page") path, unchanged. A monotonically increasing request
 * sequence number guards against a stale response overwriting a newer
 * navigation. */
async function loadLeafTopicPage(leafRef) {
  const seq = ++browseRequestSeq;
  const displayLabel = formatDisplayLabel(leafRef.label || leafRef.query);
  browseContentEl.innerHTML = `<p class="hint">Loading evidence for "${escapeHtml(displayLabel)}"…</p>`;

  const category = findCategory(leafRef.categoryId);
  const subcategory = category ? findSubcategory(category, leafRef.subcategoryId) : null;
  const categoryContext =
    category && subcategory ? `${category.label} > ${subcategory.label}` : category?.label || null;
  const query = leafRef.query || displayLabel;

  try {
    const prebuilt = await fetchPrebuiltTopicPage(leafRef.tag);
    if (seq !== browseRequestSeq) return;

    let data;
    if (prebuilt) {
      data = {
        ok: true,
        mode: "topic_page",
        answer: prebuilt.answer_markdown,
        cards: prebuilt.cards || [],
        figures: prebuilt.figures || [],
        who_cross_mentions: prebuilt.who_cross_mentions || [],
        debug: null,
      };
    } else {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(query, "topic_page", { categoryContext })),
      });
      data = await resp.json();
    }
    if (seq !== browseRequestSeq) return;

    if (!data.ok) {
      browseContentEl.innerHTML = `<p class="error-text">${escapeHtml(data.error || data.answer_error || "Request failed")}</p>`;
      return;
    }

    let html = prebuilt
      ? '<p class="hint topic-prebuilt-hint">Prebuilt (pilot) — cached topic page from a prior run, not a fresh live query. See docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md.</p>'
      : "";
    html += renderTopicPageResult(data, query, {
      tag: leafRef.tag,
      provenance: leafRef.provenance || null,
    });
    browseContentEl.innerHTML = html;
    bindPreviewHandlers(browseContentEl);
    bindDdxLinks(browseContentEl);
  } catch (err) {
    if (seq !== browseRequestSeq) return;
    browseContentEl.innerHTML = `<p class="error-text">${escapeHtml(String(err))}</p>`;
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
sessionNotes.addEventListener("input", scheduleNotesSave);
copyNotesBtn.addEventListener("click", copySessionNotes);
exportNotesBtn.addEventListener("click", exportSessionNotes);

viewTabs.forEach((tab) => {
  tab.addEventListener("click", () => setActiveView(tab.dataset.view));
});

loadSessionNotes();
updateModeHint();
setActiveView("browse");
browseContentEl.innerHTML = '<p class="hint">Loading Browse topic index…</p>';
loadBrowseIndex().then(() => {
  renderBrowseView();
});
refreshHealth();
