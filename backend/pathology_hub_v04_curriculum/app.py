
import os, re, json, sqlite3, time, hmac, hashlib, base64, io, urllib.parse, csv, html
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
import numpy as np
import faiss
from fastapi import FastAPI, Header, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from google.cloud import storage
from openai import OpenAI
from PIL import Image

APP_VERSION = "1.5.7-page-images-v04"

TEXTBOOK_SQLITE_GCS = os.environ.get("TEXTBOOK_SQLITE_GCS")
TEXTBOOK_MANIFEST_GCS = os.environ.get("TEXTBOOK_MANIFEST_GCS")
TEXTBOOK_FAISS_GCS = os.environ.get("TEXTBOOK_FAISS_GCS")
TEXTBOOK_DOCSTORE_GCS = os.environ.get("TEXTBOOK_DOCSTORE_GCS")
TEXTBOOK_VECTOR_MANIFEST_GCS = os.environ.get("TEXTBOOK_VECTOR_MANIFEST_GCS")
TEXTBOOK_FIGURES_GCS = os.environ.get("TEXTBOOK_FIGURES_GCS")
TEXTBOOK_WEB_MAP_GCS = os.environ.get("TEXTBOOK_WEB_MAP_GCS")
UPSTREAM_EVIDENCE_URL = os.environ.get("UPSTREAM_EVIDENCE_URL", "")

EXPECTED_API_KEY = os.environ.get("PATHOLOGY_HUB_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FIGURE_PROXY_SECRET = os.environ.get("FIGURE_PROXY_SECRET", "") or EXPECTED_API_KEY

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
RRF_K = int(os.environ.get("RRF_K", "60"))
FTS_POOL = int(os.environ.get("FTS_POOL", "25"))
VECTOR_POOL = int(os.environ.get("VECTOR_POOL", "25"))
FIGURE_URL_TTL_SECONDS = int(os.environ.get("FIGURE_URL_TTL_SECONDS", "21600"))

DATA_DIR = Path("/tmp/pathology_hub_textbooks")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "textbook_lean_fts.sqlite"
MANIFEST_PATH = DATA_DIR / "textbook_lean_index_manifest.json"
FAISS_PATH = DATA_DIR / "textbook_lean_faiss.index"
DOCSTORE_PATH = DATA_DIR / "textbook_lean_vector_docstore.jsonl"
VECTOR_MANIFEST_PATH = DATA_DIR / "textbook_lean_vector_manifest.json"
FIGURES_PATH = DATA_DIR / "textbook_lean_figures.jsonl"
WEB_MAP_PATH = DATA_DIR / "textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl"

app = FastAPI(
    title="Pathology Hub Unified Evidence API v04.3",
    version=APP_VERSION,
    description="Unified evidence API with WHO/Journals/PathOut proxy, hybrid textbook search, and controlled textbook figure proxy."
)

class EvidenceSearchRequest(BaseModel):
    query: str = Field(..., description="Short keyword-style pathology evidence query.")
    sources: List[str] = Field(default_factory=lambda: ["textbooks"])
    max_results: int = Field(1, ge=1, le=10)
    include_figures: bool = False
    max_figures: int = Field(0, ge=0, le=10)
    compact: bool = True
    excerpt_char_limit: int = Field(900, ge=200, le=4000)
    render_html: bool = False
    html_profile: str = Field("teaching_page", description="teaching_page, gallery, or evidence_packet")
    html_title: Optional[str] = None
    target_figure_count: int = Field(10, ge=1, le=50)
    html_include_toc: bool = True
    html_include_source_sections: bool = True

_INDEX = None
_DOCSTORE = None
_OPENAI_CLIENT = None
_FIGURES = None
_FIGURES_BY_SOURCE_PAGE = None
_WEB_FIGURE_MAP = None

def _parse_gs_uri(uri: str):
    assert uri.startswith("gs://")
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return bucket, key

def _download_gcs(uri: str, dest: Path):
    bucket_name, blob_name = _parse_gs_uri(uri)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(blob_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(dest))
    return dest

def ensure_artifacts():
    required = [
        (TEXTBOOK_SQLITE_GCS, DB_PATH),
        (TEXTBOOK_MANIFEST_GCS, MANIFEST_PATH),
        (TEXTBOOK_FAISS_GCS, FAISS_PATH),
        (TEXTBOOK_DOCSTORE_GCS, DOCSTORE_PATH),
        (TEXTBOOK_VECTOR_MANIFEST_GCS, VECTOR_MANIFEST_PATH),
        (TEXTBOOK_FIGURES_GCS, FIGURES_PATH),
        (TEXTBOOK_WEB_MAP_GCS, WEB_MAP_PATH),
    ]
    for uri, dest in required:
        if not uri:
            continue
        if not dest.exists() or dest.stat().st_size < 1024:
            _download_gcs(uri, dest)

def require_key(x_api_key: Optional[str]):
    if EXPECTED_API_KEY:
        if not x_api_key or x_api_key != EXPECTED_API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")
    return True

def storage_https_to_gs(url: Optional[str]):
    if not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("gs://"):
        return url
    if url.startswith("https://storage.googleapis.com/"):
        rest = url.replace("https://storage.googleapis.com/", "", 1)
        parts = rest.split("/", 1)
        if len(parts) == 2:
            bucket, key = parts
            return f"gs://{bucket}/{urllib.parse.unquote(key)}"
    return None

def is_allowed_figure_gs(gs_uri: str):
    return isinstance(gs_uri, str) and gs_uri.startswith("gs://pathology_hub/01_staged/textbooks/assets/figure_images/")

def _b64url(s: str):
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")

def _b64url_decode(s: str):
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii")).decode("utf-8")

def _sign_payload(payload: str):
    secret = FIGURE_PROXY_SECRET or EXPECTED_API_KEY or "dev-secret"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def make_figure_proxy_url(base_url: str, gs_uri: str):
    if not gs_uri or not is_allowed_figure_gs(gs_uri):
        return None
    exp = str(int(time.time()) + FIGURE_URL_TTL_SECONDS)
    u = _b64url(gs_uri)
    sig = _sign_payload(f"{u}.{exp}")
    return f"{base_url.rstrip('/')}/figures/textbook?u={u}&exp={exp}&sig={sig}"

def verify_figure_sig(u: str, exp: str, sig: str):
    try:
        if int(exp) < int(time.time()):
            return False
    except Exception:
        return False
    expected = _sign_payload(f"{u}.{exp}")
    return hmac.compare_digest(expected, sig or "")

@app.get("/figures/textbook")
def get_textbook_figure(
    u: str = Query(...),
    exp: str = Query(...),
    sig: str = Query(...)
):
    if not verify_figure_sig(u, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired figure URL")

    try:
        gs_uri = _b64url_decode(u)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad figure token")

    if not is_allowed_figure_gs(gs_uri):
        raise HTTPException(status_code=403, detail="Figure path not allowed")

    try:
        bucket_name, blob_name = _parse_gs_uri(gs_uri)
        blob = storage.Client().bucket(bucket_name).blob(blob_name)
        raw = blob.download_as_bytes()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Figure object not found: {repr(e)}")

    suffix = Path(blob_name).suffix.lower()
    content_type = blob.content_type or ""

    if suffix in {".jpg", ".jpeg"} or content_type in {"image/jpeg", "image/jpg"}:
        return Response(content=raw, media_type="image/jpeg")
    if suffix == ".png" or content_type == "image/png":
        return Response(content=raw, media_type="image/png")
    if suffix == ".webp" or content_type == "image/webp":
        return Response(content=raw, media_type="image/webp")
    if suffix == ".gif" or content_type == "image/gif":
        return Response(content=raw, media_type="image/gif")

    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=88, optimize=True)
        return Response(content=out.getvalue(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=415, detail=f"Unsupported image format or conversion failed: {repr(e)}")

def tokenize_for_fts(query: str):
    terms = re.findall(r"[A-Za-z0-9_]+", query.lower())
    stop = {"the","and","or","of","in","to","for","with","a","an","on","by","from","is","are","as"}
    return [t for t in terms if len(t) > 1 and t not in stop][:12]

def build_fts_queries(query: str):
    terms = tokenize_for_fts(query)
    if not terms:
        return [query]
    quoted = [f'"{t}"' for t in terms]
    if len(quoted) > 1:
        return [" AND ".join(quoted), " OR ".join(quoted)]
    return [quoted[0]]

def parse_jsonish(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, str) and x.strip():
        try:
            y = json.loads(x)
            return y if isinstance(y, list) else []
        except Exception:
            return []
    return []

def make_excerpt(text: str, query: str, limit: int):
    text = text or ""
    if len(text) <= limit:
        return text
    terms = tokenize_for_fts(query)
    low = text.lower()
    pos = -1
    for t in terms:
        pos = low.find(t.lower())
        if pos >= 0:
            break
    if pos < 0:
        return text[:limit]
    start = max(0, pos - limit // 3)
    end = min(len(text), start + limit)
    return ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")

def table_columns(conn, table_name):
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except Exception:
        return set()

def detect_tables(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()]
    base = "textbook_chunks" if "textbook_chunks" in names else None
    fts = "textbook_chunks_fts" if "textbook_chunks_fts" in names else None
    if not base:
        for n in names:
            if n.endswith("_chunks") or n == "chunks":
                base = n
                break
    if not fts:
        for n in names:
            if "fts" in n.lower():
                fts = n
                break
    if not base or not fts:
        raise RuntimeError(f"Could not detect chunk/FTS tables. Tables={names}")
    return base, fts

def load_figures():
    global _FIGURES, _FIGURES_BY_SOURCE_PAGE
    ensure_artifacts()
    if _FIGURES is not None and _FIGURES_BY_SOURCE_PAGE is not None:
        return _FIGURES, _FIGURES_BY_SOURCE_PAGE

    figures = []
    by_sp = {}

    with FIGURES_PATH.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            img = obj.get("image_path") or obj.get("image_url") or obj.get("figure_url") or obj.get("path") or obj.get("gcs_uri") or obj.get("url")
            gs = storage_https_to_gs(img)
            if not gs:
                continue

            source_id = obj.get("source_id")
            page = obj.get("page") or obj.get("source_page")
            cap = obj.get("caption") or obj.get("legend") or obj.get("text") or ""

            rec = {
                "line_no": line_no,
                "source_id": source_id,
                "source_title": obj.get("source_title") or obj.get("title") or source_id,
                "page": page,
                "figure_id": obj.get("figure_id"),
                "caption": cap,
                "image_path": gs,
                "original_image_url": img,
                "chunk_id": obj.get("chunk_id"),
            }
            figures.append(rec)
            key = (str(source_id), str(page))
            by_sp.setdefault(key, []).append(rec)

    _FIGURES = figures
    _FIGURES_BY_SOURCE_PAGE = by_sp
    return figures, by_sp

EXCLUDED_FIGURE_SOURCE_IDS = {"derm_mckee", "bone_dorfman"}

def load_web_figure_map():
    # Map original private GCS figure paths to public web-safe derivative URLs.
    # Uses the filtered map that excludes derm_mckee and bone_dorfman.
    global _WEB_FIGURE_MAP
    ensure_artifacts()
    if _WEB_FIGURE_MAP is not None:
        return _WEB_FIGURE_MAP

    m = {}
    if WEB_MAP_PATH.exists():
        with WEB_MAP_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                sid = str(obj.get("source_id") or obj.get("source") or "")
                if sid in EXCLUDED_FIGURE_SOURCE_IDS:
                    continue

                orig = (
                    obj.get("original_gs_uri")
                    or obj.get("original_image_path")
                    or obj.get("image_path")
                    or obj.get("image_url")
                    or obj.get("path")
                    or obj.get("url")
                )
                orig_gs = storage_https_to_gs(orig)

                pub = (
                    obj.get("public_url")
                    or obj.get("web_url")
                    or obj.get("figure_url")
                    or obj.get("image_url")
                    or obj.get("url")
                )

                if orig_gs and isinstance(pub, str) and pub.startswith("https://"):
                    m[orig_gs] = pub

    _WEB_FIGURE_MAP = m
    return m

def figure_to_response(rec: dict, base_url: str, rank: int = None):
    sid = str(rec.get("source_id") or "")
    if sid in EXCLUDED_FIGURE_SOURCE_IDS:
        return None

    gs = storage_https_to_gs(rec.get("image_path") or rec.get("original_image_url"))
    if not gs:
        return None

    web_map = load_web_figure_map()
    public_url = web_map.get(gs)

    if public_url:
        final_url = public_url
        mode = "public_web_derivative"
        proxy_fallback_used = False
    else:
        final_url = make_figure_proxy_url(base_url, gs)
        mode = "expiring_proxy_fallback"
        proxy_fallback_used = True

    if not final_url:
        return None

    return {
        "rank": rank,
        "title": rec.get("source_title") or rec.get("source_id"),
        "caption": rec.get("caption"),
        "figure_id": rec.get("figure_id"),
        "figure_url": final_url,
        "image_url": final_url,
        "image_path": gs,
        "original_image_path": gs,
        "original_image_url": rec.get("original_image_url"),
        "public_derivative_url": public_url,
        "proxy_fallback_used": proxy_fallback_used,
        "figure_serving_mode": mode,
        "source": "textbooks",
        "source_name": "textbooks",
        "source_id": rec.get("source_id"),
        "page": rec.get("page"),
    }

def collect_textbook_figures(textbook_results: list, base_url: str, max_figures: int):
    if max_figures <= 0:
        return []

    figures, by_sp = load_figures()
    out = []
    seen = set()

    def add_rec(rec):
        if not rec:
            return
        sid = str(rec.get("source_id") or "")
        if sid in EXCLUDED_FIGURE_SOURCE_IDS:
            return

        gs = storage_https_to_gs(rec.get("image_path") or rec.get("original_image_url"))
        if not gs or gs in seen:
            return

        response_rec = figure_to_response(rec, base_url, rank=len(out) + 1)
        if not response_rec:
            return

        seen.add(gs)
        out.append(response_rec)

    # First: exact image_path on figure-caption hits.
    for r in textbook_results:
        if str(r.get("source_id") or "") in EXCLUDED_FIGURE_SOURCE_IDS:
            continue
        img = r.get("image_path")
        gs = storage_https_to_gs(img)
        if gs:
            add_rec({
                "source_id": r.get("source_id"),
                "source_title": r.get("title") or r.get("source_title"),
                "page": r.get("page"),
                "figure_id": r.get("figure_id"),
                "caption": r.get("text") or r.get("excerpt"),
                "image_path": gs,
                "original_image_url": img,
            })
            if len(out) >= max_figures:
                return out

    # Second: figures from the same source/page as top hits.
    for r in textbook_results:
        if str(r.get("source_id") or "") in EXCLUDED_FIGURE_SOURCE_IDS:
            continue
        key = (str(r.get("source_id")), str(r.get("page")))
        for rec in by_sp.get(key, []):
            add_rec(rec)
            if len(out) >= max_figures:
                return out

    return out



def row_to_textbook_result(d, query, limit, rank=None, retrieval_mode="fts", extra=None):
    text = d.get("text") or d.get("chunk_text") or ""
    result = {
        "rank": rank,
        "title": d.get("source_title") or d.get("source_id"),
        "source_name": "textbooks",
        "source_type": "textbook_chunk",
        "source_id": d.get("source_id"),
        "chunk_id": d.get("chunk_id"),
        "chunk_type": d.get("chunk_type"),
        "page": d.get("page"),
        "chapter_number": d.get("chapter_number"),
        "chapter_title": d.get("chapter_title"),
        "section": d.get("section") or d.get("section_heading"),
        "section_heading": d.get("section_heading") or d.get("section"),
        "figure_id": d.get("figure_id"),
        "image_path": d.get("image_path"),
        "excerpt": make_excerpt(text, query, limit),
        "text": make_excerpt(text, query, limit),
        "candidate_tags": parse_jsonish(d.get("candidate_tags")),
        "ai_tags": parse_jsonish(d.get("ai_tags")),
        "context_tags": parse_jsonish(d.get("context_tags")),
        "reviewed_tags": parse_jsonish(d.get("reviewed_tags")),
        "tagging_status": d.get("tagging_status"),
        "retrieval_mode": retrieval_mode,
    }
    if extra:
        result.update(extra)
    return result

def fts_search_pool(query: str, pool_size: int):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    base, fts = detect_tables(conn)
    cols = table_columns(conn, base)

    wanted = [
        "chunk_id", "source_id", "source_title", "chunk_type", "page",
        "chapter_number", "chapter_title", "section_heading",
        "figure_id", "image_path", "text",
        "candidate_tags", "ai_tags", "context_tags", "reviewed_tags",
        "tagging_status"
    ]
    select_parts = []
    for c in wanted:
        select_parts.append(f"c.{c} AS {c}" if c in cols else f"NULL AS {c}")
    select_sql = ", ".join(select_parts)

    rows = []
    for fts_q in build_fts_queries(query):
        try:
            sql = f"""
                SELECT {select_sql}, bm25({fts}) AS bm25_score
                FROM {fts}
                JOIN {base} c ON c.rowid = {fts}.rowid
                WHERE {fts} MATCH ?
                ORDER BY bm25_score
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_q, pool_size)).fetchall()
            if rows:
                break
        except Exception:
            rows = []

    if not rows:
        terms = tokenize_for_fts(query)
        term = terms[0] if terms else query
        try:
            sql = f"""
                SELECT {select_sql}, 9999.0 AS bm25_score
                FROM {base} c
                WHERE c.text LIKE ?
                LIMIT ?
            """
            rows = conn.execute(sql, (f"%{term}%", pool_size)).fetchall()
        except Exception:
            rows = []

    conn.close()
    out = []
    for i, r in enumerate(rows, start=1):
        d = dict(r)
        d["_fts_rank"] = i
        d["_bm25_score"] = d.get("bm25_score")
        out.append(d)
    return out

def get_openai_client():
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        _OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")
    return _OPENAI_CLIENT

def load_vector_assets():
    global _INDEX, _DOCSTORE
    ensure_artifacts()
    if _INDEX is None:
        _INDEX = faiss.read_index(str(FAISS_PATH))
    if _DOCSTORE is None:
        docs = []
        with DOCSTORE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    docs.append(json.loads(line))
        _DOCSTORE = docs
    return _INDEX, _DOCSTORE

def embed_query(query: str):
    client = get_openai_client()
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[query], encoding_format="float")
    q = np.array([resp.data[0].embedding], dtype=np.float32)
    faiss.normalize_L2(q)
    return q

def vector_search_pool(query: str, pool_size: int):
    index, docs = load_vector_assets()
    q = embed_query(query)
    D, I = index.search(q, pool_size)
    out = []
    for rank, (score, idx) in enumerate(zip(D[0], I[0]), start=1):
        if idx < 0:
            continue
        d = dict(docs[int(idx)])
        d["_vector_rank"] = rank
        d["_vector_score"] = float(score)
        out.append(d)
    return out

def hybrid_textbook_search(query: str, max_results: int, excerpt_char_limit: int):
    ensure_artifacts()
    fts_hits = fts_search_pool(query, max(FTS_POOL, max_results))
    vector_warnings = []
    try:
        vector_hits = vector_search_pool(query, max(VECTOR_POOL, max_results))
    except Exception as e:
        vector_hits = []
        vector_warnings.append(
            f"textbook_vector_unavailable_using_fts_only: {repr(e)}"
        )
    merged = {}

    for h in fts_hits:
        key = h.get("chunk_id") or f"fts:{len(merged)}"
        if key not in merged:
            merged[key] = {"doc": h, "fts_rank": None, "vector_rank": None, "bm25_score": None, "vector_score": None}
        merged[key]["doc"].update({k: v for k, v in h.items() if v is not None})
        merged[key]["fts_rank"] = h.get("_fts_rank")
        merged[key]["bm25_score"] = h.get("_bm25_score")

    for h in vector_hits:
        key = h.get("chunk_id") or f"vec:{h.get('vector_row')}"
        if key not in merged:
            merged[key] = {"doc": h, "fts_rank": None, "vector_rank": None, "bm25_score": None, "vector_score": None}
        merged[key]["doc"].update({k: v for k, v in h.items() if v is not None})
        merged[key]["vector_rank"] = h.get("_vector_rank")
        merged[key]["vector_score"] = h.get("_vector_score")

    ranked = []
    for key, item in merged.items():
        score = 0.0
        if item["fts_rank"]:
            score += 1.0 / (RRF_K + item["fts_rank"])
        if item["vector_rank"]:
            score += 1.0 / (RRF_K + item["vector_rank"])
        if item["fts_rank"] and item["vector_rank"]:
            score += 0.005
        item["fusion_score"] = score
        ranked.append(item)
    ranked.sort(key=lambda x: x["fusion_score"], reverse=True)

    results = []
    for rank, item in enumerate(ranked[:max_results], start=1):
        extra = {
            "fusion_score": item["fusion_score"],
            "fts_rank": item["fts_rank"],
            "vector_rank": item["vector_rank"],
            "bm25_score": item["bm25_score"],
            "vector_score": item["vector_score"],
        }
        if item["fts_rank"] and item["vector_rank"]:
            mode = "hybrid_fts_vector"
        elif item["vector_rank"]:
            mode = "vector_only"
        else:
            mode = "fts_only"
        results.append(row_to_textbook_result(item["doc"], query, excerpt_char_limit, rank, mode, extra))

    if vector_hits:
        warnings = [
            "Textbook retrieval uses hybrid SQLite FTS + FAISS vector search with reciprocal-rank fusion.",
            "Vector search can retrieve semantically related but off-target chunks; judge relevance.",
            "Textbook figure URLs prefer direct public web-safe derivative URLs and fall back to expiring proxy URLs if needed.",
        ]
    else:
        warnings = [
            "Textbook retrieval is using SQLite FTS only because vector embeddings were unavailable.",
            "Textbook figure URLs prefer direct public web-safe derivative URLs and fall back to expiring proxy URLs if needed.",
        ]
    warnings.extend(vector_warnings)
    return results, warnings

def manifest_summary(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

@app.on_event("startup")
def startup_event():
    try:
        ensure_artifacts()
    except Exception as e:
        print(f"Startup artifact download warning: {e}")

@app.get("/health")
def health():
    ensure_artifacts()
    fig_count = 0
    try:
        figs, _ = load_figures()
        fig_count = len(figs)
    except Exception:
        fig_count = -1
    return {
        "schema_version": "pathology_hub_health.v1.5.3",
        "service": "pathology-hub-v04",
        "version": APP_VERSION,
        "loaded": True,
        "textbook_search_mode": "hybrid_fts_faiss_vector_rrf",
        "textbook_figure_mode": "public_web_derivative_urls_with_proxy_fallback",
        "textbook_sqlite_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "textbook_faiss_size_bytes": FAISS_PATH.stat().st_size if FAISS_PATH.exists() else 0,
        "textbook_docstore_size_bytes": DOCSTORE_PATH.stat().st_size if DOCSTORE_PATH.exists() else 0,
        "textbook_figures_size_bytes": FIGURES_PATH.stat().st_size if FIGURES_PATH.exists() else 0,
        "textbook_figure_records_loaded": fig_count,
        "embedding_model": EMBEDDING_MODEL,
        "vectorized": True,
        "api_exposed": True,
        "figure_proxy_enabled": True,
        "public_figure_map_enabled": True,
        "public_figure_map_size_bytes": WEB_MAP_PATH.stat().st_size if WEB_MAP_PATH.exists() else 0,
        "public_figure_map_records_loaded": len(load_web_figure_map()) if WEB_MAP_PATH.exists() else 0,
        "manifest_summary": manifest_summary(MANIFEST_PATH),
        "vector_manifest_summary": manifest_summary(VECTOR_MANIFEST_PATH),
        "upstream_evidence_url": UPSTREAM_EVIDENCE_URL,
    }

@app.post("/evidence/search")
def search_evidence(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    require_key(x_api_key)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base_url = f"{proto}://{host}".rstrip("/")

    sources = [s.lower() for s in (req.sources or ["textbooks"])]
    allowed = {"who", "journals", "pathout", "textbooks"}
    bad = [s for s in sources if s not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unsupported source(s): {bad}")

    response = {
        "schema_version": "evidence_search_response.v1.5.3",
        "query": req.query,
        "source_status": {"who": "not_requested", "journals": "not_requested", "pathout": "not_requested", "textbooks": "not_requested"},
        "who_results": [],
        "journal_results": [],
        "pathout_results": [],
        "textbook_results": [],
        "figures": [],
        "warnings": [],
        "search_mode": {"textbooks": "hybrid_fts_faiss_vector_rrf", "who": "upstream", "journals": "upstream", "pathout": "upstream"}
    }

    if "textbooks" in sources:
        try:
            results, warnings = hybrid_textbook_search(req.query, req.max_results, req.excerpt_char_limit)
            response["textbook_results"] = results
            response["source_status"]["textbooks"] = "ok"
            response["warnings"].extend(warnings)
            if req.include_figures and req.max_figures > 0:
                response["figures"].extend(collect_textbook_figures(results, base_url, req.max_figures))
        except Exception as e:
            response["source_status"]["textbooks"] = "error"
            response["warnings"].append(f"textbook_hybrid_error: {repr(e)}")

    upstream_sources = [s for s in sources if s in {"who", "journals", "pathout"}]
    if upstream_sources:
        if not UPSTREAM_EVIDENCE_URL:
            for s in upstream_sources:
                response["source_status"][s] = "error_no_upstream"
        else:
            try:
                payload = req.dict()
                payload["sources"] = upstream_sources
                headers = {"Content-Type": "application/json"}
                if x_api_key:
                    headers["X-API-Key"] = x_api_key
                r = requests.post(UPSTREAM_EVIDENCE_URL, headers=headers, json=payload, timeout=90)
                if r.status_code >= 400:
                    for s in upstream_sources:
                        response["source_status"][s] = f"upstream_http_{r.status_code}"
                    response["warnings"].append(f"Upstream error {r.status_code}: {r.text[:500]}")
                else:
                    u = r.json()
                    response["who_results"] = u.get("who_results", [])
                    response["journal_results"] = u.get("journal_results", [])
                    response["pathout_results"] = u.get("pathout_results", [])
                    response["figures"].extend(u.get("figures", []) or [])
                    uss = u.get("source_status", {}) or {}
                    for s in upstream_sources:
                        response["source_status"][s] = uss.get(s, "ok")
                    response["warnings"].extend(u.get("warnings", []) or [])
            except Exception as e:
                for s in upstream_sources:
                    response["source_status"][s] = "upstream_error"
                response["warnings"].append(f"upstream_proxy_error: {repr(e)}")

    if not req.include_figures:
        response["figures"] = []
    else:
        response["figures"] = response["figures"][:req.max_figures]

    return response


# ============================================================
# v04.5 JOURNAL HYBRID VECTOR PATCH
# Appended patch: journals = upstream FTS + local FAISS vector + RRF
# ============================================================

JOURNAL_FAISS_GCS = os.environ.get("JOURNAL_FAISS_GCS")
JOURNAL_DOCSTORE_GCS = os.environ.get("JOURNAL_DOCSTORE_GCS")
JOURNAL_VECTOR_MANIFEST_GCS = os.environ.get("JOURNAL_VECTOR_MANIFEST_GCS")

JOURNAL_DATA_DIR = DATA_DIR / "journals"
JOURNAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

JOURNAL_FAISS_PATH = JOURNAL_DATA_DIR / "journal_faiss.index"
JOURNAL_DOCSTORE_PATH = JOURNAL_DATA_DIR / "journal_vector_docstore.jsonl"
JOURNAL_VECTOR_MANIFEST_PATH = JOURNAL_DATA_DIR / "journal_vector_manifest.json"

JOURNAL_VECTOR_POOL = int(os.environ.get("JOURNAL_VECTOR_POOL", "25"))
JOURNAL_FTS_POOL = int(os.environ.get("JOURNAL_FTS_POOL", "10"))

_JOURNAL_INDEX = None
_JOURNAL_DOCSTORE = None

def ensure_journal_artifacts():
    required = [
        (JOURNAL_FAISS_GCS, JOURNAL_FAISS_PATH),
        (JOURNAL_DOCSTORE_GCS, JOURNAL_DOCSTORE_PATH),
        (JOURNAL_VECTOR_MANIFEST_GCS, JOURNAL_VECTOR_MANIFEST_PATH),
    ]
    for uri, dest in required:
        if not uri:
            continue
        if not dest.exists() or dest.stat().st_size < 1024:
            _download_gcs(uri, dest)

def load_journal_vector_assets():
    global _JOURNAL_INDEX, _JOURNAL_DOCSTORE
    ensure_journal_artifacts()
    if _JOURNAL_INDEX is None:
        _JOURNAL_INDEX = faiss.read_index(str(JOURNAL_FAISS_PATH))
    if _JOURNAL_DOCSTORE is None:
        docs = []
        with JOURNAL_DOCSTORE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    docs.append(json.loads(line))
        _JOURNAL_DOCSTORE = docs
    return _JOURNAL_INDEX, _JOURNAL_DOCSTORE

def journal_vector_search_pool(query: str, pool_size: int):
    index, docs = load_journal_vector_assets()
    q = embed_query(query)
    D, I = index.search(q, pool_size)
    out = []
    for rank, (score, idx) in enumerate(zip(D[0], I[0]), start=1):
        if idx < 0:
            continue
        d = dict(docs[int(idx)])
        d["_vector_rank"] = rank
        d["_vector_score"] = float(score)
        out.append(d)
    return out

def upstream_journal_fts_pool(query: str, pool_size: int, x_api_key: Optional[str], req: EvidenceSearchRequest, include_figures: bool = False, max_figures: int = 0):
    if not UPSTREAM_EVIDENCE_URL:
        return [], [], ["journal_fts_no_upstream"], "error_no_upstream"

    payload = req.dict()
    payload["query"] = query
    payload["sources"] = ["journals"]
    payload["max_results"] = max(1, min(10, int(pool_size)))
    payload["include_figures"] = bool(include_figures)
    payload["max_figures"] = max(0, min(10, int(max_figures)))
    payload["compact"] = True

    headers = {"Content-Type": "application/json"}
    if x_api_key:
        headers["X-API-Key"] = x_api_key

    try:
        r = requests.post(UPSTREAM_EVIDENCE_URL, headers=headers, json=payload, timeout=90)
        if r.status_code >= 400:
            return [], [], [f"journal_fts_upstream_http_{r.status_code}: {r.text[:300]}"], f"upstream_http_{r.status_code}"
        u = r.json()
        hits = u.get("journal_results", []) or []
        figs = u.get("figures", []) or []
        warnings = u.get("warnings", []) or []
        status = (u.get("source_status", {}) or {}).get("journals", "ok")
        out = []
        for i, h in enumerate(hits, start=1):
            hh = dict(h)
            hh["_fts_rank"] = i
            hh["_bm25_score"] = h.get("score")
            out.append(hh)
        return out, figs, warnings, status
    except Exception as e:
        return [], [], [f"journal_fts_upstream_error: {repr(e)}"], "upstream_error"

def journal_key(d: dict):
    doi = str(d.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    url = str(d.get("source_url") or d.get("url") or "").strip().lower()
    if url:
        return "url:" + url
    title = str(d.get("title") or "").strip().lower()
    if title:
        return "title:" + re.sub(r"\s+", " ", title)
    chunk_id = str(d.get("chunk_id") or "").strip()
    if chunk_id:
        return "chunk:" + chunk_id
    txt = str(d.get("text") or d.get("excerpt") or "")[:200]
    return "hash:" + hashlib.sha256(txt.encode("utf-8", errors="ignore")).hexdigest()

def merge_nonempty(dst: dict, src: dict):
    for k, v in src.items():
        if k.startswith("_"):
            continue
        if v is None or v == "" or v == []:
            continue
        # Prefer vector text when available, but preserve strong bibliographic fields.
        if k in {"text", "excerpt"}:
            dst[k] = v
        elif k not in dst or dst.get(k) is None or dst.get(k) == "" or dst.get(k) == []:
            dst[k] = v
    return dst

def row_to_journal_result(d, query, limit, rank=None, retrieval_mode="journal_fts", extra=None):
    text = d.get("text") or d.get("chunk_text") or d.get("excerpt") or ""
    title = d.get("title") or d.get("article_title") or ""
    journal = d.get("journal") or d.get("source_name") or d.get("source") or "journals"
    url = d.get("source_url") or d.get("url") or d.get("article_url")
    result = {
        "rank": rank,
        "title": title,
        "source": "journals",
        "source_name": journal,
        "journal": journal,
        "doi": d.get("doi"),
        "source_url": url,
        "url": url,
        "article_id": d.get("article_id"),
        "source_id": d.get("source_id"),
        "record_id": d.get("record_id"),
        "chunk_id": d.get("chunk_id"),
        "chunk_type": d.get("chunk_type"),
        "section": d.get("section"),
        "year": d.get("year"),
        "excerpt": make_excerpt(text, query, limit),
        "text": make_excerpt(text, query, limit),
        "retrieval_mode": retrieval_mode,
    }
    if extra:
        result.update(extra)
    return result

def hybrid_journal_search(query: str, max_results: int, excerpt_char_limit: int, x_api_key: Optional[str], req: EvidenceSearchRequest):
    warnings = [
        "Journal retrieval uses upstream journal FTS plus local FAISS vector search with reciprocal-rank fusion.",
        "Hybrid journal vector search is semantic; judge article relevance, especially for broad entities."
    ]

    fts_hits, upstream_figures, fts_warnings, fts_status = upstream_journal_fts_pool(
        query=query,
        pool_size=max(JOURNAL_FTS_POOL, max_results),
        x_api_key=x_api_key,
        req=req,
        include_figures=req.include_figures,
        max_figures=req.max_figures,
    )
    warnings.extend(fts_warnings or [])

    vector_hits = []
    vector_error = None
    try:
        vector_hits = journal_vector_search_pool(query, max(JOURNAL_VECTOR_POOL, max_results))
    except Exception as e:
        vector_error = repr(e)
        warnings.append(f"journal_vector_error: {vector_error}")

    merged = {}

    for h in fts_hits:
        key = journal_key(h)
        if key not in merged:
            merged[key] = {"doc": {}, "fts_rank": None, "vector_rank": None, "bm25_score": None, "vector_score": None}
        merge_nonempty(merged[key]["doc"], h)
        merged[key]["fts_rank"] = h.get("_fts_rank")
        merged[key]["bm25_score"] = h.get("_bm25_score")

    for h in vector_hits:
        key = journal_key(h)
        if key not in merged:
            merged[key] = {"doc": {}, "fts_rank": None, "vector_rank": None, "bm25_score": None, "vector_score": None}
        merge_nonempty(merged[key]["doc"], h)
        merged[key]["vector_rank"] = h.get("_vector_rank")
        merged[key]["vector_score"] = h.get("_vector_score")

    ranked = []
    for key, item in merged.items():
        score = 0.0
        if item["fts_rank"]:
            score += 1.0 / (RRF_K + item["fts_rank"])
        if item["vector_rank"]:
            score += 1.0 / (RRF_K + item["vector_rank"])
        if item["fts_rank"] and item["vector_rank"]:
            score += 0.006
        item["fusion_score"] = score
        ranked.append(item)

    ranked.sort(key=lambda x: x["fusion_score"], reverse=True)

    results = []
    for rank, item in enumerate(ranked[:max_results], start=1):
        if item["fts_rank"] and item["vector_rank"]:
            mode = "hybrid_fts_vector"
        elif item["vector_rank"]:
            mode = "vector_only"
        else:
            mode = "fts_only"
        extra = {
            "fusion_score": item["fusion_score"],
            "fts_rank": item["fts_rank"],
            "vector_rank": item["vector_rank"],
            "bm25_score": item["bm25_score"],
            "vector_score": item["vector_score"],
        }
        results.append(row_to_journal_result(item["doc"], query, excerpt_char_limit, rank, mode, extra))

    if results:
        status = "ok"
    elif vector_error and fts_status != "ok":
        status = "error"
    else:
        status = fts_status or "ok"

    return results, upstream_figures, warnings, status

# Remove old health and evidence route, then re-register v04.5 versions.
app.router.routes = [
    r for r in app.router.routes
    if not (
        (getattr(r, "path", None) == "/evidence/search" and "POST" in getattr(r, "methods", set()))
        or (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    )
]

@app.on_event("startup")
def startup_event_v045():
    try:
        ensure_artifacts()
    except Exception as e:
        print(f"Startup textbook artifact warning: {e}")
    try:
        ensure_journal_artifacts()
    except Exception as e:
        print(f"Startup journal artifact warning: {e}")

@app.get("/health")
def health_v045():
    ensure_artifacts()
    ensure_journal_artifacts()
    fig_count = 0
    try:
        figs, _ = load_figures()
        fig_count = len(figs)
    except Exception:
        fig_count = -1

    web_map_count = 0
    try:
        if "load_web_figure_map" in globals():
            web_map_count = len(load_web_figure_map())
    except Exception:
        web_map_count = -1

    journal_manifest = manifest_summary(JOURNAL_VECTOR_MANIFEST_PATH)

    return {
        "schema_version": "pathology_hub_health.v1.5.5",
        "service": "pathology-hub-v04",
        "version": APP_VERSION,
        "loaded": True,
        "textbook_search_mode": "hybrid_fts_faiss_vector_rrf",
        "journal_search_mode": "hybrid_upstream_fts_faiss_vector_rrf",
        "textbook_figure_mode": "public_web_derivative_urls_with_proxy_fallback",
        "textbook_sqlite_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "textbook_faiss_size_bytes": FAISS_PATH.stat().st_size if FAISS_PATH.exists() else 0,
        "textbook_docstore_size_bytes": DOCSTORE_PATH.stat().st_size if DOCSTORE_PATH.exists() else 0,
        "textbook_figures_size_bytes": FIGURES_PATH.stat().st_size if FIGURES_PATH.exists() else 0,
        "textbook_figure_records_loaded": fig_count,
        "public_figure_map_enabled": "load_web_figure_map" in globals(),
        "public_figure_map_records_loaded": web_map_count,
        "journal_faiss_size_bytes": JOURNAL_FAISS_PATH.stat().st_size if JOURNAL_FAISS_PATH.exists() else 0,
        "journal_docstore_size_bytes": JOURNAL_DOCSTORE_PATH.stat().st_size if JOURNAL_DOCSTORE_PATH.exists() else 0,
        "journal_vector_manifest_summary": journal_manifest,
        "journal_vectorized": bool(journal_manifest.get("vectorized")),
        "journal_vector_records": journal_manifest.get("record_count"),
        "embedding_model": EMBEDDING_MODEL,
        "vectorized": True,
        "api_exposed": True,
        "figure_proxy_enabled": True,
        "manifest_summary": manifest_summary(MANIFEST_PATH),
        "vector_manifest_summary": manifest_summary(VECTOR_MANIFEST_PATH),
        "upstream_evidence_url": UPSTREAM_EVIDENCE_URL,
    }

@app.post("/evidence/search")
def search_evidence_v045(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    require_key(x_api_key)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base_url = f"{proto}://{host}".rstrip("/")

    sources = [s.lower() for s in (req.sources or ["textbooks"])]
    allowed = {"who", "journals", "pathout", "textbooks"}
    bad = [s for s in sources if s not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unsupported source(s): {bad}")

    response = {
        "schema_version": "evidence_search_response.v1.5.5",
        "query": req.query,
        "source_status": {"who": "not_requested", "journals": "not_requested", "pathout": "not_requested", "textbooks": "not_requested"},
        "who_results": [],
        "journal_results": [],
        "pathout_results": [],
        "textbook_results": [],
        "figures": [],
        "warnings": [],
        "search_mode": {
            "textbooks": "hybrid_fts_faiss_vector_rrf",
            "journals": "hybrid_upstream_fts_faiss_vector_rrf",
            "who": "upstream",
            "pathout": "upstream",
        }
    }

    if "textbooks" in sources:
        try:
            results, warnings = hybrid_textbook_search(req.query, req.max_results, req.excerpt_char_limit)
            response["textbook_results"] = results
            response["source_status"]["textbooks"] = "ok"
            response["warnings"].extend(warnings)
            if req.include_figures and req.max_figures > 0:
                response["figures"].extend(collect_textbook_figures(results, base_url, req.max_figures))
        except Exception as e:
            response["source_status"]["textbooks"] = "error"
            response["warnings"].append(f"textbook_hybrid_error: {repr(e)}")

    if "journals" in sources:
        try:
            j_results, j_figures, j_warnings, j_status = hybrid_journal_search(
                req.query, req.max_results, req.excerpt_char_limit, x_api_key, req
            )
            response["journal_results"] = j_results
            response["source_status"]["journals"] = j_status
            response["warnings"].extend(j_warnings)
            if req.include_figures and req.max_figures > 0:
                response["figures"].extend(j_figures or [])
        except Exception as e:
            response["source_status"]["journals"] = "error"
            response["warnings"].append(f"journal_hybrid_error: {repr(e)}")

    upstream_sources = [s for s in sources if s in {"who", "pathout"}]
    if upstream_sources:
        if not UPSTREAM_EVIDENCE_URL:
            for s in upstream_sources:
                response["source_status"][s] = "error_no_upstream"
        else:
            try:
                payload = req.dict()
                payload["sources"] = upstream_sources
                headers = {"Content-Type": "application/json"}
                if x_api_key:
                    headers["X-API-Key"] = x_api_key
                r = requests.post(UPSTREAM_EVIDENCE_URL, headers=headers, json=payload, timeout=90)
                if r.status_code >= 400:
                    for s in upstream_sources:
                        response["source_status"][s] = f"upstream_http_{r.status_code}"
                    response["warnings"].append(f"Upstream error {r.status_code}: {r.text[:500]}")
                else:
                    u = r.json()
                    response["who_results"] = u.get("who_results", [])
                    response["pathout_results"] = u.get("pathout_results", [])
                    response["figures"].extend(u.get("figures", []) or [])
                    uss = u.get("source_status", {}) or {}
                    for s in upstream_sources:
                        response["source_status"][s] = uss.get(s, "ok")
                    response["warnings"].extend(u.get("warnings", []) or [])
            except Exception as e:
                for s in upstream_sources:
                    response["source_status"][s] = "upstream_error"
                response["warnings"].append(f"upstream_proxy_error: {repr(e)}")

    if not req.include_figures:
        response["figures"] = []
    else:
        response["figures"] = response["figures"][:req.max_figures]

    return response


# ============================================================
# v04.6 SOURCE LOCATOR PATCH
# Enriches searchEvidence results with source/reference links.
# No new GPT Action.
# ============================================================

SOURCE_LOCATOR_REGISTRY_GCS = os.environ.get("SOURCE_LOCATOR_REGISTRY_GCS")
SOURCE_LOCATOR_PATH = DATA_DIR / "source_locator_registry_v1.jsonl"
_SOURCE_LOCATOR = None

def ensure_source_locator_registry():
    if SOURCE_LOCATOR_REGISTRY_GCS and (not SOURCE_LOCATOR_PATH.exists() or SOURCE_LOCATOR_PATH.stat().st_size < 100):
        _download_gcs(SOURCE_LOCATOR_REGISTRY_GCS, SOURCE_LOCATOR_PATH)

def load_source_locator_registry():
    global _SOURCE_LOCATOR
    ensure_source_locator_registry()
    if _SOURCE_LOCATOR is not None:
        return _SOURCE_LOCATOR

    by_family_id = {}
    by_source_id = {}

    if SOURCE_LOCATOR_PATH.exists():
        with SOURCE_LOCATOR_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                fam = str(r.get("source_family") or "").lower()
                sid = str(r.get("source_id") or "").strip()
                if sid:
                    by_family_id[(fam, sid)] = r
                    by_source_id.setdefault(sid, r)

    _SOURCE_LOCATOR = {
        "by_family_id": by_family_id,
        "by_source_id": by_source_id,
        "count": len(by_family_id),
    }
    return _SOURCE_LOCATOR

def _safe_int(x):
    try:
        if x is None or x == "":
            return None
        return int(float(x))
    except Exception:
        return None

def _safe_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None

def _append_fragment(url, fragment):
    if not url:
        return None
    base = str(url).split("#", 1)[0]
    return base + fragment

def make_pdf_page_url(pdf_url, page, offset=0):
    p = _safe_int(page)
    off = _safe_int(offset) or 0
    if not pdf_url or p is None:
        return None
    # Browser PDF viewers commonly use #page=N. This is document-page based.
    return _append_fragment(pdf_url, f"#page={max(1, p + off)}")

def make_video_time_url(video_url, start_sec=None, end_sec=None):
    s = _safe_float(start_sec)
    e = _safe_float(end_sec)
    if not video_url or s is None:
        return None
    if e is not None and e > s:
        return _append_fragment(video_url, f"#t={s:g},{e:g}")
    return _append_fragment(video_url, f"#t={s:g}")

def enrich_hit_with_locator(hit: dict, family_hint: str = None):
    if not isinstance(hit, dict):
        return hit

    loc = load_source_locator_registry()
    by_family_id = loc.get("by_family_id", {})
    by_source_id = loc.get("by_source_id", {})

    source_id = str(hit.get("source_id") or hit.get("source") or hit.get("article_id") or "").strip()
    family = (family_hint or hit.get("source") or hit.get("source_name") or "").lower()

    rec = None
    if source_id:
        rec = by_family_id.get((family, source_id)) or by_family_id.get(("textbooks", source_id)) or by_family_id.get(("videos", source_id)) or by_source_id.get(source_id)

    reference_links = list(hit.get("reference_links") or [])

    # Existing source URL from WHO/PathOut/Journals.
    existing_url = hit.get("source_url") or hit.get("url")
    if existing_url:
        reference_links.append({
            "kind": "source_url",
            "label": "Source URL",
            "url": existing_url,
            "source_family": family_hint or hit.get("source") or hit.get("source_name"),
        })

    if rec:
        # Textbook PDF page links.
        pdf_url = rec.get("pdf_url")
        page = hit.get("page")
        page_url = make_pdf_page_url(pdf_url, page, rec.get("pdf_page_offset", 0))

        if pdf_url:
            hit["source_pdf_url"] = pdf_url
            hit["source_pdf_gcs_uri"] = rec.get("pdf_gcs_uri")
        if page_url:
            hit["source_page_url"] = page_url
            hit["pdf_page_link_verified"] = bool(rec.get("page_link_verified"))
            reference_links.append({
                "kind": "textbook_pdf_page",
                "label": f"PDF page {page}",
                "url": page_url,
                "source_family": "textbooks",
                "source_id": rec.get("source_id"),
                "page": page,
                "pdf_page_offset": rec.get("pdf_page_offset", 0),
                "verified": bool(rec.get("page_link_verified")),
            })

        # Video timestamp links.
        video_url = rec.get("video_url")
        start_sec = hit.get("start_sec") or hit.get("timestamp_start_sec") or hit.get("start")
        end_sec = hit.get("end_sec") or hit.get("timestamp_end_sec") or hit.get("end")
        time_url = make_video_time_url(video_url, start_sec, end_sec)

        if video_url:
            hit["video_url"] = video_url
            hit["video_gcs_uri"] = rec.get("video_gcs_uri")
            reference_links.append({
                "kind": "video",
                "label": "Source video",
                "url": video_url,
                "source_family": "videos",
                "source_id": rec.get("source_id"),
            })
        if time_url:
            hit["video_time_url"] = time_url
            hit["timestamp_link_verified"] = bool(rec.get("timestamp_link_verified"))
            reference_links.append({
                "kind": "video_timestamp",
                "label": f"Video timestamp {start_sec}",
                "url": time_url,
                "source_family": "videos",
                "source_id": rec.get("source_id"),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "verified": bool(rec.get("timestamp_link_verified")),
            })

        hit["source_locator"] = {
            "source_family": rec.get("source_family"),
            "source_id": rec.get("source_id"),
            "title": rec.get("title"),
            "page_link_method": rec.get("page_link_method"),
            "timestamp_link_method": rec.get("timestamp_link_method"),
        }

    # Deduplicate reference_links by URL/kind.
    seen = set()
    clean_links = []
    for link in reference_links:
        key = (link.get("kind"), link.get("url"))
        if not link.get("url") or key in seen:
            continue
        seen.add(key)
        clean_links.append(link)

    if clean_links:
        hit["reference_links"] = clean_links

    return hit

def enrich_evidence_response_with_locators(resp):
    if not isinstance(resp, dict):
        return resp

    for group, fam in [
        ("textbook_results", "textbooks"),
        ("journal_results", "journals"),
        ("pathout_results", "pathout"),
        ("who_results", "who"),
        ("video_results", "videos"),
    ]:
        if isinstance(resp.get(group), list):
            resp[group] = [enrich_hit_with_locator(h, fam) for h in resp[group]]

    if isinstance(resp.get("figures"), list):
        for f in resp["figures"]:
            if isinstance(f, dict):
                # Figures already should have figure_url/image_url. Add source URL link if present.
                links = list(f.get("reference_links") or [])
                for url_key in ["figure_url", "image_url", "source_url", "url"]:
                    url = f.get(url_key)
                    if url:
                        links.append({
                            "kind": url_key,
                            "label": url_key,
                            "url": url,
                            "source_family": f.get("source") or f.get("source_name"),
                            "source_id": f.get("source_id"),
                        })
                seen = set()
                out = []
                for link in links:
                    key = (link.get("kind"), link.get("url"))
                    if not link.get("url") or key in seen:
                        continue
                    seen.add(key)
                    out.append(link)
                if out:
                    f["reference_links"] = out

    resp.setdefault("warnings", [])
    try:
        count = load_source_locator_registry().get("count", 0)
        resp["source_locator_status"] = {
            "enabled": True,
            "registry_records_loaded": count,
            "note": "Textbook page links use #page=N from chunk page plus optional offset; timestamp links require start_sec/end_sec."
        }
    except Exception as e:
        resp["source_locator_status"] = {"enabled": False, "error": repr(e)}
        resp["warnings"].append(f"source_locator_error: {repr(e)}")

    return resp

# Capture existing routes before replacement.
_OLD_HEALTH_ENDPOINT_V046 = None
_OLD_SEARCH_ENDPOINT_V046 = None

for _r in list(app.router.routes):
    if getattr(_r, "path", None) == "/health" and "GET" in getattr(_r, "methods", set()):
        _OLD_HEALTH_ENDPOINT_V046 = getattr(_r, "endpoint", None)
    if getattr(_r, "path", None) == "/evidence/search" and "POST" in getattr(_r, "methods", set()):
        _OLD_SEARCH_ENDPOINT_V046 = getattr(_r, "endpoint", None)

# Remove old /health and /evidence/search routes.
app.router.routes = [
    r for r in app.router.routes
    if not (
        (getattr(r, "path", None) == "/evidence/search" and "POST" in getattr(r, "methods", set()))
        or (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    )
]

@app.on_event("startup")
def startup_event_v046():
    try:
        ensure_artifacts()
    except Exception as e:
        print(f"Startup artifact warning: {e}")
    try:
        ensure_source_locator_registry()
    except Exception as e:
        print(f"Startup source locator warning: {e}")

@app.get("/health")
def health_v046():
    base = {}
    if _OLD_HEALTH_ENDPOINT_V046:
        try:
            base = _OLD_HEALTH_ENDPOINT_V046()
        except Exception as e:
            base = {"old_health_error": repr(e)}
    if not isinstance(base, dict):
        base = {"old_health": str(base)}

    try:
        locator = load_source_locator_registry()
        base["source_locator_enabled"] = True
        base["source_locator_records_loaded"] = locator.get("count", 0)
        base["source_locator_registry_gcs"] = SOURCE_LOCATOR_REGISTRY_GCS
    except Exception as e:
        base["source_locator_enabled"] = False
        base["source_locator_error"] = repr(e)

    base["version"] = "1.5.6-source-locator-v04"
    base["source_locator_mode"] = "textbook_pdf_page_links_and_video_timestamp_links"
    return base

@app.post("/evidence/search")
def search_evidence_v046(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not _OLD_SEARCH_ENDPOINT_V046:
        raise HTTPException(status_code=500, detail="Previous searchEvidence endpoint not found for v04.6 wrapper.")

    try:
        resp = _OLD_SEARCH_ENDPOINT_V046(req, request, x_api_key)
    except TypeError:
        # Fallback for older function arg order/names.
        resp = _OLD_SEARCH_ENDPOINT_V046(req=req, request=request, x_api_key=x_api_key)

    return enrich_evidence_response_with_locators(resp)


# ============================================================
# v04.7 PAGE IMAGE LOCATOR PATCH
# Enriches textbook hits with public page_image_url links.
# No new GPT Action.
# ============================================================

TEXTBOOK_PAGE_IMAGE_INVENTORY_GCS = os.environ.get("TEXTBOOK_PAGE_IMAGE_INVENTORY_GCS")
TEXTBOOK_PAGE_IMAGE_INVENTORY_PATH = DATA_DIR / "textbook_page_image_inventory_v1.jsonl"
_PAGE_IMAGE_INVENTORY = None

def ensure_page_image_inventory():
    if TEXTBOOK_PAGE_IMAGE_INVENTORY_GCS and (not TEXTBOOK_PAGE_IMAGE_INVENTORY_PATH.exists() or TEXTBOOK_PAGE_IMAGE_INVENTORY_PATH.stat().st_size < 100):
        _download_gcs(TEXTBOOK_PAGE_IMAGE_INVENTORY_GCS, TEXTBOOK_PAGE_IMAGE_INVENTORY_PATH)

def load_page_image_inventory():
    global _PAGE_IMAGE_INVENTORY
    ensure_page_image_inventory()
    if _PAGE_IMAGE_INVENTORY is not None:
        return _PAGE_IMAGE_INVENTORY
    by_source_page = {}
    count = 0
    if TEXTBOOK_PAGE_IMAGE_INVENTORY_PATH.exists():
        with TEXTBOOK_PAGE_IMAGE_INVENTORY_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                sid = str(r.get("source_id") or "").strip()
                try:
                    page = int(float(r.get("page")))
                except Exception:
                    continue
                if sid:
                    by_source_page[(sid, page)] = r
                    count += 1
    _PAGE_IMAGE_INVENTORY = {"by_source_page": by_source_page, "count": count}
    return _PAGE_IMAGE_INVENTORY

def enrich_hit_with_page_image(hit: dict):
    if not isinstance(hit, dict):
        return hit
    sid = str(hit.get("source_id") or "").strip()
    try:
        page = int(float(hit.get("page")))
    except Exception:
        page = None
    if not sid or page is None:
        return hit
    inv = load_page_image_inventory().get("by_source_page", {})
    row = inv.get((sid, page))
    if not row:
        hit.setdefault("page_image_status", "not_audited")
        return hit
    hit["page_image_status"] = row.get("page_image_status") or ("exists" if row.get("page_image_url") else "missing")
    if row.get("page_image_url"):
        hit["page_image_url"] = row.get("page_image_url")
        hit["page_image_gcs_uri"] = row.get("page_image_gcs_uri")
    if row.get("source_pdf_url") and not hit.get("source_pdf_url"):
        hit["source_pdf_url"] = row.get("source_pdf_url")
    if row.get("source_page_url") and not hit.get("source_page_url"):
        hit["source_page_url"] = row.get("source_page_url")
    if "pdf_page_link_verified" not in hit:
        hit["pdf_page_link_verified"] = bool(row.get("pdf_page_link_verified"))

    links = list(hit.get("reference_links") or [])
    if row.get("page_image_url"):
        links.insert(0, {
            "kind": "textbook_page_image",
            "label": f"Page image {page}",
            "url": row.get("page_image_url"),
            "source_family": "textbooks",
            "source_id": sid,
            "page": page,
            "verified": True,
        })
    if row.get("source_page_url"):
        links.append({
            "kind": "textbook_pdf_page",
            "label": f"PDF page {page}",
            "url": row.get("source_page_url"),
            "source_family": "textbooks",
            "source_id": sid,
            "page": page,
            "verified": bool(row.get("pdf_page_link_verified")),
        })
    seen = set()
    out = []
    for l in links:
        key = (l.get("kind"), l.get("url"))
        if not l.get("url") or key in seen:
            continue
        seen.add(key)
        out.append(l)
    if out:
        hit["reference_links"] = out
    return hit

def enrich_response_with_page_images(resp):
    if not isinstance(resp, dict):
        return resp
    if isinstance(resp.get("textbook_results"), list):
        resp["textbook_results"] = [enrich_hit_with_page_image(h) for h in resp["textbook_results"]]
    if isinstance(resp.get("figures"), list):
        inv = load_page_image_inventory().get("by_source_page", {})
        for f in resp["figures"]:
            if not isinstance(f, dict):
                continue
            sid = str(f.get("source_id") or "").strip()
            try:
                page = int(float(f.get("page")))
            except Exception:
                page = None
            if sid and page is not None:
                row = inv.get((sid, page))
                if row and row.get("page_image_url"):
                    f["page_image_url"] = row.get("page_image_url")
                    f["page_image_gcs_uri"] = row.get("page_image_gcs_uri")
                    f["page_image_status"] = row.get("page_image_status")
    try:
        resp["page_image_locator_status"] = {
            "enabled": True,
            "inventory_records_loaded": load_page_image_inventory().get("count", 0),
            "inventory_gcs": TEXTBOOK_PAGE_IMAGE_INVENTORY_GCS,
        }
    except Exception as e:
        resp["page_image_locator_status"] = {"enabled": False, "error": repr(e)}
        resp.setdefault("warnings", []).append(f"page_image_locator_error: {repr(e)}")
    return resp

_OLD_HEALTH_ENDPOINT_V047 = None
_OLD_SEARCH_ENDPOINT_V047 = None
for _r in list(app.router.routes):
    if getattr(_r, "path", None) == "/health" and "GET" in getattr(_r, "methods", set()):
        _OLD_HEALTH_ENDPOINT_V047 = getattr(_r, "endpoint", None)
    if getattr(_r, "path", None) == "/evidence/search" and "POST" in getattr(_r, "methods", set()):
        _OLD_SEARCH_ENDPOINT_V047 = getattr(_r, "endpoint", None)

app.router.routes = [
    r for r in app.router.routes
    if not (
        (getattr(r, "path", None) == "/evidence/search" and "POST" in getattr(r, "methods", set()))
        or (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    )
]

@app.on_event("startup")
def startup_event_v047():
    try:
        ensure_page_image_inventory()
    except Exception as e:
        print(f"Startup page image inventory warning: {e}")

@app.get("/health")
def health_v047():
    base = {}
    if _OLD_HEALTH_ENDPOINT_V047:
        try:
            base = _OLD_HEALTH_ENDPOINT_V047()
        except Exception as e:
            base = {"old_health_error": repr(e)}
    if not isinstance(base, dict):
        base = {"old_health": str(base)}
    try:
        inv = load_page_image_inventory()
        base["page_image_locator_enabled"] = True
        base["page_image_inventory_records_loaded"] = inv.get("count", 0)
        base["page_image_inventory_gcs"] = TEXTBOOK_PAGE_IMAGE_INVENTORY_GCS
    except Exception as e:
        base["page_image_locator_enabled"] = False
        base["page_image_locator_error"] = repr(e)
    base["version"] = "1.5.7-page-images-v04"
    base["page_image_locator_mode"] = "public_textbook_page_images_with_pdf_fallback"
    return base

@app.post("/evidence/search")
def search_evidence_v047(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not _OLD_SEARCH_ENDPOINT_V047:
        raise HTTPException(status_code=500, detail="Previous searchEvidence endpoint not found for v04.7 wrapper.")
    try:
        resp = _OLD_SEARCH_ENDPOINT_V047(req, request, x_api_key)
    except TypeError:
        resp = _OLD_SEARCH_ENDPOINT_V047(req=req, request=request, x_api_key=x_api_key)
    return enrich_response_with_page_images(resp)


# ============================================================
# v04.8 PATHOUT + LECTURE VECTOR + TEXTBOOK TAG SIDECAR PATCH
# Adds:
# - textbook primary_tag sidecar enrichment
# - PathOut AP-diagnostic local FAISS vector search
# - lecture STRICT_CYTO_v9 local FAISS vector search
# No new GPT Action; still POST /evidence/search.
# ============================================================

APP_VERSION_V048 = "1.5.8-pathout-lecture-tags-v04"

TEXTBOOK_PRIMARY_TAGGED_CHUNKS_GCS = os.environ.get(
    "TEXTBOOK_PRIMARY_TAGGED_CHUNKS_GCS",
    "gs://pathology_hub/02_normalized/textbooks/lean/tags/textbook_primary_tagged_chunks_v1.jsonl",
)
TEXTBOOK_PRIMARY_TAGGED_CHUNKS_PATH = DATA_DIR / "textbook_primary_tagged_chunks_v1.jsonl"
_TEXTBOOK_PRIMARY_TAG_LOOKUP = None

PATHOUT_AP_FAISS_GCS = os.environ.get(
    "PATHOUT_AP_FAISS_GCS",
    "gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_faiss.index",
)
PATHOUT_AP_DOCSTORE_GCS = os.environ.get(
    "PATHOUT_AP_DOCSTORE_GCS",
    "gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl",
)
PATHOUT_AP_VECTOR_MANIFEST_GCS = os.environ.get(
    "PATHOUT_AP_VECTOR_MANIFEST_GCS",
    "gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_manifest.json",
)

PATHOUT_AP_DATA_DIR = DATA_DIR / "pathout_ap_diagnostic_vector"
PATHOUT_AP_DATA_DIR.mkdir(parents=True, exist_ok=True)
PATHOUT_AP_FAISS_PATH = PATHOUT_AP_DATA_DIR / "pathout_ap_diagnostic_faiss.index"
PATHOUT_AP_DOCSTORE_PATH = PATHOUT_AP_DATA_DIR / "pathout_ap_diagnostic_vector_docstore.jsonl"
PATHOUT_AP_VECTOR_MANIFEST_PATH = PATHOUT_AP_DATA_DIR / "pathout_ap_diagnostic_vector_manifest.json"
PATHOUT_AP_VECTOR_POOL = int(os.environ.get("PATHOUT_AP_VECTOR_POOL", "25"))

_PATHOUT_AP_INDEX = None
_PATHOUT_AP_DOCSTORE = None

LECTURE_FAISS_GCS = os.environ.get(
    "LECTURE_FAISS_GCS",
    "gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_faiss_STRICT_CYTO_v9.index",
)
LECTURE_DOCSTORE_GCS = os.environ.get(
    "LECTURE_DOCSTORE_GCS",
    "gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl",
)
LECTURE_VECTOR_MANIFEST_GCS = os.environ.get(
    "LECTURE_VECTOR_MANIFEST_GCS",
    "gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_manifest_STRICT_CYTO_v9.json",
)

LECTURE_DATA_DIR = DATA_DIR / "lectures_vector_STRICT_CYTO_v9"
LECTURE_DATA_DIR.mkdir(parents=True, exist_ok=True)
LECTURE_FAISS_PATH = LECTURE_DATA_DIR / "lecture_timecoded_faiss_STRICT_CYTO_v9.index"
LECTURE_DOCSTORE_PATH = LECTURE_DATA_DIR / "lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl"
LECTURE_VECTOR_MANIFEST_PATH = LECTURE_DATA_DIR / "lecture_timecoded_vector_manifest_STRICT_CYTO_v9.json"
LECTURE_VECTOR_POOL = int(os.environ.get("LECTURE_VECTOR_POOL", "25"))

_LECTURE_INDEX = None
_LECTURE_DOCSTORE = None

def _download_if_needed_v048(uri: str, dest: Path, min_size: int = 100):
    if uri and (not dest.exists() or dest.stat().st_size < min_size):
        _download_gcs(uri, dest)
    return dest

def _norm_int_v048(x):
    try:
        if x is None or x == "":
            return None
        return int(float(x))
    except Exception:
        return None

def _doc_text_v048(d: dict):
    if not isinstance(d, dict):
        return ""
    for k in [
        "text", "chunk_text", "clean_text", "content", "body",
        "topic_text", "page_text", "transcript_text", "excerpt"
    ]:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""

def _clone_request_sources_v048(req: EvidenceSearchRequest, sources: list):
    data = req.dict()
    data["sources"] = sources
    return EvidenceSearchRequest(**data)

def ensure_textbook_primary_tag_sidecar():
    return _download_if_needed_v048(
        TEXTBOOK_PRIMARY_TAGGED_CHUNKS_GCS,
        TEXTBOOK_PRIMARY_TAGGED_CHUNKS_PATH,
        min_size=1000,
    )

def load_textbook_primary_tag_lookup():
    global _TEXTBOOK_PRIMARY_TAG_LOOKUP
    ensure_textbook_primary_tag_sidecar()
    if _TEXTBOOK_PRIMARY_TAG_LOOKUP is not None:
        return _TEXTBOOK_PRIMARY_TAG_LOOKUP

    by_chunk = {}
    by_source_page = {}
    count = 0

    if TEXTBOOK_PRIMARY_TAGGED_CHUNKS_PATH.exists():
        with TEXTBOOK_PRIMARY_TAGGED_CHUNKS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                count += 1
                cid = str(r.get("chunk_id") or r.get("id") or "").strip()
                if cid:
                    by_chunk[cid] = r

                sid = str(r.get("source_id") or "").strip()
                page = _norm_int_v048(r.get("page") or r.get("page_number") or r.get("source_page"))
                if sid and page is not None:
                    by_source_page.setdefault((sid, page), r)

    _TEXTBOOK_PRIMARY_TAG_LOOKUP = {
        "by_chunk": by_chunk,
        "by_source_page": by_source_page,
        "count": count,
    }
    return _TEXTBOOK_PRIMARY_TAG_LOOKUP

def enrich_textbook_results_with_primary_tags_v048(resp: dict):
    if not isinstance(resp, dict) or not isinstance(resp.get("textbook_results"), list):
        return resp

    try:
        lookup = load_textbook_primary_tag_lookup()
        by_chunk = lookup.get("by_chunk", {})
        by_source_page = lookup.get("by_source_page", {})

        for h in resp.get("textbook_results", []):
            if not isinstance(h, dict):
                continue

            cid = str(h.get("chunk_id") or "").strip()
            row = by_chunk.get(cid)

            if row is None:
                sid = str(h.get("source_id") or "").strip()
                page = _norm_int_v048(h.get("page"))
                if sid and page is not None:
                    row = by_source_page.get((sid, page))

            if row:
                h["primary_tag"] = row.get("primary_tag", "__UNMAPPED__")
                h["primary_tag_status"] = row.get("primary_tag_status") or row.get("tag_status")
                h["primary_tag_basis"] = row.get("primary_tag_basis") or row.get("tag_basis")
                if row.get("primary_tag_join_key"):
                    h["primary_tag_join_key"] = row.get("primary_tag_join_key")
            else:
                h.setdefault("primary_tag", "__UNMAPPED__")
                h.setdefault("primary_tag_status", "missing_from_textbook_primary_tag_sidecar")

        resp["textbook_primary_tag_sidecar_status"] = {
            "enabled": True,
            "records_loaded": lookup.get("count", 0),
            "gcs": TEXTBOOK_PRIMARY_TAGGED_CHUNKS_GCS,
        }

    except Exception as e:
        resp.setdefault("warnings", []).append(f"textbook_primary_tag_sidecar_error: {repr(e)}")
        resp["textbook_primary_tag_sidecar_status"] = {
            "enabled": False,
            "error": repr(e),
            "gcs": TEXTBOOK_PRIMARY_TAGGED_CHUNKS_GCS,
        }

    return resp

def ensure_pathout_ap_vector_artifacts():
    _download_if_needed_v048(PATHOUT_AP_FAISS_GCS, PATHOUT_AP_FAISS_PATH, min_size=1000)
    _download_if_needed_v048(PATHOUT_AP_DOCSTORE_GCS, PATHOUT_AP_DOCSTORE_PATH, min_size=1000)
    _download_if_needed_v048(PATHOUT_AP_VECTOR_MANIFEST_GCS, PATHOUT_AP_VECTOR_MANIFEST_PATH, min_size=100)

def load_pathout_ap_vector_assets():
    global _PATHOUT_AP_INDEX, _PATHOUT_AP_DOCSTORE
    ensure_pathout_ap_vector_artifacts()
    if _PATHOUT_AP_INDEX is None:
        _PATHOUT_AP_INDEX = faiss.read_index(str(PATHOUT_AP_FAISS_PATH))
    if _PATHOUT_AP_DOCSTORE is None:
        docs = []
        with PATHOUT_AP_DOCSTORE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    docs.append(json.loads(line))
        _PATHOUT_AP_DOCSTORE = docs
    return _PATHOUT_AP_INDEX, _PATHOUT_AP_DOCSTORE

def pathout_ap_vector_pool(query: str, pool_size: int):
    index, docs = load_pathout_ap_vector_assets()
    q = embed_query(query)
    D, I = index.search(q, pool_size)
    out = []
    for rank, (score, idx) in enumerate(zip(D[0], I[0]), start=1):
        if idx < 0:
            continue
        d = dict(docs[int(idx)])
        d["_vector_rank"] = rank
        d["_vector_score"] = float(score)
        out.append(d)
    return out

def row_to_pathout_result_v048(d: dict, query: str, limit: int, rank: int = None):
    text = _doc_text_v048(d)
    url = (
        d.get("source_url") or d.get("url") or d.get("pathout_url")
        or d.get("topic_url") or d.get("canonical_url")
    )
    title = (
        d.get("title") or d.get("topic_title") or d.get("heading")
        or d.get("source_title") or d.get("source_id") or "Pathology Outlines"
    )
    return {
        "rank": rank,
        "title": title,
        "source": "pathout",
        "source_name": "Pathology Outlines",
        "source_type": "pathout_ap_diagnostic_vector",
        "source_id": d.get("source_id") or d.get("topic_id") or d.get("pathout_id"),
        "record_id": d.get("record_id") or d.get("id"),
        "document_id": d.get("document_id") or d.get("doc_id"),
        "chunk_id": d.get("chunk_id") or d.get("id"),
        "url": url,
        "source_url": url,
        "section": d.get("section") or d.get("section_heading"),
        "topic": d.get("topic") or d.get("topic_title"),
        "site": d.get("site") or d.get("organ_system") or d.get("subject"),
        "primary_tag": d.get("primary_tag"),
        "tag_status": d.get("tag_status"),
        "excerpt": make_excerpt(text, query, limit),
        "text": make_excerpt(text, query, limit),
        "retrieval_mode": "pathout_ap_diagnostic_vector",
        "vector_rank": d.get("_vector_rank"),
        "vector_score": d.get("_vector_score"),
        "api_exposed_source": "local_pathout_ap_vector_v048",
    }

def _result_key_v048(d: dict):
    if not isinstance(d, dict):
        return "none"
    for k in ["source_url", "url", "chunk_id", "document_id", "record_id", "title"]:
        v = d.get(k)
        if v:
            return f"{k}:{str(v).strip().lower()}"
    txt = str(d.get("text") or d.get("excerpt") or "")[:300]
    return "hash:" + hashlib.sha256(txt.encode("utf-8", errors="ignore")).hexdigest()

def _merge_result_lists_v048(preferred: list, fallback: list, max_results: int):
    out = []
    seen = set()
    for group in [preferred or [], fallback or []]:
        for h in group:
            key = _result_key_v048(h)
            if key in seen:
                continue
            seen.add(key)
            out.append(h)
            if len(out) >= max_results:
                return out
    return out

def local_pathout_ap_search_v048(query: str, max_results: int, excerpt_char_limit: int):
    hits = pathout_ap_vector_pool(query, max(PATHOUT_AP_VECTOR_POOL, max_results))
    results = [
        row_to_pathout_result_v048(h, query, excerpt_char_limit, rank=i)
        for i, h in enumerate(hits[:max_results], start=1)
    ]
    warnings = [
        "PathOut retrieval includes local AP-diagnostic filtered FAISS vector search.",
        "PathOut AP vector artifacts are filtered/tagged offline; judge semantic vector hits for specificity.",
    ]
    return results, warnings

def ensure_lecture_vector_artifacts():
    _download_if_needed_v048(LECTURE_FAISS_GCS, LECTURE_FAISS_PATH, min_size=1000)
    _download_if_needed_v048(LECTURE_DOCSTORE_GCS, LECTURE_DOCSTORE_PATH, min_size=1000)
    _download_if_needed_v048(LECTURE_VECTOR_MANIFEST_GCS, LECTURE_VECTOR_MANIFEST_PATH, min_size=100)

def load_lecture_vector_assets():
    global _LECTURE_INDEX, _LECTURE_DOCSTORE
    ensure_lecture_vector_artifacts()
    if _LECTURE_INDEX is None:
        _LECTURE_INDEX = faiss.read_index(str(LECTURE_FAISS_PATH))
    if _LECTURE_DOCSTORE is None:
        docs = []
        with LECTURE_DOCSTORE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    docs.append(json.loads(line))
        _LECTURE_DOCSTORE = docs
    return _LECTURE_INDEX, _LECTURE_DOCSTORE

def lecture_vector_pool(query: str, pool_size: int):
    index, docs = load_lecture_vector_assets()
    q = embed_query(query)
    D, I = index.search(q, pool_size)
    out = []
    for rank, (score, idx) in enumerate(zip(D[0], I[0]), start=1):
        if idx < 0:
            continue
        d = dict(docs[int(idx)])
        d["_vector_rank"] = rank
        d["_vector_score"] = float(score)
        out.append(d)
    return out

def row_to_lecture_result_v048(d: dict, query: str, limit: int, rank: int = None):
    text = _doc_text_v048(d)
    video_url = d.get("video_url") or d.get("source_video_url")
    start_sec = d.get("start_sec") or d.get("timestamp_start_sec") or d.get("start")
    end_sec = d.get("end_sec") or d.get("timestamp_end_sec") or d.get("end")
    time_url = d.get("video_time_url") or make_video_time_url(video_url, start_sec, end_sec)

    return {
        "rank": rank,
        "title": d.get("title") or d.get("lecture_title") or d.get("video_id") or "Lecture",
        "source": "videos",
        "source_name": "lectures",
        "source_type": "lecture_timecoded_chunk",
        "source_id": d.get("video_id") or d.get("source_id") or d.get("lecture_id"),
        "video_id": d.get("video_id") or d.get("source_id") or d.get("lecture_id"),
        "chunk_id": d.get("chunk_id") or d.get("id"),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "video_url": video_url,
        "video_time_url": time_url,
        "primary_tag": d.get("primary_tag"),
        "tag_status": d.get("tag_status"),
        "tag_basis": d.get("tag_basis"),
        "tagging_scope": d.get("tagging_scope") or "STRICT_CYTO_v9_routed_only",
        "excerpt": make_excerpt(text, query, limit),
        "text": make_excerpt(text, query, limit),
        "retrieval_mode": "lecture_STRICT_CYTO_v9_vector",
        "vector_rank": d.get("_vector_rank"),
        "vector_score": d.get("_vector_score"),
        "api_exposed_source": "local_lecture_vector_STRICT_CYTO_v9_v048",
    }

def local_lecture_search_v048(query: str, max_results: int, excerpt_char_limit: int):
    hits = lecture_vector_pool(query, max(LECTURE_VECTOR_POOL, max_results))
    results = [
        row_to_lecture_result_v048(h, query, excerpt_char_limit, rank=i)
        for i, h in enumerate(hits[:max_results], start=1)
    ]
    warnings = [
        "Lecture retrieval uses local STRICT_CYTO_v9 routed-only FAISS vector artifacts.",
        "Uncertain lecture chunks are held out from this index; __UNMAPPED__ routed chunks remain searchable.",
    ]
    return results, warnings

_OLD_HEALTH_ENDPOINT_V048 = None
_OLD_SEARCH_ENDPOINT_V048 = None
for _r in list(app.router.routes):
    if getattr(_r, "path", None) == "/health" and "GET" in getattr(_r, "methods", set()):
        _OLD_HEALTH_ENDPOINT_V048 = getattr(_r, "endpoint", None)
    if getattr(_r, "path", None) == "/evidence/search" and "POST" in getattr(_r, "methods", set()):
        _OLD_SEARCH_ENDPOINT_V048 = getattr(_r, "endpoint", None)

app.router.routes = [
    r for r in app.router.routes
    if not (
        (getattr(r, "path", None) == "/evidence/search" and "POST" in getattr(r, "methods", set()))
        or (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    )
]

@app.on_event("startup")
def startup_event_v048():
    for name, fn in [
        ("textbook_primary_tag_sidecar", ensure_textbook_primary_tag_sidecar),
        ("pathout_ap_vector", ensure_pathout_ap_vector_artifacts),
        ("lecture_vector", ensure_lecture_vector_artifacts),
    ]:
        try:
            fn()
        except Exception as e:
            print(f"Startup {name} warning: {e}")

@app.get("/health")
def health_v048():
    base = {}
    if _OLD_HEALTH_ENDPOINT_V048:
        try:
            base = _OLD_HEALTH_ENDPOINT_V048()
        except Exception as e:
            base = {"old_health_error": repr(e)}
    if not isinstance(base, dict):
        base = {"old_health": str(base)}

    base["schema_version"] = "pathology_hub_health.v1.5.8"
    base["version"] = APP_VERSION_V048
    base["textbook_primary_tag_sidecar_gcs"] = TEXTBOOK_PRIMARY_TAGGED_CHUNKS_GCS

    try:
        ensure_textbook_primary_tag_sidecar()
        base["textbook_primary_tag_sidecar_enabled"] = True
        base["textbook_primary_tag_sidecar_size_bytes"] = TEXTBOOK_PRIMARY_TAGGED_CHUNKS_PATH.stat().st_size
    except Exception as e:
        base["textbook_primary_tag_sidecar_enabled"] = False
        base["textbook_primary_tag_sidecar_error"] = repr(e)

    try:
        ensure_pathout_ap_vector_artifacts()
        pm = manifest_summary(PATHOUT_AP_VECTOR_MANIFEST_PATH)
        base["pathout_ap_vector_manifest_summary"] = pm
        base["pathout_ap_vectorized"] = bool(pm.get("vectorized"))
        base["pathout_ap_vector_records"] = pm.get("record_count")
        base["pathout_ap_api_exposed"] = True
        base["pathout_ap_faiss_size_bytes"] = PATHOUT_AP_FAISS_PATH.stat().st_size if PATHOUT_AP_FAISS_PATH.exists() else 0
        base["pathout_ap_docstore_size_bytes"] = PATHOUT_AP_DOCSTORE_PATH.stat().st_size if PATHOUT_AP_DOCSTORE_PATH.exists() else 0
    except Exception as e:
        base["pathout_ap_api_exposed"] = False
        base["pathout_ap_vector_error"] = repr(e)

    try:
        ensure_lecture_vector_artifacts()
        lm = manifest_summary(LECTURE_VECTOR_MANIFEST_PATH)
        base["lecture_vector_manifest_summary"] = lm
        base["lecture_vectorized"] = bool(lm.get("vectorized"))
        base["lecture_vector_records"] = lm.get("record_count")
        base["lecture_api_exposed"] = True
        base["lecture_faiss_size_bytes"] = LECTURE_FAISS_PATH.stat().st_size if LECTURE_FAISS_PATH.exists() else 0
        base["lecture_docstore_size_bytes"] = LECTURE_DOCSTORE_PATH.stat().st_size if LECTURE_DOCSTORE_PATH.exists() else 0
    except Exception as e:
        base["lecture_api_exposed"] = False
        base["lecture_vector_error"] = repr(e)

    base["search_mode"] = {
        "textbooks": "hybrid_fts_faiss_vector_rrf_plus_primary_tag_sidecar",
        "journals": "hybrid_upstream_fts_faiss_vector_rrf",
        "pathout": "upstream_plus_local_ap_diagnostic_faiss_vector",
        "lectures": "local_STRICT_CYTO_v9_faiss_vector",
        "videos": "local_STRICT_CYTO_v9_faiss_vector",
        "who": "upstream",
    }
    return base

@app.post("/evidence/search")
def search_evidence_v048(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    require_key(x_api_key)

    requested = [str(s).lower() for s in (req.sources or ["textbooks"])]
    alias_to_source = {
        "lecture": "lectures",
        "lectures": "lectures",
        "video": "lectures",
        "videos": "lectures",
        "textbook": "textbooks",
        "textbooks": "textbooks",
        "journal": "journals",
        "journals": "journals",
        "who": "who",
        "pathout": "pathout",
        "pathology_outlines": "pathout",
    }
    normalized = [alias_to_source.get(s, s) for s in requested]
    allowed = {"who", "journals", "pathout", "textbooks", "lectures"}
    bad = [s for s in normalized if s not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unsupported source(s): {bad}")

    old_sources = [s for s in normalized if s in {"who", "journals", "pathout", "textbooks"}]
    wants_lectures = "lectures" in normalized
    wants_pathout = "pathout" in normalized

    if old_sources and _OLD_SEARCH_ENDPOINT_V048:
        old_req = _clone_request_sources_v048(req, old_sources)
        try:
            resp = _OLD_SEARCH_ENDPOINT_V048(old_req, request, x_api_key)
        except TypeError:
            resp = _OLD_SEARCH_ENDPOINT_V048(req=old_req, request=request, x_api_key=x_api_key)
    else:
        resp = {
            "schema_version": "evidence_search_response.v1.5.8",
            "query": req.query,
            "source_status": {
                "who": "not_requested",
                "journals": "not_requested",
                "pathout": "not_requested",
                "textbooks": "not_requested",
                "lectures": "not_requested",
                "videos": "not_requested",
            },
            "who_results": [],
            "journal_results": [],
            "pathout_results": [],
            "textbook_results": [],
            "lecture_results": [],
            "video_results": [],
            "figures": [],
            "warnings": [],
            "search_mode": {},
        }

    if not isinstance(resp, dict):
        resp = {"raw_response": resp, "warnings": ["old_endpoint_returned_non_dict"]}

    resp["schema_version"] = "evidence_search_response.v1.5.8"
    resp.setdefault("source_status", {})
    resp.setdefault("warnings", [])
    resp.setdefault("search_mode", {})
    resp.setdefault("textbook_results", [])
    resp.setdefault("pathout_results", [])
    resp.setdefault("journal_results", [])
    resp.setdefault("who_results", [])
    resp.setdefault("figures", [])

    if "textbooks" in normalized or resp.get("textbook_results"):
        enrich_textbook_results_with_primary_tags_v048(resp)
        resp["search_mode"]["textbooks"] = "hybrid_fts_faiss_vector_rrf_plus_primary_tag_sidecar"

    if wants_pathout:
        try:
            local_po, po_warnings = local_pathout_ap_search_v048(req.query, req.max_results, req.excerpt_char_limit)
            resp["pathout_results"] = _merge_result_lists_v048(local_po, resp.get("pathout_results", []), req.max_results)
            resp["source_status"]["pathout"] = "ok"
            resp["warnings"].extend(po_warnings)
            resp["search_mode"]["pathout"] = "upstream_plus_local_ap_diagnostic_faiss_vector"
            resp["pathout_ap_vector_status"] = {
                "enabled": True,
                "api_exposed": True,
                "manifest_gcs": PATHOUT_AP_VECTOR_MANIFEST_GCS,
                "records": manifest_summary(PATHOUT_AP_VECTOR_MANIFEST_PATH).get("record_count") if PATHOUT_AP_VECTOR_MANIFEST_PATH.exists() else None,
            }
        except Exception as e:
            if resp["source_status"].get("pathout") in (None, "not_requested"):
                resp["source_status"]["pathout"] = "vector_error"
            resp["warnings"].append(f"pathout_ap_vector_error: {repr(e)}")
            resp["pathout_ap_vector_status"] = {"enabled": False, "error": repr(e)}

    if wants_lectures:
        try:
            lecture_hits, lecture_warnings = local_lecture_search_v048(req.query, req.max_results, req.excerpt_char_limit)
            resp["video_results"] = lecture_hits
            resp["lecture_results"] = lecture_hits
            resp["source_status"]["lectures"] = "ok"
            resp["source_status"]["videos"] = "ok"
            resp["warnings"].extend(lecture_warnings)
            resp["search_mode"]["lectures"] = "local_STRICT_CYTO_v9_faiss_vector"
            resp["search_mode"]["videos"] = "local_STRICT_CYTO_v9_faiss_vector"
            resp["lecture_vector_status"] = {
                "enabled": True,
                "api_exposed": True,
                "manifest_gcs": LECTURE_VECTOR_MANIFEST_GCS,
                "records": manifest_summary(LECTURE_VECTOR_MANIFEST_PATH).get("record_count") if LECTURE_VECTOR_MANIFEST_PATH.exists() else None,
            }
        except Exception as e:
            resp["source_status"]["lectures"] = "vector_error"
            resp["source_status"]["videos"] = "vector_error"
            resp["warnings"].append(f"lecture_vector_error: {repr(e)}")
            resp["lecture_vector_status"] = {"enabled": False, "error": repr(e)}

    try:
        if "enrich_evidence_response_with_locators" in globals():
            resp = enrich_evidence_response_with_locators(resp)
    except Exception as e:
        resp.setdefault("warnings", []).append(f"v048_source_locator_reenrich_error: {repr(e)}")

    try:
        if "enrich_response_with_page_images" in globals():
            resp = enrich_response_with_page_images(resp)
    except Exception as e:
        resp.setdefault("warnings", []).append(f"v048_page_image_reenrich_error: {repr(e)}")

    if wants_lectures and isinstance(resp.get("video_results"), list):
        resp["lecture_results"] = resp["video_results"]

    if not req.include_figures:
        resp["figures"] = []
    else:
        resp["figures"] = (resp.get("figures") or [])[:req.max_figures]

    return resp


# ============================================================
# v1.5.9 CURRICULUM MAP v0.2 PATCH
# Adds Curriculum Map v0.2 as source="curriculum" on existing
# searchEvidence only. No separate GPT Action.
# ============================================================

APP_VERSION_V159 = "1.5.9-curriculum-map-v02"

CURRICULUM_VERSION = "v0.2"
CURRICULUM_HTML_URL = os.environ.get(
    "CURRICULUM_HTML_URL",
    "https://storage.googleapis.com/pathology_hub/05_html/curriculum_map/v0_2/curriculum_browser_v0_2.html",
)
CURRICULUM_SQLITE_GCS = os.environ.get(
    "CURRICULUM_SQLITE_GCS",
    "gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_tag_index_v0_2.sqlite",
)
CURRICULUM_NODES_GCS = os.environ.get(
    "CURRICULUM_NODES_GCS",
    "gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_nodes_v0_2.csv",
)
CURRICULUM_REVIEW_QUEUE_GCS = os.environ.get(
    "CURRICULUM_REVIEW_QUEUE_GCS",
    "gs://pathology_hub/02_normalized/curriculum_map/v0_2/review_queue_v0_2.csv",
)
CURRICULUM_REJECTED_TAGS_GCS = os.environ.get(
    "CURRICULUM_REJECTED_TAGS_GCS",
    "gs://pathology_hub/02_normalized/curriculum_map/v0_2/rejected_tags_v0_2.csv",
)
CURRICULUM_ACCEPTANCE_GCS = os.environ.get(
    "CURRICULUM_ACCEPTANCE_GCS",
    "gs://pathology_hub/06_audits/curriculum_map/v0_2/acceptance_summary_v0_2.json",
)

CURRICULUM_DATA_DIR = DATA_DIR / "curriculum_map_v0_2"
CURRICULUM_DATA_DIR.mkdir(parents=True, exist_ok=True)
CURRICULUM_SQLITE_PATH = CURRICULUM_DATA_DIR / "curriculum_tag_index_v0_2.sqlite"
CURRICULUM_NODES_PATH = CURRICULUM_DATA_DIR / "curriculum_nodes_v0_2.csv"
CURRICULUM_REVIEW_QUEUE_PATH = CURRICULUM_DATA_DIR / "review_queue_v0_2.csv"
CURRICULUM_REJECTED_TAGS_PATH = CURRICULUM_DATA_DIR / "rejected_tags_v0_2.csv"
CURRICULUM_ACCEPTANCE_PATH = CURRICULUM_DATA_DIR / "acceptance_summary_v0_2.json"

_CURRICULUM_CACHE = None

CURRICULUM_FORBIDDEN_PATTERNS = [
    "::Lectures::",
    "::Textbooks::",
    "::Error",
    "Slide_",
    "Page_",
    "Digital_Pathology_Slide",
    "Pathology_Slide",
    "rejected_generated",
]

def _is_gs_uri_v159(uri: str):
    return isinstance(uri, str) and uri.startswith("gs://")

def _download_curriculum_if_needed_v159(uri: str, dest: Path, min_size: int = 1):
    if not uri:
        return dest
    if dest.exists() and dest.stat().st_size >= min_size:
        return dest
    if _is_gs_uri_v159(uri):
        return _download_gcs(uri, dest)
    src = Path(uri)
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
    return dest

def ensure_curriculum_artifacts_v159():
    _download_curriculum_if_needed_v159(CURRICULUM_SQLITE_GCS, CURRICULUM_SQLITE_PATH, min_size=1000)
    _download_curriculum_if_needed_v159(CURRICULUM_NODES_GCS, CURRICULUM_NODES_PATH, min_size=100)
    _download_curriculum_if_needed_v159(CURRICULUM_REVIEW_QUEUE_GCS, CURRICULUM_REVIEW_QUEUE_PATH, min_size=100)
    _download_curriculum_if_needed_v159(CURRICULUM_REJECTED_TAGS_GCS, CURRICULUM_REJECTED_TAGS_PATH, min_size=100)
    _download_curriculum_if_needed_v159(CURRICULUM_ACCEPTANCE_GCS, CURRICULUM_ACCEPTANCE_PATH, min_size=100)

def _contains_forbidden_curriculum_tag_v159(tag: str):
    tag = str(tag or "")
    return any(p in tag for p in CURRICULUM_FORBIDDEN_PATTERNS)

def _read_csv_count_v159(path: Path):
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0

def load_curriculum_cache_v159():
    global _CURRICULUM_CACHE
    ensure_curriculum_artifacts_v159()
    if _CURRICULUM_CACHE is not None:
        return _CURRICULUM_CACHE

    acceptance = manifest_summary(CURRICULUM_ACCEPTANCE_PATH)
    nodes = []
    if CURRICULUM_NODES_PATH.exists():
        with CURRICULUM_NODES_PATH.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                tag = row.get("tag") or ""
                if tag and not _contains_forbidden_curriculum_tag_v159(tag):
                    nodes.append({
                        "tag": tag,
                        "root": row.get("root") or (tag.split("::", 1)[0] if "::" in tag else tag),
                        "record_count": _norm_int_v048(row.get("record_count")) or 0,
                    })

    _CURRICULUM_CACHE = {
        "acceptance": acceptance,
        "nodes": nodes,
        "review_queue_count": acceptance.get("review_queue_count") or _read_csv_count_v159(CURRICULUM_REVIEW_QUEUE_PATH),
        "rejected_hidden_count": acceptance.get("records_hidden_rejected") or _read_csv_count_v159(CURRICULUM_REJECTED_TAGS_PATH),
    }
    return _CURRICULUM_CACHE

def curriculum_status_v159():
    cache = load_curriculum_cache_v159()
    acceptance = cache.get("acceptance", {}) or {}
    return {
        "version": CURRICULUM_VERSION,
        "build_status": acceptance.get("build_status", "unknown"),
        "forbidden_visible_tag_count": acceptance.get("forbidden_visible_tag_count"),
        "visible_curriculum_records": acceptance.get("records_visible_in_curriculum"),
        "review_queue_count": cache.get("review_queue_count"),
        "rejected_hidden_count": cache.get("rejected_hidden_count"),
        "html_url": CURRICULUM_HTML_URL,
        "gcs_paths_used": {
            "sqlite": CURRICULUM_SQLITE_GCS,
            "nodes": CURRICULUM_NODES_GCS,
            "review_queue": CURRICULUM_REVIEW_QUEUE_GCS,
            "rejected_tags": CURRICULUM_REJECTED_TAGS_GCS,
            "acceptance_summary": CURRICULUM_ACCEPTANCE_GCS,
        },
    }

def _curriculum_conn_v159():
    ensure_curriculum_artifacts_v159()
    conn = sqlite3.connect(str(CURRICULUM_SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _curriculum_query_mode_v159(query: str):
    q = (query or "").strip()
    low = q.lower()
    if low.startswith("root:"):
        return "root_prefix", q.split(":", 1)[1].strip()
    if low.startswith("tag:"):
        return "tag_token", q.split(":", 1)[1].strip()
    if "::" in q:
        return "tag_or_root_prefix", q
    return "free_text", q

def _curriculum_tokenize_v159(query: str):
    return [t.lower() for t in re.findall(r"[A-Za-z0-9_]+", query or "") if len(t) > 1]

def _curriculum_source_counts_v159(conn, tag: str):
    rows = conn.execute(
        "SELECT source, count FROM tag_counts WHERE tag = ? ORDER BY count DESC",
        (tag,),
    ).fetchall()
    return {str(r["source"]): int(r["count"] or 0) for r in rows}

def _curriculum_review_count_v159(conn, tag: str):
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM review_queue WHERE original_tag = ?",
            (tag,),
        ).fetchone()
        return int(row["n"] or 0)
    except Exception:
        return 0

def _curriculum_examples_v159(conn, tag: str, compact: bool):
    limit = 3 if compact else 8
    rows = conn.execute(
        """
        SELECT source, record_id, title
        FROM high_yield_examples
        WHERE tag = ?
        LIMIT ?
        """,
        (tag, limit),
    ).fetchall()
    return [dict(r) for r in rows]

def _curriculum_score_node_v159(node: dict, query: str, mode: str, value: str):
    tag = node.get("tag") or ""
    root = node.get("root") or ""
    tag_low = tag.lower()
    root_low = root.lower()
    val_low = (value or "").lower()

    if mode == "root_prefix":
        if tag_low.startswith(val_low) or root_low == val_low:
            return 1000 + int(node.get("record_count") or 0), "root_prefix"
        return 0, None
    if mode == "tag_token":
        if val_low and val_low in tag_low:
            return 800 + int(node.get("record_count") or 0), "tag_token"
        return 0, None
    if mode == "tag_or_root_prefix":
        if tag_low == val_low:
            return 1200 + int(node.get("record_count") or 0), "exact_tag"
        if tag_low.startswith(val_low):
            return 950 + int(node.get("record_count") or 0), "tag_prefix"
        if root_low == val_low:
            return 900 + int(node.get("record_count") or 0), "root"
        return 0, None

    tokens = _curriculum_tokenize_v159(query)
    if not tokens:
        return 0, None
    hits = sum(1 for t in tokens if t in tag_low or t in root_low)
    if hits <= 0:
        return 0, None
    exact_bonus = 150 if any(t == root_low for t in tokens) else 0
    return hits * 100 + exact_bonus + min(int(node.get("record_count") or 0), 2000) / 1000.0, "free_text"

def curriculum_search_v159(query: str, max_results: int, compact: bool = True):
    cache = load_curriculum_cache_v159()
    mode, value = _curriculum_query_mode_v159(query)
    scored = []
    for node in cache.get("nodes", []):
        if _contains_forbidden_curriculum_tag_v159(node.get("tag")):
            continue
        score, matched_by = _curriculum_score_node_v159(node, query, mode, value)
        if score:
            scored.append((score, matched_by, node))

    scored.sort(key=lambda x: (x[0], int(x[2].get("record_count") or 0), x[2].get("tag") or ""), reverse=True)
    limit = max(1, min(10, int(max_results or 3)))

    out = []
    warnings = []
    with _curriculum_conn_v159() as conn:
        for rank, (score, matched_by, node) in enumerate(scored[:limit], start=1):
            tag = node.get("tag")
            review_count = _curriculum_review_count_v159(conn, tag)
            rec = {
                "rank": rank,
                "tag": tag,
                "root": node.get("root"),
                "status": "approved_visible_curriculum_node",
                "source_counts": _curriculum_source_counts_v159(conn, tag),
                "sources": sorted(_curriculum_source_counts_v159(conn, tag).keys()),
                "visible_record_count": int(node.get("record_count") or 0),
                "review_count": review_count,
                "example_records": _curriculum_examples_v159(conn, tag, compact=compact),
                "examples": _curriculum_examples_v159(conn, tag, compact=compact),
                "matched_by": matched_by,
                "score": score,
            }
            out.append(rec)

    if not out:
        warnings.append("curriculum_no_approved_visible_node_match")
    if cache.get("review_queue_count"):
        warnings.append("Curriculum review_queue rows are counted in curriculum_status but are not mixed into approved curriculum_results.")
    return out, warnings

_OLD_HEALTH_ENDPOINT_V159 = None
_OLD_SEARCH_ENDPOINT_V159 = None
for _r in list(app.router.routes):
    if getattr(_r, "path", None) == "/health" and "GET" in getattr(_r, "methods", set()):
        _OLD_HEALTH_ENDPOINT_V159 = getattr(_r, "endpoint", None)
    if getattr(_r, "path", None) == "/evidence/search" and "POST" in getattr(_r, "methods", set()):
        _OLD_SEARCH_ENDPOINT_V159 = getattr(_r, "endpoint", None)

app.router.routes = [
    r for r in app.router.routes
    if not (
        (getattr(r, "path", None) == "/evidence/search" and "POST" in getattr(r, "methods", set()))
        or (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    )
]

@app.on_event("startup")
def startup_event_v159():
    try:
        ensure_curriculum_artifacts_v159()
    except Exception as e:
        print(f"Startup curriculum artifact warning: {e}")

@app.get("/health")
def health_v159():
    base = {}
    if _OLD_HEALTH_ENDPOINT_V159:
        try:
            base = _OLD_HEALTH_ENDPOINT_V159()
        except Exception as e:
            base = {"old_health_error": repr(e)}
    if not isinstance(base, dict):
        base = {"old_health": str(base)}

    try:
        status = curriculum_status_v159()
        base["curriculum_map_enabled"] = True
        base["curriculum_map_version"] = CURRICULUM_VERSION
        base["curriculum_map_build_status"] = status.get("build_status")
        base["curriculum_map_forbidden_visible_tag_count"] = status.get("forbidden_visible_tag_count")
        base["curriculum_map_records_visible"] = status.get("visible_curriculum_records")
        base["curriculum_map_review_queue_count"] = status.get("review_queue_count")
        base["curriculum_map_html_url"] = status.get("html_url")
    except Exception as e:
        base["curriculum_map_enabled"] = False
        base["curriculum_map_error"] = repr(e)

    base["schema_version"] = "pathology_hub_health.v1.5.9"
    base["version"] = APP_VERSION_V159
    base.setdefault("search_mode", {})
    if isinstance(base["search_mode"], dict):
        base["search_mode"]["curriculum"] = "local_curriculum_map_v0_2_sqlite_csv"
    return base

@app.post("/evidence/search")
def search_evidence_v159(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    require_key(x_api_key)

    requested = [str(s).lower() for s in (req.sources or ["textbooks"])]
    alias_to_source = {
        "curriculum": "curriculum",
        "curriculum_map": "curriculum",
        "lecture": "lectures",
        "lectures": "lectures",
        "video": "lectures",
        "videos": "lectures",
        "textbook": "textbooks",
        "textbooks": "textbooks",
        "journal": "journals",
        "journals": "journals",
        "who": "who",
        "pathout": "pathout",
        "pathology_outlines": "pathout",
    }
    normalized = [alias_to_source.get(s, s) for s in requested]
    allowed = {"who", "journals", "pathout", "textbooks", "lectures", "curriculum"}
    bad = [s for s in normalized if s not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unsupported source(s): {bad}")

    old_sources = [s for s in normalized if s != "curriculum"]
    wants_curriculum = "curriculum" in normalized

    if old_sources and _OLD_SEARCH_ENDPOINT_V159:
        old_req = _clone_request_sources_v048(req, old_sources)
        try:
            resp = _OLD_SEARCH_ENDPOINT_V159(old_req, request, x_api_key)
        except TypeError:
            resp = _OLD_SEARCH_ENDPOINT_V159(req=old_req, request=request, x_api_key=x_api_key)
    else:
        resp = {
            "schema_version": "evidence_search_response.v1.5.9",
            "query": req.query,
            "source_status": {
                "who": "not_requested",
                "journals": "not_requested",
                "pathout": "not_requested",
                "textbooks": "not_requested",
                "lectures": "not_requested",
                "videos": "not_requested",
                "curriculum": "not_requested",
            },
            "who_results": [],
            "journal_results": [],
            "pathout_results": [],
            "textbook_results": [],
            "lecture_results": [],
            "video_results": [],
            "curriculum_results": [],
            "figures": [],
            "warnings": [],
            "search_mode": {},
        }

    if not isinstance(resp, dict):
        resp = {"raw_response": resp, "warnings": ["old_endpoint_returned_non_dict"]}

    resp["schema_version"] = "evidence_search_response.v1.5.9"
    resp.setdefault("source_status", {})
    resp.setdefault("warnings", [])
    resp.setdefault("search_mode", {})
    resp.setdefault("curriculum_results", [])
    resp.setdefault("curriculum_status", None)
    resp["source_status"].setdefault("curriculum", "not_requested")

    if wants_curriculum:
        try:
            if "max_results" in getattr(req, "model_fields_set", set()):
                curriculum_max = req.max_results
            else:
                curriculum_max = 3
            curriculum_results, curriculum_warnings = curriculum_search_v159(
                req.query,
                curriculum_max,
                compact=bool(req.compact),
            )
            resp["curriculum_results"] = curriculum_results
            resp["curriculum_status"] = curriculum_status_v159()
            resp["source_status"]["curriculum"] = "ok"
            resp["warnings"].extend(curriculum_warnings)
            resp["search_mode"]["curriculum"] = "local_curriculum_map_v0_2_sqlite_csv"
        except Exception as e:
            resp["source_status"]["curriculum"] = "error"
            resp["curriculum_status"] = {
                "version": CURRICULUM_VERSION,
                "enabled": False,
                "error": repr(e),
                "gcs_paths_used": {
                    "sqlite": CURRICULUM_SQLITE_GCS,
                    "nodes": CURRICULUM_NODES_GCS,
                    "review_queue": CURRICULUM_REVIEW_QUEUE_GCS,
                    "rejected_tags": CURRICULUM_REJECTED_TAGS_GCS,
                    "acceptance_summary": CURRICULUM_ACCEPTANCE_GCS,
                },
            }
            resp["warnings"].append(f"curriculum_search_error: {repr(e)}")

    if not req.include_figures:
        resp["figures"] = []
    else:
        resp["figures"] = (resp.get("figures") or [])[:req.max_figures]

    return resp


# ============================================================
# v1.5.10 HTML BUNDLE PATCH
# Adds optional static HTML bundle rendering to existing
# searchEvidence only. No new GPT Action.
# ============================================================

APP_VERSION_V1510 = "1.5.10-html-bundle"
HTML_BUNDLE_VERSION = "v1.5.10"
HTML_BUNDLE_GCS_PREFIX = os.environ.get(
    "HTML_BUNDLE_GCS_PREFIX",
    "gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/",
)

HTML_PROFILES_V1510 = {"teaching_page", "gallery", "evidence_packet"}
HTML_RESULT_GROUPS_V1510 = [
    ("curriculum_results", "Curriculum map"),
    ("who_results", "WHO"),
    ("textbook_results", "Textbooks"),
    ("pathout_results", "Pathology Outlines"),
    ("journal_results", "Journals"),
    ("lecture_results", "Lectures"),
    ("video_results", "Videos"),
]

def _utc_now_v1510():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _html_escape_v1510(value):
    return html.escape(str(value or ""), quote=True)

def _first_text_v1510(obj: dict, keys: list):
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def _clean_html_profile_v1510(profile: str):
    p = str(profile or "teaching_page").strip().lower()
    return p if p in HTML_PROFILES_V1510 else "teaching_page"

def _sanitize_filename_v1510(title: str):
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(title or "searchEvidence_html")).strip("._-")
    return (base or "searchEvidence_html")[:80]

def _clone_html_request_v1510(req: EvidenceSearchRequest, query: str = None, max_figures: int = 10):
    data = req.dict()
    data["query"] = query or req.query
    data["render_html"] = False
    data["compact"] = True
    data["include_figures"] = True
    data["max_figures"] = max(0, min(10, int(max_figures or 0)))
    data["max_results"] = max(1, min(10, int(req.max_results or 3)))
    data["excerpt_char_limit"] = min(1200, max(200, int(req.excerpt_char_limit or 900)))
    return EvidenceSearchRequest(**data)

def _safe_url_v1510(value):
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.startswith("http://") or v.startswith("https://"):
        return v
    return None

def _figure_key_v1510(fig: dict):
    if not isinstance(fig, dict):
        return None
    for key in ["image_url", "figure_url", "page_image_url", "source_page_url"]:
        url = _safe_url_v1510(fig.get(key))
        if url:
            return key + ":" + url
    caption = str(fig.get("caption") or fig.get("title") or "").strip().lower()
    source = str(fig.get("source_id") or fig.get("source") or fig.get("source_name") or "").strip().lower()
    if caption or source:
        return "caption_source:" + hashlib.sha256((caption + "|" + source).encode("utf-8")).hexdigest()
    return None

def _collect_figures_v1510(resp: dict, seen: set, out: list, limit: int):
    candidates = []
    if isinstance(resp.get("figures"), list):
        candidates.extend(resp.get("figures") or [])
    for group, _label in HTML_RESULT_GROUPS_V1510:
        for hit in resp.get(group) or []:
            if not isinstance(hit, dict):
                continue
            for key in ["page_image_url", "figure_url", "image_url", "source_page_url"]:
                url = _safe_url_v1510(hit.get(key))
                if url:
                    candidates.append({
                        "title": hit.get("title") or hit.get("source_name") or hit.get("source_id"),
                        "caption": hit.get("caption") or hit.get("excerpt") or hit.get("section"),
                        key: url,
                        "source": hit.get("source") or hit.get("source_name"),
                        "source_id": hit.get("source_id"),
                        "page": hit.get("page"),
                    })
    for fig in candidates:
        if len(out) >= limit:
            break
        if not isinstance(fig, dict):
            continue
        key = _figure_key_v1510(fig)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(fig)
    return out

def _count_evidence_v1510(resp: dict):
    total = 0
    for group, _label in HTML_RESULT_GROUPS_V1510:
        total += len(resp.get(group) or [])
    return total

def _source_status_ok_v1510(resp: dict, source: str):
    ss = resp.get("source_status") or {}
    if source == "lectures":
        return ss.get("lectures") == "ok" or ss.get("videos") == "ok"
    return ss.get(source) == "ok"

def _curriculum_gate_ok_v1510(resp: dict):
    ss = resp.get("source_status") or {}
    cs = resp.get("curriculum_status") or {}
    if ss.get("curriculum") in (None, "not_requested"):
        return True
    return ss.get("curriculum") == "ok" and cs.get("forbidden_visible_tag_count") == 0

def _filter_forbidden_curriculum_v1510(resp: dict):
    clean = []
    removed = 0
    for row in resp.get("curriculum_results") or []:
        tag = str((row or {}).get("tag") or "")
        if _contains_forbidden_curriculum_tag_v159(tag):
            removed += 1
            continue
        clean.append(row)
    if "curriculum_results" in resp:
        resp["curriculum_results"] = clean
    if removed:
        resp.setdefault("warnings", []).append(f"html_removed_forbidden_curriculum_tags:{removed}")
    return resp

def _render_link_v1510(label: str, url: str):
    safe = _safe_url_v1510(url)
    if not safe:
        return ""
    return f'<a href="{_html_escape_v1510(safe)}" target="_blank" rel="noopener">{_html_escape_v1510(label)}</a>'

def _render_hit_card_v1510(hit: dict, query: str):
    title = _first_text_v1510(hit, ["title", "source_name", "source_id", "tag", "root"]) or "Untitled"
    excerpt = _first_text_v1510(hit, ["excerpt", "text", "section", "caption"]) or ""
    source = _first_text_v1510(hit, ["source", "source_name", "source_type"]) or ""
    tag = _first_text_v1510(hit, ["primary_tag", "tag"]) or ""
    links = []
    for key, label in [
        ("source_url", "Source"),
        ("url", "URL"),
        ("source_page_url", "Page"),
        ("page_image_url", "Page image"),
        ("figure_url", "Figure"),
        ("image_url", "Image"),
        ("video_time_url", "Timestamp"),
        ("video_url", "Video"),
    ]:
        link = _render_link_v1510(label, hit.get(key))
        if link and link not in links:
            links.append(link)
    return f"""
    <article class="card">
      <h3>{_html_escape_v1510(title)}</h3>
      <div class="meta">{_html_escape_v1510(source)}{(' · ' + _html_escape_v1510(tag)) if tag else ''}</div>
      <p>{_html_escape_v1510(excerpt[:1200])}</p>
      <div class="links">{' '.join(links)}</div>
    </article>
    """

def _render_figure_v1510(fig: dict):
    url = _safe_url_v1510(fig.get("image_url") or fig.get("figure_url") or fig.get("page_image_url") or fig.get("source_page_url"))
    if not url:
        return ""
    title = _first_text_v1510(fig, ["title", "source_title", "source_id"]) or "Figure"
    caption = _first_text_v1510(fig, ["caption", "legend", "text"]) or ""
    return f"""
    <figure class="figure-card">
      <a href="{_html_escape_v1510(url)}" target="_blank" rel="noopener">
        <img src="{_html_escape_v1510(url)}" alt="{_html_escape_v1510(title)}" loading="lazy">
      </a>
      <figcaption><strong>{_html_escape_v1510(title)}</strong>{(': ' + _html_escape_v1510(caption[:500])) if caption else ''}</figcaption>
    </figure>
    """

def _build_html_v1510(query: str, title: str, profile: str, responses: list, figures: list, include_toc: bool, include_sections: bool, warnings: list):
    generated = _utc_now_v1510()
    safe_title = title or f"Pathology Hub: {query}"
    evidence_total = sum(_count_evidence_v1510(r) for r in responses)
    toc = ""
    if include_toc:
        toc = """
        <nav class="toc">
          <a href="#summary">Summary</a>
          <a href="#figures">Figures</a>
          <a href="#evidence">Evidence</a>
          <a href="#warnings">Warnings</a>
        </nav>
        """
    fig_html = "\n".join(_render_figure_v1510(f) for f in figures)
    if not fig_html:
        fig_html = '<p class="muted">No figure or page image URLs were returned by the evidence sources.</p>'
    sections = []
    if include_sections:
        for group, label in HTML_RESULT_GROUPS_V1510:
            hits = []
            for resp in responses:
                hits.extend(resp.get(group) or [])
            if not hits:
                continue
            cards = "\n".join(_render_hit_card_v1510(h, query) for h in hits[:20])
            sections.append(f'<section><h2>{_html_escape_v1510(label)}</h2>{cards}</section>')
    evidence_html = "\n".join(sections) or '<p class="muted">No source sections were returned.</p>'
    warning_html = "".join(f"<li>{_html_escape_v1510(w)}</li>" for w in warnings) or "<li>No warnings.</li>"
    profile_note = {
        "gallery": "Gallery bundle focused on returned figure, page image, and source page URLs.",
        "evidence_packet": "Compact evidence packet with source-separated evidence cards.",
        "teaching_page": "Teaching page with source-separated sections and returned media links.",
    }.get(profile, "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html_escape_v1510(safe_title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; color: #1f2933; background: #f7f7f4; line-height: 1.5; }}
    header {{ background: #12343b; color: white; padding: 28px 32px; }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin-top: 32px; border-bottom: 2px solid #d6d3c8; padding-bottom: 6px; }}
    h3 {{ margin: 0 0 6px; font-size: 18px; }}
    .toc {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0 0; }}
    .toc a, .links a {{ color: #0f766e; font-weight: 700; margin-right: 12px; }}
    .summary, .card, .figure-card {{ background: white; border: 1px solid #ddd8c8; border-radius: 8px; padding: 16px; margin: 12px 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }}
    .figure-card img {{ width: 100%; max-height: 360px; object-fit: contain; background: #eceae2; border-radius: 6px; }}
    .meta, .muted {{ color: #65727c; font-size: 13px; }}
    figcaption {{ font-size: 13px; margin-top: 8px; }}
    ul {{ padding-left: 22px; }}
  </style>
</head>
<body>
  <header>
    <h1>{_html_escape_v1510(safe_title)}</h1>
    <div>Generated {generated} · Profile: {_html_escape_v1510(profile)} · Query: {_html_escape_v1510(query)}</div>
    {toc}
  </header>
  <main>
    <section id="summary" class="summary">
      <h2>Summary</h2>
      <p>{_html_escape_v1510(profile_note)}</p>
      <p><strong>Evidence cards:</strong> {evidence_total} · <strong>Figures/media links:</strong> {len(figures)}</p>
      <p class="muted">This bundle contains only URLs, excerpts, and metadata returned by Pathology Hub sources. It does not invent citations, page numbers, timestamps, or image URLs.</p>
    </section>
    <section id="figures">
      <h2>Figures and Media</h2>
      <div class="grid">{fig_html}</div>
    </section>
    <section id="evidence">
      <h2>Evidence</h2>
      {evidence_html}
    </section>
    <section id="warnings">
      <h2>Warnings</h2>
      <ul>{warning_html}</ul>
    </section>
  </main>
</body>
</html>
"""

def _upload_html_v1510(html_text: str, title: str, audit_metadata: Optional[dict] = None):
    bucket_name, prefix = _parse_gs_uri(HTML_BUNDLE_GCS_PREFIX.rstrip("/") + "/placeholder")
    prefix = prefix.rsplit("/", 1)[0].rstrip("/")
    generated = _utc_now_v1510().replace(":", "").replace("-", "")
    digest = hashlib.sha256(html_text.encode("utf-8")).hexdigest()[:12]
    filename = f"{generated}_{_sanitize_filename_v1510(title)}_{digest}.html"
    blob_name = f"{prefix}/{filename}" if prefix else filename
    audit_blob_name = f"{blob_name}.audit.json"
    html_gcs_uri = f"gs://{bucket_name}/{blob_name}"
    audit_gcs_uri = f"gs://{bucket_name}/{audit_blob_name}"
    audit = {
        "schema_version": "pathology_hub.html_bundle_generation_audit.v1.5.10",
        "created_at_utc": _utc_now_v1510(),
        "input_paths": {
            "search_endpoint": "/evidence/search",
            "html_bundle_gcs_prefix": HTML_BUNDLE_GCS_PREFIX,
        },
        "output_paths": {
            "html": html_gcs_uri,
            "audit": audit_gcs_uri,
        },
        "counts": {},
        "known_limitations": [
            "HTML bundle contains only URLs, excerpts, and metadata returned by Pathology Hub sources.",
            "Image pixels are not interpreted during bundle generation.",
            "No citations, image URLs, page numbers, timestamps, or captions are invented.",
        ],
    }
    if isinstance(audit_metadata, dict):
        audit.update({k: v for k, v in audit_metadata.items() if k not in {"schema_version", "output_paths"}})
        audit.setdefault("counts", audit_metadata.get("counts", {}))
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    audit_blob = bucket.blob(audit_blob_name)
    audit_blob.upload_from_string(
        json.dumps(audit, indent=2, sort_keys=True),
        content_type="application/json; charset=utf-8",
    )
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html_text, content_type="text/html; charset=utf-8")
    return html_gcs_uri, f"https://storage.googleapis.com/{bucket_name}/{urllib.parse.quote(blob_name)}", audit_gcs_uri

def _html_query_variants_v1510(query: str):
    q = str(query or "").strip()
    variants = [q]
    for suffix in ["histology", "gross", "microscopy", "diagnosis", "figure", "image", "pathology"]:
        v = f"{q} {suffix}".strip()
        if v.lower() not in {x.lower() for x in variants}:
            variants.append(v)
    return variants

def _build_html_bundle_response_v1510(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str]):
    profile = _clean_html_profile_v1510(req.html_profile)
    title = req.html_title or f"{req.query} {profile.replace('_', ' ')}"
    target_figs = max(1, min(50, int(req.target_figure_count or 10)))
    warnings = []
    responses = []
    figures = []
    seen_figures = set()

    if not _OLD_SEARCH_ENDPOINT_V1510:
        raise HTTPException(status_code=500, detail="Previous searchEvidence endpoint not found for v1.5.10 wrapper.")

    variants = _html_query_variants_v1510(req.query) if profile == "gallery" else [req.query]
    for variant in variants:
        if profile != "gallery" and responses:
            break
        if profile == "gallery" and len(figures) >= target_figs:
            break
        internal_req = _clone_html_request_v1510(req, query=variant, max_figures=min(10, target_figs))
        try:
            resp = _OLD_SEARCH_ENDPOINT_V1510(internal_req, request, x_api_key)
        except TypeError:
            resp = _OLD_SEARCH_ENDPOINT_V1510(req=internal_req, request=request, x_api_key=x_api_key)
        if not isinstance(resp, dict):
            warnings.append("html_internal_search_returned_non_dict")
            continue
        resp = _filter_forbidden_curriculum_v1510(resp)
        if not _curriculum_gate_ok_v1510(resp):
            warnings.append("curriculum_visibility_gate_failed_for_html")
            resp["curriculum_results"] = []
        responses.append(resp)
        _collect_figures_v1510(resp, seen_figures, figures, target_figs)

    if profile == "gallery" and len(figures) < target_figs:
        warnings.append(f"requested_{target_figs}_figures_but_only_{len(figures)}_unique_returned")

    for resp in responses:
        warnings.extend(resp.get("warnings") or [])
    warnings = list(dict.fromkeys(str(w) for w in warnings if w))

    html_text = _build_html_v1510(
        query=req.query,
        title=title,
        profile=profile,
        responses=responses,
        figures=figures,
        include_toc=bool(req.html_include_toc),
        include_sections=bool(req.html_include_source_sections),
        warnings=warnings,
    )
    evidence_count = sum(_count_evidence_v1510(r) for r in responses)
    sources_used = sorted({
        source
        for resp in responses
        for source, status in (resp.get("source_status") or {}).items()
        if status == "ok"
    })
    status = "ok"
    if profile == "gallery" and len(figures) < target_figs:
        status = "partial"
    generated_at_utc = _utc_now_v1510()
    audit_metadata = {
        "workstream": "Backend API / HTML rendering / Custom GPT frontend",
        "build_status": "generated_by_searchEvidence_html_bundle",
        "request": {
            "query": req.query,
            "sources": req.sources,
            "max_results": req.max_results,
            "compact": req.compact,
            "include_figures": req.include_figures,
            "max_figures": req.max_figures,
            "render_html": req.render_html,
            "html_profile": profile,
            "html_title": title,
            "target_figure_count": target_figs,
        },
        "counts": {
            "figure_count": len(figures),
            "evidence_count": evidence_count,
            "internal_response_count": len(responses),
            "warning_count": len(warnings),
        },
        "sources_used": sources_used,
        "known_limitations": [
            "Static HTML artifact only; not a live API integration.",
            "HTML content is derived from compact internal search results.",
            "Source availability depends on the configured backend indexes and upstream services.",
            "OpenAI embedding quota failures fall back where local keyword indexes are available.",
        ],
    }
    html_gcs_uri, html_url, audit_gcs_uri = _upload_html_v1510(html_text, title, audit_metadata)

    result = {
        "schema_version": "evidence_search_response.v1.5.10",
        "query": req.query,
        "source_status": responses[0].get("source_status", {}) if responses else {},
        "warnings": warnings,
        "html_result": {
            "status": status,
            "profile": profile,
            "title": title,
            "html_url": html_url,
            "html_gcs_uri": html_gcs_uri,
            "figure_count": len(figures),
            "evidence_count": evidence_count,
            "sources_used": sources_used,
            "warnings": warnings,
            "generated_at_utc": generated_at_utc,
            "audit_gcs_uri": audit_gcs_uri,
        },
    }
    if responses and responses[0].get("curriculum_status"):
        result["curriculum_status"] = responses[0].get("curriculum_status")
    return result

_OLD_HEALTH_ENDPOINT_V1510 = None
_OLD_SEARCH_ENDPOINT_V1510 = None
for _r in list(app.router.routes):
    if getattr(_r, "path", None) == "/health" and "GET" in getattr(_r, "methods", set()):
        _OLD_HEALTH_ENDPOINT_V1510 = getattr(_r, "endpoint", None)
    if getattr(_r, "path", None) == "/evidence/search" and "POST" in getattr(_r, "methods", set()):
        _OLD_SEARCH_ENDPOINT_V1510 = getattr(_r, "endpoint", None)

app.router.routes = [
    r for r in app.router.routes
    if not (
        (getattr(r, "path", None) == "/evidence/search" and "POST" in getattr(r, "methods", set()))
        or (getattr(r, "path", None) == "/health" and "GET" in getattr(r, "methods", set()))
    )
]

@app.get("/health")
def health_v1510():
    base = {}
    if _OLD_HEALTH_ENDPOINT_V1510:
        try:
            base = _OLD_HEALTH_ENDPOINT_V1510()
        except Exception as e:
            base = {"old_health_error": repr(e)}
    if not isinstance(base, dict):
        base = {"old_health": str(base)}
    base["schema_version"] = "pathology_hub_health.v1.5.10"
    base["version"] = APP_VERSION_V1510
    base["html_bundle_enabled"] = True
    base["html_bundle_version"] = HTML_BUNDLE_VERSION
    base["html_bundle_gcs_prefix"] = HTML_BUNDLE_GCS_PREFIX
    return base

@app.post("/evidence/search")
def search_evidence_v1510(req: EvidenceSearchRequest, request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    require_key(x_api_key)
    if not bool(req.render_html):
        if not _OLD_SEARCH_ENDPOINT_V1510:
            raise HTTPException(status_code=500, detail="Previous searchEvidence endpoint not found for v1.5.10 wrapper.")
        try:
            return _OLD_SEARCH_ENDPOINT_V1510(req, request, x_api_key)
        except TypeError:
            return _OLD_SEARCH_ENDPOINT_V1510(req=req, request=request, x_api_key=x_api_key)

    return _build_html_bundle_response_v1510(req, request, x_api_key)
