"""Live literature / knowledge APIs for topic pages.

Fetches clean abstracts + DOI links from Elsevier Scopus and NCBI PubMed,
plus optional OncoKB molecular annotations. Replaces the retired local
journal FAISS corpus for topic-page evidence.

Secrets (env first, then GCP Secret Manager names):
  ELSEVIER_API_KEY / Elsevier
  NCBI_API_KEY     / NCBI
  ONCOKB_API_TOKEN / OncoKB

Never logs secret values.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from secrets_helper import get_elsevier_api_key, get_ncbi_api_key, get_oncokb_api_token

# Feature flag — default ON for topic pages.
def live_literature_enabled() -> bool:
    raw = os.environ.get("TOPIC_PAGE_LIVE_LITERATURE", "1")
    return str(raw).strip().lower() not in {"0", "false", "off", "no"}


# Common pathology genes / fusions worth probing OncoKB when mentioned.
_ONCOKB_GENE_RE = re.compile(
    r"\b("
    r"BRAF|NRAS|KRAS|HRAS|EGFR|ALK|ROS1|RET|MET|ERBB2|HER2|KIT|PDGFRA|"
    r"NTRK1|NTRK2|NTRK3|ETV6|MYB|MYBL1|NFIB|PLAG1|HMGA2|EWSR1|FLI1|"
    r"SS18|SSX1|SSX2|BCOR|CIC|YAP1|TFE3|TFEB|PRCC|ASPSCR1|"
    r"IDH1|IDH2|TP53|RB1|CDKN2A|PTEN|PIK3CA|AKT1|CTNNB1|APC|"
    r"BRCA1|BRCA2|PALB2|ATM|CHEK2|MLH1|MSH2|MSH6|PMS2|"
    r"BCL2|BCL6|MYC|CCND1|IGH|JAK2|CALR|MPL|NPM1|FLT3|IDH|"
    r"VHL|BAP1|PBRM1|SETD2|FH|SDHB|SDHA|SDHC|SDHD|"
    r"KIT|PDGFRA|BRAF"
    r")\b",
    re.I,
)

_USER_AGENT = "PathologyHubChatMVP/0.1 (literature; research; non-commercial)"


def _http_get_json(url: str, headers: dict[str, str], timeout: float = 25.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_bytes(url: str, headers: dict[str, str], timeout: float = 25.0) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _doi_url(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = str(doi).strip()
    if not doi:
        return None
    if doi.startswith("http"):
        return doi
    return f"https://doi.org/{doi}"


def _card(
    *,
    title: str,
    journal: str,
    doi: Optional[str],
    abstract: str,
    year: Optional[str],
    retrieval_mode: str,
    source_name: str,
    extra: Optional[dict] = None,
) -> dict[str, Any]:
    url = _doi_url(doi)
    card: dict[str, Any] = {
        "source": "literature",
        "source_name": source_name or journal or "Literature",
        "journal": journal or None,
        "title": title,
        "doi": doi,
        "source_url": url,
        "url": url,
        "excerpt": (abstract or "")[:1200],
        "text": abstract or "",
        "year": year,
        "retrieval_mode": retrieval_mode,
        "rank": None,
    }
    if extra:
        card.update(extra)
    return card


def _sanitize_scopus_query_text(query: str) -> str:
    """Strip characters that break Scopus TITLE-ABS-KEY(...) syntax.

    Entity labels from Browse often look like ``Lobular carcinoma in situ (LCIS)``.
    Nested parentheses inside ``TITLE-ABS-KEY(...)`` make Elsevier return HTTP 400,
    which showed up live as "elsevier failed" with zero Scopus cards. Also strip
    braces/brackets/quotes and collapse whitespace.
    """
    text = str(query or "")
    text = re.sub(r"[(){}\[\]\"'\\]", " ", text)
    # Boolean operators as free tokens can also break bare TITLE-ABS-KEY queries.
    text = re.sub(r"\b(?:AND|OR|NOT|W\/\d+|PRE\/\d+)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def search_scopus(query: str, max_results: int = 5) -> tuple[list[dict], dict]:
    """Elsevier Scopus search — titles, journals, DOIs; abstracts via Abstract API when possible."""
    api_key = get_elsevier_api_key()
    meta: dict[str, Any] = {"provider": "elsevier_scopus", "ok": False}
    if not api_key:
        meta["error"] = "missing_api_key"
        return [], meta

    clean = _sanitize_scopus_query_text(query)
    if not clean:
        meta["error"] = "empty_query_after_sanitize"
        return [], meta
    meta["query_sanitized"] = clean

    # Prefer pathology journals in ranking via query terms; keep query short.
    # No explicit `sort` param: Scopus defaults to relevancy ranking. An
    # earlier version forced `sort=-coverDate`, which meant every query
    # returned only the *most recently published* matches regardless of how
    # well they matched — in practice a stream of very recent case reports
    # (Elsevier indexes those fast) crowding out any older, more substantive,
    # more-cited literature. Relevancy ranking surfaces the latter instead.
    q = f'TITLE-ABS-KEY({clean}) AND PUBYEAR > 2005'
    params = urllib.parse.urlencode(
        {
            "query": q,
            "count": max(1, min(max_results, 8)),
            "field": "dc:title,prism:doi,prism:publicationName,prism:coverDate,description,subtypeDescription",
        }
    )
    url = f"https://api.elsevier.com/content/search/scopus?{params}"
    headers = {
        "Accept": "application/json",
        "X-ELS-APIKey": api_key,
        "User-Agent": _USER_AGENT,
    }
    try:
        data = _http_get_json(url, headers)
    except urllib.error.HTTPError as exc:
        meta["error"] = f"http_{exc.code}"
        # Include a short body snippet for diagnostics (never includes API key).
        try:
            body = exc.read().decode("utf-8", errors="replace")[:240]
            if body:
                meta["error_body"] = body
        except Exception:
            pass
        return [], meta
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}"
        return [], meta

    sr = data.get("search-results") or {}
    meta["ok"] = True
    meta["total"] = sr.get("opensearch:totalResults")
    entries = [e for e in (sr.get("entry") or []) if e.get("dc:title")]
    cards: list[dict] = []
    for e in entries[:max_results]:
        doi = e.get("prism:doi")
        abstract = (e.get("description") or "").strip()
        # Enrich with Abstract Retrieval when search omitted abstract.
        if doi and not abstract:
            abstract = _scopus_abstract_by_doi(doi, api_key) or ""
        date = e.get("prism:coverDate") or ""
        year = date[:4] if date else None
        cards.append(
            _card(
                title=e.get("dc:title") or "",
                journal=e.get("prism:publicationName") or "",
                doi=doi,
                abstract=abstract,
                year=year,
                retrieval_mode="elsevier_scopus",
                source_name="Elsevier Scopus",
                extra={"subtype": e.get("subtypeDescription")},
            )
        )
    meta["returned"] = len(cards)
    return cards, meta


def _scopus_abstract_by_doi(doi: str, api_key: str) -> Optional[str]:
    url = f"https://api.elsevier.com/content/abstract/doi/{urllib.parse.quote(doi, safe='')}"
    headers = {
        "Accept": "application/json",
        "X-ELS-APIKey": api_key,
        "User-Agent": _USER_AGENT,
    }
    try:
        data = _http_get_json(url, headers, timeout=20.0)
    except Exception:
        return None
    absrec = data.get("abstracts-retrieval-response") or {}
    core = absrec.get("coredata") or {}
    if core.get("dc:description"):
        return str(core["dc:description"]).strip()
    absnode = (absrec.get("abstracts") or {}).get("abstract")
    if isinstance(absnode, dict):
        paras = absnode.get("para")
        if isinstance(paras, str):
            return paras.strip()
        if isinstance(paras, list):
            return " ".join(str(x) for x in paras).strip()
    return None


def search_pubmed(query: str, max_results: int = 5) -> tuple[list[dict], dict]:
    """NCBI PubMed esearch + efetch — titles, journals, abstracts, PMIDs."""
    api_key = get_ncbi_api_key()
    meta: dict[str, Any] = {"provider": "pubmed_ncbi", "ok": False}
    key_q = f"&api_key={urllib.parse.quote(api_key)}" if api_key else ""
    term = urllib.parse.quote(f"{query}[Title/Abstract]")
    # Explicit relevance sort — esearch's default sort for db=pubmed is not
    # documented as relevance and has been observed to skew toward most-recent
    # (same failure mode as the old Scopus `-coverDate` sort; see comment
    # there). Explicit `sort=relevance` avoids relying on an undocumented default.
    search_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&retmode=json&retmax={max(1, min(max_results, 8))}&sort=relevance&term={term}{key_q}"
    )
    headers = {"User-Agent": _USER_AGENT}
    try:
        data = _http_get_json(search_url, headers)
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}"
        return [], meta

    ids = (data.get("esearchresult") or {}).get("idlist") or []
    meta["total"] = (data.get("esearchresult") or {}).get("count")
    if not ids:
        meta["ok"] = True
        meta["returned"] = 0
        return [], meta

    fetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&retmode=xml&id={','.join(ids)}{key_q}"
    )
    try:
        xml_bytes = _http_get_bytes(fetch_url, headers)
        root = ET.fromstring(xml_bytes)
    except Exception as exc:
        meta["error"] = f"efetch_{type(exc).__name__}"
        return [], meta

    cards: list[dict] = []
    for art in root.findall(".//PubmedArticle"):
        title = "".join(art.findtext(".//ArticleTitle") or "")
        journal = art.findtext(".//Journal/Title") or art.findtext(".//MedlineJournalInfo/MedlineTA") or ""
        year = art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(".//PubDate/Year")
        pmid = art.findtext(".//PMID")
        abstract_parts = []
        for el in art.findall(".//Abstract/AbstractText"):
            label = el.attrib.get("Label")
            text = "".join(el.itertext()) if el is not None else ""
            if label and text:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts).strip()
        doi = None
        for aid in art.findall(".//ArticleId"):
            if aid.attrib.get("IdType") == "doi" and aid.text:
                doi = aid.text.strip()
                break
        url = _doi_url(doi) or (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None)
        cards.append(
            _card(
                title=title,
                journal=journal,
                doi=doi,
                abstract=abstract,
                year=year,
                retrieval_mode="pubmed_ncbi",
                source_name="PubMed",
                extra={"pmid": pmid, "source_url": url, "url": url},
            )
        )
    meta["ok"] = True
    meta["returned"] = len(cards)
    return cards[:max_results], meta


def _extract_genes(text: str) -> list[str]:
    found = []
    seen = set()
    for m in _ONCOKB_GENE_RE.finditer(text or ""):
        g = m.group(1).upper()
        if g == "HER2":
            g = "ERBB2"
        if g not in seen:
            seen.add(g)
            found.append(g)
    return found[:4]


# Public alias for iterative retrieval / callers outside this module.
extract_genes = _extract_genes


def annotate_oncokb(query: str, tumor_type: Optional[str] = None) -> tuple[list[dict], dict]:
    """OncoKB protein-change / fusion hints for genes mentioned in the query."""
    token = get_oncokb_api_token()
    meta: dict[str, Any] = {"provider": "oncokb", "ok": False}
    if not token:
        meta["error"] = "missing_api_key"
        return [], meta

    genes = _extract_genes(query)
    if not genes:
        meta["ok"] = True
        meta["skipped"] = "no_gene_tokens"
        return [], meta

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": _USER_AGENT,
    }
    cards: list[dict] = []
    # Probe gene-level + common Fusion alteration when fusion-prone genes appear.
    fusion_prone = {"ETV6", "NTRK1", "NTRK2", "NTRK3", "ALK", "ROS1", "RET", "EWSR1", "SS18", "MYB"}
    for gene in genes:
        alterations = ["Fusion"] if gene in fusion_prone else [""]
        if gene == "BRAF":
            alterations = ["V600E"]
        for alt in alterations:
            params: dict[str, str] = {"hugoSymbol": gene}
            if alt:
                params["alteration"] = alt
            if tumor_type:
                params["tumorType"] = tumor_type
            qs = urllib.parse.urlencode(params)
            url = f"https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange?{qs}"
            try:
                data = _http_get_json(url, headers, timeout=20.0)
            except Exception as exc:
                meta.setdefault("errors", []).append(f"{gene}:{type(exc).__name__}")
                continue
            oncogenic = data.get("oncogenic")
            effect = data.get("mutationEffect")
            if isinstance(effect, dict):
                effect = effect.get("knownEffect")
            treatments = data.get("treatments") or []
            drug_lines = []
            for t in treatments[:4]:
                drugs = ", ".join(d.get("drugName") or "" for d in (t.get("drugs") or []) if d.get("drugName"))
                level = t.get("level") or ""
                if drugs:
                    drug_lines.append(f"{level}: {drugs}".strip(": "))
            summary_bits = [
                f"Gene: {gene}" + (f" / {alt}" if alt else ""),
                f"Oncogenic: {oncogenic}" if oncogenic else None,
                f"Effect: {effect}" if effect else None,
            ]
            if drug_lines:
                summary_bits.append("Treatments: " + "; ".join(drug_lines))
            abstract = "\n".join(b for b in summary_bits if b)
            if not oncogenic and not treatments:
                continue
            cards.append(
                _card(
                    title=f"OncoKB: {gene}" + (f" {alt}" if alt else ""),
                    journal="OncoKB",
                    doi=None,
                    abstract=abstract,
                    year=None,
                    retrieval_mode="oncokb",
                    source_name="OncoKB",
                    extra={
                        "source_url": f"https://www.oncokb.org/gene/{gene}",
                        "url": f"https://www.oncokb.org/gene/{gene}",
                        "gene": gene,
                        "alteration": alt or None,
                        "oncogenic": oncogenic,
                    },
                )
            )
    meta["ok"] = True
    meta["genes"] = genes
    meta["returned"] = len(cards)
    return cards, meta


# Organ scoping for literature queries — reduces classic off-target hits
# (e.g. prostate "intraductal carcinoma" for breast LCIS).
_ORGAN_POSITIVE: dict[str, tuple[str, ...]] = {
    "breast": ("breast", "mammary", "ductal", "lobular", "lcis", "dcis", "mastectomy"),
    "prostate": ("prostate", "prostatic", "pin", "gleason"),
    "salivary": ("salivary", "parotid", "submandibular", "minor salivary"),
    "colon": ("colon", "colorectal", "rectal", "bowel"),
    "cervix": ("cervix", "cervical", "cin", "hsil", "lsil"),
    "thyroid": ("thyroid", "papillary thyroid", "follicular thyroid"),
    "lung": ("lung", "pulmonary", "bronchial"),
    "skin": ("skin", "cutaneous", "melanoma", "dermat"),
}
_ORGAN_BLOCKS: dict[str, tuple[str, ...]] = {
    "breast": ("prostate", "prostatic", "salivary", "parotid", "colon", "cervix", "ovarian", "endometrial"),
    "prostate": ("breast", "salivary", "colon", "cervix", "thyroid"),
    "salivary": ("breast", "prostate", "colon", "cervix"),
    "colon": ("breast", "prostate", "salivary", "cervix", "thyroid"),
    "cervix": ("breast", "prostate", "salivary", "colon"),
    "thyroid": ("breast", "prostate", "salivary", "colon", "cervix"),
    "lung": ("breast", "prostate", "salivary", "colon"),
    "skin": ("breast", "prostate", "salivary", "colon", "cervix"),
}


def infer_organ_hint(query: str, tumor_type: Optional[str] = None) -> Optional[str]:
    blob = f"{query or ''} {tumor_type or ''}".lower()
    # Specific abbreviations first.
    if re.search(r"\b(lcis|dcis)\b", blob) or "lobular carcinoma in situ" in blob:
        return "breast"
    for organ, positives in _ORGAN_POSITIVE.items():
        if any(p in blob for p in positives):
            return organ
    return None


def scope_literature_query(query: str, organ_hint: Optional[str] = None) -> str:
    """Append a light organ scope term when the bare query is organ-ambiguous."""
    q = (query or "").strip()
    if not q or not organ_hint:
        return q
    positives = _ORGAN_POSITIVE.get(organ_hint) or ()
    low = q.lower()
    if any(p in low for p in positives[:3]):  # already scoped
        return q
    # One anchoring organ word — enough for PubMed/Scopus without drowning the entity.
    anchor = {"breast": "breast", "prostate": "prostate", "salivary": "salivary", "colon": "colorectal"}.get(
        organ_hint, organ_hint
    )
    return f"{q} {anchor}"


def _literature_haystack(card: dict) -> str:
    return " ".join(
        str(card.get(k) or "")
        for k in ("title", "excerpt", "text", "journal", "abstract")
    ).lower()


def _query_entity_tokens(query: str) -> list[str]:
    stop = {
        "the",
        "a",
        "an",
        "of",
        "in",
        "for",
        "and",
        "or",
        "with",
        "to",
        "on",
        "at",
        "by",
        "from",
        "features",
        "molecular",
        "genetics",
        "macroscopic",
        "clinicopathologic",
        "review",
    }
    tokens = re.findall(r"[a-z0-9]{3,}", (query or "").lower())
    return [t for t in tokens if t not in stop]


def filter_literature_cards(
    query: str,
    cards: list[dict],
    *,
    organ_hint: Optional[str] = None,
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Drop organ-conflict / weak-match literature before synthesis + UI.

    Returns (kept, dropped, stats).
    """
    organ = organ_hint or infer_organ_hint(query)
    entity_tokens = _query_entity_tokens(query)
    # Prefer distinctive tokens (lcis, lobular, …) over generic ones.
    strong = [t for t in entity_tokens if t not in {"carcinoma", "cancer", "tumor", "tumour", "lesion", "breast"}]
    if not strong:
        strong = entity_tokens[:4]

    kept: list[dict] = []
    dropped: list[dict] = []
    for card in cards or []:
        # OncoKB cards are gene-level — keep when present.
        if (card.get("retrieval_mode") or "") == "oncokb":
            kept.append(card)
            continue
        hay = _literature_haystack(card)
        if not hay.strip():
            dropped.append(card)
            continue
        if organ:
            blocks = _ORGAN_BLOCKS.get(organ) or ()
            positives = _ORGAN_POSITIVE.get(organ) or ()
            has_block = any(b in hay for b in blocks)
            has_pos = any(p in hay for p in positives)
            if has_block and not has_pos:
                dropped.append(card)
                continue
        if strong:
            hits = sum(1 for t in strong if t in hay)
            # Require at least one distinctive entity token in title/abstract.
            if hits < 1:
                dropped.append(card)
                continue
        kept.append(card)

    stats = {
        "organ_hint": organ,
        "input": len(cards or []),
        "kept": len(kept),
        "dropped": len(dropped),
        "entity_tokens": strong[:8],
    }
    return kept, dropped, stats


def fetch_live_literature(
    query: str,
    *,
    max_per_provider: int = 4,
    tumor_type: Optional[str] = None,
    include_oncokb: bool = True,
) -> dict[str, Any]:
    """Parallel fetch from Scopus + PubMed (+ OncoKB). Returns cards + provider meta."""
    if not live_literature_enabled():
        return {
            "enabled": False,
            "cards": [],
            "providers": {},
            "warnings": ["live_literature_disabled"],
        }

    providers: dict[str, Any] = {}
    cards: list[dict] = []
    warnings: list[str] = []

    organ_hint = infer_organ_hint(query, tumor_type)
    scoped_query = scope_literature_query(query, organ_hint)

    jobs = {
        "scopus": lambda: search_scopus(scoped_query, max_per_provider),
        "pubmed": lambda: search_pubmed(scoped_query, max_per_provider),
    }
    if include_oncokb:
        jobs["oncokb"] = lambda: annotate_oncokb(query, tumor_type=tumor_type)

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                part_cards, part_meta = fut.result()
            except Exception as exc:
                providers[name] = {"ok": False, "error": type(exc).__name__}
                warnings.append(f"literature_{name}_error")
                continue
            providers[name] = part_meta
            cards.extend(part_cards)
            if not part_meta.get("ok"):
                warnings.append(f"literature_{name}_{part_meta.get('error', 'failed')}")

    # Prefer cards that have abstracts; de-dupe by DOI / title.
    seen: set[str] = set()
    deduped: list[dict] = []
    for card in sorted(cards, key=lambda c: (0 if (c.get("text") or c.get("excerpt")) else 1, c.get("retrieval_mode") or "")):
        key = (card.get("doi") or "").lower() or (card.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(card)

    kept, dropped, filt_stats = filter_literature_cards(
        query, deduped, organ_hint=organ_hint
    )
    if dropped:
        warnings.append(f"literature_filtered_offtopic_{len(dropped)}")

    return {
        "enabled": True,
        "cards": kept,
        "providers": providers,
        "warnings": warnings,
        "query": query,
        "scoped_query": scoped_query,
        "filter": filt_stats,
        "dropped_offtopic": len(dropped),
    }
