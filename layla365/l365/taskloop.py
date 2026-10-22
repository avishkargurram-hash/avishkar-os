"""Generic work loop shared by all nine agents (their local-model "brain").

Per tick (30 s), per agent:
  1. heartbeat to Layla (she sees alive/silent/paused);
  2. if not paused, collect at most ONE task from her inbox;
  3. work it: up to MAX_STEPS turns of {thought, action|final}; every action is a
     gateway request to Layla (a fixed catalogue she enforces) routed through
     agent.act() so shadow mode / budgets / audit apply uniformly;
  4. report the outcome to Layla and mark the task done.
Daily at 21:00 IST each agent files one summary report; Layla briefs the owner
at 08:00. Agents think ONLY with the local model and write English only
(Layla translates for the owner).
"""
import datetime as _dt
import json
import re
from zoneinfo import ZoneInfo

from . import gateway

IST = ZoneInfo("Asia/Kolkata")
MAX_STEPS = 4
DAILY_HOUR = 21

SYSTEM = (
    "You are {title} -- {summary}\n"
    "You are one of nine agents working for your boss Layla and her owner Avishkar. "
    "Today is {now} (India time). Write in English only. Be concrete and brief.\n"
    "You can only act through the listed ACTIONS (Layla runs them for you). You can never make payments. "
    "Never invent facts: if an action returns nothing useful, say so."
)

PROMPT = (
    "TASK: {task}\n\nACTIONS you may call (one per turn):\n{actions}\n\nSO FAR:\n{scratch}\n\n"
    "Reply with ONLY a JSON object: "
    '{{"thought": "one short sentence", "action": "<action name from the list, or final>", '
    '"args": {{}}, "final": "your complete answer/report when action is final (max 120 words)"}}'
)


def _parse(raw):
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001
        return {}


def _fmt_actions(actions):
    if not actions:
        return "(none -- answer from your own knowledge)"
    return "\n".join(f"- {n}: args {json.dumps(spec, ensure_ascii=False)}" for n, spec in actions.items())


def work(agent, task, actions):
    """Returns (ok, final_text)."""
    scratch = []
    now = _dt.datetime.now(IST).strftime("%A %d %b %Y %H:%M")
    system = SYSTEM.format(title=agent.cfg.get("title", agent.name), summary=agent.cfg.get("summary", ""), now=now)
    for step in range(MAX_STEPS):
        prompt = PROMPT.format(task=task, actions=_fmt_actions(actions),
                               scratch="\n".join(scratch) or "(nothing yet)")
        d = _parse(agent.think(prompt, system=system, json_mode=True, max_tokens=400))
        action = str(d.get("action", "final"))
        if action == "final" or action not in (actions or {}) or step == MAX_STEPS - 1:
            final = str(d.get("final") or d.get("thought") or "").strip()
            if action != "final" and action in (actions or {}) and step == MAX_STEPS - 1:
                final = final or f"Ran out of steps before finishing. Progress: {'; '.join(scratch)[:400]}"
            return bool(final), final or "I couldn't produce an answer for this task."
        res = agent.act("layla.request", {"action": action, "args": d.get("args") or {}},
                        summary=f"{agent.name}: {action}")
        if res["status"] == "shadow":
            return True, f"[shadow mode -- nothing executed] I would call {action} with {json.dumps(d.get('args') or {}, ensure_ascii=False)[:200]}. Thought: {d.get('thought', '')}"
        if res["status"] != "executed":
            scratch.append(f"{action} -> NOT RUN ({res['status']}: {res.get('reason')})")
            continue
        r = res.get("result") or {}
        scratch.append(f"{action} -> {'OK' if r.get('ok') else 'FAILED'}: {str(r.get('output') or r.get('error'))[:700]}")
    return False, "no result"


def step(agent):
    """Called by the runner once per tick for each enabled agent."""
    st = agent.state()
    code, hb = gateway.heartbeat(agent.name, {"mode": st["mode"], "model": "qwen3-4b"})
    if code != 200 or hb.get("paused"):
        return
    _maybe_daily(agent)
    try:  # self-started duties (own thread, live agents only) -- see duties.py
        from . import duties
        from .agent import Agent
        duties.maybe_run(agent, lambda n, cfg=agent.cfg: Agent(n, cfg))
    except Exception as e:  # noqa: BLE001  a duty problem must never stop heartbeats/tasks
        print(f"[l365] duty scheduling failed for {agent.name}: {type(e).__name__}: {e}", flush=True)
    code, ib = gateway.inbox(agent.name)
    if code != 200:
        return
    for t in (ib.get("tasks") or [])[:1]:
        try:
            ok, final = work(agent, t["task"], ib.get("actions") or {})
        except Exception as e:  # noqa: BLE001  (budget exceeded, model down, ...)
            ok, final = False, f"{type(e).__name__}: {e}"
        gateway.report(agent.name, "note", t["task"][:100], final, "info" if ok else "warn")
        gateway.task_done(agent.name, t["id"], ok, final)
        agent.audit("task_done", {"task": t["task"][:200], "ok": ok, "result": final[:400]})


def _maybe_daily(agent):
    now = _dt.datetime.now(IST)
    if now.hour < DAILY_HOUR:
        return
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(_dt.timezone.utc)
    done = agent._q("SELECT 1 FROM core.audit WHERE agent=%s AND event='daily_report' AND ts >= %s LIMIT 1",
                    (agent.name, start), True)
    if done:
        return
    rows = agent._q("SELECT detail FROM core.audit WHERE agent=%s AND event='task_done' AND ts >= %s ORDER BY ts",
                    (agent.name, start), True)
    duty_rows = agent._q("SELECT event, count(*) FROM core.audit WHERE agent=%s AND event LIKE 'duty:%%' AND ts >= %s "
                         "GROUP BY event", (agent.name, start), True)
    duty_line = ("Own duties run today: " + ", ".join(f"{e[5:]} x{n}" for e, n in duty_rows) + ".") if duty_rows else ""
    if not rows:
        body = ("No tasks were assigned today. " + duty_line).strip()
    else:
        items = "\n".join(f"- {r[0].get('task', '')[:100]} => {'done' if r[0].get('ok') else 'FAILED'}: {r[0].get('result', '')[:200]}"
                          for r in rows)
        try:
            body = agent.think(f"Summarise your day for your boss Layla in at most 80 words, English, plain sentences:\n{items}",
                               max_tokens=220)
            body = re.sub(r"<think>.*?</think>", "", body, flags=re.S).strip() or items[:600]
        except Exception:  # noqa: BLE001
            body = items[:900]
    code, _ = gateway.report(agent.name, "daily", f"{agent.cfg.get('title', agent.name)} -- daily report", body)
    if code == 200:
        agent.audit("daily_report", {"tasks": len(rows)})
