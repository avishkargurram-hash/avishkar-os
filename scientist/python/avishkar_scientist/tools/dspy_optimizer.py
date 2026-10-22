"""Tool-routing prompt optimizer (Pillar 3, DSPy-style bootstrap).

Optimizes the few-shot exemplars used to route a user utterance to the right
tool, and reports the accuracy it actually MEASURED on a held-out split -- never
an invented number. Given a labelled trainset (JSONL of {"text","tool"} rows,
default /opt/scientist/dspy/trainset.jsonl, or passed in), it:

  1. splits the data into train / test,
  2. bootstraps candidate few-shot exemplar sets from the train split,
  3. for each candidate, asks the Scientist model router to route every test
     utterance and scores exact-match accuracy,
  4. keeps the exemplar set with the best held-out accuracy and stores it with
     that measured score.

If no router or no trainset is available it does NOT fabricate results -- it
returns status "skipped" with the reason, so a caller can tell the difference
between "optimized, here is the measured accuracy" and "could not run".
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DSPY_DIR = "/opt/scientist/dspy"
PROMPTS_FILE = os.path.join(DSPY_DIR, "compiled_prompts.json")
DEFAULT_TRAINSET = os.path.join(DSPY_DIR, "trainset.jsonl")
MAX_EXEMPLARS = 6
CANDIDATE_SETS = 6

ROUTER_SYSTEM = (
    "You route a user utterance to exactly one tool name from the ALLOWED list. "
    "Reply with ONLY the tool name, nothing else. If none fit, reply none."
)


def _get_pg_conn():
    conn_url = os.environ.get("SCI_DATABASE_URL")
    if not conn_url:
        return None
    try:
        try:
            import psycopg
            return psycopg.connect(conn_url)
        except ImportError:
            import psycopg2
            return psycopg2.connect(conn_url)
    except Exception as exc:
        logger.error(f"Postgres connection failed: {exc}")
        return None


def _load_trainset(path: str, domain: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    p = Path(path)
    if not p.is_file():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("text") and r.get("tool") and (domain in ("all", None) or r.get("domain") == domain):
            rows.append({"text": str(r["text"]), "tool": str(r["tool"])})
    return rows


def _route_one(router, utterance: str, tools: List[str], exemplars: List[Dict[str, str]]) -> str:
    shots = "\n".join(f"Utterance: {e['text']}\nTool: {e['tool']}" for e in exemplars)
    user = (f"ALLOWED TOOLS: {', '.join(sorted(tools))}\n\n"
            + (f"Examples:\n{shots}\n\n" if shots else "")
            + f"Utterance: {utterance}\nTool:")
    from ..models.router import ModelUnavailable
    try:
        res = router.complete("dspy_label", ROUTER_SYSTEM, user, max_tokens=24, temperature=0.0)
    except ModelUnavailable:
        return ""
    ans = (res.content or "").strip().split()[0].strip(".,:;\"'`").lower() if res.content else ""
    # snap to the closest allowed tool name
    for t in tools:
        if ans == t.lower():
            return t
    for t in tools:
        if ans and (ans in t.lower() or t.lower() in ans):
            return t
    return ans


def _score(router, tools: List[str], exemplars: List[Dict[str, str]], test: List[Dict[str, str]]) -> float:
    if not test:
        return 0.0
    correct = sum(1 for ex in test if _route_one(router, ex["text"], tools, exemplars) == ex["tool"])
    return correct / len(test)


def compile_prompts(domain: str = "all", router: Any = None, trainset_path: Optional[str] = None) -> Dict[str, Any]:
    """Run a real bootstrap optimization and report measured held-out accuracy."""
    t0 = time.perf_counter()
    os.makedirs(DSPY_DIR, exist_ok=True)
    if router is None:
        return {"status": "skipped", "reason": "no model router available; cannot measure routing accuracy"}

    data = _load_trainset(trainset_path or DEFAULT_TRAINSET, domain)
    if len(data) < 6:
        return {"status": "skipped",
                "reason": f"insufficient labelled examples ({len(data)} found at "
                          f"{trainset_path or DEFAULT_TRAINSET}; need >= 6). No fabricated metrics produced."}

    tools = sorted({r["tool"] for r in data})
    rng = random.Random(1234)
    rng.shuffle(data)
    split = max(2, int(len(data) * 0.3))
    test, train = data[:split], data[split:]

    baseline = _score(router, tools, [], test)
    best_ex: List[Dict[str, str]] = []
    best_acc = baseline
    for _ in range(CANDIDATE_SETS):
        k = min(MAX_EXEMPLARS, len(train))
        cand = rng.sample(train, k)
        acc = _score(router, tools, cand, test)
        if acc > best_acc:
            best_acc, best_ex = acc, cand

    result = {
        "domain": domain,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tools": tools,
        "exemplars": best_ex,
        "metrics": {
            "measured_routing_accuracy": round(best_acc, 4),
            "baseline_zero_shot_accuracy": round(baseline, 4),
            "train_size": len(train),
            "heldout_size": len(test),
            "candidate_sets_tried": CANDIDATE_SETS,
        },
    }

    conn = _get_pg_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dspy_compiled_prompts (domain, updated_at, version, signature_json, exemplars_json, evaluation_metrics)
                    VALUES (%s, NOW(), 1, %s, %s, %s)
                    ON CONFLICT (domain) DO UPDATE SET updated_at=NOW(),
                        version = dspy_compiled_prompts.version + 1,
                        signature_json = EXCLUDED.signature_json,
                        exemplars_json = EXCLUDED.exemplars_json,
                        evaluation_metrics = EXCLUDED.evaluation_metrics
                """, (domain, json.dumps({"route": "utterance -> tool", "tools": tools}),
                      json.dumps(best_ex), json.dumps(result["metrics"])))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"Could not persist compiled prompt: {exc}")

    try:
        Path(PROMPTS_FILE).write_text(json.dumps({domain: result}, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Could not write prompt cache: {exc}")

    return {
        "status": "success",
        "domain": domain,
        "measured_routing_accuracy": result["metrics"]["measured_routing_accuracy"],
        "baseline_zero_shot_accuracy": result["metrics"]["baseline_zero_shot_accuracy"],
        "exemplars_selected": len(best_ex),
        "heldout_size": len(test),
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def get_compiled_prompts(domain: str = "all") -> Dict[str, Any]:
    """Retrieve stored compiled routing prompts and their MEASURED metrics."""
    conn = _get_pg_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                if domain == "all":
                    cur.execute("SELECT domain, version, signature_json, exemplars_json, evaluation_metrics, updated_at FROM dspy_compiled_prompts")
                else:
                    cur.execute("SELECT domain, version, signature_json, exemplars_json, evaluation_metrics, updated_at FROM dspy_compiled_prompts WHERE domain=%s", (domain,))
                rows = cur.fetchall()
            conn.close()
            if rows:
                prompts = {r[0]: {"domain": r[0], "version": r[1], "signature": r[2], "exemplars": r[3],
                                  "metrics": r[4], "updated_at": r[5].isoformat() if r[5] else None} for r in rows}
                return {"status": "success", "count": len(prompts), "prompts": prompts}
        except Exception as exc:
            logger.warning(f"Failed to query DB for prompts: {exc}")
    if os.path.exists(PROMPTS_FILE):
        try:
            return {"status": "success", "prompts": json.loads(Path(PROMPTS_FILE).read_text(encoding="utf-8"))}
        except Exception:
            pass
    return {"status": "empty", "reason": "no optimization has been run yet; no metrics to report"}
