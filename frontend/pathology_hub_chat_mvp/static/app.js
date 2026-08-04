const DEFAULT_SOURCES = ["textbooks", "pathout", "who"];
/** Most-recently-rendered chat/topic-page result, for the "Export current
 * page as JSON" button — replaces the old teaching-session-notes panel. */
let lastExportableResult = null;
/** From /api/health — drives cache skip + status badge. */
let healthFlags = {
  iterative: true,
  liveLiterature: true,
  streamEndpoint: true,
  scopusSanitize: true,
  buildMarker: "",
  buildSha: "",
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
  biopsy: "Biopsy",
  biopsy_interpretation: "Biopsy",
  biopsy_interpretation_neoplastic: "Biopsy",
  biopsy_interpretation_non_neoplastic: "Biopsy",
  // BST (Bone/Soft Tissue) textbook packages — bone_dorfman, bst_horvai,
  // softtissue_enzinger, {bone,softtissue}_pattern (source_id prefix is
  // stripped before this lookup, so keys are just the book-name suffix).
  dorfman: "Dorfman",
  horvai: "Horvai",
  enzinger: "Enzinger",
  pattern: "Pattern",
};

/** Normalize inline markdown link labels baked into prebuild/synthesis text. */
const INLINE_LINK_LABEL_ALIASES = {
  pathout: "Pathoutlines",
  "path out": "Pathoutlines",
  "hn atlas": "Atlas",
  "hn_gnepp": "Gnepp",
  "hn gnepp": "Gnepp",
};

/** Internal response shapes — not user-facing. Ask always auto-routes. */
const AUTO_MODE_HINT =
  "One Ask box: entity / “what is…” → topic page · compare/vs → comparison · show figures → visual · “sources only” → raw cards · otherwise a short grounded answer.";

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
    glyph: "Breast",
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
    glyph: "Cervix",
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
    glyph: "Uterus",
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
    glyph: "Ovary",
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
    glyph: "Hepatobiliary",
    gradient: "linear-gradient(135deg, #b5722f, #5e3813)",
    subcategories: [
      { id: "liver", label: "Liver", entities: ["Hepatocellular carcinoma", "Focal nodular hyperplasia", "Hepatic adenoma"] },
      { id: "pancreas", label: "Pancreas", entities: ["Pancreatic ductal adenocarcinoma", "Intraductal papillary mucinous neoplasm (IPMN)", "Pancreatic neuroendocrine tumor"] },
    ],
  },
  {
    id: "gu_prostate_bladder",
    label: "GU — Prostate & Bladder",
    glyph: "Prostate",
    gradient: "linear-gradient(135deg, #3f8fc9, #1c3f66)",
    subcategories: [
      { id: "prostate", label: "Prostate", entities: ["Prostatic adenocarcinoma (Gleason grading)", "High-grade prostatic intraepithelial neoplasia (HGPIN)", "Atypical adenomatous hyperplasia (adenosis)", "Benign prostatic hyperplasia"] },
      { id: "bladder", label: "Bladder", entities: ["High-grade urothelial carcinoma", "Low-grade papillary urothelial carcinoma", "Urothelial carcinoma in situ", "Urothelial papilloma"] },
    ],
  },
  {
    id: "gu_kidney_testis",
    label: "GU — Kidney & Testis",
    glyph: "Kidney",
    gradient: "linear-gradient(135deg, #4aa3a3, #1f4d4d)",
    subcategories: [
      { id: "kidney", label: "Kidney", entities: ["Clear cell renal cell carcinoma", "Papillary renal cell carcinoma", "Chromophobe renal cell carcinoma", "Angiomyolipoma", "Oncocytoma"] },
      { id: "testis", label: "Testis", entities: ["Seminoma", "Embryonal carcinoma", "Yolk sac tumor of testis", "Leydig cell tumor"] },
    ],
  },
  {
    id: "skin",
    label: "Skin / Dermatopathology",
    glyph: "Skin",
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
    glyph: "Head & Neck",
    gradient: "linear-gradient(135deg, #5f9ea0, #2b4a4b)",
    subcategories: [
      { id: "mucosal", label: "Mucosal / Squamous", entities: ["Squamous cell carcinoma of oral cavity", "Nasopharyngeal carcinoma", "Laryngeal squamous cell carcinoma"] },
      { id: "salivary", label: "Salivary Gland", entities: ["Pleomorphic adenoma", "Warthin tumor", "Mucoepidermoid carcinoma", "Adenoid cystic carcinoma", "Epithelial-myoepithelial carcinoma", "Myoepithelial carcinoma", "Basal cell adenocarcinoma", "Acinic cell carcinoma"] },
    ],
  },
  {
    id: "bone_soft_tissue",
    label: "Bone & Soft Tissue",
    glyph: "BST",
    gradient: "linear-gradient(135deg, #9a9a9a, #4a4a4a)",
    subcategories: [
      { id: "bone", label: "Bone Tumors", entities: ["Osteosarcoma", "Giant cell tumor of bone", "Chondrosarcoma", "Ewing sarcoma", "Chordoma"] },
      { id: "soft_tissue", label: "Soft Tissue Tumors", entities: ["Liposarcoma", "Leiomyosarcoma of soft tissue", "Synovial sarcoma", "Nodular fasciitis", "Meningioma"] },
    ],
  },
  {
    id: "heme",
    label: "Hematolymphoid",
    glyph: "Heme",
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
    glyph: "Endo",
    gradient: "linear-gradient(135deg, #5fb87d, #245c38)",
    subcategories: [
      { id: "thyroid", label: "Thyroid", entities: ["Papillary thyroid carcinoma", "Follicular adenoma of thyroid", "Medullary thyroid carcinoma", "Hashimoto thyroiditis"] },
      { id: "other_endocrine", label: "Parathyroid & Adrenal", entities: ["Parathyroid adenoma", "Adrenal cortical adenoma", "Pheochromocytoma"] },
    ],
  },
  {
    id: "neuro",
    label: "Neuropathology",
    glyph: "Neuro",
    gradient: "linear-gradient(135deg, #7a5fc9, #382a6b)",
    subcategories: [
      { id: "tumors", label: "CNS Tumors", entities: ["Glioblastoma", "Meningioma", "Pilocytic astrocytoma", "Schwannoma"] },
      { id: "other", label: "Other", entities: ["Metastatic carcinoma to brain"] },
    ],
  },
  {
    id: "thorax",
    label: "Thorax / Mediastinum",
    glyph: "Thorax",
    gradient: "linear-gradient(135deg, #4d79c9, #24356b)",
    subcategories: [
      { id: "lung", label: "Lung", entities: ["Lung adenocarcinoma", "Squamous cell carcinoma of lung", "Small cell lung carcinoma"] },
      { id: "mediastinum", label: "Mediastinum & Pleura", entities: ["Thymoma", "Mesothelioma"] },
    ],
  },
  {
    id: "cyto",
    label: "Cytopathology",
    glyph: "Cyto",
    gradient: "linear-gradient(135deg, #4fc9b8, #1f6b5f)",
    subcategories: [
      { id: "cyto_topics", label: "Common FNA / Exfoliative Cytology", entities: ["Thyroid FNA (Bethesda system)", "Pap smear HSIL", "Pancreatic FNA, adenocarcinoma", "Effusion cytology, adenocarcinoma"] },
    ],
  },
  {
    id: "peds",
    label: "Pediatric",
    glyph: "Peds",
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

/** Locked browse-nav policy: accepted topic tags come from ABPath AP content
 * specifications and/or WHO only (PathOut is citation-only, not nav). */
const ACCEPTED_NAV_PROVENANCES = new Set(["abpath", "who", "both", "pathout"]);
const NAV_PROVENANCE_LABELS = {
  abpath: "ABPath content specifications",
  who: "WHO classification map",
  both: "Shared board entity",
  pathout: "PathologyOutlines",
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

/** Strip trailing / standalone NOS so "DLBCL" matches "Diffuse_Large_B_Cell_Lymphoma_NOS". */
function stripNosMatchKey(value) {
  return normalizeTopicMatchKey(value)
    .replace(/\bnos\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Normalize browse/index root ids for comparison (Heme ≈ heme, Cyto_Fluids ≈ cyto). */
function normalizeBrowseRootId(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

/** Browse root id encoded in a tag (`Heme::…` or `ABPathSpec::heme::…`). */
function tagBrowseRootId(tag) {
  const parts = String(tag || "")
    .split("::")
    .map((p) => p.trim())
    .filter(Boolean);
  if (!parts.length) return "";
  const head = normalizeBrowseRootId(parts[0]);
  if (head === "abpathspec" && parts[1]) return normalizeBrowseRootId(parts[1]);
  return head;
}

/** True when a board-index leaf belongs under the Browse category the user opened. */
function leafMatchesBrowseRoot(leafRef, row, leaf) {
  const preferred = normalizeBrowseRootId(leafRef?.categoryId);
  if (!preferred) return true;
  const indexRoot = normalizeBrowseRootId(row?.root?.id);
  const tagRoot = tagBrowseRootId(leaf?.tag);
  if (preferred === indexRoot || preferred === tagRoot) return true;
  // Browse "cyto" covers every Cyto_* organ root in the index.
  if (preferred === "cyto" && (indexRoot.startsWith("cyto") || tagRoot.startsWith("cyto"))) {
    return true;
  }
  return false;
}

/**
 * When Browse opens a curated starter leaf (`tag: null`), try to attach the
 * real ABPath/WHO hierarchical tag from the full browse index so the topic
 * page can show board/curricular location instead of a blank tag header.
 *
 * Critical: when the user is under Hematopathology / Breast / etc., only map
 * to tags in that same root — otherwise extranodal organ-site clones
 * (Breast::…::Diffuse_Large_B_Cell_Lymphoma) steal the match and root-narrow
 * drops real heme pathout/videos/textbooks.
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

  const allRows = collectLeavesFromRoots(activeBrowseRoots() || []);
  const preferredRoot = normalizeBrowseRootId(leafRef.categoryId);
  const scopedRows = preferredRoot
    ? allRows.filter((row) => leafMatchesBrowseRoot(leafRef, row, row.leaf))
    : allRows;
  // Prefer same-root candidates; fall back only if that pool has no usable match.
  const pools = scopedRows.length ? [scopedRows, allRows] : [allRows];

  let best = null;
  let bestScore = -1;
  for (const pool of pools) {
    best = null;
    bestScore = -1;
    for (const row of pool) {
      const leaf = row.leaf;
      if (!leaf?.tag) continue;
      const leafKeys = [leaf.label, leaf.query, leaf.tag?.split("::").pop()].map(normalizeTopicMatchKey);
      let score = 0;
      for (const k of keys) {
        const kNos = stripNosMatchKey(k);
        for (const lk of leafKeys) {
          if (!lk) continue;
          const lkNos = stripNosMatchKey(lk);
          if (lk === k) score = Math.max(score, 100);
          else if (kNos && lkNos && lkNos === kNos) score = Math.max(score, 98);
          else if (lk.includes(k) || k.includes(lk)) score = Math.max(score, 60);
          else if (kNos && lkNos && (lkNos.includes(kNos) || kNos.includes(lkNos))) {
            score = Math.max(score, 58);
          }
        }
      }
      // Bare starter "LCIS" / classic labels must not map to Florid /
      // Pleomorphic / EBV+ / leg-type board tags unless the starter names them.
      const starterBlob = [...keys].join(" ");
      const leafBlob = leafKeys.join(" ");
      for (const mod of ENTITY_SUBTYPE_MODIFIERS) {
        if (leafBlob.includes(mod) && !starterBlob.includes(mod)) score -= 40;
      }
      const prov = String(leaf.provenance || "").toLowerCase();
      if (prov === "abpath" || prov === "both") score += 5;
      if (leafMatchesBrowseRoot(leafRef, row, leaf)) score += 25;
      // Prefer canonical NOS / shorter tag over long extranodal site clones.
      const tagDepth = String(leaf.tag || "").split("::").length;
      if (tagDepth <= 4) score += 2;
      if (/\bnos\b/i.test(leafBlob) && !/ebv|kshv|cutaneous|inflammation|myc/i.test(leafBlob)) {
        score += 3;
      }
      if (score > bestScore) {
        bestScore = score;
        best = { row, leaf };
      }
    }
    if (best && bestScore >= 58) break;
  }
  if (!best || bestScore < 58) return leafRef;
  return {
    ...leafRef,
    tag: best.leaf.tag,
    provenance: best.leaf.provenance || leafRef.provenance || null,
    label: leafRef.label || best.leaf.label,
    query: leafRef.query || best.leaf.query || best.leaf.label,
    // Keep the Browse root the user opened (heme), not the mapped tag's root.
    categoryId: leafRef.categoryId || best.row.root?.id || null,
    subcategoryId: leafRef.subcategoryId || best.row.sub?.id || null,
    boardResolvedFrom: "browse_tag_index",
  };
}

/** Known-root tile styling, keyed by the generated index's root `id`s (see
 * build_browse_tag_index_who_abpath_spec_v0_1.py). `glyph` is a short but
 * legible root name (not a cryptic 2-letter code) shown large on the tile;
 * the banner below shows the fuller descriptive root label. Any root not
 * listed here (e.g. small PathOut-only residual roots) gets a neutral
 * default look — never a hard failure. */
const BROWSE_ROOT_STYLE = {
  cyto: { glyph: "Cyto", gradient: "linear-gradient(135deg, #4fc9b8, #1f6b5f)" },
  breast: { glyph: "Breast", gradient: "linear-gradient(135deg, #d1477a, #6b2142)" },
  gyn: { glyph: "GYN", gradient: "linear-gradient(135deg, #a84a9c, #4a2159)" },
  gi: { glyph: "GI", gradient: "linear-gradient(135deg, #c98a3f, #6b4416)" },
  gu: { glyph: "GU", gradient: "linear-gradient(135deg, #3f8fc9, #1c3f66)" },
  skin: { glyph: "Skin", gradient: "linear-gradient(135deg, #d9a066, #6e4a29)" },
  hn: { glyph: "Head & Neck", gradient: "linear-gradient(135deg, #5f9ea0, #2b4a4b)" },
  bst: { glyph: "BST", gradient: "linear-gradient(135deg, #9a9a9a, #4a4a4a)" },
  heme: { glyph: "Heme", gradient: "linear-gradient(135deg, #c94f4f, #6b2323)" },
  endo: { glyph: "Endo", gradient: "linear-gradient(135deg, #5fb87d, #245c38)" },
  neuro: { glyph: "Neuro", gradient: "linear-gradient(135deg, #7a5fc9, #382a6b)" },
  thorax_mediastinum: { glyph: "Thorax", gradient: "linear-gradient(135deg, #4d79c9, #24356b)" },
  peds: { glyph: "Peds", gradient: "linear-gradient(135deg, #e0b84f, #7a5f1f)" },
  molecular: { glyph: "Molecular", gradient: "linear-gradient(135deg, #6b8fb8, #2e4a66)" },
  eye_orbit: { glyph: "Eye / Orbit", gradient: "linear-gradient(135deg, #8fae5f, #3f4f24)" },
  eye: { glyph: "Eye / Orbit", gradient: "linear-gradient(135deg, #8fae5f, #3f4f24)" },
  cardio: { glyph: "Cardio", gradient: "linear-gradient(135deg, #c45c6a, #5c2430)" },
  forensic: { glyph: "Forensic", gradient: "linear-gradient(135deg, #6a7a8a, #2e3844)" },
  general_pathology: { glyph: "General", gradient: "linear-gradient(135deg, #8a8a8a, #3a3a3a)" },
};
const DEFAULT_ROOT_STYLE = { glyph: "Path", gradient: "linear-gradient(135deg, #7a7a7a, #3a3a3a)" };

function rootTileStyle(rootId, label) {
  const known = BROWSE_ROOT_STYLE[rootId];
  if (known) return known;
  const fallback = formatDisplayLabel(label || rootId || "Path").split(" ")[0] || "Path";
  return { glyph: fallback, gradient: DEFAULT_ROOT_STYLE.gradient };
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

const BROWSE_PROVENANCE_RANK = { abpath: 0, both: 1, who: 2, pathout: 3 };
const BROWSE_LEAF_PREVIEW_CAP = 48;
const BROWSE_NAV_THINNING = {
  abpath_primary: false,
  hide_cyto_surgical_dupes: true,
  drop_cyto_pattern: true,
};

/** Browse ships exactly one indexed tree: WHO + ABPath content-spec
 * diagnoses, aggressively deduped. No mode toggle is shown to the user;
 * the curated taxonomy below is only an automatic fallback when the
 * generated index fails to load. */
let browseFilterQuery = "";

function getBrowseNavRootsFull() {
  if (browseIndex && Array.isArray(browseIndex.nav_roots_full) && browseIndex.nav_roots_full.length) {
    return browseIndex.nav_roots_full;
  }
  return null;
}

function activeBrowseRoots() {
  return getBrowseNavRootsFull() || curatedFallbackRoots();
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
  return activeBrowseRoots();
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

/** Collapsible tree view for Browse — clickable, connected dot-and-line
 * hierarchy (root organ -> subcategory -> diagnosis leaf). This is the one
 * and only Browse-home visualization; the old tile-grid/mode-toggle only
 * remains as a degraded fallback for when the tag index itself fails to
 * load (see renderBrowseHome). */
const ONCOTREE_BASE_ROW_HEIGHT = 30;
const ONCOTREE_BASE_COL_WIDTH = 320;
const ONCOTREE_LEAF_CAP_PER_SUB = 80;
/** Subcategories bigger than this get chunked into branches — but by real
 * pathology category (from the WHO tag's own hierarchy), not alphabet. */
const ONCOTREE_GROUP_THRESHOLD = 16;
/** A leaf whose tag carries no categorical segment (bare ABPathSpec tags,
 * or a WHO tag with no intermediate segment) can't be placed into a
 * meaningful branch — it gets dropped from the tree with a disclosed count,
 * findable via search/Tile view instead, rather than faked into an
 * alphabetical or "Other" bucket. If fewer than this fraction of a
 * subcategory's leaves carry a usable category, there isn't enough real
 * structure to build a nice hierarchy at all — show it flat instead. */
const ONCOTREE_MIN_CATEGORY_COVERAGE = 0.4;
const ONCOTREE_ZOOM_STEPS = [0.6, 0.8, 1, 1.2, 1.5];
/** Above this many matches, an in-tree highlighted search would explode into
 * an unnavigable wall of expanded nodes — fall back to the flat list. Set
 * high enough to cover realistic partial-word searches (e.g. "adeno" ~270
 * matches, "carcinoma" ~440) so the tree actively fills in live as the user
 * types instead of bailing to a flat list; only near-single-letter queries
 * (thousands of matches) still fall back. */
const ONCOTREE_SEARCH_INLINE_CAP = 600;

let browseTreeExpanded = new Set();
let browseTreeZoomIdx = ONCOTREE_ZOOM_STEPS.indexOf(1);

function oncotreeDotColor(rootId, rootLabel) {
  const style = rootTileStyle(rootId, rootLabel);
  const match = /#([0-9a-f]{6})/i.exec(style.gradient || "");
  return match ? `#${match[1]}` : "#7a7a7a";
}

function oncotreeZoom() {
  return ONCOTREE_ZOOM_STEPS[browseTreeZoomIdx] ?? 1;
}

/** Real pathology category for a leaf, read off its own tag hierarchy —
 * never invented. WHO tags carry genuine categorical structure beyond
 * root/subcategory (e.g. "BST::Soft_Tissue::Fibroblastic::Acral_Fibromyxoma"
 * — "Fibroblastic" is WHO's own classification, the same grouping used in
 * the WHO Blue Books). ABPathSpec tags (content-spec derived) and shallow
 * 3-segment WHO tags carry no such segment and return null — those leaves
 * have nothing to hang a "nice" branch off of.
 *
 * Cytopathology is a partial exception: `Cyto_<System>::…` WHO/PathOut tags
 * and `ABPathSpec::cyto::…` tags both bucket the Browse *subcategory* on
 * organ system (see build_browse_tag_index_who_abpath_spec_v0_1.py
 * CYTO_SYSTEM_* constants), one segment earlier than every other root — so
 * the real histologic category (WHO's own "Benign"/"Malignant"/"SIL", or
 * ABPath's own content-spec heading) sits one segment sooner too. */
function leafCategoryFromTag(tag) {
  if (!tag) return null;
  // Cyto_<System>::<Category>::<Leaf> is only 3 segments (the system IS
  // the root+subcategory already) — category is one segment earlier than
  // every other root's Root::Sub::Category::Leaf shape. Covers both real
  // WHO/PathOut Cyto_ tags and native ABPath-derived ones (2026-08-02: cyto
  // ABPath leaves now carry this same native shape, no more separate
  // "ABPathSpec::cyto::…" wrapper to special-case here).
  if (tag.startsWith("Cyto_")) {
    const parts = tag.split("::").filter(Boolean);
    return parts.length > 2 ? formatDisplayLabel(parts[1]) : null;
  }
  if (tag.startsWith("ABPathSpec::")) return null;
  const parts = tag.split("::").filter(Boolean);
  if (parts.length <= 3) return null;
  return formatDisplayLabel(parts[2]);
}

/** Chunk leaves into branches by real pathology category (from the WHO tag
 * hierarchy) instead of alphabet. Leaves with no usable category segment
 * (mostly ABPath-content-spec leaves, which don't carry a WHO-style
 * category segment at all) go into a real, clickable "Other" group instead
 * of being silently dropped from the tree (2026-08-04 — a static "N without
 * a clear category — use search" note with no node/click target was a dead
 * end: reported as "cant expand those without category"). Returns `null`
 * when there isn't enough categorical structure to build a meaningful
 * hierarchy at all (caller should fall back to a flat list rather than
 * force a fake grouping) — that decision still looks at how much of the
 * list got a REAL category, ignoring the "Other" catch-all, so a subcategory
 * that's mostly uncategorized still falls back to flat instead of a tree
 * that's one enormous "Other" node next to a couple of tiny real ones. */
function buildOncotreeCategoryGroups(leaves) {
  const byCategory = new Map();
  const other = [];
  for (const leaf of leaves) {
    const cat = leafCategoryFromTag(leaf.tag);
    if (!cat) {
      other.push(leaf);
      continue;
    }
    if (!byCategory.has(cat)) byCategory.set(cat, []);
    byCategory.get(cat).push(leaf);
  }
  const coverage = leaves.length ? (leaves.length - other.length) / leaves.length : 0;
  if (coverage < ONCOTREE_MIN_CATEGORY_COVERAGE || byCategory.size < 2) {
    return null;
  }
  const groups = [...byCategory.entries()]
    .map(([label, catLeaves]) => ({
      id: slugifyForTree(label),
      label,
      leaf_count: catLeaves.length,
      leaves: catLeaves,
    }))
    .sort((a, b) => b.leaf_count - a.leaf_count || a.label.localeCompare(b.label));
  if (other.length) {
    groups.push({ id: "other", label: "Other", leaf_count: other.length, leaves: other });
  }
  return { groups, droppedCount: 0 };
}

function slugifyForTree(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "cat";
}

/** Above this many direct subcategories, a root's own fan-out is the
 * unmanageable part of the tree — not any one subcategory's leaf list. WHO
 * roots (BST, GYN, GU, GI, ...) stay under this because WHO's own hierarchy
 * already nests by organ before diagnosis; the mostly-ABPath-content-spec
 * roots (Peds, Neuro, Skin, Heme, Forensic) blow past it because ABPath
 * flattens every disease-process header straight under the root. Reported
 * 2026-08-02: "prob also need to make another level of category to manage
 * long lists of things like in peds path and neuro path". */
const ONCOTREE_SUBCATEGORY_GROUP_THRESHOLD = 20;

/** A leaf label this long (chars) reliably overflows one row's ~300px
 * width at 100% zoom — wrap it onto a second line (see ONCOTREE_TALL_*
 * CSS) instead of truncating to an identical-looking prefix. */
const ONCOTREE_TALL_LABEL_CHARS = 34;

/** Heuristic disease-process bucket for a *subcategory* label (not a single
 * diagnosis) — inserts one extra branch level (root -> process -> existing
 * subcategory -> leaf) purely to cut down an unmanageable root fan-out; it
 * never changes which subcategory a leaf lives in, and every subcategory
 * still appears somewhere (the catch-all "General / Other" bucket, not a
 * drop). Order matters: more specific/rare patterns are checked first so a
 * label naming several processes lands on the most useful one (e.g.
 * "Familial Tumor Predisposition Syndromes" -> Genetic, not Neoplastic).
 * Necessarily imperfect prose-matching over ABPath's own section headers —
 * disclosed via the (?) info panel, never claimed to be WHO taxonomy. */
const SUBCATEGORY_PROCESS_RULES = [
  ["Vascular", /vascular|vasculopath|infarct|ischemi|hemorrhag|thrombo|embol|aneurysm|vasculitis|angiopathy/i],
  [
    "Traumatic / Mechanical",
    /trauma|injur|wound|fracture|blunt|firearm|gunshot|sharp injur|cutting|stabbing|\bburn|thermal|asphyxia|electrical|lightning|\bbomb\b|explosion|\babuse\b/i,
  ],
  [
    "Postmortem / Forensic Investigation",
    /postmortem|forensic|jurisprudence|criminalistic|identification of human|toxicology|anthropology|deaths?\b|mortality|certification/i,
  ],
  [
    "Infectious / Inflammatory",
    /infect|bacteria|viral|fungal|parasitic|mycobacter|inflamm|autoimmune|granulomatous|reactive|reaction pattern|panniculitis|\babscess|arthropod|\btick\b|infestation|demyelinat|multiple sclerosis|leukoencephalopathy/i,
  ],
  [
    "Congenital / Developmental / Genetic",
    /congenital|developmental|malformation|migration defect|induction|anomal|genetic|hereditary|inherited|familial|syndrome|chromosomal|neural tube|gene defect|trinucleotide repeat/i,
  ],
  [
    "Metabolic / Degenerative / Toxic",
    /metabolic|metabolism|storage disease|toxicity|\btoxic\b|degenerat|dystroph|deficienc|lysosomal|leukodystroph|tauopath|\bprion\b|acidopathy|cholestatic|alzheimer|dementia|parkinson|amyotrophic|motor neuron disease|huntington|\binclusion|deposit|mucinos|alcoholism|substance abuse|peroxisomal|mitochondrial|\belectrolyte|\blewy\b/i,
  ],
  [
    "Hematologic / Coagulation",
    /anemia|anaemia|hemoglobinopath|coagulation|thrombophilic|platelet|hemolytic|erythrocyte|von willebrand/i,
  ],
  [
    "Neoplastic",
    /neoplas|tumou?rs?\b|carcinoma|lymphoma|leuk[ae]mia|sarcoma|adenoma|blastoma|gliom|melanocytic|nevus|nevi\b|\bcyst|malignan|\bbenign\b|angioma|fibroma|papilloma|hamartoma|schwannoma|meningioma|chordoma|paraganglioma|hemangioma|myoma|lipoma|metasta|histiocyt/i,
  ],
  ["Laboratory / Testing", /\btest(?:s|ing)?\b|\bassay\b|molecular pathology/i],
  ["Organ System (unclassified by process)", /\bsystem\b|\btract\b/i],
];

function subcategoryProcessCategory(label) {
  const text = String(label || "");
  for (const [name, rx] of SUBCATEGORY_PROCESS_RULES) {
    if (rx.test(text)) return name;
  }
  return "General / Other";
}

/** Group a root's own direct subcategories by disease-process bucket — see
 * ONCOTREE_SUBCATEGORY_GROUP_THRESHOLD. Unlike buildOncotreeCategoryGroups
 * (leaf-level), nothing is ever dropped: every subcategory lands in some
 * group, worst case "General / Other". Returns null when grouping wouldn't
 * actually simplify anything (everything landed in one bucket). */
function buildOncotreeSubcategoryGroups(subcategories) {
  const byProcess = new Map();
  for (const sub of subcategories) {
    const cat = subcategoryProcessCategory(sub.label);
    if (!byProcess.has(cat)) byProcess.set(cat, []);
    byProcess.get(cat).push(sub);
  }
  if (byProcess.size < 2) return null;
  const groups = [...byProcess.entries()]
    .map(([label, subs]) => ({
      id: slugifyForTree(label),
      label,
      leaf_count: subs.reduce((sum, s) => sum + (s.leaf_count || 0), 0),
      subcategories: subs,
    }))
    // "General / Other" always last regardless of size — it's the leftover
    // bucket, not a first-class category to lead with.
    .sort((a, b) => {
      if (a.label === "General / Other") return 1;
      if (b.label === "General / Other") return -1;
      return b.leaf_count - a.leaf_count || a.label.localeCompare(b.label);
    });
  return groups;
}

/** Hand-curated "trunk" clusters — several genuinely-distinct ABPath
 * subcategories that are all facets of one diagnostic family and read as
 * confusing near-duplicate siblings when they fan out flat at the same
 * level (2026-08-02 feedback: "many permutations of a melanocytic type
 * branch... these should all be a layer of branches within a melanocytic
 * trunk"). Deliberately a short, audited list (exact subcategory label
 * match) rather than a generic auto-clusterer — a keyword-frequency sweep
 * of every root surfaced far more coincidental word overlaps (e.g. every
 * "X Reaction Pattern"/"X System"/"X Tumors" sharing one word) than
 * genuine families; only clusters that were unambiguously one family on
 * inspection are listed. Never touches subcategory identity/leaves —
 * purely one extra branch level at render time, like the disease-process
 * supergroups above. */
const SUBCATEGORY_TRUNK_MAP = {
  skin: [
    {
      trunk: "Melanocytic",
      labels: ["Melanocytic", "Melanocytic Nevi", "Malignant Melanocytic Lesions", "Melanocytoma", "Dermal Melanocytic Lesions"],
    },
    {
      trunk: "Reaction Patterns",
      labels: [
        "Granulomatous Reaction Pattern, Non-Infectious",
        "Interface Dermatitis (Lichenoid Reaction Pattern)",
        "Psoriasiform Reaction Pattern",
        "Spongiotic Reaction Pattern",
        "Vasculopathic Reaction Pattern",
        "Vesiculobullous Reaction Pattern",
      ],
    },
    {
      trunk: "Infiltrates",
      labels: [
        "Eosinophilic Infiltrates",
        "Histiocytic Infiltrates (Non-Langerhans Cell)",
        "Plasma Cell Infiltrates",
        "Xanthomatous Infiltrates",
      ],
    },
    {
      trunk: "Deposits",
      labels: [
        "Cutaneous Deposits",
        "Drug Deposits and Pigmentation",
        "Hyaline Deposits",
        "Miscellaneous Deposits",
        "Pigment and Related Deposits",
      ],
    },
  ],
  neuro: [
    {
      trunk: "Inclusions",
      labels: [
        "Cytoskeleton and Filamentous Inclusions",
        "Cytosolic Inclusions",
        "Membrane Bound Inclusions",
        "Neuronal Nuclear Inclusions",
      ],
    },
    {
      trunk: "Malformations",
      labels: ["Chiari Malformations", "Malformations of the Cerebellum", "Malformations of the Spinal Cord"],
    },
  ],
  heme: [
    {
      trunk: "Erythrocyte Disorders",
      labels: ["Erythrocyte & Plasma Infections", "Erythrocyte Enzyme Disorders", "Erythrocyte Membrane Disorders"],
    },
    {
      trunk: "Histiocytic / Dendritic Cell Disorders",
      labels: ["Histiocytic Dendritic", "Histiocytic Disorders", "Histiocytic/Dendritic Cell Neoplasms"],
    },
  ],
  forensic: [
    {
      trunk: "Toxicology",
      labels: [
        "Environmental and Industrial Toxicology",
        "Forensic Toxicology and Postmortem Chemistry",
        "Interpretive Toxicology",
      ],
    },
  ],
};

/** Applies SUBCATEGORY_TRUNK_MAP to a subcategory list, returning a mixed
 * array (trunk nodes tagged `_treeKind: "trunk"`, everything else left as
 * plain subcategory objects) in the SAME shape buildOncotreeLayout's
 * `visit()` already iterates for a "sub"-kind children list — trunk
 * members render one level deeper (visit() treats a "trunk" node's own
 * children as plain "sub"), everything not covered by a trunk passes
 * through completely unchanged. A no-op (returns `subcategories` as-is)
 * when this root has no curated trunks or none matched (>= 2 members
 * present). */
function applyTrunkGrouping(rootId, subcategories) {
  const trunkDefs = SUBCATEGORY_TRUNK_MAP[rootId];
  if (!trunkDefs || !subcategories.length) return subcategories;
  const byLabel = new Map(subcategories.map((s) => [s.label, s]));
  const claimed = new Set();
  const trunkNodes = [];
  for (const { trunk, labels } of trunkDefs) {
    const members = labels.map((l) => byLabel.get(l)).filter(Boolean);
    if (members.length < 2) continue;
    members.forEach((m) => claimed.add(m.id));
    trunkNodes.push({
      id: slugifyForTree(trunk),
      label: trunk,
      leaf_count: members.reduce((sum, m) => sum + (m.leaf_count || 0), 0),
      subcategories: members,
      _treeKind: "trunk",
    });
  }
  if (!trunkNodes.length) return subcategories;
  const ungrouped = subcategories.filter((s) => !claimed.has(s.id));
  // Trunks first (they're the "headline" groupings), then whatever wasn't
  // claimed, in its original order.
  return [...trunkNodes, ...ungrouped];
}

/** Build the OncoTree-style layout: nodes with computed {x,y}, and the
 * bezier links between parent and child. Only expanded nodes recurse into
 * their children; collapsed nodes occupy exactly one row.
 *
 * `extraExpanded` force-expands paths beyond the user's manual toggles (used
 * to auto-reveal the ancestor chain down to an in-tree search match).
 * `isMatch(leafNode)` flags a leaf for highlighting when searching. */
function buildOncotreeLayout(roots, options = {}) {
  const extraExpanded = options.extraExpanded || null;
  const isMatchFn = options.isMatch || null;
  const zoom = oncotreeZoom();
  const rowH = ONCOTREE_BASE_ROW_HEIGHT * zoom;
  const colW = ONCOTREE_BASE_COL_WIDTH * zoom;
  const nodes = [];
  const links = [];
  let rowCursor = 0;
  // A node's own (x,y) isn't known until AFTER all of its children have been
  // visited (its row is the average of theirs) — so a parent->child link
  // can't be drawn at the moment the child is visited. Record path pairs
  // during the recursive pass instead, then resolve them to coordinates
  // once every node's final position is known (see pathToNode below).
  const linkPairs = [];

  function visit(kind, node, depth, color, path, ancestorRootId, ancestorSubId) {
    const isLeaf = kind === "leaf";
    const rootIdForNode = kind === "root" ? node.id : ancestorRootId;
    const subIdForNode = kind === "sub" ? node.id : ancestorSubId;
    const expanded = !isLeaf && (browseTreeExpanded.has(path) || Boolean(extraExpanded && extraExpanded.has(path)));
    const isMatch = isLeaf && isMatchFn ? isMatchFn(node) : false;
    // Long WHO subtype names (e.g. "B lymphoblastic leukaemia/lymphoma with
    // recurrent genetic abnormality, <gene>") used to all truncate to the
    // same identical prefix on one fixed-height row, making distinct
    // entities indistinguishable at a glance. Wrap onto a second line
    // instead — same column width, twice the row height — rather than
    // widening the column (2026-08-02 feedback: "instead of 300 max gets
    // 300x2 max").
    const isTall = isLeaf && formatDisplayLabel(node.label).length > ONCOTREE_TALL_LABEL_CHARS;
    let midRow;
    let truncatedNote = null;
    if (isLeaf || !expanded) {
      midRow = rowCursor;
      rowCursor += isTall ? 2 : 1;
    } else {
      // While an in-tree search is active, only show what's relevant to it
      // — otherwise a single match inside a 19-leaf subcategory drags in
      // every unrelated sibling as noise and stretches the connecting
      // curves across most of the canvas for no reason.
      let children;
      let childKind;
      let categoryDroppedCount = 0;
      if (kind === "root") {
        const allSubs = node.subcategories || [];
        let processGroups = null;
        if (!isMatchFn && allSubs.length > ONCOTREE_SUBCATEGORY_GROUP_THRESHOLD) {
          processGroups = buildOncotreeSubcategoryGroups(allSubs);
        }
        if (processGroups) {
          childKind = "supergroup";
          children = processGroups;
        } else {
          childKind = "sub";
          children = allSubs;
          if (!isMatchFn) children = applyTrunkGrouping(rootIdForNode, children);
          if (isMatchFn && extraExpanded) {
            children = children.filter((c) => extraExpanded.has(`${path}::${c.id}`));
          }
        }
      } else if (kind === "supergroup") {
        childKind = "sub";
        children = node.subcategories || [];
        if (!isMatchFn) children = applyTrunkGrouping(rootIdForNode, children);
      } else if (kind === "trunk") {
        childKind = "sub";
        children = node.subcategories || [];
      } else if (kind === "sub") {
        let leaves = node.leaves || [];
        if (isMatchFn) leaves = leaves.filter((l) => isMatchFn(l));
        let categorized = null;
        if (!isMatchFn && leaves.length > ONCOTREE_GROUP_THRESHOLD) {
          categorized = buildOncotreeCategoryGroups(leaves);
        }
        if (categorized) {
          childKind = "group";
          children = categorized.groups;
          categoryDroppedCount = categorized.droppedCount;
        } else {
          // No usable categorical structure (e.g. a purely ABPath-sourced
          // subcategory) — show flat rather than force a fake grouping.
          childKind = "leaf";
          children = leaves.slice(0, ONCOTREE_LEAF_CAP_PER_SUB);
        }
      } else {
        // kind === "group"
        childKind = "leaf";
        children = (node.leaves || []).slice(0, ONCOTREE_LEAF_CAP_PER_SUB);
      }
      const hiddenCount =
        kind === "sub" && !isMatchFn && childKind === "leaf"
          ? Math.max(0, (node.leaves || []).length - children.length)
          : categoryDroppedCount;
      const hiddenReason = categoryDroppedCount > 0 ? "no_category" : "cap";
      if (!children.length) {
        midRow = rowCursor;
        rowCursor += 1;
      } else {
        const childMids = [];
        children.forEach((child, i) => {
          // A trunk-grouped child (see applyTrunkGrouping) overrides the
          // otherwise-uniform childKind for this one item; everything else
          // in the list still uses childKind as before.
          const kindForChild = child._treeKind || childKind;
          const childPath = `${path}::${kindForChild === "leaf" ? i : child.id}`;
          linkPairs.push({ parentPath: path, childPath, color });
          const mid = visit(kindForChild, child, depth + 1, color, childPath, rootIdForNode, subIdForNode);
          childMids.push(mid);
        });
        if (hiddenCount > 0) {
          truncatedNote = { row: rowCursor, count: hiddenCount, reason: hiddenReason };
          rowCursor += 1;
        }
        // True average of ALL children (not just first/last) — keeps the
        // parent near the actual "center of mass" of its children instead
        // of producing a long, exaggerated S-curve when one child is heavily
        // expanded (many rows) while its siblings sit collapsed nearby.
        midRow = childMids.reduce((sum, m) => sum + m, 0) / childMids.length;
      }
    }
    const x = depth * colW;
    const y = midRow * rowH;
    const label = formatDisplayLabel(node.label);
    nodes.push({
      kind,
      path,
      depth,
      x,
      y,
      color,
      label,
      isMatch,
      isTall,
      hasChildren: !isLeaf,
      expanded,
      leafCount:
        kind === "root" || kind === "sub" || kind === "group" || kind === "supergroup" || kind === "trunk"
          ? node.leaf_count
          : null,
      leaf: isLeaf ? node : null,
      rootId: rootIdForNode,
      subId: subIdForNode,
    });
    if (truncatedNote) {
      const noteLabel =
        truncatedNote.reason === "no_category"
          ? `${truncatedNote.count} without a clear category — hidden here, use search`
          : `+${truncatedNote.count} more — use search`;
      nodes.push({
        kind: "more",
        path: `${path}::more`,
        depth: depth + 1,
        x: (depth + 1) * colW,
        y: truncatedNote.row * rowH,
        color,
        label: noteLabel,
        hasChildren: false,
      });
      links.push({
        x1: x,
        y1: y,
        x2: (depth + 1) * colW,
        y2: truncatedNote.row * rowH,
        color,
      });
    }
    return midRow;
  }

  const rootMids = [];
  const rootColors = [];
  for (const root of roots) {
    const color = oncotreeDotColor(root.id, root.label);
    rootColors.push(color);
    rootMids.push(visit("root", root, 1, color, root.id));
  }
  if (rootMids.length) {
    const superMidRow = rootMids.reduce((sum, m) => sum + m, 0) / rootMids.length;
    const superY = superMidRow * rowH;
    nodes.push({
      kind: "super",
      path: "__all__",
      depth: 0,
      x: 0,
      y: superY,
      color: "#4a4a4a",
      label: "All Diagnoses",
      hasChildren: false,
    });
    roots.forEach((root, i) => {
      linkPairs.push({ parentPath: "__all__", childPath: root.id, color: rootColors[i] });
    });
  }

  // Every node's final (x,y) is now known (including the synthetic
  // "All Diagnoses" super-root pushed just above) — resolve the recorded
  // parent->child path pairs into actual drawable link coordinates. Missing
  // endpoints (shouldn't happen, but a layout bug here should never crash
  // the whole tree) are silently skipped.
  const pathToNode = new Map();
  for (const n of nodes) pathToNode.set(n.path, n);
  for (const pair of linkPairs) {
    const from = pathToNode.get(pair.parentPath);
    const to = pathToNode.get(pair.childPath);
    if (!from || !to) continue;
    links.push({ x1: from.x, y1: from.y, x2: to.x, y2: to.y, color: pair.color });
  }
  return { nodes, links, totalRows: rowCursor, rowH, colW };
}

function renderOncotreeHtml(roots, options = {}) {
  const { nodes, links, totalRows, rowH, colW } = buildOncotreeLayout(roots, options);
  const maxDepth = nodes.reduce((m, n) => Math.max(m, n.depth), 0);
  const width = (maxDepth + 1) * colW + 40;
  const height = Math.max(totalRows * rowH + 24, 200);
  const dotSize = Math.max(8, Math.round(10 * oncotreeZoom()));

  let svg = `<svg class="oncotree-links" width="${width}" height="${height}" aria-hidden="true">`;
  for (const link of links) {
    const midX = (link.x1 + link.x2) / 2;
    const off = dotSize / 2 + 4;
    svg += `<path d="M ${link.x1 + off} ${link.y1 + off} C ${midX} ${link.y1 + off}, ${midX} ${link.y2 + off}, ${link.x2 + off} ${link.y2 + off}" stroke="${link.color}" stroke-opacity="0.45" fill="none" stroke-width="1.5" />`;
  }
  svg += "</svg>";

  let nodesHtml = "";
  for (const n of nodes) {
    const top = n.y;
    const left = n.x;
    if (n.kind === "more") {
      nodesHtml += `<div class="oncotree-node oncotree-more" style="top:${top}px;left:${left}px;">${escapeHtml(n.label)}</div>`;
      continue;
    }
    if (n.kind === "super") {
      nodesHtml += `<div class="oncotree-node oncotree-super" style="top:${top}px;left:${left}px;font-size:${13 * oncotreeZoom()}px;"><span class="oncotree-dot" style="width:${dotSize}px;height:${dotSize}px;background:${n.color};border-color:${n.color};"></span><span class="oncotree-label">${escapeHtml(n.label)}</span></div>`;
      continue;
    }
    const dotClass = n.hasChildren ? "oncotree-dot oncotree-dot-branch" : "oncotree-dot";
    const caret = n.hasChildren ? `<span class="oncotree-caret">${n.expanded ? "\u25be" : "\u25b8"}</span>` : "";
    const countBadge =
      n.kind !== "leaf" && n.leafCount != null ? `<span class="oncotree-count">${n.leafCount}</span>` : "";
    const payload = escapeAttr(
      JSON.stringify({
        kind: n.kind,
        path: n.path,
        rootId: n.rootId,
        subId: n.subId,
        leaf: n.leaf
          ? { tag: n.leaf.tag, label: n.leaf.label, query: n.leaf.query, provenance: n.leaf.provenance || null }
          : null,
      }),
    );
    const classes = ["oncotree-node"];
    if (n.kind === "leaf") classes.push("oncotree-leaf");
    if (n.kind === "group") classes.push("oncotree-group");
    if (n.kind === "supergroup") classes.push("oncotree-supergroup");
    if (n.kind === "trunk") classes.push("oncotree-trunk");
    if (n.isMatch) classes.push("oncotree-match");
    if (n.isTall) classes.push("oncotree-tall");
    // Leaves get a small sibling VS button next to the label button — a
    // button can't nest inside another button (invalid HTML, and clicks
    // would double-fire), so wrap both in a plain positioned div instead.
    const isLeafNode = n.kind === "leaf";
    // A tall (long-label) leaf wraps onto a 2nd line within the same
    // column width instead of truncating — needs 2 rows' worth of height
    // (see ONCOTREE_TALL_LABEL_CHARS).
    const wrapStyle = n.isTall
      ? `top:${top}px;left:${left}px;height:${2 * rowH}px;`
      : `top:${top}px;left:${left}px;`;
    const wrapClass = n.isTall ? "oncotree-node-wrap oncotree-node-wrap-tall" : "oncotree-node-wrap";
    const wrapOpen = isLeafNode ? `<div class="${wrapClass}" style="${wrapStyle}">` : "";
    const wrapClose = isLeafNode ? "</div>" : "";
    const btnStyle = isLeafNode
      ? `font-size:${13 * oncotreeZoom()}px;`
      : `top:${top}px;left:${left}px;font-size:${13 * oncotreeZoom()}px;`;
    nodesHtml += wrapOpen;
    nodesHtml += `<button type="button" class="${classes.join(" ")}" style="${btnStyle}" data-node="${payload}" title="${escapeAttr(n.label)}">`;
    nodesHtml += `<span class="${dotClass}" style="width:${dotSize}px;height:${dotSize}px;background:${n.hasChildren ? "transparent" : n.color};border-color:${n.color};"></span>`;
    nodesHtml += `<span class="oncotree-label">${escapeHtml(n.label)}</span>${countBadge}${caret}`;
    nodesHtml += "</button>";
    if (isLeafNode) {
      const compareEntity = comparePayloadFromLeaf(n.rootId, n.subId, n.leaf);
      nodesHtml += renderVsButton(compareEntity, " oncotree-vs-btn");
    }
    nodesHtml += wrapClose;
  }

  return `<div class="oncotree-container"><div class="oncotree-canvas" style="width:${width}px;height:${height}px;">${svg}${nodesHtml}</div></div>`;
}

function oncotreeToolbarHtml() {
  const zoom = oncotreeZoom();
  const canZoomOut = browseTreeZoomIdx > 0;
  const canZoomIn = browseTreeZoomIdx < ONCOTREE_ZOOM_STEPS.length - 1;
  return `<div class="oncotree-toolbar">
    <button type="button" class="btn-secondary" id="oncotree-expand-organs" title="Expand every organ root to show its subcategories">Expand organs</button>
    <button type="button" class="btn-secondary" id="oncotree-collapse-all" title="Collapse everything back to the 17 organ roots">Collapse all</button>
    <span class="oncotree-zoom-group" role="group" aria-label="Zoom">
      <button type="button" class="btn-secondary" id="oncotree-zoom-out" ${canZoomOut ? "" : "disabled"} title="Zoom out">\u2212</button>
      <span class="oncotree-zoom-label">${Math.round(zoom * 100)}%</span>
      <button type="button" class="btn-secondary" id="oncotree-zoom-in" ${canZoomIn ? "" : "disabled"} title="Zoom in">+</button>
    </span>
  </div>`;
}

function bindOncotreeToolbarHandlers(onRerender) {
  document.getElementById("oncotree-expand-organs")?.addEventListener("click", () => {
    for (const r of activeBrowseRoots()) browseTreeExpanded.add(r.id);
    onRerender();
  });
  document.getElementById("oncotree-collapse-all")?.addEventListener("click", () => {
    browseTreeExpanded.clear();
    onRerender();
  });
  document.getElementById("oncotree-zoom-out")?.addEventListener("click", () => {
    browseTreeZoomIdx = Math.max(0, browseTreeZoomIdx - 1);
    onRerender();
  });
  document.getElementById("oncotree-zoom-in")?.addEventListener("click", () => {
    browseTreeZoomIdx = Math.min(ONCOTREE_ZOOM_STEPS.length - 1, browseTreeZoomIdx + 1);
    onRerender();
  });
}

function bindOncotreeHandlers(roots, onRerender) {
  browseContentEl.querySelectorAll(".oncotree-node[data-node]").forEach((el) => {
    el.addEventListener("click", () => {
      const data = JSON.parse(el.dataset.node);
      if (data.kind === "leaf") {
        const leaf = data.leaf || {};
        browseState = {
          level: "leaf",
          categoryId: data.rootId,
          subcategoryId: data.subId,
          tag: leaf.tag,
          label: leaf.label,
          query: leaf.query,
          provenance: leaf.provenance || null,
        };
        renderBrowseView();
        return;
      }
      if (browseTreeExpanded.has(data.path)) {
        browseTreeExpanded.delete(data.path);
      } else {
        browseTreeExpanded.add(data.path);
      }
      onRerender();
    });
  });
}

/** Small (?) affordance that opens the "How to use Browse" modal instead of
 * permanently-visible instructional paragraphs cluttering the tree. */
function infoButtonHtml() {
  return `<button type="button" id="browse-info-btn" class="oncotree-info-btn" title="How to use Browse" aria-label="How to use Browse">?</button>`;
}

function bindInfoButtonHandler() {
  document.getElementById("browse-info-btn")?.addEventListener("click", () => {
    infoModal?.classList.remove("hidden");
  });
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
    const hasAbpathNav =
      navSources.includes("abpath_content_spec") || navSources.includes("abpath");
    if (!hasAbpathNav || !navSources.includes("who") || rules.pathout_nav !== false) {
      throw new Error("Browse index default nav_sources are not WHO + ABPath content-spec only");
    }
    if (rules.bloated_abpath_ontology_excluded === false) {
      throw new Error("Browse index still claims bloated ABPath ontology nav");
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
      label_dedupe_within_root: "one leaf per root+display_label; prefer abpath > both > who > pathout",
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

/** Subtype adjectives that must be queried explicitly — bare "LCIS" should
 * resolve to classic lobular carcinoma in situ, not Florid/Pleomorphic.
 * Trailing "NOS" is handled separately (equivalence, not a penalty). */
const ENTITY_SUBTYPE_MODIFIERS = new Set([
  "florid",
  "pleomorphic",
  "classic",
  "atypical",
  "ebv",
  "kshv",
  "hhv8",
  "primary cutaneous",
  "leg type",
  "associated with chronic inflammation",
  "high grade with myc",
]);

function normalizeEntityName(name) {
  const base = String(name || "")
    .toLowerCase()
    .replace(/\([^)]*\)/g, " ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!base) return "";
  const tokens = base.split(" ").filter(Boolean);
  const tokenSet = new Set(tokens);
  // Expand abbrev tokens only when the expanded words are not already present.
  // Otherwise "Lobular Carcinoma In Situ LCIS" becomes the phrase twice and
  // loses the exact match against query "LCIS" → "lobular carcinoma in situ",
  // letting subtype leaves like Florid LCIS win on substring score.
  const expanded = [];
  for (const token of tokens) {
    const phrase = ENTITY_ABBREVIATION_EXPANSIONS[token];
    if (!phrase) {
      expanded.push(token);
      continue;
    }
    const words = phrase.split(" ").filter(Boolean);
    if (words.every((w) => tokenSet.has(w))) continue;
    expanded.push(...words);
  }
  return expanded.join(" ").replace(/\s+/g, " ").trim();
}

/** Built from the thinned full index when available (curated fallback until
 * loadBrowseIndex() resolves). Mutable (`let`), not a one-time IIFE const,
 * because the underlying roots can change once at startup when the generated
 * index finishes loading. */
function buildLeafIndex() {
  const list = [];
  const roots = activeBrowseRoots();
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

function leafHasUnrequestedSubtype(leaf, queryNorm) {
  const leafTokens = new Set(String(leaf?.normalized || "").split(" ").filter(Boolean));
  const queryTokens = new Set(String(queryNorm || "").split(" ").filter(Boolean));
  for (const mod of ENTITY_SUBTYPE_MODIFIERS) {
    if (leafTokens.has(mod) && !queryTokens.has(mod)) return true;
  }
  return false;
}

function pickBestLeaf(candidates, pageContext, queryNorm = "") {
  if (!candidates?.length) return null;
  let best = null;
  let bestScore = -Infinity;
  for (const leaf of candidates) {
    let score = scoreLeafForPageContext(leaf, pageContext);
    // Prefer classic entity over Florid/Pleomorphic when the user didn't ask
    // for that subtype (bare "LCIS" / "what is LCIS").
    if (leafHasUnrequestedSubtype(leaf, queryNorm)) score -= 50;
    // Prefer shorter/more exact labels when scores tie.
    score -= Math.min(String(leaf.normalized || "").length, 80) / 1000;
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
    return leafRefFrom(pickBestLeaf(exactMatches, ctx, norm));
  }

  if (fuzzyByScore.size) {
    // Re-rank all fuzzy hits with subtype penalty so bare "LCIS" does not
    // prefer Florid/Pleomorphic just because those labels contain the phrase.
    const allFuzzy = [];
    for (const leaves of fuzzyByScore.values()) allFuzzy.push(...leaves);
    const ranked = pickBestLeaf(allFuzzy, ctx, norm);
    if (ranked) {
      const rawScore =
        [...fuzzyByScore.entries()].find(([, leaves]) => leaves.includes(ranked))?.[0] || 0;
      const adj = leafHasUnrequestedSubtype(ranked, norm) ? rawScore - 0.3 : rawScore;
      if (adj >= 0.5 || ranked.normalized === norm) {
        return leafRefFrom(ranked);
      }
    }
  }
  return null;
}

const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const queryInput = document.getElementById("query-input");
const mentionDropdownEl = document.getElementById("mention-dropdown");
const sendBtn = document.getElementById("send-btn");
const modeHint = document.getElementById("mode-hint");
const maxResultsInput = document.getElementById("max-results");
const debugToggle = document.getElementById("debug-toggle");
const modelSelect = document.getElementById("model-select");
const SYNTHESIS_MODEL_KEY = "ph_synthesis_model_v0_1";

function selectedSynthesisModel() {
  return modelSelect?.value || null;
}

(function restoreSynthesisModelSelection() {
  if (!modelSelect) return;
  try {
    const stored = localStorage.getItem(SYNTHESIS_MODEL_KEY);
    if (stored && [...modelSelect.options].some((o) => o.value === stored)) {
      modelSelect.value = stored;
    }
  } catch (_err) {
    // ignore private-mode/quota failures — falls back to the default option
  }
  modelSelect.addEventListener("change", () => {
    try {
      localStorage.setItem(SYNTHESIS_MODEL_KEY, modelSelect.value);
    } catch (_err) {
      // ignore
    }
  });
})();
const healthStatus = document.getElementById("health-status");
const sourceCheckboxes = document.getElementById("source-checkboxes");
const exportPageBtn = document.getElementById("export-page-btn");
const exportStatus = document.getElementById("export-status");
const exportInfoBtn = document.getElementById("export-info-btn");
const exportInfoModal = document.getElementById("export-info-modal");
const citeHoverCard = document.getElementById("cite-hover-card");
const citeHoverImg = document.getElementById("cite-hover-img");
const citeHoverTitleEl = document.getElementById("cite-hover-title");
const citeHoverMetaEl = document.getElementById("cite-hover-meta");
const citeHoverExcerptEl = document.getElementById("cite-hover-excerpt");
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
const infoModal = document.getElementById("info-modal");
const homeBtn = document.getElementById("home-btn");

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

/** Strip the organ-root prefix from textbook source_id (e.g. hn_gnepp → Gnepp,
 * breast_atlas → Atlas). Prefer short book aliases over generic "Textbook(s)". */
function textbookLabel(sourceId) {
  if (!sourceId) return "Textbook";
  const parts = String(sourceId).split("_").filter(Boolean);
  if (parts.length < 2) {
    const one = String(sourceId).toLowerCase();
    if (TEXTBOOK_ALIASES[one]) return TEXTBOOK_ALIASES[one];
    if (one.includes("atlas")) return "Atlas";
    return formatDisplayLabel(sourceId);
  }
  parts.shift();
  const bookKey = parts.join("_").toLowerCase();
  if (TEXTBOOK_ALIASES[bookKey]) return TEXTBOOK_ALIASES[bookKey];
  // Token fallback: breast_diagnostic_atlas → Atlas, hn_gnepp_5e → Gnepp.
  for (const token of bookKey.split("_")) {
    if (TEXTBOOK_ALIASES[token]) return TEXTBOOK_ALIASES[token];
  }
  if (bookKey.includes("atlas")) return "Atlas";
  if (bookKey.includes("gnepp")) return "Gnepp";
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
  if (conflicts.length && conflicts.length === videos.length) {
    return {
      shown: [],
      hidden: videos,
      note: `${conflicts.length} lecture segment${conflicts.length === 1 ? "" : "s"} matched the wrong topic.`,
    };
  }
  // Nothing named the exact entity verbatim (common for narrow/rare
  // diagnoses — transcripts rarely say a specific rare-tumor name in full),
  // but at least one segment isn't flagged as wrong-topic — showing the
  // closest topic-area lecture segments is more useful to a resident than
  // an empty section with a phantom "Videos: N" badge above it (reported
  // 2026-08-01: BPOP page showed "Videos 8" but zero links anywhere).
  if (irrelevant.length) {
    const shown = irrelevant.slice(0, maxShown).map((row) => row.item);
    return {
      shown,
      hidden: conflicts.map((row) => row.item),
      note: "No lecture segment names this exact entity verbatim — showing the closest topic-area lecture segments instead.",
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

let activeCiteBySource = new Map();

/** URL -> {image, title, meta, excerpt} rich hover-card payload for every
 * live-literature/DOI citation on the current page (title/journal/year/
 * excerpt, never an image — see buildLiteratureByUrl()). */
let activeLiteratureByUrl = new Map();

/** Same shape, for every hub source (WHO/Pathoutlines/textbook/video) —
 * see buildCiteHoverIndex(). citeHoverPayload()/showCiteHoverCard() below
 * check both maps together for the actual hover-card UI. */
let activeCiteHoverByUrl = new Map();

function buildLiteratureByUrl(literatureCards) {
  const map = new Map();
  for (const card of literatureCards || []) {
    if (!card || typeof card !== "object") continue;
    const title = card.title || "Untitled";
    const journal = card.journal || card.source_name || "";
    const year = card.year || "";
    const mode = card.retrieval_mode || "";
    const excerpt = (card.excerpt || card.text || "").replace(/\s+/g, " ").trim().slice(0, 320);
    const doi = String(card.doi || "").trim();
    const doiUrl = doi ? (doi.startsWith("http") ? doi : `https://doi.org/${doi.replace(/^doi:/i, "")}`) : "";
    const entry = {
      image: null,
      title,
      meta: [journal, year, mode].filter(Boolean).join(" \u00b7 "),
      excerpt: excerpt || null,
    };
    for (const url of [pickHttp(card.source_url), pickHttp(card.url), pickHttp(doiUrl)]) {
      if (url && !map.has(url)) map.set(url, entry);
    }
  }
  return map;
}

/** Every non-literature evidence card (WHO/Pathoutlines/textbook/video) ->
 * a rich hover-card payload, keyed by every resolvable URL variant so an
 * inline citation link's own href finds it directly. Textbook/video cards
 * that have a real page image or a generated timestamped-frame thumbnail
 * carry it as `image` — per feedback (2026-08-02), when an image is
 * available the source name alone is enough context, so `excerpt` is left
 * null rather than also cramming in extracted page text; pure-text sources
 * (Pathoutlines, WHO entries with no page scan) fall back to a short
 * excerpt so hovering still shows something informative. */
function buildCiteHoverIndex(cards) {
  const map = new Map();
  const addUrl = (url, payload) => {
    if (typeof url === "string" && url.startsWith("http") && !map.has(url)) map.set(url, payload);
  };
  for (const card of cards || []) {
    if (!card || typeof card !== "object") continue;
    const src = String(card.source || "").toLowerCase();
    if (src === "literature") continue; // handled by buildLiteratureByUrl above
    const isVideo = src === "videos" || src === "lectures" || Boolean(card.video_id);
    const presentation = isVideo ? lectureCardPresentation(card) : cardPresentation(card);
    const hasImage = Boolean(presentation.previewUrl);
    const excerpt = cleanCardExcerptForHover(card.excerpt || card.text || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 240);
    const payload = {
      image: hasImage ? presentation.previewUrl : null,
      title: cardTitle(card),
      meta: [citationSourceLabel(card), isVideo ? formatVideoTimestamp(card) : null].filter(Boolean).join(" \u00b7 "),
      excerpt: hasImage ? null : excerpt || null,
    };
    const urlFields = isVideo
      ? ["video_time_url", "video_url", "source_url"]
      : ["source_url", "source_page_url", "source_pdf_url", "page_image_url", "figure_url", "image_url"];
    for (const field of urlFields) addUrl(card[field], payload);
  }
  return map;
}

function citeHoverPayload(url) {
  return activeCiteHoverByUrl.get(url) || activeLiteratureByUrl.get(url) || null;
}

/** Many hub-source chunks (Pathoutlines especially) carry a retrieval
 * metadata preamble ahead of their actual content — "Source: Pathology
 * Outlines Subject: ... Title: ... Header: ... URL: ... Primary tag:
 * X::Y::Z Clean text: <actual content>" — useful for retrieval, not for a
 * human-facing hover card. Strip it so the excerpt starts at real prose. */
function cleanCardExcerptForHover(text) {
  let s = String(text || "");
  s = s.replace(/^Source:.*?Primary tag:\s*\S+\s*/i, "");
  s = s.replace(/^(Clean text|Top headings):\s*/i, "");
  return s.trim();
}
/** Normalized WHO Classification of Tumours entity name → list of
 * {volume, url, text} candidates on the REAL tumourclassification.iarc.who.int
 * site (see who_genetic_syndromes_links_v0_1.json / scripts/
 * build_who_genetic_syndromes_links_v0_1.py — despite the filename this
 * covers general diagnostic entities, not just genetic syndromes). Loaded
 * once at startup so it is ready before the first topic page renders.
 * Coverage is partial (~31% of browse leaves) — unmatched entities keep
 * Pathology Hub's own WHO_HTML mirror link, which is still real WHO content,
 * just self-hosted. */
let whoLinksIndex = null;

/** Browse root → dominant WHO 5th-edition volume number, used to pick the
 * right candidate when a name is ambiguous across volumes (e.g. "Osteoma"
 * is a distinct chapter in Soft Tissue & Bone, Head & Neck, and Skin).
 * Empirically derived by cross-tabulating browse-leaf root vs. matched
 * volume counts — see docs/WHO_VOLUME_BY_ROOT_DERIVATION.md for the exact
 * counts and per-root confidence notes. */
const WHO_VOLUME_BY_ROOT = {
  bst: "33",
  breast: "32",
  skin: "64",
  endo: "53",
  eye_orbit: "65",
  gi: "31",
  gu: "36",
  gyn: "34",
  hn: "52",
  heme: "63",
  peds: "44",
  thorax_mediastinum: "35",
  neuro: "44", // lowest-confidence entry — shared plurality with peds
};

function normalizeSyndromeName(text) {
  let s = String(text || "").toLowerCase();
  s = s.replace(/\([^)]*\)/g, " "); // drop "(NF1)" gene-name parenthetical
  s = s.replace(/[^a-z0-9]+/g, " ");
  return s.replace(/\s+/g, " ").trim();
}

async function loadWhoSyndromeLinks() {
  try {
    const resp = await fetch("/static/who_genetic_syndromes_links_v0_1.json");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    whoLinksIndex = (data && data.entries) || {};
  } catch (err) {
    whoLinksIndex = {};
    // eslint-disable-next-line no-console
    console.warn("WHO chapter-link index unavailable; WHO cites stay on the internal mirror.", err);
  }
}

/** Real WHO URL for an entity, or null when it isn't covered by
 * who_genetic_syndromes_links_v0_1.json (most entities — those keep the
 * Pathology Hub WHO_HTML mirror link). Tries the leaf tag's last segment
 * first (cleanest, e.g. "Neurofibromatosis_Type_1"), then the display
 * label/query. When a name is ambiguous across WHO volumes, prefers the
 * candidate matching `rootId`'s dominant volume (WHO_VOLUME_BY_ROOT); falls
 * back to the first parsed candidate otherwise. */
function whoSyndromeUrlForEntity(tag, rootId, ...labels) {
  if (!whoLinksIndex) return null;
  const candidates = [];
  if (tag) {
    const lastSeg = String(tag).split("::").pop();
    if (lastSeg) candidates.push(lastSeg.replace(/_/g, " "));
  }
  for (const label of labels) {
    if (label) candidates.push(String(label));
  }
  const preferredVolume = WHO_VOLUME_BY_ROOT[rootId];
  for (const candidate of candidates) {
    const norm = normalizeSyndromeName(candidate);
    const matches = norm && whoLinksIndex[norm];
    if (!matches || !matches.length) continue;
    if (preferredVolume) {
      const preferred = matches.find((m) => m.volume === preferredVolume);
      if (preferred) return preferred.url;
    }
    return matches[0].url;
  }
  return null;
}

/** Real WHO URL for the entity on the CURRENTLY rendered topic page (set once
 * per renderTopicPageResult() call). Inline markdown WHO links have their
 * https://storage.googleapis.com/pathology-hub-0/WHO/WHO_HTML/... URL baked
 * directly into the stored answer_markdown text (unlike bare "(WHO)"
 * citations, which resolve their href from data.cards at render time) — so
 * rewriting data.cards alone isn't enough; renderInlineLink() below also
 * needs this to redirect an already-written mirror URL. */
let activeWhoOverrideUrl = null;

/** URL → short textbook name (Atlas, Gnepp, …) for cite label rewrite. */
let activeTextbookLabelByUrl = new Map();

function rememberTextbookUrlLabel(url, label) {
  const u = pickHttp(url);
  const book = String(label || "").trim();
  if (!u || !book || /^textbooks?$/i.test(book)) return;
  if (!activeTextbookLabelByUrl.has(u)) activeTextbookLabelByUrl.set(u, book);
}

function indexTextbookLabelsFromCards(cards, figures) {
  activeTextbookLabelByUrl = new Map();
  for (const card of cards || []) {
    if (!card || typeof card !== "object") continue;
    if (String(card.source || "").toLowerCase() !== "textbooks") continue;
    const book = textbookLabel(card.source_id);
    for (const field of [
      "source_url",
      "source_page_url",
      "source_pdf_url",
      "figure_url",
      "page_image_url",
      "image_url",
    ]) {
      rememberTextbookUrlLabel(card[field], book);
    }
    for (const fig of card.figures || []) {
      if (!fig || typeof fig !== "object") continue;
      rememberTextbookUrlLabel(fig.figure_url || fig.image_url || fig.url, book);
      rememberTextbookUrlLabel(fig.source_url || fig.source_page_url, book);
    }
  }
  for (const fig of figures || []) {
    if (!fig || typeof fig !== "object") continue;
    const src = String(fig.source || fig.source_kind || "").toLowerCase();
    const sid = String(fig.source_id || "");
    if (src !== "textbooks" && !sid) continue;
    if (src && src !== "textbooks" && src !== "inline_markdown") continue;
    if (!sid) continue;
    const book = textbookLabel(sid);
    rememberTextbookUrlLabel(fig.figure_url || fig.image_url || fig.url, book);
    rememberTextbookUrlLabel(fig.source_url || fig.source_page_url, book);
  }
}

/** Resolve Atlas/Gnepp/… from a cite URL when the model said generic Textbooks. */
function textbookLabelFromUrl(url) {
  const u = pickHttp(url);
  if (!u) return "";
  if (activeTextbookLabelByUrl.has(u)) return activeTextbookLabelByUrl.get(u);
  const lower = u.toLowerCase();
  if (lower.includes("atlas")) return "Atlas";
  if (lower.includes("gnepp")) return "Gnepp";
  if (lower.includes("cardesa")) return "Cardesa";
  if (lower.includes("vasef")) return "Vasef";
  if (lower.includes("biopsy")) return "Biopsy";
  if (lower.includes("dorfman")) return "Dorfman";
  if (lower.includes("horvai")) return "Horvai";
  if (lower.includes("enzinger")) return "Enzinger";
  return "";
}

function buildCiteBySource(cards, literatureCards) {
  const map = new Map();
  const setFirst = (key, url) => {
    if (!key || !url || map.has(key)) return;
    map.set(key, url);
  };
  const consider = (card) => {
    if (!card || typeof card !== "object") return;
    const src = String(card.source || "").toLowerCase();
    const doi = String(card.doi || "").trim();
    const doiUrl = doi ? (doi.startsWith("http") ? doi : `https://doi.org/${doi.replace(/^doi:/i, "")}`) : "";
    const url =
      pickHttp(card.source_url) ||
      pickHttp(card.source_page_url) ||
      pickHttp(doiUrl) ||
      pickHttp(card.video_time_url);
    if (!url) return;
    if (src === "who" || /who/i.test(String(card.source_name || ""))) setFirst("who", url);
    if (src === "pathout") setFirst("pathout", url);
    if (src === "textbooks") {
      setFirst("textbooks", url);
      const book = textbookLabel(card.source_id);
      if (book && !/^textbooks?$/i.test(book)) setFirst(book.toLowerCase(), url);
    }
    if (src === "videos") setFirst("videos", url);
    if (src === "lectures") setFirst("lectures", url);
    if (src === "literature" || doiUrl || /doi\.org/i.test(url)) setFirst("doi", url);
  };
  for (const card of cards || []) consider(card);
  for (const card of literatureCards || []) consider(card);
  return map;
}

function isDoiOrJournalUrl(url) {
  const u = String(url || "").toLowerCase();
  return (
    u.includes("doi.org") ||
    u.includes("pubmed.ncbi.nlm.nih.gov") ||
    u.includes("ncbi.nlm.nih.gov/pubmed") ||
    u.includes("ncbi.nlm.nih.gov/pmc") ||
    /\/doi\//.test(u)
  );
}

function citeDisplayLabel(label, url) {
  const raw = String(label || "").trim().replace(/^\(+|\)+$/g, "");
  const normalized = normalizeInlineLinkLabel(raw);
  // Generic "Textbooks" → specific book when the URL maps to breast_atlas etc.
  if (/^textbooks?$/i.test(normalized)) {
    return textbookLabelFromUrl(url) || "Textbook";
  }
  // Book-name chips (Gnepp/Atlas/Cardesa/Vasef/Biopsy/FAQ): the synthesis prompt
  // gives these as *examples* of a short book name, but the model sometimes
  // picks one reflexively instead of grounding in the citation's real
  // source_id (e.g. writing "Gnepp" — a Head & Neck atlas — for a Bone/Soft
  // Tissue citation that is actually softtissue_enzinger). Always prefer the
  // deterministic URL→book mapping (built from the real evidence cards) over
  // the model's text when the URL resolves to a book at all; only fall back
  // to the model's text for a URL we have no textbook mapping for.
  if (/^(Gnepp|Atlas|Cardesa|Vasef|Biopsy|FAQ|Dorfman|Horvai|Enzinger|Pattern)$/i.test(normalized)) {
    return textbookLabelFromUrl(url) || normalized;
  }
  // Keep non-textbook hub badges as-is.
  if (/^(WHO|Pathoutlines|Lectures|Videos)$/i.test(normalized)) {
    return normalized;
  }
  if (/^breast\s*atlas$/i.test(normalized)) return "Atlas";
  if (isDoiOrJournalUrl(url)) return "DOI";
  // Publisher / paper titles ("Virchows Archiv review", "fibroepithelial tumor review").
  if (/\b(review|archiv|virchow|modern\s*pathol|histopathol|journal|pubmed|doi)\b/i.test(raw)) {
    return "DOI";
  }
  if (
    cardSourceFromUrl(url) === "literature" ||
    String(url || "").includes("elsevier") ||
    String(url || "").includes("springer")
  ) {
    return "DOI";
  }
  // Textbook URL with a long model label → prefer short book name.
  const fromUrl = textbookLabelFromUrl(url);
  if (fromUrl && /textbook|atlas|gnepp|biopsy|cardesa|vasef/i.test(normalized)) {
    return fromUrl;
  }
  return normalized;
}

function cardSourceFromUrl(url) {
  const u = String(url || "").toLowerCase();
  if (!u) return "";
  if (u.includes("who") && u.includes("storage.googleapis.com")) return "who";
  if (u.includes("pathologyoutlines") || u.includes("pathout")) return "pathout";
  if (isDoiOrJournalUrl(u)) return "literature";
  return "";
}

/** Collapse ((WHO)) / (((Textbooks))) → (WHO) / (Textbooks) before linkify. */
function normalizeSourceParenLayers(text) {
  let s = String(text || "");
  s = s.replace(
    /\(+(\s*(?:WHO(?:\s+Blue\s+Books?)?|Pathoutlines?|PathOut(?:lines)?|Textbooks?|Textbook|Lectures?|Videos?|DOI|Atlas|Gnepp|Cardesa|Vasef|Biopsy)\s*)\)+/gi,
    "($1)",
  );
  // (([WHO](url))) → ([WHO](url)) — later unwrapped to [WHO](url).
  s = s.replace(/\(+(\s*\[[^\]]+\]\(https?:[^)\s]+\)\s*)\)+/g, "($1)");
  return s;
}

/** Turn bare (WHO)/(Pathoutlines)/(Atlas) into markdown links when we have a URL. */
function linkifyBareSourceParens(text) {
  let s = normalizeSourceParenLayers(text);
  const rules = [
    { re: /\(+WHO(?:\s+Blue\s+Books?)?\)+/gi, key: "who", label: "WHO" },
    { re: /\(+Pathoutlines?\)+/gi, key: "pathout", label: "Pathoutlines" },
    { re: /\(+PathOut(?:lines)?\)+/gi, key: "pathout", label: "Pathoutlines" },
    { re: /\(+Textbooks?\)+/gi, key: "textbooks", label: "Textbook" },
    { re: /\(+Atlas\)+/gi, key: "atlas", label: "Atlas" },
    { re: /\(+Gnepp\)+/gi, key: "gnepp", label: "Gnepp" },
    { re: /\(+Biopsy\)+/gi, key: "biopsy", label: "Biopsy" },
    { re: /\(+Lectures?\)+/gi, key: "lectures", label: "Lectures" },
    { re: /\(+Videos?\)+/gi, key: "videos", label: "Videos" },
  ];
  for (const rule of rules) {
    let url = activeCiteBySource.get(rule.key);
    if (!url && rule.key === "atlas") url = activeCiteBySource.get("textbooks");
    if (!url && rule.key === "gnepp") url = activeCiteBySource.get("textbooks");
    if (!url && rule.key === "biopsy") url = activeCiteBySource.get("textbooks");
    if (!url && rule.key === "textbooks") {
      // Prefer a concrete book URL when rewriting generic (Textbook).
      url =
        activeCiteBySource.get("atlas") ||
        activeCiteBySource.get("gnepp") ||
        activeCiteBySource.get("biopsy") ||
        activeCiteBySource.get("textbooks");
    }
    if (!url) continue;
    const label =
      rule.key === "textbooks" ? textbookLabelFromUrl(url) || rule.label : rule.label;
    s = s.replace(rule.re, `[${label}](${url})`);
  }
  return s;
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

    // Models often wrap each table row in a markdown bullet ("- | a | b |").
    // Detect that before the generic list renderer turns pipes into <li> text.
    const tableFromBullets = coerceBulletWrappedMarkdownTable(trimmed);
    if (tableFromBullets) {
      htmlBlocks.push(renderMarkdownTable(tableFromBullets));
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
  if (!lines.every((line) => line.includes("|"))) return false;
  // Require a real multi-column shape (avoids "see A | B" prose).
  return lines.some((line) => line.replace(/^\s*[-*]\s+/, "").split("|").filter((c) => c.trim()).length >= 2);
}

/** If every non-empty line is a bullet + pipe row, return cleaned table text. */
function coerceBulletWrappedMarkdownTable(block) {
  const lines = String(block || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) return null;
  if (!lines.every((line) => /^[-*]\s+/.test(line) && line.includes("|"))) return null;
  const stripped = lines.map((line) => line.replace(/^\s*[-*]\s+/, "")).join("\n");
  return isMarkdownTable(stripped) ? stripped : null;
}

/** Split mixed DDX content into table runs + leftover prose/bullets.
 * Models often emit "- | a | b |" rows then trailing lecture/DOI links. */
function splitDdxTablesAndProse(text) {
  const lines = String(text || "").split("\n");
  const parts = [];
  let proseBuf = [];
  const flushProse = () => {
    const blob = proseBuf.join("\n").trim();
    proseBuf = [];
    if (blob) parts.push({ type: "prose", text: blob });
  };
  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trim();
    if (!trimmed) {
      proseBuf.push(raw);
      i += 1;
      continue;
    }
    const stripped = trimmed.replace(/^[-*]\s+/, "");
    const looksTableRow = stripped.includes("|") && stripped.split("|").filter((c) => c.trim()).length >= 2;
    if (looksTableRow) {
      flushProse();
      const tableLines = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        if (!t) {
          i += 1;
          continue;
        }
        const s = t.replace(/^[-*]\s+/, "");
        if (!(s.includes("|") && s.split("|").filter((c) => c.trim()).length >= 2)) break;
        tableLines.push(s);
        i += 1;
      }
      if (tableLines.length >= 2 && isMarkdownTable(tableLines.join("\n"))) {
        parts.push({ type: "table", text: tableLines.join("\n") });
      } else {
        proseBuf.push(...tableLines.map((l) => `- ${l}`));
      }
      continue;
    }
    proseBuf.push(raw);
    i += 1;
  }
  flushProse();
  return parts;
}

function renderMarkdownTable(block) {
  const lines = block
    .split("\n")
    .map((line) => line.replace(/^\s*[-*]\s+/, "").trim())
    .filter((line) => line && !/^\|?[\s\-:|]+\|?$/.test(line));
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
  text = stripFigureReferences(linkifyBareSourceParens(text));
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

  // Unwrap "([WHO](url))" / "((DOI))" / "(([Atlas](url)))" so we never render ((WHO)).
  scratch = scratch.replace(/\(+(\s*\[([^\]]+)\]\((https?:[^)\s]+)\)\s*)\)+/g, "[$2]($3)");
  scratch = scratch.replace(/\(\s*\[([^\]]+)\]\((https?:[^)\s]+)\)\s*\)/g, "[$1]($2)");

  // Plain links: [label](url) -> preview-aware link when we recognize the URL,
  // otherwise a normal external link. Journal/DOI targets always show as (DOI).
  scratch = scratch.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (_, label, url) => {
    return stash(renderInlineLink(citeDisplayLabel(label, url), url, previewIndex));
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

/** WHO_HTML mirror URL → real WHO URL when the current page matched a
 * covered entity (see activeWhoOverrideUrl). Inline markdown links carry
 * their URL as literal text baked into the stored answer, so this has to
 * run at render time, not just once on data.cards. */
function resolveWhoOverrideUrl(url) {
  if (!activeWhoOverrideUrl) return url;
  if (!/pathology-hub-0\/WHO\/WHO_HTML\//i.test(String(url || ""))) return url;
  return activeWhoOverrideUrl;
}

function renderInlineLink(label, rawUrl, previewIndex) {
  const url = resolveWhoOverrideUrl(rawUrl);
  const preview = previewIndex?.get(url);
  const safeHref = escapeAttr(url);
  // Journal/DOI → "(DOI)". Hub sources stay bare "WHO"/"Textbooks" so surrounding
  // prose parentheses from the model do not become ((WHO)).
  const bare = String(label || "").replace(/^\(+|\)+$/g, "");
  const display = /^DOI$/i.test(bare) ? "(DOI)" : bare;
  const safeLabel = escapeHtml(display);
  // Rich hover card (image when one exists — textbook page scan, generated
  // timestamped video frame — plus title/source/excerpt) for every citation
  // type: DOI/literature, WHO, Pathoutlines, textbooks, videos. See
  // citeHoverPayload()/showCiteHoverCard(); bindPreviewHandlers() wires the
  // actual mouseenter/mouseleave listeners once this markup is in the DOM.
  const hoverPayload = citeHoverPayload(url);
  const hoverAttr = hoverPayload ? ` data-cite-hover="${escapeAttr(JSON.stringify(hoverPayload))}"` : "";
  const hoverClass = hoverPayload ? " inline-cite-link-hover" : "";
  if (preview?.previewUrl) {
    const payload = escapeAttr(JSON.stringify(preview));
    return `<a href="${safeHref}" target="_blank" rel="noopener" class="inline-cite-link${hoverClass}" data-preview="${payload}"${hoverAttr}>${safeLabel}</a>`;
  }
  return `<a href="${safeHref}" target="_blank" rel="noopener" class="inline-cite-link${hoverClass}"${hoverAttr}>${safeLabel}</a>`;
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
  // Ask always passes an explicit resolved mode; Browse hardcodes topic_page.
  const mode = modeOverride || "auto";
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
  // Browse category the user opened (heme/breast/…) — used as root-narrow
  // authority so a wrong extranodal board tag cannot drop on-root pathout/videos.
  if (mode === "topic_page" && options.browseRoot) {
    payload.browse_root = options.browseRoot;
  }
  if (options.rebuild) {
    payload.rebuild = true;
  }
  const chosenModel = selectedSynthesisModel();
  if (chosenModel && chosenModel !== "gpt-5.6-luna") {
    payload.model = chosenModel;
  }
  return payload;
}

/** Pull an entity name out of Ask phrasing like "what is LCIS?". */
function extractEntityFromAskQuery(query) {
  const q = String(query || "").trim();
  if (!q) return null;
  const m = q.match(
    /^(?:what\s+is|what'?s|whats|define|explain|tell\s+me\s+about|describe|features?\s+of|pathology\s+of|histology\s+of|criteria\s+for|workup\s+of)\s+(.+?)\??$/i,
  );
  if (m) return m[1].replace(/[?.!]+$/g, "").trim();
  // Visual / compare phrasing is not a bare entity label.
  if (VISUAL_QUERY_RE.test(q) || /\b(difference|differ|vs\.?|versus|compare|between)\b/i.test(q)) {
    return null;
  }
  // Bare short entity / abbreviation ("LCIS", "florid LCIS").
  if (/^[A-Za-z][A-Za-z0-9\- ]{0,40}$/.test(q) && q.split(/\s+/).length <= 6) {
    return q;
  }
  return null;
}

function expandAskEntity(entity) {
  const key = String(entity || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
  return ENTITY_ABBREVIATION_EXPANSIONS[key] || ENTITY_ABBREVIATION_EXPANSIONS[String(entity || "").toLowerCase()] || entity;
}

/**
 * Single Ask entry: infer the internal response shape from the query.
 * No user-facing mode picker — Browse still forces topic_page separately.
 */
function planAskRequest(rawQuery) {
  const q = String(rawQuery || "").trim();
  if (!q) {
    return { query: q, mode: "gpt_like", leaf: null, routed: false, routeNote: "" };
  }

  if (/\b(sources?\s+only|search\s+only|raw\s+evidence|no\s+synthesis|just\s+(the\s+)?(sources|cards|evidence))\b/i.test(q)) {
    return {
      query: q,
      mode: "search_only",
      leaf: null,
      routed: true,
      routeNote: "Inferred: raw evidence cards only (no synthesis).",
    };
  }

  if (/\b(html\s+teaching|teaching\s+page|lecture\s+handout)\b/i.test(q)) {
    return {
      query: q,
      mode: "html_teaching",
      leaf: null,
      routed: true,
      routeNote: "Inferred: HTML teaching page.",
    };
  }

  if (/\b(difference|differ|vs\.?|versus|compare|comparison|between)\b/i.test(q)) {
    return {
      query: q,
      mode: "compare_sources",
      leaf: null,
      routed: true,
      routeNote: "Inferred: comparison answer across sources.",
    };
  }

  const entity = extractEntityFromAskQuery(q);
  const looksTopic =
    Boolean(entity) ||
    /\b(diagnostic\s+criteria|differential\s+diagnosis|molecular\s+features|gross\s+(pathology|findings)|microscopic\s+features|ancillary\s+(studies|tests)|clinical\s+features)\b/i.test(
      q,
    );

  if (looksTopic && entity && !/\b(difference|differ|vs\.?|versus|compare|between)\b/i.test(entity)) {
    let leaf = findTaxonomyMatch(entity, null);
    if (leaf) leaf = resolveBoardMappedLeaf(leaf) || leaf;
    if (leaf) {
      const label = leaf.label || entity;
      return {
        query: leaf.query || leaf.label || entity,
        mode: "topic_page",
        leaf,
        routed: true,
        routeNote: `Inferred topic page for ${formatDisplayLabel(label)}.`,
      };
    }
    const expanded = expandAskEntity(entity);
    return {
      query: expanded,
      mode: "topic_page",
      leaf: null,
      routed: true,
      routeNote: `Inferred topic page for “${entity}”.`,
    };
  }

  if (looksTopic && !entity) {
    return {
      query: q,
      mode: "topic_page",
      leaf: null,
      routed: true,
      routeNote: "Inferred topic-page reference from the query.",
    };
  }

  if (VISUAL_QUERY_RE.test(q)) {
    return {
      query: q,
      mode: "visual",
      leaf: null,
      routed: true,
      routeNote: "Inferred: figure-focused answer.",
    };
  }

  return { query: q, mode: "gpt_like", leaf: null, routed: false, routeNote: "" };
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
  hideCiteHoverCard();
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

/** Fixed-position rich hover card (image + title/source/excerpt) for any
 * inline citation with a data-cite-hover payload — see citeHoverPayload().
 * Positioned near the anchor's own bounding box, flipped above/left when it
 * would otherwise overflow the viewport. */
function showCiteHoverCard(anchorEl, payload) {
  if (!citeHoverCard || !payload) return;
  if (payload.image) {
    citeHoverImg.src = payload.image;
    citeHoverImg.alt = payload.title || "";
    citeHoverImg.hidden = false;
  } else {
    citeHoverImg.hidden = true;
    citeHoverImg.removeAttribute("src");
  }
  citeHoverTitleEl.textContent = payload.title || "";
  citeHoverMetaEl.textContent = payload.meta || "";
  citeHoverExcerptEl.textContent = payload.excerpt ? `\u201c${payload.excerpt}\u201d` : "";
  citeHoverCard.classList.remove("hidden");
  citeHoverCard.setAttribute("aria-hidden", "false");

  const rect = anchorEl.getBoundingClientRect();
  const cardRect = citeHoverCard.getBoundingClientRect();
  const margin = 8;
  let top = rect.bottom + margin;
  let left = rect.left;
  if (top + cardRect.height > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - cardRect.height - margin);
  }
  if (left + cardRect.width > window.innerWidth - margin) {
    left = Math.max(margin, window.innerWidth - cardRect.width - margin);
  }
  citeHoverCard.style.top = `${top}px`;
  citeHoverCard.style.left = `${left}px`;
}

function hideCiteHoverCard() {
  if (!citeHoverCard) return;
  citeHoverCard.classList.add("hidden");
  citeHoverCard.setAttribute("aria-hidden", "true");
}

/** Wires hover listeners for every citation link with a rich hover payload
 * (data-cite-hover, attached in renderInlineLink) within `root`. Re-run on
 * every render since content is replaced wholesale (innerHTML), same as
 * bindVsButtons/bindPreviewHandlers elsewhere in this file. */
function bindCiteHoverHandlers(root) {
  root.querySelectorAll("[data-cite-hover]").forEach((el) => {
    let payload = null;
    try {
      payload = JSON.parse(el.dataset.citeHover);
    } catch (_err) {
      return;
    }
    el.addEventListener("mouseenter", () => showCiteHoverCard(el, payload));
    el.addEventListener("mouseleave", hideCiteHoverCard);
    el.addEventListener("focus", () => showCiteHoverCard(el, payload));
    el.addEventListener("blur", hideCiteHoverCard);
  });
}

function bindPreviewHandlers(root) {
  scrubDefectiveImages(root);
  bindCiteHoverHandlers(root);
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
    healthFlags.scopusSanitize = data.scopus_paren_sanitize === true;
    healthFlags.buildMarker = data.build_marker || "";
    healthFlags.buildSha = data.build_git_sha || "";

    const hubKey = data.secrets?.pathology_hub?.present;
    const openaiKey = data.secrets?.openai?.present;
    const backendOk = data.backend?.ok;
    const outdatedBuild = !healthFlags.streamEndpoint || !healthFlags.scopusSanitize;
    healthStatus.className = "status";
    if (outdatedBuild) {
      healthStatus.classList.add("error");
      healthStatus.textContent = "Outdated server — pull iterative branch";
      healthStatus.title =
        "This process is NOT cursor/topic-iterative-sse-layout-9231 (missing " +
        "topic_page_iterative / scopus_paren_sanitize). Elsevier LCIS 400s and " +
        "missing thinking panel mean the wrong checkout is still running. " +
        "git fetch && git checkout cursor/topic-iterative-sse-layout-9231 && " +
        "restart ./scripts/run_local.sh — look for startup log " +
        "[chat-mvp] BUILD=topic-iterative-sse-layout-9231";
    } else if (backendOk && hubKey) {
      healthStatus.classList.add("ok");
      const bits = [openaiKey ? "Ready" : "Ready (search-only)"];
      if (healthFlags.streamEndpoint && healthFlags.iterative) bits.push("live thinking");
      if (healthFlags.liveLiterature) bits.push("literature");
      if (healthFlags.buildSha) bits.push(healthFlags.buildSha);
      healthStatus.textContent = bits.join(" · ");
      healthStatus.title =
        `Build ${healthFlags.buildMarker || "ok"} @ ${healthFlags.buildSha || "?"} — ` +
        "iterative SSE + Scopus parenthesis sanitize active.";
    } else if (!hubKey) {
      healthStatus.classList.add("warn");
      healthStatus.textContent = "API key missing";
      healthStatus.title = "PATHOLOGY_HUB_API_KEY is not configured for this app instance.";
    } else {
      healthStatus.classList.add("warn");
      healthStatus.textContent = "Backend unreachable";
      // Distinct from this chat app itself, which just answered this health
      // check fine — "backend" is the separate upstream pathology-hub-v04
      // Cloud Run service (textbooks/WHO/Pathoutlines/video search) this
      // app calls into. A cold start after scale-to-zero or a transient
      // 5xx there is the usual cause; it's normally transient.
      const backendUrl = data.backend?.url || "the pathology-hub-v04 API";
      const backendStatus = data.backend?.status_code;
      healthStatus.title =
        `This chat app is fine — the separate evidence backend it depends on (${backendUrl}) ` +
        `did not respond${backendStatus ? ` (HTTP ${backendStatus})` : ""}. Usually a transient ` +
        "cold start after scale-to-zero; try again in a few seconds or refresh.";
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
  if (modeHint) modeHint.textContent = AUTO_MODE_HINT;
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

/** Parses a fetch Response as JSON, but never throws a raw SyntaxError up
 * to the caller — if the body isn't valid JSON (e.g. a proxy/infrastructure
 * layer in front of this app returning a plain-text "upstream request
 * timeout" instead of the app's own JSON error, reported 2026-08-02 on
 * /api/compare when the evidence backend was down), returns a normalized
 * `{ok: false, error: <readable message>}` instead so callers always get
 * a real, displayable error string rather than "SyntaxError: Unexpected
 * token…". */
async function parseJsonResponseSafely(resp) {
  const rawText = await resp.text();
  try {
    return JSON.parse(rawText);
  } catch (_err) {
    const looksLikeInfra = /upstream|gateway|timeout|bad gateway|<html/i.test(rawText);
    const detail = rawText.trim().slice(0, 200) || `HTTP ${resp.status}`;
    return {
      ok: false,
      error: looksLikeInfra
        ? "The server didn't respond in time (likely a transient Cloud Run cold start or the evidence backend being unreachable). Try again in a few seconds."
        : `Unexpected non-JSON response: ${detail}`,
    };
  }
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
        model: selectedSynthesisModel(),
      }),
    });
    const data = await parseJsonResponseSafely(resp);
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
  hideCiteHoverCard();
  renderBrowseBreadcrumbs();
  // The Browse-home tree/tile filter is now driven by the single top query
  // overlay input rather than its own in-page search box — keep it in sync
  // regardless of which code path reset browseFilterQuery (breadcrumbs,
  // tile clicks, leaf navigation, …). Only touch the box while Browse is
  // actually the visible tab and the user isn't mid-keystroke in it, so a
  // background re-render can never clobber an in-progress Ask question or
  // move the caret while typing.
  if (queryInput && askViewEl.classList.contains("hidden") && document.activeElement !== queryInput) {
    queryInput.value = browseState.level === "home" ? browseFilterQuery : "";
  }
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
  const fullRoots = getBrowseNavRootsFull();
  const showingIndexed = usingIndex && Boolean(fullRoots);
  const roots = activeBrowseRoots();

  // Browse is tree-only now — the tile grid only ever appears as a
  // degraded fallback when the tag index itself failed to load (its
  // curated taxonomy uses a different, string-only shape the tree can't
  // render). No mode toggle, no "OncoTree" branding — see infoButtonHtml()
  // for the one small (?) affordance that explains how to use it.
  if (!showingIndexed) {
    let html = '<p class="hint">Browse tag index unavailable — showing the curated starter taxonomy fallback instead. Not a claim about what is indexed.</p>';
    html += '<div class="browse-tile-grid">';
    for (const root of roots) {
      const style = rootTileStyle(root.id, root.label);
      const countLabel = `${root.leaf_count} topic${root.leaf_count === 1 ? "" : "s"}`;
      html += `<button type="button" class="browse-tile" data-category-id="${escapeAttr(root.id)}" style="background:${style.gradient}">`;
      html += `<span class="browse-tile-glyph">${escapeHtml(style.glyph)}</span>`;
      html += `<span class="browse-tile-banner"><span class="browse-tile-label">${escapeHtml(formatDisplayLabel(root.label))}</span><span class="browse-tile-count">${countLabel}</span></span>`;
      html += "</button>";
    }
    html += "</div>";
    browseContentEl.innerHTML = html;
    browseContentEl.querySelectorAll(".browse-tile").forEach((el) => {
      el.addEventListener("click", () => {
        browseFilterQuery = "";
        browseState = { level: "category", categoryId: el.dataset.categoryId };
        renderBrowseView();
      });
    });
    return;
  }

  const treeSearchQuery = browseFilterQuery.trim();
  let treeSearchMatches = null;
  if (treeSearchQuery) {
    treeSearchMatches = collectLeavesFromRoots(roots).filter((row) => leafMatchesBrowseFilter(row.leaf, browseFilterQuery));
  }
  const useInlineTreeSearch = treeSearchQuery && treeSearchMatches.length > 0 && treeSearchMatches.length <= ONCOTREE_SEARCH_INLINE_CAP;

  let html = '<div class="oncotree-topbar">';
  html += oncotreeToolbarHtml();
  html += infoButtonHtml();
  html += "</div>";

  if (!treeSearchQuery || useInlineTreeSearch) {
    let treeOptions = {};
    if (useInlineTreeSearch) {
      const matchSet = new Set(treeSearchMatches.map((row) => row.leaf));
      const extraExpanded = new Set();
      for (const row of treeSearchMatches) {
        extraExpanded.add(row.root.id);
        extraExpanded.add(`${row.root.id}::${row.sub.id}`);
      }
      treeOptions = { extraExpanded, isMatch: (leafNode) => matchSet.has(leafNode) };
      html += `<p class="hint">${treeSearchMatches.length} match${treeSearchMatches.length === 1 ? "" : "es"} for "${escapeHtml(treeSearchQuery)}" — highlighted below, ancestors auto-expanded.</p>`;
    }
    html += renderOncotreeHtml(roots, treeOptions);
    browseContentEl.innerHTML = html;
    bindOncotreeToolbarHandlers(() => renderBrowseView());
    bindInfoButtonHandler();
    bindOncotreeHandlers(roots, () => renderBrowseView());
    bindVsButtons(browseContentEl);
    if (useInlineTreeSearch) {
      const firstMatchEl = browseContentEl.querySelector(".oncotree-match");
      firstMatchEl?.scrollIntoView({ block: "center" });
    }
    return;
  }

  // Degenerate query (near-every-leaf match, e.g. a single letter) — flat
  // list instead of an unnavigable wall of expanded tree nodes.
  html += `<p class="hint">${treeSearchMatches.length} matches — too many to highlight in the tree; showing a flat list instead. Refine your search to narrow it.</p>`;
  html += '<div class="chevron-list">';
  for (const row of treeSearchMatches.slice(0, 120)) {
    const compareEntity = comparePayloadFromLeaf(row.root.id, row.sub.id, row.leaf);
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
    html += '<div class="browse-leaf-row">';
    html += `<button type="button" class="chevron-item browse-search-hit" data-leaf="${leafPayload}"><span>${escapeHtml(row.displayLabel)} <span class="chevron-count">(${escapeHtml(formatDisplayLabel(row.root.label))})</span></span><span class="chevron">\u203a</span></button>`;
    html += renderVsButton(compareEntity);
    html += "</div>";
  }
  html += "</div>";
  if (treeSearchMatches.length > 120) {
    html += `<p class="hint">Showing first 120 matches — refine your search to narrow further.</p>`;
  }
  browseContentEl.innerHTML = html;
  bindInfoButtonHandler();
  bindVsButtons(browseContentEl);
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
}

function renderBrowseCategory(categoryId) {
  const cat = findCategory(categoryId);
  if (!cat) {
    browseState = { level: "home" };
    renderBrowseView();
    return;
  }
  const showingIndexed = Boolean(browseIndex && getBrowseNavRootsFull());
  let html = `<h2 class="browse-heading">${escapeHtml(formatDisplayLabel(cat.label))}</h2>`;
  html += showingIndexed
    ? '<p class="hint">WHO + ABPath content-spec tags for this root. Pick a subcategory, then a topic — or filter on the next screen when lists are long.</p>'
    : '<p class="hint">Starter topic list for navigation — not a claim about what is indexed. Pick a subcategory, then a specific diagnosis.</p>';
  if (showingIndexed) {
    html += browseSearchBarHtml(`Search within ${formatDisplayLabel(cat.label)}…`, browseFilterQuery);
  }
  const subs = (cat.subcategories || []).filter((sub) => {
    if (!browseFilterQuery.trim()) return true;
    return (sub.leaves || []).some((leaf) => leafMatchesBrowseFilter(leaf, browseFilterQuery));
  });
  if (showingIndexed && browseFilterQuery.trim()) {
    html += `<p class="hint">${subs.length} subcategor${subs.length === 1 ? "y" : "ies"} with matches.</p>`;
  }
  html += '<div class="chevron-list">';
  for (const sub of subs) {
    const matchCount = browseFilterQuery.trim()
      ? (sub.leaves || []).filter((leaf) => leafMatchesBrowseFilter(leaf, browseFilterQuery)).length
      : sub.leaf_count;
    html += `<button type="button" class="chevron-item" data-sub-id="${escapeAttr(sub.id)}"><span>${escapeHtml(formatSubcategoryLabel(sub.label))}${showingIndexed ? ` <span class="chevron-count">(${matchCount})</span>` : ""}</span><span class="chevron">\u203a</span></button>`;
  }
  html += "</div>";
  browseContentEl.innerHTML = html;
  if (showingIndexed) {
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
  const showingIndexed = Boolean(browseIndex && getBrowseNavRootsFull());
  const allLeaves = sub.leaves || [];
  const filteredLeaves = allLeaves.filter((leaf) => leafMatchesBrowseFilter(leaf, browseFilterQuery));
  const hasFilter = Boolean(browseFilterQuery.trim());
  const visibleLeaves = hasFilter ? filteredLeaves : filteredLeaves.slice(0, BROWSE_LEAF_PREVIEW_CAP);
  const hiddenCount = hasFilter ? 0 : Math.max(0, filteredLeaves.length - visibleLeaves.length);

  let html = `<h2 class="browse-heading">${escapeHtml(formatDisplayLabel(cat.label))} — ${escapeHtml(formatSubcategoryLabel(sub.label))}</h2>`;
  html += showingIndexed
    ? '<p class="hint">Pick a topic to load a grounded topic page. Long lists are capped until you search.</p>'
    : '<p class="hint">Pick a diagnosis to load a live, grounded topic page from current evidence.</p>';
  if (showingIndexed || allLeaves.length > BROWSE_LEAF_PREVIEW_CAP) {
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
  if (showingIndexed || allLeaves.length > BROWSE_LEAF_PREVIEW_CAP) {
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
  "Cytology",
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

function diversifyFiguresBySource(figures) {
  const groups = new Map();
  const order = [];
  for (const fig of figures || []) {
    const src = String(fig?.source || fig?.source_kind || "unknown").toLowerCase();
    if (!groups.has(src)) {
      groups.set(src, []);
      order.push(src);
    }
    groups.get(src).push(fig);
  }
  // Prefer WHO / textbooks / pathout early so WHO photos are not crowded out.
  const prefer = ["who", "textbooks", "pathout", "videos", "lectures", "literature", "inline_markdown", "unknown"];
  const ranked = [
    ...prefer.filter((s) => order.includes(s)),
    ...order.filter((s) => !prefer.includes(s)),
  ];
  const out = [];
  let progress = true;
  while (progress) {
    progress = false;
    for (const src of ranked) {
      const bucket = groups.get(src);
      if (bucket?.length) {
        out.push(bucket.shift());
        progress = true;
      }
    }
  }
  return out;
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
  return diversifyFiguresBySource(merged).slice(0, maxShown);
}

/** Map figure modality → topic-page section that should own its gallery. */
const FIGURE_MODALITY_SECTION = {
  imaging: "Imaging Features",
  gross: "Gross Features",
  microscopic: "Microscopic",
  cytology: "Cytology",
  ihc: "Ancillary Tests",
};

/** Classify a retrieved/inline figure into imaging / gross / cytology / microscopic / ihc / other. */
function classifyFigureModality(fig) {
  const blob = [
    fig?.caption,
    fig?.title,
    fig?.alt,
    fig?.section,
    fig?.section_heading,
    fig?.chunk_type,
    fig?.figure_id,
    fig?.source_id,
    fig?.primary_tag,
    fig?.figure_url,
    fig?.image_url,
    fig?.url,
    fig?.excerpt,
  ]
    .map((x) => String(x || "").toLowerCase())
    .join(" ");
  const src = String(fig?.source || "").toLowerCase();
  const sid = String(fig?.source_id || "").toLowerCase();
  const explicit = String(fig?.modality || fig?.figure_kind || fig?.image_type || "").toLowerCase();

  if (explicit) {
    if (/\b(gross|macro)/.test(explicit)) return "gross";
    if (/\b(cyto)/.test(explicit)) return "cytology";
    if (/\b(imag|radio|mammo|ultrasound|mri|ct)\b/.test(explicit)) return "imaging";
    if (/\b(ihc|immuno)/.test(explicit)) return "ihc";
    if (/\b(histo|micro)/.test(explicit)) return "microscopic";
  }

  const imaging = /\b(mammograms?|mammog\w*|ultrasound|sonograph|\bmri\b|magnetic resonance|\bct\b|radiographs?|x-?rays?|pet[- ]?ct|fluoroscop\w*|radiolog\w*)\b/.test(
    blob,
  );
  const strongGross = /\b(gross\s+(photo|photograph|image|appearance|findings?|features?)|macroscopic|cut[- ]surface|external\s+surface)\b/.test(
    blob,
  );
  // "specimen" alone is too weak — micro captions often say "resection specimen, H&E".
  const weakGross = /\b(gross|fresh tissue|resection specimen|excised mass|operative specimen)\b/.test(blob);
  const ihc = /\b(ihc|immuno[- ]?histochem|immunostain|immuno stain|her2|er\/pr|ki-?67|cd\d{1,3}|cytokeratin|stain for)\b/.test(
    blob,
  );
  const cytology =
    sid.startsWith("cyto_") ||
    /\bcyto[_-]/.test(sid) ||
    /\b(cytolog|cytopath|\bfna\b|fine[- ]needle|smear|diff[- ]?quik|pap stain|liquid[- ]based|exfoliativ|bethesda|yokohama|imprint cytolog|cytospin|papanicolaou)\b/.test(
      blob,
    );
  const histology = /\b(h&amp;e|h&e|h\/e|histolog|histopath|photomicro|tissue section|low[- ]power|high[- ]power|microscop|papillary\s+fronds?|fibrovascular|ductal\s+hyperplasia)\b/.test(
    blob,
  ) || /\b(nuclear|cytoplasm|architecture|ductal|lobular|acin|stroma|epithelial)\b/.test(blob);

  // Imaging before weak gross; mammograms must not sit under Microscopic.
  if (imaging && !histology && !cytology) return "imaging";
  if (cytology && !strongGross) return "cytology";
  if (ihc && !strongGross) return "ihc";
  // Histology beats weak "specimen/gross" wording so micro photos leave Gross Features.
  if (histology && !strongGross) return "microscopic";
  if (strongGross) return "gross";
  if (weakGross && !histology && !imaging && !cytology) return "gross";
  if (imaging) return "imaging";
  if (histology) return "microscopic";
  // WHO / PathOut / textbook figures without a cue are usually histology tissue photos.
  // (Cytology books are caught above via cyto_ source_id.)
  if (src === "pathout" || src === "textbooks" || src === "who") return "microscopic";
  return "other";
}

/** When the model inlined a figure under the wrong section, prefer modality. */
function sectionForFigureModality(claimedSection, modality) {
  const modalitySection = FIGURE_MODALITY_SECTION[modality];
  if (!modalitySection || modality === "other") return claimedSection || "other";
  if (!claimedSection || claimedSection === "other") return modalitySection;
  if (claimedSection !== modalitySection) return modalitySection;
  return claimedSection;
}

/**
 * Bucket figures into section galleries. Inline placement is a hint only —
 * caption/URL modality wins when it conflicts (micro under Gross, etc.).
 */
function bucketFiguresBySection(retrievedFigures, sections) {
  const buckets = {
    "Imaging Features": [],
    "Gross Features": [],
    Microscopic: [],
    Cytology: [],
    "Ancillary Tests": [],
    other: [],
  };
  const used = new Set();
  const push = (sectionKey, fig) => {
    const url = figureGalleryUrl(fig);
    const key = sectionKey && buckets[sectionKey] ? sectionKey : "other";
    if (!url || used.has(url)) return;
    used.add(url);
    buckets[key].push(fig);
  };

  const richByUrl = new Map();
  for (const fig of retrievedFigures || []) {
    const url = figureGalleryUrl(fig);
    if (url && !richByUrl.has(url)) richByUrl.set(url, fig);
  }

  for (const name of Object.keys(buckets)) {
    if (name === "other") continue;
    for (const fig of extractInlineFiguresFromMarkdown(findSectionContent(sections, name))) {
      const rich = richByUrl.get(fig.figure_url) || {};
      const merged = {
        ...rich,
        ...fig,
        caption: fig.caption || rich.caption || rich.title,
        source: fig.source || rich.source,
        source_id: fig.source_id || rich.source_id,
        excerpt: rich.excerpt || rich.text || fig.excerpt,
      };
      const modality = classifyFigureModality(merged);
      const target = sectionForFigureModality(name, modality);
      push(target, { ...merged, _modality: modality });
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
  // No "Microscopic gallery" / "____ gallery" subtitle — the section header
  // already names the modality; keep the thumbs only.
  return (
    `<div class="section-gallery" data-section-gallery="${escapeAttr(sectionName)}">` +
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

  const parts = splitDdxTablesAndProse(text);
  if (parts.some((p) => p.type === "table")) {
    let html = "";
    for (const part of parts) {
      if (part.type === "table") {
        html += renderMarkdownTable(part.text);
      } else {
        html += renderDifferentialBulletList(part.text, previewIndex, ctx);
      }
    }
    return html || '<p class="hint">Not covered in retrieved evidence.</p>';
  }

  return renderDifferentialBulletList(text, previewIndex, ctx);
}

function renderDifferentialBulletList(text, previewIndex, pageContext = null) {
  const ctx = pageContext || pageContextFromBrowseState();
  const items = [];
  for (const rawLine of String(text || "").split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const match = line.match(/^[-*]\s*\*\*(.+?)\*\*\s*[-\u2014:]*\s*(.*)$/);
    if (!match) {
      // Trailing markdown cites (often journal/DOI) — keep them; display label
      // is normalized to (DOI) / WHO / etc. inside inlineMarkdown.
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
  // figures = retrieved pool; show ALL beside Key Facts, and also bucket into
  // Imaging / Gross / Micro / IHC section galleries below.
  const allFigures = figures || [];
  const buckets = bucketFiguresBySection(allFigures, sections);
  const gallerySections = new Set([
    "Imaging Features",
    "Gross Features",
    "Microscopic",
    "Cytology",
    "Ancillary Tests",
  ]);

  let html = '<div class="topic-page">';
  if (sectionHasContent(keyFacts) || allFigures.length) {
    html += '<div class="topic-page-top">';
    if (sectionHasContent(keyFacts)) {
      html += `<div class="topic-key-facts"><div class="topic-panel-title">Key Facts</div>${renderMarkdown(keyFacts, previewIndex)}</div>`;
    }
    if (allFigures.length) {
      html += '<div class="topic-gallery"><div class="topic-panel-title">Selected Images</div>';
      html += renderTopicGallery(allFigures, { maxItems: 16 });
      html += "</div>";
    }
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
      '<p class="hint">Figures that could not be confidently placed under Imaging, Gross, Microscopic, Cytology, or Ancillary Tests.</p>';
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

/** Compact source chips under the board map so missing textbooks are obvious. */
function renderEvidenceSourceBar(data, shownOverrides = {}) {
  const cards = data?.cards || [];
  const order = ["textbooks", "who", "pathout", "videos", "literature"];
  const counts = countItemsBySource(cards);
  if ((data.literature || []).length && !counts.literature) {
    counts.literature = data.literature.length;
  }
  const chips = [];
  for (const src of order) {
    const retrieved = counts[src] || 0;
    const shown = shownOverrides[src];
    // When a query-relevance filter hid some/all retrieved cards of this
    // source (e.g. lecture segments that don't name a rare diagnosis
    // verbatim — see filterVideoCardsByRelevance), the chip must say so
    // instead of a bare "N" that implies N are visible below when 0 are.
    const n = shown != null ? shown : retrieved;
    const label = SOURCE_LABELS[src] || src;
    const cls = n > 0 ? "source-chip ok" : "source-chip missing";
    const countText = shown != null && shown !== retrieved ? `${shown}/${retrieved} shown` : String(n);
    chips.push(`<span class="${cls}">${escapeHtml(label)} <strong>${countText}</strong></span>`);
  }
  const tb = counts.textbooks || 0;
  let note = "";
  if (tb === 0) {
    note =
      '<p class="hint source-chip-note">No textbook cards in this evidence bundle — hub Round 1 may have missed; try Rebuild. WHO/Pathout/literature may still support the page.</p>';
  }
  return `<div class="evidence-source-bar" aria-label="Evidence sources used">${chips.join("")}${note}</div>`;
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
  const pageRoot = debug?.page_root || (entryMeta?.tag?.includes("::") ? tagBrowseRootId(entryMeta.tag) : null);
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
    return parseJsonResponseSafely(fallback);
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

/** Single compact "Tag: <tag path>" line on a built topic page — the full
 * board/curriculum breadcrumb prose (root > subcategory > category > leaf)
 * is redundant with the machine tag path itself and with the breadcrumbs
 * already shown above the page (see renderBrowseBreadcrumbs), so it isn't
 * repeated here. Falls back to the human Browse path only when there is no
 * formal ABPath/WHO tag at all. */
function renderEntryTagsHeader(tag, provenance, entryMeta = null) {
  if (tag) {
    return `<div class="topic-tags-header curriculum-tagline"><span class="topic-tags-label">Tag:</span> <code class="curriculum-tag-path">${escapeHtml(tag)}</code></div>`;
  }
  const pathSegments = browsePathSegments(entryMeta || {});
  if (!pathSegments.length && !provenance) return "";
  const provenanceLabel =
    formatNavProvenanceLabel(provenance) || "Browse path only — open from Full index for ABPath board tags";
  if (!pathSegments.length) {
    return `<div class="topic-tags-header curriculum-tagline"><span class="hint">${escapeHtml(provenanceLabel)}</span></div>`;
  }
  return `<div class="topic-tags-header curriculum-tagline"><span class="topic-tags-label">Tag:</span> <code class="curriculum-tag-path">${escapeHtml(pathSegments.join(" › "))}</code></div>`;
}

function literatureProviderLabel(key) {
  const k = String(key || "").toLowerCase();
  if (k.includes("scopus") || k === "elsevier") return "Elsevier Scopus";
  if (k.includes("pubmed")) return "PubMed";
  if (k.includes("oncokb")) return "OncoKB";
  if (k.includes("europe")) return "Europe PMC";
  return key;
}

function renderLiteratureProviderStatus(debug) {
  const providers = debug?.literature_providers;
  if (!providers || typeof providers !== "object") return "";
  const parts = [];
  for (const [name, meta] of Object.entries(providers)) {
    if (!meta || typeof meta !== "object") continue;
    const label = literatureProviderLabel(name);
    if (meta.ok) {
      const n = typeof meta.returned === "number" ? meta.returned : "?";
      const total = meta.total != null ? ` / ${meta.total} total` : "";
      const skipped = meta.skipped ? ` (${meta.skipped})` : "";
      const abs =
        typeof meta.abstracts_filled === "number" ? `, ${meta.abstracts_filled} with abstract` : "";
      parts.push(`${label}: ok (${n}${total}${abs})${skipped}`);
    } else {
      const err = meta.error === "missing_api_key" ? "missing provider key" : meta.error || "unknown";
      parts.push(`${label}: failed (${err})`);
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
  // Genetic-syndrome pages: point WHO citations at the real WHO
  // Classification of Tumours site instead of only Pathology Hub's own
  // WHO_HTML mirror, when this entity is one of the ~2,175 hereditary
  // tumour predisposition syndromes covered by
  // who_genetic_syndromes_links_v0_1.json. No-op (keeps the mirror link)
  // for every other (non-syndrome) entity — most WHO citations are
  // unaffected. Mutates card objects in place so exports/compare views also
  // pick up the corrected link.
  const whoUrl = whoSyndromeUrlForEntity(entryMeta?.tag, entryMeta?.categoryId, query, entryMeta?.label);
  activeWhoOverrideUrl = whoUrl || null;
  if (whoUrl && Array.isArray(data.cards)) {
    for (const card of data.cards) {
      if (card && String(card.source || "").toLowerCase() === "who") {
        card.source_url = whoUrl;
        card.url = whoUrl;
      }
    }
  }
  // Display caps mirror the actual backend retrieval caps (TOPIC_PAGE_MAX_CARDS=120,
  // TOPIC_PAGE_MAX_FIGURES=40 in pathology_backend.py) — these used to be
  // much smaller (20/16) than what was actually retrieved and sent to
  // synthesis, so the page looked far shallower than the real evidence base.
  const cardFilter = filterByQueryRelevance(query, data.cards || [], { maxShown: 80 });
  const sortedCards = cardFilter.shown.length ? cardFilter.shown : data.cards || [];
  const rawLiterature =
    data.literature || sortedCards.filter((c) => (c.source || "") === "literature");
  // Same relevance gate as figures/cards — hide prostate/etc. off-targets on breast pages.
  const litFilter = filterByQueryRelevance(query, rawLiterature, { maxShown: 10 });
  const literatureCards = litFilter.shown.length ? litFilter.shown : [];
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
  // Enables bare (WHO)/(Pathoutlines)/(Atlas) → real links, and journal labels → (DOI).
  activeCiteBySource = buildCiteBySource(data.cards || [], literatureCards);
  activeLiteratureByUrl = buildLiteratureByUrl(literatureCards);
  activeCiteHoverByUrl = buildCiteHoverIndex(data.cards || []);
  indexTextbookLabelsFromCards(data.cards || [], shownFigures);
  const pageContext = pageContextFromEntryMeta(entryMeta);
  const tag = entryMeta?.tag || null;
  const provenance = entryMeta?.provenance || null;

  // Board/curriculum hierarchy at the top (ABPath/WHO tag path when known).
  let html = renderEntryTagsHeader(tag, provenance, entryMeta);
  html += renderEvidenceSourceBar(data, { videos: lectureCards.length, literature: literatureCards.length });
  html += renderTopicPage(
    sections,
    previewIndex,
    sectionFigurePool,
    data.who_cross_mentions || [],
    lectureCards,
    pageContext,
  );
  html += renderLiteratureStrip(literatureCards, data.debug || null);
  if (litFilter.note) html += `<p class="hint">${escapeHtml(litFilter.note)}</p>`;
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
    const model = data?.model || cachedMeta?.model || "";
    const parts = ["Prebuilt page — loaded instantly from cache."];
    if (when) parts.push(`Built ${formatCachedTimestamp(when)}.`);
    if (model) parts.push(`Model: ${model}.`);
    parts.push("Click Rebuild for a fresh live query with up-to-date evidence.");
    return `<p class="hint topic-cache-hint">${escapeHtml(parts.join(" "))}</p>`;
  }
  if (data?.cache_saved) {
    return `<p class="hint topic-cache-hint">Saved this page for the next visitor.</p>`;
  }
  return "";
}

function formatCachedTimestamp(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch (err) {
    return iso;
  }
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
    // Prebuilt/cached pages should load instantly — that is the entire point
    // of prebuilding. Always check the cache first (unless the user asked to
    // Rebuild); only fall through to a live SSE build on a cache miss.
    let cachedMeta = null;
    const allowCache = !rebuild && Boolean(leafRef.tag);
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
          browseRoot: leafRef.categoryId || browseState.categoryId || null,
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

/** @mention entity picker: type "@" anywhere in the top query box to search
 * the full entity index and insert a clean, disambiguated reference — click
 * a suggestion (or its "+") to insert "@Label; " and keep typing more
 * mentions. Works from any tab/view (unlike the tree-only live-filter
 * below and the tree's VS button, both of which are only reachable from
 * Browse). On submit, 2+ resolved mentions route straight to Compare
 * instead of a live chat answer; exactly 1 mention with no other text opens
 * that entity's topic page directly; mixed mentions + a question clean the
 * @/; syntax out of the text sent to the model (keeping the disambiguated
 * entity name) so retrieval isn't confused by the raw syntax. */
let mentionInsertions = []; // ordered {label, leafRef} picked via the dropdown; positionally matched to parsed @mentions on submit so a dropdown pick always resolves to the exact entity chosen, even when its label collides with another root's same-named entity.
let mentionActiveIndex = -1;

function currentMentionContext() {
  const val = queryInput.value;
  const pos = queryInput.selectionStart ?? val.length;
  const uptoCursor = val.slice(0, pos);
  const lastAt = uptoCursor.lastIndexOf("@");
  if (lastAt === -1) return null;
  const between = uptoCursor.slice(lastAt + 1);
  if (between.includes(";") || between.includes("@")) return null; // already-closed mention
  return { start: lastAt, end: pos, text: between };
}

function mentionSuggestionsFor(text) {
  const query = String(text || "").trim();
  const pool = TAXONOMY_LEAF_INDEX;
  if (!query) return pool.slice(0, 8);
  const norm = normalizeEntityName(query);
  const scored = [];
  for (const leaf of pool) {
    const hay = leaf.normalized || "";
    let score = -1;
    if (hay === norm) score = 100;
    else if (hay.startsWith(norm)) score = 80;
    else if (hay.includes(` ${norm}`)) score = 60;
    else if (norm.length >= 3 && hay.includes(norm)) score = 40;
    if (score > 0) scored.push({ leaf, score });
  }
  scored.sort((a, b) => b.score - a.score || a.leaf.entityName.length - b.leaf.entityName.length);
  return scored.slice(0, 8).map((s) => s.leaf);
}

function closeMentionDropdown() {
  if (!mentionDropdownEl) return;
  mentionDropdownEl.classList.add("hidden");
  mentionDropdownEl.innerHTML = "";
  mentionDropdownEl._suggestions = null;
  mentionDropdownEl._ctx = null;
  mentionActiveIndex = -1;
}

function renderMentionDropdown(suggestions, ctx) {
  if (!mentionDropdownEl) return;
  if (!suggestions.length) {
    closeMentionDropdown();
    return;
  }
  // Positioned in JS (not CSS) because .query-overlay is sticky and its
  // rendered height/width varies (e.g. wraps on narrow screens).
  const rect = form.getBoundingClientRect();
  mentionDropdownEl.style.top = `${rect.bottom}px`;
  mentionDropdownEl.style.left = `${rect.left}px`;
  mentionDropdownEl.style.width = `${rect.width}px`;
  let html = "";
  suggestions.forEach((leaf, i) => {
    const active = i === mentionActiveIndex ? " active" : "";
    html += `<div class="mention-row${active}" data-idx="${i}">`;
    const rootLabel = findCategory(leaf.categoryId)?.label || leaf.categoryId || "";
    html += `<span class="mention-row-label">${escapeHtml(formatDisplayLabel(leaf.label))}</span>`;
    html += `<span class="mention-row-path">${escapeHtml(formatDisplayLabel(rootLabel))}</span>`;
    html += `<button type="button" class="mention-add-btn" data-idx="${i}" title="Add to query">+</button>`;
    html += `</div>`;
  });
  mentionDropdownEl.innerHTML = html;
  mentionDropdownEl.classList.remove("hidden");
  mentionDropdownEl._suggestions = suggestions;
  mentionDropdownEl._ctx = ctx;
  mentionDropdownEl.querySelectorAll("[data-idx]").forEach((el) => {
    // mousedown (not click) fires before the input blurs, so selectionStart
    // in selectMentionSuggestion() still reflects where the user was typing.
    el.addEventListener("mousedown", (event) => {
      event.preventDefault();
      selectMentionSuggestion(Number(el.dataset.idx));
    });
  });
}

function selectMentionSuggestion(idx) {
  const suggestions = mentionDropdownEl?._suggestions || [];
  const ctx = mentionDropdownEl?._ctx;
  const leaf = suggestions[idx];
  if (!leaf || !ctx) return;
  const label = formatDisplayLabel(leaf.label);
  const before = queryInput.value.slice(0, ctx.start);
  const after = queryInput.value.slice(ctx.end);
  const insertion = `@${label}; `;
  queryInput.value = `${before}${insertion}${after}`;
  const caret = before.length + insertion.length;
  queryInput.focus();
  queryInput.setSelectionRange(caret, caret);
  mentionInsertions.push({ label, leafRef: leafRefFrom(leaf) });
  closeMentionDropdown();
}

function updateMentionDropdown() {
  const ctx = currentMentionContext();
  if (!ctx) {
    closeMentionDropdown();
    return;
  }
  mentionActiveIndex = 0;
  renderMentionDropdown(mentionSuggestionsFor(ctx.text), ctx);
}

queryInput.addEventListener("keydown", (event) => {
  if (!mentionDropdownEl || mentionDropdownEl.classList.contains("hidden")) return;
  const suggestions = mentionDropdownEl._suggestions || [];
  if (!suggestions.length) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    mentionActiveIndex = Math.min(mentionActiveIndex + 1, suggestions.length - 1);
    renderMentionDropdown(suggestions, mentionDropdownEl._ctx);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    mentionActiveIndex = Math.max(mentionActiveIndex - 1, 0);
    renderMentionDropdown(suggestions, mentionDropdownEl._ctx);
  } else if (event.key === "Enter" || event.key === "Tab") {
    if (mentionActiveIndex >= 0) {
      event.preventDefault();
      selectMentionSuggestion(mentionActiveIndex);
    }
  } else if (event.key === "Escape") {
    closeMentionDropdown();
  }
});

queryInput.addEventListener("click", updateMentionDropdown);
document.addEventListener("click", (event) => {
  if (mentionDropdownEl && !mentionDropdownEl.contains(event.target) && event.target !== queryInput) {
    closeMentionDropdown();
  }
});

/** Parse "@Label;" segments out of the submitted query text. Resolves each
 * to an exact leaf via the positional dropdown-insertion record when
 * available (correct even when the label collides with a same-named entity
 * in a different root), falling back to a fuzzy TAXONOMY_LEAF_INDEX match
 * for hand-typed/edited mentions. `cleanedQuery` strips the @/; syntax
 * while keeping each mention's plain entity name in place, for the mixed
 * mentions+question case. */
function parseQueryMentions(text) {
  const mentionRe = /@([^;@]+);?/g;
  const mentions = [];
  let match;
  while ((match = mentionRe.exec(text))) {
    const label = match[1].trim();
    if (label) mentions.push({ raw: match[0], label });
  }
  const cleanedQuery = text
    .replace(mentionRe, (_full, rawLabel) => rawLabel.trim())
    .replace(/\s+/g, " ")
    .trim();
  const freeText = text.replace(mentionRe, " ").replace(/\s+/g, " ").trim();
  const resolved = mentions
    .map((m, i) => {
      const tracked = mentionInsertions[i];
      if (tracked && tracked.label.toLowerCase() === m.label.toLowerCase()) return tracked.leafRef;
      const norm = normalizeEntityName(m.label);
      let best = TAXONOMY_LEAF_INDEX.find((l) => l.normalized === norm);
      if (!best) best = TAXONOMY_LEAF_INDEX.find((l) => l.entityName.toLowerCase() === m.label.toLowerCase());
      if (!best) best = TAXONOMY_LEAF_INDEX.find((l) => norm.length > 3 && l.normalized.includes(norm));
      return best ? leafRefFrom(best) : null;
    })
    .filter(Boolean);
  return { mentions, freeText, cleanedQuery, resolved };
}

/** Dual function of the top query overlay: while the Browse tab is showing
 * its home tree/tile grid, typing live-filters it (same box, no separate
 * search input); pressing Enter still asks a full question via the submit
 * handler below regardless of what's currently typed. */
queryInput.addEventListener("input", () => {
  updateMentionDropdown();
  if (!askViewEl.classList.contains("hidden")) return;
  if (browseState.level !== "home") return;
  // Once the user starts an @mention, the raw "@Label; @Label2" text isn't
  // meaningful as a plain tree-filter query (and would otherwise show a
  // confusing "0 matches" message stacked behind the mention dropdown) —
  // leave the tree showing whatever it last showed until mentions are done.
  if (queryInput.value.includes("@")) return;
  browseFilterQuery = queryInput.value;
  renderBrowseHome();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const rawQuery = queryInput.value.trim();
  if (!rawQuery) return;
  closeMentionDropdown();

  if (rawQuery.includes("@")) {
    const { resolved, freeText, cleanedQuery } = parseQueryMentions(rawQuery);
    mentionInsertions = [];
    if (resolved.length >= 2) {
      // 2+ entities mentioned — go straight to Compare, same destination as
      // the tree's VS button, but reachable from any tab.
      compareSet = resolved.map((r) => comparePayloadFromLeaf(r.categoryId, r.subcategoryId, r));
      renderCompareTray();
      browseFilterQuery = "";
      queryInput.value = "";
      browseState = { level: "compare" };
      setActiveView("browse");
      renderBrowseView();
      return;
    }
    if (resolved.length === 1 && !freeText) {
      // One disambiguated mention, no extra question — open its topic page.
      const leafRef = resolved[0];
      browseFilterQuery = "";
      queryInput.value = "";
      browseState = {
        level: "leaf",
        categoryId: leafRef.categoryId,
        subcategoryId: leafRef.subcategoryId,
        tag: leafRef.tag,
        label: leafRef.label,
        query: leafRef.query,
      };
      setActiveView("browse");
      renderBrowseView();
      return;
    }
    // Mixed mention(s) + question, or an unresolved mention — fall through
    // to the normal ask flow below with the @/; syntax stripped out.
    queryInput.value = cleanedQuery || rawQuery;
  }

  const query = queryInput.value.trim();
  if (!query) return;

  // Pressing Enter always answers the question, never just filters — and
  // switching to the Ask tab hides the Browse tree/tiles behind it.
  browseFilterQuery = "";
  setActiveView("ask");
  appendMessage("user", escapeHtml(query));
  queryInput.value = "";
  sendBtn.disabled = true;

  const plan = planAskRequest(query);
  const category = plan.leaf?.categoryId ? findCategory(plan.leaf.categoryId) : null;
  const subcategory =
    category && plan.leaf?.subcategoryId ? findSubcategory(category, plan.leaf.subcategoryId) : null;
  const categoryContext =
    category && subcategory ? `${category.label} > ${subcategory.label}` : category?.label || null;

  const steps = [];
  if (plan.routed) {
    steps.push({
      status: "done",
      label: plan.routeNote ? "Inferred answer shape" : "Routed",
      detail: plan.routeNote,
    });
  }
  const thinking = appendMessage("assistant", renderThinkingPanel(steps, { live: true }));
  const bodyEl = thinking.querySelector(".body");
  const paintThinking = () => {
    bodyEl.innerHTML = renderThinkingPanel(steps, { live: true });
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  try {
    const data = await streamChat(
      buildPayload(plan.query, plan.mode, {
        categoryContext,
        pageTag: plan.leaf?.tag || null,
      }),
      {
        onProgress: async (ev) => {
          upsertThinkingStep(steps, ev);
          paintThinking();
        },
      },
    );
    let body = "";
    const doneSteps = steps.map((s) => (s.status === "running" ? { ...s, status: "done" } : s));
    if (doneSteps.length) {
      body += renderThinkingPanel(doneSteps);
    }
    if (plan.routed) {
      body += `<p class="hint topic-route-hint">${escapeHtml(plan.routeNote)}</p>`;
    }

    if (data.ok) {
      setLastExportableResult({
        source: data.mode || "chat",
        query: plan.query,
        original_query: query,
        tag: plan.leaf?.tag || null,
        label: plan.leaf?.label || null,
        data,
      });
    }

    if (!data.ok) {
      body = `<p class="error-text">${escapeHtml(data.error || data.answer_error || "Request failed")}</p>`;
    } else if (data.mode === "topic_page") {
      body += renderTopicPageResult(data, plan.query, {
        tag: plan.leaf?.tag || null,
        provenance: plan.leaf?.provenance || null,
        categoryId: plan.leaf?.categoryId || null,
        subcategoryId: plan.leaf?.subcategoryId || null,
        label: plan.leaf?.label || plan.query,
        query: plan.query,
      });
    } else {
      const cardFilter = filterByQueryRelevance(query, data.cards || [], { maxShown: 20 });
      const sortedCards = cardFilter.shown.length ? cardFilter.shown : data.cards || [];
      const previewIndex = buildUrlPreviewIndex(data.cards || [], data.figures || []);
      activeCiteBySource = buildCiteBySource(data.cards || [], []);
      activeLiteratureByUrl = new Map();
      activeCiteHoverByUrl = buildCiteHoverIndex(data.cards || []);
      indexTextbookLabelsFromCards(data.cards || [], data.figures || []);

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

infoModal?.querySelectorAll("[data-info-close]").forEach((el) => {
  el.addEventListener("click", () => infoModal.classList.add("hidden"));
});

exportInfoBtn?.addEventListener("click", () => {
  exportInfoModal?.classList.remove("hidden");
});
exportInfoModal?.querySelectorAll("[data-export-info-close]").forEach((el) => {
  el.addEventListener("click", () => exportInfoModal.classList.add("hidden"));
});

homeBtn?.addEventListener("click", () => {
  browseFilterQuery = "";
  browseState = { level: "home" };
  setActiveView("browse");
  renderBrowseView();
});

updateModeHint();
setActiveView("browse");
browseContentEl.innerHTML = '<p class="hint">Loading Browse topic index…</p>';
loadBrowseIndex().then(() => {
  renderBrowseView();
});
loadWhoSyndromeLinks();
refreshHealth();
