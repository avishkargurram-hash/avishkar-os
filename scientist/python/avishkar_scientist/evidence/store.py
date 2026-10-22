"""Evidence store: idempotent writes for sources, documents, hypotheses,
claims, evidence links and provenance edges.

Every writer takes an open transaction (`conn`) so a handler's whole
effect commits atomically, and every insert is ON CONFLICT-safe so a task
re-executed after a crash produces the same rows, not duplicates.
"""

from __future__ import annotations

import re
from typing import Optional

from ..events import emit
from ..models.embed import vec_literal
from ..storage.db import J
from ..tools.literature import lineage_root, quality_of

_NORM = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str) -> str:
    return _NORM.sub(" ", (text or "").lower()).strip()


# -- sources ---------------------------------------------------------------
def upsert_source(conn, objects, mission_id: str, rec: dict, *, query: Optional[str] = None) -> tuple:
    """-> (source_id, is_new). Cross-provider duplicates collapse on lineage_root;
    a later provider may fill in a missing abstract / citation count."""
    root = lineage_root(rec)
    demo = rec.get("provider") == "demo_simulated"
    row = conn.execute(
        """INSERT INTO sources(mission_id, provider, external_id, doi, title, authors, year, venue, url,
                               source_type, is_retracted, citation_count, lineage_root, referenced, quality,
                               demo_simulated, query)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (mission_id, lineage_root) DO UPDATE
              SET citation_count = GREATEST(COALESCE(sources.citation_count,0), COALESCE(EXCLUDED.citation_count,0)),
                  is_retracted = sources.is_retracted OR EXCLUDED.is_retracted,
                  referenced = CASE WHEN jsonb_array_length(sources.referenced)=0 THEN EXCLUDED.referenced
                                    ELSE sources.referenced END
           RETURNING id, (xmax = 0) AS inserted""",
        (mission_id, rec.get("provider") or "unknown", rec.get("external_id"), rec.get("doi"),
         (rec.get("title") or "(untitled)")[:1000], J(rec.get("authors") or []), rec.get("year"),
         rec.get("venue"), rec.get("url"), rec.get("source_type") or "unknown", bool(rec.get("is_retracted")),
         rec.get("citation_count"), root, J(rec.get("referenced") or []), quality_of(rec), demo, query),
    ).fetchone()
    sid, new = row["id"], bool(row["inserted"])
    abstract = rec.get("abstract") or ""
    if abstract and objects is not None:
        sha = objects.put(abstract)
        conn.execute("INSERT INTO documents(source_id, kind, sha256, text_len) VALUES (%s,'abstract',%s,%s) "
                     "ON CONFLICT (source_id, kind) DO NOTHING", (sid, sha, len(abstract)))
        add_provenance(conn, mission_id, "document", sha, "source", sid, "extracted_from")
    if new:
        emit(conn, mission_id, "SOURCE_FOUND", {
            "source_id": sid, "title": rec.get("title"), "provider": rec.get("provider"),
            "year": rec.get("year"), "doi": rec.get("doi"), "demo_simulated": demo})
    return sid, new


def source_abstract(conn, objects, source_id: int) -> str:
    row = conn.execute("SELECT sha256 FROM documents WHERE source_id=%s AND kind='abstract'",
                       (source_id,)).fetchone()
    if not row or objects is None or not objects.exists(row["sha256"]):
        return ""
    return objects.get_text(row["sha256"])


# -- hypotheses --------------------------------------------------------------
def upsert_hypothesis(conn, mission_id: str, label: str, statement: str, kind: str,
                      rationale: Optional[str] = None) -> int:
    row = conn.execute(
        """INSERT INTO hypotheses(mission_id, label, statement, kind, rationale) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (mission_id, label) DO UPDATE SET updated_at = hypotheses.updated_at
           RETURNING id, (xmax = 0) AS inserted""",
        (mission_id, label, statement, kind, rationale)).fetchone()
    if row["inserted"]:
        emit(conn, mission_id, "HYPOTHESIS_CREATED", {"hypothesis_id": row["id"], "label": label,
                                                      "statement": statement, "kind": kind})
    return row["id"]


def primary_hypothesis(conn, mission_id: str):
    return conn.execute("SELECT * FROM hypotheses WHERE mission_id=%s AND label='H1'", (mission_id,)).fetchone()


# -- claims ----------------------------------------------------------------
def upsert_claim(conn, mission_id: str, text: str, *, stance: str, epistemic: str,
                 hypothesis_id: Optional[int] = None, embedding=None) -> tuple:
    """`stance` is the claim's direction toward H1. -> (claim_id, is_new)."""
    norm = normalize_text(text)[:2000]
    row = conn.execute(
        """INSERT INTO claims(mission_id, hypothesis_id, text, normalized, stance, epistemic, embedding)
           VALUES (%s,%s,%s,%s,%s,%s,%s::vector)
           ON CONFLICT (mission_id, normalized) DO UPDATE SET embedding = COALESCE(claims.embedding, EXCLUDED.embedding)
           RETURNING id, (xmax = 0) AS inserted""",
        (mission_id, hypothesis_id, text[:4000], norm, stance, epistemic,
         vec_literal(embedding) if embedding else None)).fetchone()
    if row["inserted"]:
        emit(conn, mission_id, "CLAIM_CREATED", {"claim_id": row["id"], "text": text[:300],
                                                 "stance": stance, "epistemic": epistemic})
        if hypothesis_id:
            add_provenance(conn, mission_id, "claim", row["id"], "hypothesis", hypothesis_id,
                           "supports" if stance == "SUPPORTS" else "refutes" if stance == "REFUTES" else "about")
    return row["id"], bool(row["inserted"])


# -- evidence ----------------------------------------------------------------
def add_evidence(conn, mission_id: str, claim_id: int, *, stance: str, strength: float, epistemic: str,
                 source_id: Optional[int] = None, experiment_run_id: Optional[int] = None,
                 quote: Optional[str] = None, quote_verified: bool = False,
                 extractor: Optional[str] = None) -> Optional[int]:
    """`stance` is toward the *claim* (SUPPORTS = this origin backs the claim)."""
    if (source_id is None) == (experiment_run_id is None):
        raise ValueError("evidence needs exactly one origin")
    conflict = "(claim_id, source_id) WHERE source_id IS NOT NULL" if source_id is not None \
        else "(claim_id, experiment_run_id) WHERE experiment_run_id IS NOT NULL"
    row = conn.execute(
        f"""INSERT INTO evidence(mission_id, claim_id, source_id, experiment_run_id, stance, quote,
                                 quote_verified, strength, epistemic, extractor)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT {conflict} DO NOTHING RETURNING id""",
        (mission_id, claim_id, source_id, experiment_run_id, stance, quote, quote_verified,
         max(0.0, min(1.0, float(strength))), epistemic, extractor)).fetchone()
    if row is None:
        return None
    origin_kind, origin_id = ("source", source_id) if source_id is not None else ("experiment_run", experiment_run_id)
    emit(conn, mission_id, "EVIDENCE_ADDED", {"evidence_id": row["id"], "claim_id": claim_id,
                                              "origin": origin_kind, "origin_id": origin_id, "stance": stance})
    add_provenance(conn, mission_id, "evidence", row["id"], origin_kind, origin_id, "extracted_from"
                   if origin_kind == "source" else "produced")
    add_provenance(conn, mission_id, "evidence", row["id"], "claim", claim_id,
                   "supports" if stance == "SUPPORTS" else "refutes")
    return row["id"]


def add_provenance(conn, mission_id: str, from_kind: str, from_id, to_kind: str, to_id, relation: str) -> None:
    conn.execute(
        "INSERT INTO provenance(mission_id, from_kind, from_id, to_kind, to_id, relation) VALUES (%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT DO NOTHING", (mission_id, from_kind, str(from_id), to_kind, str(to_id), relation))
