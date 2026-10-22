"""Source independence (spec section 41).

Ten papers from one lab repeating one measurement are not ten pieces of
evidence. Sources are grouped (union-find) when they are near-duplicates
(title Jaccard >= 0.75) or share >= 50% of authors (same group). Inside a
group only the strongest piece of evidence per direction counts
(confidence.py). Citation links are recorded for the report but do not
merge groups: an independent replication *cites* the original by necessity.
Each experiment is its own group ("exp:<id>"); its seed replications are
not independent of it, so they share that group.
"""

from __future__ import annotations

from ..models.embed import jaccard

TITLE_DUP = 0.75
AUTHOR_OVERLAP = 0.5


def _authors(src) -> set:
    out = set()
    for a in src.get("authors") or []:
        name = a if isinstance(a, str) else (a or {}).get("name", "")
        parts = [p for p in name.replace(",", " ").split() if p]
        if parts:
            out.add(parts[-1].lower().strip("."))   # surname is the stable part across providers
    return out


def group_sources(sources: list) -> dict:
    """sources: rows with id, title, authors. -> {source_id: group_label}."""
    parent = {s["id"]: s["id"] for s in sources}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    auth = {s["id"]: _authors(s) for s in sources}
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            same = jaccard(a["title"] or "", b["title"] or "") >= TITLE_DUP
            if not same:
                aa, ab = auth[a["id"]], auth[b["id"]]
                if aa and ab and len(aa & ab) / min(len(aa), len(ab)) >= AUTHOR_OVERLAP:
                    same = True
            if same:
                ra, rb = find(a["id"]), find(b["id"])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    return {sid: f"src:{find(sid)}" for sid in parent}


def summarize(groups: dict) -> dict:
    labels = set(groups.values())
    return {"sources": len(groups), "independent_groups": len(labels),
            "merged": len(groups) - len(labels)}
