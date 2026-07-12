#!/usr/bin/env python3
"""Build indexable lecture chunks that are actually usefully tagged.

v0_2 policy (replaces tag-crumbs-then-merge for indexing):
  1. Drop housekeeping ASR crumbs
  2. Time-merge remaining crumbs into provisional teaching windows
  3. Embed each window (text-embedding-3-small)
  4. Cosine against canonical browse leaves for the package root
     (Heme::* or Breast::* etc. via --leaf-dir / --root)
  5. KEEP only if quality gates pass:
       - similarity >= min_sim
       - (best - second) >= min_margin   # unambiguous
       - duration/chars above floors
       - not an agenda/TOC multi-entity dump
  6. Write ONLY keepers to chunks_indexable.jsonl

Everything else stays in segments*.jsonl for audit — not indexed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import numpy as np
from openai import OpenAI


EMBEDDING_MODEL = "text-embedding-3-small"

HOUSEKEEPING = [
    r"^\s*thank you",
    r"\bi thank you\b",
    r"\bthanks?\b.{0,40}(attention|listening|time)\b",
    r"\backnowledg",
    r"\bdisclosures?\b",
    r"\bconflict of interest\b",
    r"hello,?\s+my name is",
    r"delighted to participate",
    r"society for hematopathology",
    r"virtual curriculum",
    r"any questions",
]

LECTURE_PRIORS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"aggressive_b", re.I), ["Heme::Mature_B_Cell::Large_B_Cell", "Heme::Mature_B_Cell::Burkitt"]),
    (re.compile(r"small_b_cell", re.I), ["Heme::Mature_B_Cell"]),
    (re.compile(r"hodgkin", re.I), ["Heme::Hodgkin_Lymphoma"]),
    (re.compile(r"t_nk", re.I), ["Heme::Mature_T_NK_Cell", "Heme::T_NK_Cell"]),
    (re.compile(r"^heme_sh_aml", re.I), ["Heme::Acute_Myeloid_Leukemia", "Heme::Acute_Leukemia"]),
    (re.compile(r"mds_mpn", re.I), ["Heme::Myelodysplastic", "Heme::Myeloproliferative", "Heme::Myelodysplastic_Myeloproliferative", "Heme::Myeloid_Neoplasms"]),
    (re.compile(r"plasma_cell", re.I), ["Heme::Plasma_Cell_Neoplasm"]),
    (re.compile(r"histiocytic", re.I), ["Heme::Histiocytic_Dendritic_Cell", "Heme::Histiocytic_Dendritic"]),
    (re.compile(r"spleen", re.I), ["Heme::Mature_B_Cell::Splenic", "Heme::Non_Neoplastic::Spleen", "Heme::Stroma_Derived"]),
    (re.compile(r"reactive_lymphoid|heme_sh_reactive", re.I), ["Heme::Non_Neoplastic", "Heme::Tumor_Like", "Heme::Infection"]),
    (re.compile(r"bm_failure|bm_intro|bm_systemic", re.I), [
        "Heme::Non_Neoplastic",
        "Heme::Myelodysplastic",
        "Heme::Acute_Myeloid_Leukemia",
        "Heme::Metastasis",
        "Heme::Myeloproliferative_Neoplasm",
        "Heme::Stroma_Derived",
    ]),
    (re.compile(r"ia_lpd|immune", re.I), ["Heme::Immune_Deficiency_Associated"]),
    (re.compile(r"pt_lpd", re.I), ["Heme::Immune_Deficiency_Associated"]),
    (re.compile(r"heme_sh_ihc|ihc_for_lpd", re.I), ["Heme::Mature_B_Cell", "Heme::Mature_T_NK_Cell", "Heme::Hodgkin_Lymphoma"]),
    # Breast lecture family
    (re.compile(r"breast_lecture_invasive", re.I), ["Breast::Neoplastic::Epithelial::Malignant", "Breast::Epithelial::Ductal_Carcinoma"]),
    (re.compile(r"breast_lecture_lobular", re.I), ["Breast::Neoplastic::Epithelial"]),
    (re.compile(r"breast_lecture_epithelial", re.I), ["Breast::Epithelial", "Breast::Neoplastic::Epithelial"]),
    (re.compile(r"breast_lecture_papillary", re.I), ["Breast::Epithelial::Papillary_Neoplasms", "Breast::Neoplastic::Epithelial"]),
    (re.compile(r"breast_lecture_fibroepithelial", re.I), ["Breast::Neoplastic::Fibroepithelial", "Breast::FibroEpithelial"]),
    (re.compile(r"breast_lecture_spindle", re.I), ["Breast::Mesenchymal", "Breast::Neoplastic", "Breast::Inflammatory::Reactive"]),
    (re.compile(r"breast_lecture_normal", re.I), ["Breast::Normal_Histology", "Breast::Congenital_Structural"]),
    (re.compile(r"breast_lecture_ihc|breast_lecture_prognostic", re.I), ["Breast::Neoplastic::Epithelial", "Breast::Genetics"]),
    (re.compile(r"breast_lecture_treated", re.I), ["Breast::Neoplastic::Epithelial", "Breast::Inflammatory"]),
    (re.compile(r"breast_lecture_grossing|breast_lecture_rad", re.I), ["Breast::Normal_Histology", "Breast::Congenital_Structural", "Breast::Neoplastic"]),
    (re.compile(r"^breast_lecture", re.I), ["Breast::"]),
    # GI lecture family
    (re.compile(r"gi_lecture_.*liver|gi_lecture_0_gross_liver", re.I), ["GI::Liver", "GI::Hepatobiliary"]),
    (re.compile(r"gi_lecture_.*pancreas", re.I), ["GI::Pancreas", "GI::Ampulla"]),
    (re.compile(r"gi_lecture_.*colon|gi_lecture_.*ibd", re.I), ["GI::Colon", "GI::Large_Intestine", "GI::Intestine"]),
    (re.compile(r"gi_lecture_.*esophagus", re.I), ["GI::Esophagus"]),
    (re.compile(r"gi_lecture_.*stomach", re.I), ["GI::Stomach"]),
    (re.compile(r"gi_lecture_.*smallintestine|gi_lecture_.*small_intestine", re.I), ["GI::Small_Intestine", "GI::Intestine"]),
    (re.compile(r"gi_lecture_.*peds", re.I), ["GI::", "Peds::"]),
    (re.compile(r"^gi_lecture", re.I), ["GI::"]),
    # GYN lecture family
    (re.compile(r"gyn_lecture_.*cervix_glandular", re.I), ["GYN::Cervix", "GYN::Cervix_Uteri"]),
    (re.compile(r"gyn_lecture_.*cervix_squamous", re.I), ["GYN::Cervix", "GYN::Cervix_Uteri"]),
    (re.compile(r"gyn_lecture_.*endometrium", re.I), ["GYN::Uterus", "GYN::Endometrium", "GYN::Corpus"]),
    (re.compile(r"gyn_lecture_.*gestational", re.I), ["GYN::Gestational", "GYN::Placenta", "GYN::Trophoblast"]),
    (re.compile(r"gyn_lecture_.*ovary", re.I), ["GYN::Ovary"]),
    (re.compile(r"gyn_lecture_.*uterine_mesenchymal", re.I), ["GYN::Uterus", "GYN::Myometrium", "GYN::Soft_Tissue"]),
    (re.compile(r"gyn_lecture_.*grossing", re.I), ["GYN::"]),
    (re.compile(r"^gyn_lecture", re.I), ["GYN::"]),
    # BST lecture family
    (re.compile(r"bst_lecture_.*softtissue|bst_lecture_.*soft_tissue|bst_lecture_.*softissue", re.I), ["BST::Soft_Tissue", "BST::"]),
    (re.compile(r"bst_lecture_.*bone", re.I), ["BST::Bone", "BST::"]),
    (re.compile(r"bst_lecture_.*grossing", re.I), ["BST::"]),
    (re.compile(r"^bst_lecture", re.I), ["BST::"]),
    # GU
    (re.compile(r"gu_lecture_.*prostate", re.I), ["GU::Prostate"]),
    (re.compile(r"gu_lecture_.*kidney", re.I), ["GU::Kidney", "GU::Renal"]),
    (re.compile(r"gu_lecture_.*testis", re.I), ["GU::Testis", "GU::Testicle"]),
    (re.compile(r"gu_lecture_.*bladder", re.I), ["GU::Bladder", "GU::Urothelial"]),
    (re.compile(r"^gu_lecture", re.I), ["GU::"]),
    # HN
    (re.compile(r"hn_lecture_.*salivary", re.I), ["HN::Salivary", "HN::Salivary_Gland"]),
    (re.compile(r"hn_lecture_.*thyroid", re.I), ["HN::Thyroid", "Endo::Thyroid"]),
    (re.compile(r"hn_lecture_.*odontogenic", re.I), ["HN::Odontogenic", "HN::Jaw"]),
    (re.compile(r"hn_lecture_.*oral", re.I), ["HN::Oral", "HN::Mouth"]),
    (re.compile(r"hn_lecture_.*hpv", re.I), ["HN::", "HN::Oropharynx", "HN::Tonsil"]),
    (re.compile(r"hn_lecture_.*grossing", re.I), ["HN::"]),
    (re.compile(r"^hn_lecture", re.I), ["HN::"]),
    # Thoracic
    (re.compile(r"thoracic_lecture_.*non_neoplastic|thoracic_lecture_.*ild|thoracic_lecture_.*ars", re.I), ["Thorax_Mediastinum::"]),
    (re.compile(r"thoracic_lecture_.*neoplastic|thoracic_lecture_.*molecular", re.I), ["Thorax_Mediastinum::"]),
    (re.compile(r"thoracic_lecture_.*thymus", re.I), ["Thorax_Mediastinum::Thymus", "Thorax_Mediastinum::"]),
    (re.compile(r"^thoracic_lecture", re.I), ["Thorax_Mediastinum::"]),
    # YT GI / Cyto
    (re.compile(r"^yt_gi", re.I), ["GI::"]),
    (re.compile(r"^yt_cyto", re.I), ["Cyto_"]),
]

ENTITYISH = re.compile(
    r"\b(lymphoma|leukemia|myeloma|mds|mpn|hodgkin|burkitt|follicular|mantle|"
    r"marginal|cll|aml|apl|ptld|amyloid|histiocyt|reed.?sternberg|myelofibrosis|"
    r"polycythemia|thrombocythemia|mastocyt|castleman|rosai|langerhans|"
    r"carcinoma|dcis|lcis|lobular|ductal|fibroadenoma|phyllodes|papillary|"
    r"mucinous|tubular|metaplastic|her2|ki-?67|er\b|pr\b|triple.?negative|"
    r"radial scar|adenosis|paget|nipple|spindle|myofibroblastoma|angiosarcoma|"
    r"invasive|in situ|breast|"
    # GI
    r"hepatocellular|hcc|cholangiocarcinoma|cirrhosis|steatohepatitis|nash|nafld|"
    r"barrett|esophagitis|gastritis|helicobacter|crohn|ulcerative colitis|ibd|"
    r"adenoma|adenocarcinoma|gist|carcinoid|neuroendocrine|pancreat|ampulla|"
    r"celiac|colitis|polyp|dysplasia|liver|colon|stomach|esophagus|"
    # GYN
    r"endometri|cervix|cervical|hsil|lsil|cin\b|ais\b|serous|mucinous|endometrioid|"
    r"clear cell|germ cell|sex cord|brenner|leiomyoma|leiomyosarcoma|adenomyosis|"
    r"molar|hydatidiform|choriocarcinoma|gestational|ovary|ovarian|fallopian|"
    # BST
    r"sarcoma|liposarcoma|synovial|ewing|osteosarcoma|chondrosarcoma|giant cell|"
    r"fibromatosis|desmoid|schwannoma|mpnst|dfsp|undifferentiated|soft tissue|bone|"
    # GU
    r"urothelial|bladder|prostate|gleason|pin\b|kidney|renal|clear cell|papillary renal|"
    r"oncocytoma|chromophobe|testis|seminoma|teratoma|yolk sac|wilms|"
    # HN
    r"salivary|pleomorphic adenoma|warthin|mucoepidermoid|adenoid cystic|thyroid|"
    r"papillary thyroid|follicular thyroid|medullary thyroid|odontogenic|ameloblastoma|"
    r"oral|leukoplakia|hpv|p16|oropharynx|squamous|"
    # Thoracic
    r"lung|pulmonary|adenocarcinoma|squamous|small cell|mesothelioma|thymoma|thymic|"
    r"interstitial|ild|sarcoid|nsip|uip|organizing pneumonia|"
    # Cyto
    r"cytolog|fna|pap smear|bethesda|ascus|ascus|lisil|tis|effusion)\b",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcs_to_https(gcs_uri: str) -> str:
    without = gcs_uri[len("gs://") :]
    bucket, _, key = without.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{quote(key, safe='/')}"


def make_video_time_url(video_url: Optional[str], start: Any, end: Any) -> Optional[str]:
    """Build a seek URL. YouTube watch/embed uses &t=NNNs; GCS/other uses #t=."""
    if not video_url:
        return None
    try:
        s = float(start)
        e = float(end) if end is not None else None
    except (TypeError, ValueError):
        return None
    lower = video_url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        # YouTube deep links seek to start only; strip any prior fragment/query t=
        parsed = urlparse(video_url)
        qs = parse_qs(parsed.query)
        qs.pop("t", None)
        qs["t"] = [f"{int(max(0, s))}s"]
        # Prefer canonical watch URL when we have v=
        if "youtu.be" in (parsed.netloc or "").lower():
            vid = parsed.path.strip("/").split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}&t={int(max(0, s))}s"
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs, doseq=True), "")
        )
    if e is not None:
        return f"{video_url}#t={s:g},{e:g}"
    return f"{video_url}#t={s:g}"


def lecture_priors(package_id: str) -> list[str]:
    out: list[str] = []
    for pat, prefs in LECTURE_PRIORS:
        if pat.search(package_id):
            out.extend(prefs)
    return out


def is_housekeeping(text: str, start_sec: float, duration: Optional[float]) -> bool:
    t = text.lower()
    open_cut = 100.0
    if duration and duration > 0:
        open_cut = min(160.0, max(80.0, duration * 0.025))
    if start_sec < open_cut and re.search(
        r"hello|my name is|delighted|society for hematopathology|virtual curriculum|"
        r"listed on this slide|entities that we will|overview|agenda|outline|disclosures|"
        r"we'll be discussing|we will be discussing",
        t,
    ):
        return True
    if duration and start_sec > duration - 80 and re.search(r"thank|attention|questions|wrap", t):
        return True
    for pat in HOUSEKEEPING:
        if re.search(pat, t):
            return True
    if len(re.findall(r"[a-z0-9]+", t)) < 5:
        return True
    return False


def is_agenda_dump(text: str) -> bool:
    """TOC-style windows that name many entities but teach none.

    Teaching DDx windows often mention several entities (esp. Breast invasive
    subtypes). Require TOC/list cues — do not reject solely on entity count.
    """
    t = text.lower()
    if re.search(
        r"listed on this slide|provisional entit|in italicized text|established categories|"
        r"learning objectives|today'?s (agenda|outline)|outline of (today|this)|"
        r"we will cover the following|topics (we|i) will (cover|discuss)",
        t,
    ):
        return True
    hits = ENTITYISH.findall(t)
    distinct = len(set(h.lower() for h in hits))
    # Pure laundry-list cue + many entities
    listish = bool(
        re.search(
            r"we'll of course talk about|we will of course talk about|starting off with|"
            r"first[,.].{0,40}second[,.].{0,40}third|including:\s|as follows:",
            t,
        )
    )
    if listish and distinct >= 3:
        return True
    # Extremely entity-dense short window still looks like a TOC dump
    if distinct >= 8 and len(t) < 1200:
        return True
    return False


def embed_texts(client: OpenAI, texts: list[str], *, batch_size: int = 64) -> np.ndarray:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch, encoding_format="float")
        by_idx = sorted(resp.data, key=lambda d: d.index)
        vectors.extend([d.embedding for d in by_idx])
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-12)
    return arr / norms


def time_merge(
    rows: list[dict[str, Any]],
    *,
    max_duration_sec: float,
    max_chars: int,
    gap_flush_sec: float,
    min_chars: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = " ".join((r.get("text") or "").strip() for r in buf)
        text = " ".join(text.split())
        if len(text) < min_chars:
            buf = []
            return
        start = float(buf[0]["start_sec"])
        end = float(buf[-1]["end_sec"])
        first = buf[0]
        chunks.append(
            {
                "text": text,
                "start_sec": start,
                "end_sec": end,
                "duration_sec": round(end - start, 3),
                "char_count": len(text),
                "source_segment_ids": [r.get("segment_id") for r in buf],
                "source_segment_count": len(buf),
                "video_url": first.get("video_url"),
                "raw_source_gcs_uri": first.get("raw_source_gcs_uri"),
                "raw_source_join_basis": first.get("raw_source_join_basis"),
                "video_id": first.get("video_id"),
                "youtube_url": first.get("youtube_url"),
                "package_id": first.get("package_id"),
                "root": first.get("root") or "Heme",
            }
        )
        buf = []

    for row in rows:
        if not buf:
            buf = [row]
            continue
        gap = float(row["start_sec"]) - float(buf[-1]["end_sec"])
        trial_text = " ".join((r.get("text") or "").strip() for r in buf + [row])
        trial_text = " ".join(trial_text.split())
        trial_dur = float(row["end_sec"]) - float(buf[0]["start_sec"])
        if gap > gap_flush_sec or trial_dur > max_duration_sec or len(trial_text) > max_chars:
            flush()
            buf = [row]
        else:
            buf.append(row)
    flush()
    return chunks


def apply_prior(scores: np.ndarray, tags: list[str], priors: list[str], bonus: float = 0.05) -> np.ndarray:
    if not priors:
        return scores
    out = scores.copy()
    for i, tag in enumerate(tags):
        for j, pref in enumerate(priors):
            if tag.startswith(pref):
                out[i] += bonus * (1.0 - 0.12 * j)
                break
    return out


def matches_prior(tag: str, priors: list[str]) -> bool:
    return any(tag.startswith(p) for p in priors)


def branch_of(tag: str) -> str:
    parts = tag.split("::")
    return "::".join(parts[:3]) if len(parts) >= 3 else tag


def gate_tag(
    sims: np.ndarray,
    tags: list[str],
    priors: list[str],
    text: str,
    *,
    min_sim: float,
    min_margin: float,
) -> tuple[Optional[str], str, dict[str, Any]]:
    if is_agenda_dump(text):
        return None, "reject_agenda_dump", {}

    boosted = apply_prior(sims, tags, priors)
    order = np.argsort(-boosted)
    i1, i2 = int(order[0]), int(order[1])
    raw1, raw2 = float(sims[i1]), float(sims[i2])
    b1, b2 = float(boosted[i1]), float(boosted[i2])
    tag1, tag2 = tags[i1], tags[i2]
    margin = b1 - b2
    meta = {
        "top1_tag": tag1,
        "top1_sim": round(raw1, 4),
        "top1_boosted": round(b1, 4),
        "top2_tag": tag2,
        "top2_sim": round(raw2, 4),
        "top2_boosted": round(b2, 4),
        "margin": round(margin, 4),
        "prior_match": matches_prior(tag1, priors),
    }

    if raw1 < min_sim:
        return None, "reject_low_similarity", meta

    # Known ASR pitfall: "nodular sclerosis" Classic HL ≠ NLPHL.
    tlow = text.lower()
    ns_classic = bool(re.search(r"nodular\s+scler|nodular\s+sclerosis|nschl|grade\s*[12]\s+nodular", tlow))
    nlphl_cues = bool(re.search(r"lymphocyte[\s-]?predominant|nlphl|lp cell|popcorn|nodular lymphocyte", tlow))
    if "Nodular_Lymphocyte_Predominant_Hodgkin_Lymphoma" in tag1 and ns_classic and not nlphl_cues:
        # Prefer Classic if it's competitive; else reject as ambiguous.
        classic = "Heme::Hodgkin_Lymphoma::Classic_Hodgkin_Lymphoma"
        if classic in tags:
            ci = tags.index(classic)
            if float(boosted[ci]) >= b1 - 0.02 and float(sims[ci]) >= min_sim:
                tag1 = classic
                raw1 = float(sims[ci])
                b1 = float(boosted[ci])
                margin = b1 - b2
                meta.update(
                    {
                        "top1_tag": tag1,
                        "top1_sim": round(raw1, 4),
                        "top1_boosted": round(b1, 4),
                        "margin": round(margin, 4),
                        "disambiguation": "nodular_sclerosis_vs_nlphl",
                    }
                )
            else:
                return None, "reject_ns_nlphl_ambiguity", meta

    # Off-prior leaves need a clearly stronger semantic win.
    if priors and not matches_prior(tag1, priors):
        if raw1 < (min_sim + 0.08) or margin < (min_margin + 0.02):
            return None, "reject_off_prior_weak", meta
    if margin < min_margin:
        same_branch = branch_of(tag1) == branch_of(tag2)
        if not (same_branch and margin >= (min_margin * 0.55) and raw1 >= (min_sim + 0.05)):
            return None, "reject_ambiguous_margin", meta
    if not ENTITYISH.search(text) and raw1 < min_sim + 0.06:
        return None, "reject_no_entity_signal", meta

    leaf_root = tag1.split("::", 1)[0].lower() if tag1 else "taxonomy"
    return tag1, f"semantic_gated_best_of_{leaf_root}", meta


def process_package(
    package_dir: Path,
    *,
    leaf_meta: dict[str, Any],
    leaf_matrix: np.ndarray,
    client: OpenAI,
    min_sim: float,
    min_margin: float,
    max_duration_sec: float,
    max_chars: int,
    min_chars: int,
    min_duration_sec: float,
    gap_flush_sec: float,
    root: Optional[str] = None,
) -> dict[str, Any]:
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    package_id = manifest.get("package_id") or package_dir.name
    root = root or manifest.get("root") or leaf_meta.get("root") or "Heme"
    priors = lecture_priors(package_id)
    duration = manifest.get("duration_seconds")
    try:
        duration_f = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_f = None

    tags = [leaf["tag"] for leaf in leaf_meta["leaves"]]
    rows = [json.loads(ln) for ln in (package_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Ensure segment root reflects package root for merged windows
    for row in rows:
        row.setdefault("root", root)

    kept_segs: list[dict[str, Any]] = []
    reject_hk = 0
    for row in rows:
        text = row.get("text") or ""
        start = float(row.get("start_sec") or 0.0)
        if is_housekeeping(text, start, duration_f):
            row["indexable"] = False
            row["primary_tag"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = "housekeeping"
            reject_hk += 1
            continue
        kept_segs.append(row)

    provisional = time_merge(
        kept_segs,
        max_duration_sec=max_duration_sec,
        max_chars=max_chars,
        gap_flush_sec=gap_flush_sec,
        min_chars=min_chars,
    )
    # duration floor
    provisional = [c for c in provisional if c["duration_sec"] >= min_duration_sec]

    if not provisional:
        chunks: list[dict[str, Any]] = []
        reject_counts: Counter[str] = Counter({"no_provisional_windows": 1})
    else:
        texts = [c["text"] for c in provisional]
        emb = embed_texts(client, texts)
        sims = emb @ leaf_matrix.T
        chunks = []
        reject_counts = Counter()
        for c, srow in zip(provisional, sims):
            tag, basis, meta = gate_tag(srow, tags, priors, c["text"], min_sim=min_sim, min_margin=min_margin)
            if not tag:
                reject_counts[basis] += 1
                continue
            video_url = c.get("video_url")
            chunk = {
                "schema_version": "lecture_deck_chunk.v0_2",
                "package_id": package_id,
                "chunk_id": f"{package_id}::chunk_{len(chunks):04d}",
                "start_sec": c["start_sec"],
                "end_sec": c["end_sec"],
                "duration_sec": c["duration_sec"],
                "text": c["text"],
                "char_count": c["char_count"],
                "primary_tag": tag,
                "entity_name": tag.split("::")[-1],
                "tag_status": "semantic_gated_v0_2",
                "tag_basis": basis,
                "tag_score": meta.get("top1_sim"),
                "tag_score_boosted": meta.get("top1_boosted"),
                "tag_margin": meta.get("margin"),
                "tag_runner_up": meta.get("top2_tag"),
                "indexable": True,
                "root": c.get("root") or root,
                "video_id": c.get("video_id"),
                "video_url": video_url,
                "video_time_url": make_video_time_url(video_url, c["start_sec"], c["end_sec"]),
                "youtube_url": c.get("youtube_url"),
                "raw_source_gcs_uri": c.get("raw_source_gcs_uri"),
                "raw_source_join_basis": c.get("raw_source_join_basis"),
                "source_segment_ids": c["source_segment_ids"],
                "source_segment_count": c["source_segment_count"],
            }
            chunks.append(chunk)
            reject_counts["accepted"] += 1

    # Mark segments covered by accepted chunks as supporting; others non-indexable for vector use
    covered: set[str] = set()
    tag_by_seg: dict[str, str] = {}
    for ch in chunks:
        for sid in ch.get("source_segment_ids") or []:
            if sid:
                covered.add(sid)
                tag_by_seg[sid] = ch["primary_tag"]

    for row in rows:
        sid = row.get("segment_id")
        if sid in covered:
            row["indexable"] = False  # index grain is chunks only
            row["supports_indexable_chunk"] = True
            row["primary_tag"] = tag_by_seg.get(sid)
            row["tag_status"] = "chunk_support_only_v0_2"
            row["tag_basis"] = "inherited_from_gated_chunk"
        elif row.get("tag_basis") != "housekeeping":
            row["indexable"] = False
            row["supports_indexable_chunk"] = False
            row["primary_tag"] = None
            row["tag_status"] = "not_in_gated_chunk"
            row["tag_basis"] = "excluded_from_index"

    by_tag = Counter(c["primary_tag"] for c in chunks)
    durs = [c["duration_sec"] for c in chunks]
    sims_acc = [c["tag_score"] for c in chunks if c.get("tag_score") is not None]
    margins = [c["tag_margin"] for c in chunks if c.get("tag_margin") is not None]

    counts = dict(manifest.get("counts") or {})
    counts.update(
        {
            "segments_total": len(rows),
            "segments_housekeeping": reject_hk,
            "provisional_windows": len(provisional) if provisional else 0,
            "chunks_indexable": len(chunks),
            "chunks_by_tag": dict(by_tag.most_common()),
            "chunk_duration_sec_mean": round(sum(durs) / len(durs), 2) if durs else 0,
            "chunk_duration_sec_median": sorted(durs)[len(durs) // 2] if durs else 0,
            "semantic_similarity_mean": round(float(np.mean(sims_acc)), 4) if sims_acc else None,
            "semantic_similarity_median": round(float(np.median(sims_acc)), 4) if sims_acc else None,
            "semantic_margin_median": round(float(np.median(margins)), 4) if margins else None,
            "gate_rejects": {k: v for k, v in reject_counts.items() if k != "accepted"},
            "semantic_min_sim": min_sim,
            "semantic_min_margin": min_margin,
        }
    )
    # drop misleading crumb by_tag from v0_1 if present
    counts.pop("by_tag", None)
    counts.pop("segments_indexable", None)

    manifest["counts"] = counts
    manifest["index_artifact"] = "chunks_indexable.jsonl"
    manifest["index_policy"] = (
        "Index ONLY chunks_indexable.jsonl. Each chunk passed semantic quality gates "
        "(min similarity, top1-top2 margin, duration/chars, not agenda dump). "
        "segments_*.jsonl are audit/support only — do not vectorize."
    )
    manifest["tagging"] = {
        "method": f"time_merge_then_semantic_gated_best_of_{root}_v0_2",
        "embedding_model": EMBEDDING_MODEL,
        "root": root,
        "leaf_count": len(tags),
        "lecture_priors": priors,
        "min_similarity": min_sim,
        "min_margin": min_margin,
        "created_at_utc": utc_now(),
    }
    limitations = [
        x
        for x in (manifest.get("known_limitations") or [])
        if "primary_tag" not in x.lower()
        and "heuristic" not in x.lower()
        and "cosine best" not in x.lower()
        and "Indexable chunks only" not in x
    ]
    limitations.insert(
        0,
        f"Indexable chunks only: time-merged windows with gated embedding match to canonical {root}::* leaves "
        f"(min_sim={min_sim}, min_margin={min_margin}). Ambiguous/low-sim/agenda windows excluded.",
    )
    manifest["known_limitations"] = limitations

    with (package_dir / "chunks_indexable.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (package_dir / "segments.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # clear crumb indexable file or rewrite empty-ish support note
    with (package_dir / "segments_indexable.jsonl").open("w", encoding="utf-8") as f:
        f.write("")  # intentionally empty — index grain is chunks only

    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    audit = {
        "schema_version": "lecture_deck_semantic_gated_chunk_audit.v0_2",
        "created_at_utc": utc_now(),
        "package_id": package_id,
        "input_paths": [str(package_dir / "segments.jsonl")],
        "output_paths": [str(package_dir / "chunks_indexable.jsonl"), str(package_dir / "manifest.json")],
        "counts": counts,
        "params": {
            "min_sim": min_sim,
            "min_margin": min_margin,
            "max_duration_sec": max_duration_sec,
            "max_chars": max_chars,
            "min_chars": min_chars,
            "min_duration_sec": min_duration_sec,
            "gap_flush_sec": gap_flush_sec,
        },
        "lecture_priors": priors,
        "known_limitations": [
            "Only gated chunks are indexable; rejected windows are omitted on purpose.",
            "Still not human gold — but every retained chunk met usefulness gates.",
        ],
    }
    (package_dir / "chunk_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit


def resolve_leaf_artifacts(leaf_dir: Path, root: Optional[str]) -> tuple[dict[str, Any], np.ndarray]:
    """Accept heme_* filenames or {root_slug}_* filenames."""
    candidates_meta = [
        leaf_dir / "heme_leaf_embeddings_meta.json",
        leaf_dir / "breast_leaf_embeddings_meta.json",
    ]
    candidates_npy = [
        leaf_dir / "heme_leaf_embeddings.npy",
        leaf_dir / "breast_leaf_embeddings.npy",
    ]
    if root:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", root.strip()).strip("_").lower()
        candidates_meta.insert(0, leaf_dir / f"{slug}_leaf_embeddings_meta.json")
        candidates_npy.insert(0, leaf_dir / f"{slug}_leaf_embeddings.npy")
    # also accept any *_leaf_embeddings_meta.json
    candidates_meta.extend(sorted(leaf_dir.glob("*_leaf_embeddings_meta.json")))
    candidates_npy.extend(sorted(leaf_dir.glob("*_leaf_embeddings.npy")))

    meta_path = next((p for p in candidates_meta if p.is_file()), None)
    npy_path = next((p for p in candidates_npy if p.is_file()), None)
    if not meta_path or not npy_path:
        raise FileNotFoundError(f"Leaf embeddings not found under {leaf_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    matrix = np.load(npy_path)
    return meta, matrix


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package-dir", type=Path, required=True)
    p.add_argument("--leaf-dir", type=Path, default=Path("outputs/heme_browse_leaf_embeddings_v0_1"))
    p.add_argument("--root", default=None, help="Browse root label (Breast, Heme, …)")
    p.add_argument("--min-sim", type=float, default=0.50)
    p.add_argument("--min-margin", type=float, default=0.035)
    p.add_argument("--max-duration-sec", type=float, default=140.0)
    p.add_argument("--max-chars", type=int, default=2600)
    p.add_argument("--min-chars", type=int, default=400)
    p.add_argument("--min-duration-sec", type=float, default=35.0)
    p.add_argument("--gap-flush-sec", type=float, default=20.0)
    args = p.parse_args()

    meta, matrix = resolve_leaf_artifacts(args.leaf_dir, args.root)
    client = OpenAI()
    audit = process_package(
        args.package_dir,
        leaf_meta=meta,
        leaf_matrix=matrix,
        client=client,
        min_sim=args.min_sim,
        min_margin=args.min_margin,
        max_duration_sec=args.max_duration_sec,
        max_chars=args.max_chars,
        min_chars=args.min_chars,
        min_duration_sec=args.min_duration_sec,
        gap_flush_sec=args.gap_flush_sec,
        root=args.root or meta.get("root"),
    )
    print(
        json.dumps(
            {
                "ok": True,
                "package_id": audit["package_id"],
                "chunks_indexable": audit["counts"]["chunks_indexable"],
                "sim_median": audit["counts"].get("semantic_similarity_median"),
                "margin_median": audit["counts"].get("semantic_margin_median"),
                "rejects": audit["counts"].get("gate_rejects"),
                "top_tags": list((audit["counts"].get("chunks_by_tag") or {}).items())[:8],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
