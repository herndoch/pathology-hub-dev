"""
tag_search_backend_patch.py — drop-in helper for searchEvidence tag-aware branch.
This module assumes a SQLite tag index built from primary_tag metadata.
"""
import json, sqlite3, re
from pathlib import Path

VALID_MATCH = {"exact", "prefix", "root", "any"}
VALID_MODES = {"tag_browse", "tag_contents", "tag_then_query"}

def _row_to_dict(cur, row):
    return {desc[0]: row[i] for i, desc in enumerate(cur.description)}

class TagIndex:
    def __init__(self, sqlite_path: str):
        self.sqlite_path = sqlite_path
        self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def status(self):
        cur = self.conn.cursor()
        out = {"tag_index_loaded": True, "tag_index_path": self.sqlite_path}
        for table in ["tag_records", "tag_catalog"]:
            try:
                out[table + "_count"] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception as e:
                out[table + "_error"] = str(e)
        return out

    def _source_clause(self, sources):
        sources = [s for s in (sources or []) if s]
        if not sources:
            return "", []
        q = ",".join(["?"]*len(sources))
        return f" AND source IN ({q})", sources

    def browse_tags(self, tags=None, tag_match="prefix", sources=None, limit=100, offset=0):
        tags = tags or []
        tag_match = tag_match if tag_match in VALID_MATCH else "prefix"
        src_sql, params = self._source_clause(sources)
        where = "1=1" + src_sql
        if tags:
            t = tags[0]
            if tag_match == "exact":
                where += " AND tag = ?"; params.append(t)
            elif tag_match == "root":
                root = t.split("::")[0]
                where += " AND root = ?"; params.append(root)
            else:
                where += " AND tag LIKE ?"; params.append(t.rstrip(':') + "%")
        sql = f"SELECT tag, root, GROUP_CONCAT(source) AS sources, SUM(record_count) AS record_count FROM tag_catalog WHERE {where} GROUP BY tag, root ORDER BY tag LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def contents(self, tags, tag_match="exact", sources=None, query="", limit=10, offset=0):
        tags = tags or []
        tag_match = tag_match if tag_match in VALID_MATCH else "exact"
        src_sql, params = self._source_clause(sources)
        clauses = ["1=1" + src_sql]
        if tags:
            tag_clauses = []
            for t in tags:
                if tag_match == "exact":
                    tag_clauses.append("primary_tag = ?"); params.append(t)
                elif tag_match == "root":
                    tag_clauses.append("root = ?"); params.append(t.split("::")[0])
                else:
                    tag_clauses.append("primary_tag LIKE ?"); params.append(t.rstrip(':') + "%")
            clauses.append("(" + " OR ".join(tag_clauses) + ")")
        if query:
            # Lightweight keyword fallback. Full FTS ranking can be added by joining tag_records_fts.
            for term in [x for x in re.split(r"\s+", query.strip()) if x][:6]:
                clauses.append("(title LIKE ? OR text_excerpt LIKE ? OR primary_tag LIKE ?)")
                like = f"%{term}%"; params.extend([like, like, like])
        sql = "SELECT source, record_id, primary_tag, root, title, url, source_id, page, start_sec, end_sec, text_excerpt, metadata_json FROM tag_records WHERE " + " AND ".join(clauses) + " ORDER BY source, primary_tag LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        cur = self.conn.execute(sql, params)
        out=[]
        for r in cur.fetchall():
            d=dict(r)
            try: d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
            except Exception: d.pop("metadata_json", None)
            out.append(d)
        return out

def handle_tagaware_search(payload, tag_index: TagIndex):
    mode = payload.get("search_mode") or ("tag_contents" if payload.get("tags") else "tag_browse")
    sources = payload.get("sources") or []
    tags = payload.get("tags") or []
    tag_match = payload.get("tag_match") or "exact"
    max_results = int(payload.get("max_results") or 10)
    query = payload.get("query") or ""
    if mode == "tag_browse":
        return {"query": query, "search_mode": mode, "tag_index_status": tag_index.status(), "tag_facets": tag_index.browse_tags(tags, tag_match, sources, payload.get("tag_limit", max_results), payload.get("tag_offset", 0)), "warnings": []}
    if mode in {"tag_contents", "tag_then_query"}:
        return {"query": query, "search_mode": mode, "tag_index_status": tag_index.status(), "tag_results": tag_index.contents(tags, tag_match, sources, query if mode == "tag_then_query" else "", max_results, payload.get("tag_offset", 0)), "warnings": []}
    return {"query": query, "search_mode": mode, "warnings": ["Unsupported tag-aware mode"]}
