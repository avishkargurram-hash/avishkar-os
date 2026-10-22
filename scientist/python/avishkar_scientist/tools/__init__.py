"""Tool layer: `build_registry` wires every concrete tool into a Registry
(spec section 12). Handlers only ever reach tools through the registry."""

from __future__ import annotations

import math
import statistics

from . import literature as lit
from .mock import search_demo
from .registry import Registry, ToolDenied, ToolError, ToolSpec
from .sandbox import Sandbox

__all__ = ["build_registry", "Registry", "ToolDenied", "ToolError", "ToolSpec", "SEARCH_TOOLS"]

SEARCH_TOOLS = {
    "openalex": "openalex.search",
    "arxiv": "arxiv.search",
    "crossref": "crossref.search",
    "semantic_scholar": "semantic_scholar.search",
    "pubmed": "pubmed.search",
    "demo": "demo.search",
}

_SEARCH_IN = {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
              "required": ["query"]}
_SEARCH_OUT = {"type": "array", "items": {"type": "object", "description": "normalized literature record"}}


def _describe(values, timeout_s=0) -> dict:
    xs = [float(v) for v in values]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": statistics.fmean(xs), "median": statistics.median(xs),
            "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0, "min": min(xs), "max": max(xs)}


def _wilson(successes, n, z=1.96, timeout_s=0) -> dict:
    """Wilson score interval for a proportion."""
    s, n = int(successes), int(n)
    if n <= 0:
        return {"n": 0}
    p = s / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"n": n, "p": p, "low": max(0.0, c - h), "high": min(1.0, c + h)}


def build_registry(settings, db=None, objects=None, *, embedder=None, sandbox=None, http=None) -> Registry:
    reg = Registry()
    http = http or lit.HttpClient(db, objects, settings.contact_email)
    email = settings.contact_email

    def add_search(name, fn, desc):
        reg.register(ToolSpec(
            name=name, category="ACADEMIC_SEARCH", description=desc, version="1.0",
            permissions=("net.academic",), input_schema=_SEARCH_IN, output_schema=_SEARCH_OUT,
            cost=0.0, timeout_s=30.0,
            security_policy="read-only HTTPS GET to a fixed academic API host; responses cached; per-host spacing",
            fn=fn))

    add_search("openalex.search", lambda timeout_s, query, limit=8: lit.search_openalex(http, query, limit, timeout_s, email),
               "OpenAlex works search (free, no key)")
    add_search("arxiv.search", lambda timeout_s, query, limit=8: lit.search_arxiv(http, query, limit, timeout_s),
               "arXiv Atom API search")
    add_search("crossref.search", lambda timeout_s, query, limit=8: lit.search_crossref(http, query, limit, timeout_s, email),
               "Crossref REST works search (polite pool)")
    add_search("semantic_scholar.search",
               lambda timeout_s, query, limit=8: lit.search_semantic_scholar(http, query, limit, timeout_s),
               "Semantic Scholar Graph API paper search")
    add_search("pubmed.search", lambda timeout_s, query, limit=8: lit.search_pubmed(http, query, limit, timeout_s, email),
               "NCBI PubMed E-utilities search")
    add_search("demo.search", lambda timeout_s, query, limit=8: search_demo(query, limit, timeout_s),
               "DEMO -- SIMULATED fictional records; only for demo/offline missions")

    sb = sandbox or Sandbox(settings.sandbox_cmd, settings.sandbox_jobs_dir)
    reg.register(ToolSpec(
        name="sandbox.python", category="CODE_EXECUTION",
        description="Run a statically validated Python program in the isolated Docker sandbox",
        version="1.0", permissions=("sandbox.exec",),
        input_schema={"type": "object", "properties": {"code": {"type": "string"}, "seed": {"type": "integer"},
                                                        "run_timeout_s": {"type": "integer"}}, "required": ["code"]},
        output_schema={"type": "object", "description": "RunResult"}, cost=0.0, timeout_s=330.0,
        security_policy="AST whitelist, then docker --network none --read-only --memory 512m --cpus 1 "
                        "--pids-limit 64 --user 65534 --cap-drop ALL; never executed on the host",
        fn=lambda timeout_s, code, seed=0, run_timeout_s=60: sb.run(code, seed=seed, timeout_s=run_timeout_s)))

    reg.register(ToolSpec(
        name="stats.describe", category="STATISTICS", description="Descriptive statistics of a numeric list",
        version="1.0", permissions=("compute.local",),
        input_schema={"type": "object", "properties": {"values": {"type": "array"}}},
        output_schema={"type": "object"}, cost=0.0, timeout_s=5.0,
        security_policy="pure function, no I/O", fn=_describe))
    reg.register(ToolSpec(
        name="stats.proportion_ci", category="STATISTICS", description="Wilson 95% interval for a proportion",
        version="1.0", permissions=("compute.local",),
        input_schema={"type": "object", "properties": {"successes": {"type": "integer"}, "n": {"type": "integer"}}},
        output_schema={"type": "object"}, cost=0.0, timeout_s=5.0,
        security_policy="pure function, no I/O", fn=_wilson))

    if embedder is not None:
        reg.register(ToolSpec(
            name="embed.text", category="EMBEDDING", description="BGE-M3 1024-d embeddings (local server)",
            version="1.0", permissions=(), input_schema={"type": "object", "properties": {"texts": {"type": "array"}}},
            output_schema={"type": "array"}, cost=0.0, timeout_s=60.0,
            security_policy="loopback-only local model; no third-party egress",
            fn=lambda timeout_s, texts: embedder.embed(texts)))
    return reg
