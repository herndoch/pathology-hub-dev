"""Helper functions for a backend to query the v11 approved-only curriculum tag index."""
import sqlite3
from typing import Iterable, Optional

JUNK_SUBSTRINGS = ["::Lectures::", "::Textbooks::", "Digital_Pathology_Slide", "Pathology_Slide"]

def is_visible_tag(tag: str) -> bool:
    if not tag or tag == "__UNMAPPED__":
        return False
    return not any(s.lower() in tag.lower() for s in JUNK_SUBSTRINGS)

def tag_exact(db_path: str, tags: Iterable[str], sources: Optional[Iterable[str]] = None, limit: int = 20):
    tags = [t for t in tags if is_visible_tag(t)]
    if not tags:
        return []
    params = list(tags)
    where = ["primary_tag IN (%s)" % ",".join("?" for _ in tags)]
    if sources:
        sources = list(sources)
        where.append("source IN (%s)" % ",".join("?" for _ in sources))
        params.extend(sources)
    sql = "SELECT source, record_id, primary_tag, title, url, excerpt, locator_json FROM records WHERE " + " AND ".join(where) + " LIMIT ?"
    params.append(limit)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def tag_prefix(db_path: str, prefixes: Iterable[str], sources: Optional[Iterable[str]] = None, limit: int = 50):
    clauses, params = [], []
    for p in prefixes:
        if p and p != "__UNMAPPED__":
            clauses.append("primary_tag LIKE ?")
            params.append(p.rstrip(':') + '::%')
    if not clauses:
        return []
    where = ["(" + " OR ".join(clauses) + ")"]
    if sources:
        sources = list(sources)
        where.append("source IN (%s)" % ",".join("?" for _ in sources))
        params.extend(sources)
    sql = "SELECT source, record_id, primary_tag, title, url, excerpt, locator_json FROM records WHERE " + " AND ".join(where) + " LIMIT ?"
    params.append(limit)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
