"""The Agent object: the ONLY way an agent thinks, remembers or acts.

Everything goes through here so that budgets, kill switch, shadow mode,
approval gates and audit are applied uniformly.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request
import uuid

from . import config, db, policy


class BudgetExceeded(Exception):
    pass


class AgentDisabled(Exception):
    pass


# kind -> callable(agent, params) -> dict.  Real executors register here.
EXECUTORS = {}


def executor(kind):
    def deco(fn):
        EXECUTORS[kind] = fn
        return fn
    return deco


def _post(url, body, headers=None, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "layla365/0.1 (python-requests-compatible)",
                 **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def qdrant(method, path, body=None, timeout=30):
    req = urllib.request.Request(
        config.QDRANT_URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"api-key": os.environ["QDRANT_API_KEY"], "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class Agent:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self._conn = None

    # ---- database (as this agent's own Postgres role) -------------------
    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = db.connect(self.name)
        return self._conn

    def _q(self, sql, args=None, fetch=False):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall() if fetch else None

    def state(self) -> dict:
        rows = self._q("SELECT enabled, mode FROM core.agent_state WHERE agent=%s", (self.name,), True)
        if not rows:
            return {"enabled": False, "mode": "shadow"}   # unknown agent => disabled
        return {"enabled": rows[0][0], "mode": rows[0][1]}

    def audit(self, event: str, detail=None):
        self._q("INSERT INTO core.audit(agent, event, detail) VALUES (%s,%s,%s)",
                (self.name, event, db.Json(detail or {})))

    # ---- usage + budgets -------------------------------------------------
    def usage_today(self, tier: str):
        rows = self._q(
            "SELECT calls, tokens_in+tokens_out FROM core.usage "
            "WHERE day=(now() at time zone 'utc')::date AND agent=%s AND tier=%s",
            (self.name, tier), True)
        return (rows[0][0], rows[0][1]) if rows else (0, 0)

    def _usage_add(self, tier, tin, tout):
        self._q(
            "INSERT INTO core.usage(day, agent, tier, calls, tokens_in, tokens_out) "
            "VALUES ((now() at time zone 'utc')::date, %s, %s, 1, %s, %s) "
            "ON CONFLICT (day, agent, tier) DO UPDATE SET calls=core.usage.calls+1, "
            "tokens_in=core.usage.tokens_in+EXCLUDED.tokens_in, "
            "tokens_out=core.usage.tokens_out+EXCLUDED.tokens_out",
            (self.name, tier, int(tin or 0), int(tout or 0)))

    # ---- thinking ----------------------------------------------------------
    def think(self, prompt, *, system=None, heavy=False, json_mode=False,
              max_tokens=300, temperature=0.0) -> str:
        if not self.state()["enabled"]:
            raise AgentDisabled(self.name)
        if heavy:
            # Owner rule (2026-10-12): agents think ONLY with the local model; Cerebras is Layla's.
            # Anything that needs a bigger brain is delegated to Layla through the gateway.
            raise BudgetExceeded(f"{self.name}: heavy tier is disabled (agents are local-model only)")
        tier = "local"
        b = self.cfg["budget"]
        calls, toks = self.usage_today(tier)
        if tier == "local" and calls >= b["local_calls"]:
            raise BudgetExceeded(f"{self.name}: local_calls {calls}/{b['local_calls']}")
        if tier == "heavy" and (calls >= b["heavy_calls"] or toks >= b["heavy_tokens"]):
            raise BudgetExceeded(f"{self.name}: heavy calls {calls}/{b['heavy_calls']} tokens {toks}/{b['heavy_tokens']}")
        m = self.cfg["models"][tier]
        sysmsg = ((system or "") + "\n/no_think").strip()   # Qwen3: no hidden reasoning, saves tokens
        messages = [{"role": "system", "content": sysmsg}, {"role": "user", "content": prompt}]
        body = {"model": m["model"], "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature,
                "chat_template_kwargs": {"enable_thinking": False}}
        headers = {}
        if tier == "local":
            if json_mode:
                body["response_format"] = {"type": "json_object"}
        else:
            headers["Authorization"] = "Bearer " + os.environ[m["key_env"]]
            body["reasoning_effort"] = "low"
        out = _post(m["base_url"] + "/chat/completions", body, headers,
                    timeout=120 if heavy else 60)
        u = out.get("usage", {})
        self._usage_add(tier, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        txt = out["choices"][0]["message"].get("content") or ""
        return re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()

    # ---- memory (Qdrant collection "<agent>_memory", local bge-m3 vectors) ---
    def embed(self, text: str):
        m = self.cfg["models"]["embed"]
        out = _post(m["base_url"] + "/embeddings", {"model": m["model"], "input": text})
        self._usage_add("embed", out.get("usage", {}).get("prompt_tokens", 0), 0)
        return out["data"][0]["embedding"]

    @property
    def collection(self) -> str:
        return f"{self.name}_memory"

    def _ensure_collection(self):
        try:
            qdrant("GET", f"/collections/{self.collection}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            qdrant("PUT", f"/collections/{self.collection}",
                   {"vectors": {"size": self.cfg["models"]["embed"]["dims"], "distance": "Cosine"}})

    def remember(self, text: str, meta=None) -> str:
        self._ensure_collection()
        pid = str(uuid.uuid4())
        qdrant("PUT", f"/collections/{self.collection}/points?wait=true", {"points": [{
            "id": pid, "vector": self.embed(text),
            "payload": {"text": text, "meta": meta or {}, "agent": self.name,
                        "ts": datetime.datetime.utcnow().isoformat() + "Z"}}]})
        return pid

    def recall(self, query: str, k: int = 3):
        self._ensure_collection()
        res = qdrant("POST", f"/collections/{self.collection}/points/search",
                     {"vector": self.embed(query), "limit": k, "with_payload": True})["result"]
        return [{"text": r["payload"]["text"], "score": r["score"], "meta": r["payload"].get("meta")}
                for r in res]

    # ---- acting: every side effect goes through the policy gate ------------
    def _record(self, kind, tier, status, reason=None, params=None, result=None, approval_id=None):
        rows = self._q(
            "INSERT INTO core.actions(agent, kind, tier, status, reason, params, result, approval_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (self.name, kind, tier, status, reason, db.Json(params or {}),
             db.Json(result) if result is not None else None, approval_id), True)
        return {"id": rows[0][0], "kind": kind, "tier": tier, "status": status,
                "reason": reason, "approval_id": approval_id, "result": result}

    def _request_approval(self, kind, tier, params, summary, reason):
        rows = self._q(
            "INSERT INTO core.approvals(agent, kind, summary, params) VALUES (%s,%s,%s,%s) RETURNING id",
            (self.name, kind, summary or kind, db.Json(params)), True)
        return self._record(kind, tier, "pending_approval", reason, params, approval_id=rows[0][0])

    def run_executor(self, kind, params):
        """Run the registered executor. Returns (status, result_or_error)."""
        fn = EXECUTORS.get(kind)
        if fn is None:
            return "no_executor", {"note": "no executor registered for this kind"}
        try:
            return "executed", fn(self, params)
        except Exception as e:  # noqa: BLE001
            return "failed", {"error": f"{type(e).__name__}: {e}"}

    def act(self, kind: str, params=None, summary=None) -> dict:
        params = params or {}
        st = self.state()
        tier = policy.effective_tier(self.cfg["actions"], kind)
        if not st["enabled"]:
            return self._record(kind, tier, "blocked", "agent disabled (kill switch)", params)
        if tier == "A4":
            return self._record(kind, tier, "denied", "tier A4: never autonomous", params)
        if st["mode"] == "shadow":
            return self._record(kind, tier, "shadow", "shadow mode: recorded, not executed", params)
        if tier == "A3":
            return self._request_approval(kind, tier, params, summary, "tier A3: human approval required")
        if tier == "A2":
            cap = (self.cfg["caps"].get(kind) or {}).get("per_day")
            if cap is not None:
                used = self._q(
                    "SELECT count(*) FROM core.actions WHERE agent=%s AND kind=%s "
                    "AND status IN ('executed','failed','no_executor') "
                    "AND ts >= (now() at time zone 'utc')::date",
                    (self.name, kind), True)[0][0]
                if used >= cap:
                    return self._request_approval(kind, tier, params, summary,
                                                  f"daily cap reached ({used}/{cap}): approval required")
        status, result = self.run_executor(kind, params)
        return self._record(kind, tier, status,
                            result.get("error") if status == "failed" else None, params, result)
