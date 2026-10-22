"""Layla 365 framework self-test. Run on the server:
   set -a; . /opt/layla365/secrets/runner.env; set +a
   PYTHONPATH=/opt/layla365/app /opt/layla365/venv/bin/python /opt/layla365/app/tests/selftest.py
Leaves no residue: test rows are removed and every agent is returned to shadow/enabled.
"""
import os
import sys
import traceback

from l365 import config, db, policy
from l365.agent import Agent, BudgetExceeded, AgentDisabled, qdrant
from l365 import executors  # noqa: F401
from l365.runtime import Runner

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))


def section(t):
    print(f"\n== {t}")


cfg = config.load()
core = db.connect("core")


def q(sql, args=None, fetch=False):
    with core.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall() if fetch else None


def setstate(agent, enabled=True, mode="shadow"):
    q("UPDATE core.agent_state SET enabled=%s, mode=%s WHERE agent=%s", (enabled, mode, agent))


try:
    section("registry + policy (pure logic)")
    check("nine agents loaded", len(cfg["agents"]) == 9, ",".join(cfg["agents"]))
    check("unknown kind -> A3", policy.effective_tier({}, "weird.thing") == "A3")
    check("hard rule: money.* cannot be loosened to A1", policy.effective_tier({"money.transfer": "A1"}, "money.transfer") == "A3")
    check("hard rule: comm.external.* >= A3", policy.effective_tier({"comm.external.email": "A2"}, "comm.external.email") == "A3")
    check("force push is A4", policy.effective_tier({"git.force_push": "A1"}, "git.force_push") == "A4")
    check("yaml: lydia money.transfer A3", policy.effective_tier(cfg["agents"]["lydia"]["actions"], "money.transfer") == "A3")
    check("yaml: maya external email A3", policy.effective_tier(cfg["agents"]["maya"]["actions"], "comm.external.email") == "A3")
    check("yaml: naina PR is A2", policy.effective_tier(cfg["agents"]["naina"]["actions"], "git.pr_open") == "A2")

    runner = Runner()
    runner.ensure_state()
    agents = runner.agents
    for n in agents:
        setstate(n, True, "shadow")

    section("shadow mode / live mode / A2 cap / A3 approval / A4 / kill switch")
    naina = agents["naina"]
    r = naina.act("test.noop", {"x": 1})
    check("shadow: recorded, not executed", r["status"] == "shadow", r["status"])
    setstate("naina", True, "live")
    r = naina.act("test.noop", {"x": 2})
    check("live A1: executed", r["status"] == "executed" and r["result"]["echo"] == {"x": 2}, r["status"])
    s = [naina.act("test.capped")["status"] for _ in range(3)]
    check("A2 cap: 2 executed then approval required", s == ["executed", "executed", "pending_approval"], str(s))
    r = naina.act("git.force_push", {"branch": "main"})
    check("A4: denied", r["status"] == "denied", r["status"])
    setstate("naina", False, "live")
    r = naina.act("test.noop")
    check("kill switch: blocked", r["status"] == "blocked", r["status"])
    try:
        naina.think("hi")
        check("kill switch stops thinking", False)
    except AgentDisabled:
        check("kill switch stops thinking", True)
    setstate("naina", True, "shadow")

    lydia = agents["lydia"]
    setstate("lydia", True, "live")
    r = lydia.act("money.transfer", {"to": "X", "amount": 1}, summary="test transfer")
    check("money: pending approval, never auto", r["status"] == "pending_approval" and r["approval_id"], r["status"])
    runner.process_approvals()
    row = q("SELECT status FROM core.actions WHERE id=%s", (r["id"],), True)[0][0]
    check("not executed while pending", row == "pending_approval", row)
    q("UPDATE core.approvals SET status='approved', decided_by='selftest', decided_at=now() WHERE id=%s", (r["approval_id"],))
    runner.process_approvals()
    row = q("SELECT status FROM core.actions WHERE id=%s", (r["id"],), True)[0][0]
    check("after approval: handled (no executor registered)", row == "no_executor", row)
    setstate("lydia", True, "shadow")

    maya = agents["maya"]
    setstate("maya", True, "live")
    r = maya.act("comm.external.email", {"to": "a@b.c"}, summary="test email")
    check("external send: pending approval", r["status"] == "pending_approval", r["status"])
    q("UPDATE core.approvals SET status='rejected', decided_by='selftest' WHERE id=%s", (r["approval_id"],))
    runner.process_approvals()
    row = q("SELECT status FROM core.actions WHERE id=%s", (r["id"],), True)[0][0]
    check("rejected approval -> action rejected", row == "rejected", row)
    setstate("maya", True, "shadow")

    section("row-level security between agents")
    priya = agents["priya"]
    priya.audit("selftest.own", {"ok": True})
    own = q("SELECT count(*) FROM core.audit WHERE agent='priya' AND event='selftest.own'", fetch=True)[0][0]
    check("agent can write its own audit row", own == 1, str(own))
    try:
        priya._q("INSERT INTO core.audit(agent,event,detail) VALUES ('lydia','forged','{}')")
        check("agent cannot forge another agent's audit row", False)
    except Exception as e:  # noqa: BLE001
        check("agent cannot forge another agent's audit row", "row-level security" in str(e) or "policy" in str(e), type(e).__name__)
    seen = priya._q("SELECT count(*) FROM core.actions WHERE agent='lydia'", fetch=True)[0][0]
    check("agent cannot read another agent's actions", seen == 0, str(seen))
    try:
        priya._q("UPDATE core.audit SET event='x' WHERE agent='priya'")
        check("audit is append-only for agents", False)
    except Exception as e:  # noqa: BLE001
        check("audit is append-only for agents", "permission denied" in str(e), type(e).__name__)
    try:
        priya._q("SELECT * FROM lydia.nothing")
        check("schema isolation (priya vs lydia)", False)
    except Exception as e:  # noqa: BLE001
        check("schema isolation (priya vs lydia)", "permission denied" in str(e) or "does not exist" in str(e), type(e).__name__)

    section("thinking tiers + budgets")
    veda = agents["veda"]
    t = veda.think('Classify "Your OTP is 4821" as JSON {"category":"otp|spam|other"}', json_mode=True, max_tokens=40)
    check("local model answers (JSON mode)", t.strip().startswith("{"), t.strip()[:60].replace("\n", " "))
    calls, _ = veda.usage_today("local")
    check("usage metered (local)", calls >= 1, f"calls={calls}")
    if os.environ.get("CEREBRAS_API_KEY"):
        h = veda.think("Reply with exactly: OK", heavy=True, max_tokens=300)
        check("heavy tier (Cerebras) answers", "OK" in h.upper(), h.strip()[:40])
        hc, ht = veda.usage_today("heavy")
        check("usage metered (heavy)", hc >= 1 and ht > 0, f"calls={hc} tokens={ht}")
    else:
        print("  SKIP  heavy tier (no CEREBRAS_API_KEY in env)")
    saved = veda.cfg["budget"]["local_calls"]
    veda.cfg["budget"]["local_calls"] = 0
    try:
        veda.think("hi")
        check("budget cap blocks the call", False)
    except BudgetExceeded:
        check("budget cap blocks the call", True)
    veda.cfg["budget"]["local_calls"] = saved

    section("per-agent vector memory (local bge-m3 -> Qdrant)")
    shruti = agents["shruti"]
    shruti.remember("The C major scale has no sharps or flats", {"topic": "theory"})
    shruti.remember("Pick the E string first when tuning a guitar", {"topic": "guitar"})
    hit = shruti.recall("which scale has no sharps", 1)[0]
    check("recall finds the right memory", "C major" in hit["text"], f"{hit['text'][:40]} ({hit['score']:.2f})")
    check("collection is agent-prefixed", shruti.collection == "shruti_memory")
finally:
    section("cleanup")
    try:
        for n in cfg["agents"]:
            setstate(n, True, "shadow")
        q("DELETE FROM core.actions WHERE kind LIKE 'test.%' OR (kind IN ('money.transfer','comm.external.email','git.force_push') AND params::text LIKE '%X%' OR params::text LIKE '%a@b.c%' OR params::text LIKE '%main%')")
        q("DELETE FROM core.approvals WHERE kind LIKE 'test.%' OR summary IN ('test transfer','test email')")
        q("DELETE FROM core.audit WHERE event LIKE 'selftest.%'")
        q("DELETE FROM core.usage WHERE agent IN ('veda','shruti')")
        try:
            qdrant("DELETE", "/collections/shruti_memory")
        except Exception:  # noqa: BLE001
            pass
        print("  cleaned; all agents back to enabled + shadow")
    except Exception:  # noqa: BLE001
        traceback.print_exc()

print(f"\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
