"""Self-started duties: what each agent does on its own, every day, without being asked (Task 2/3).

Each duty runs on the local model only, reaches the world only through Layla's gateway (her allowlist),
and ends with a report to Layla (who briefs the owner at 08:00). Duties run only for agents in LIVE mode,
in a background thread per agent (the 30-s heartbeat/inbox loop never waits on them), at most two at a time
(the local model has two slots). A missed time-of-day duty is skipped if more than its window has passed
(a 07:30 plan delivered at 15:00 is useless). Every run is recorded as an audit event "duty:<name>".
Nothing here can pay, message other people, or publish -- those actions don't exist in the catalogue.
"""
import datetime as _dt
import json
import re
import threading
import traceback
from zoneinfo import ZoneInfo

from . import gateway
from . import executors  # noqa: F401  registers layla.request even when a duty runs outside the runner (CLI)

IST = ZoneInfo("Asia/Kolkata")
_running = {}                       # agent -> Thread
_llm_slots = threading.BoundedSemaphore(2)
HOME_CITY = "Hyderabad"


class Duty:
    def __init__(self, name, fn, at=None, every_min=None, window_h=3, weekdays_only=False):
        self.name, self.fn, self.at, self.every_min = name, fn, at, every_min
        self.window_h, self.weekdays_only = window_h, weekdays_only


# ---------------- helpers available to every duty ----------------
def _req(agent, action, args=None):
    """One gateway request through agent.act (so mode/audit/policy apply). Returns output text or None."""
    res = agent.act("layla.request", {"action": action, "args": args or {}}, summary=f"{agent.name}: {action}")
    if res["status"] != "executed":
        return None
    r = res.get("result") or {}
    return str(r.get("output")) if r.get("ok") else None


def _think(agent, prompt, max_tokens=320):
    with _llm_slots:
        sys_ = (f"You are {agent.cfg.get('title', agent.name)} -- {agent.cfg.get('summary', '')} You work for Layla "
                f"and her owner Avishkar. Today is {_dt.datetime.now(IST).strftime('%A %d %b %Y, %H:%M')} India time. "
                "Write in plain English sentences, no markdown, no lists unless asked, never invent facts.")
        return re.sub(r"<think>.*?</think>", "", agent.think(prompt, system=sys_, max_tokens=max_tokens), flags=re.S).strip()


def _report(agent, title, body, kind="note", severity="info", tg_body=None):
    code, _ = gateway.report(agent.name, kind, title, body, severity, tg_body=tg_body)
    return code == 200


def _today_start_utc():
    n = _dt.datetime.now(IST)
    return n.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(_dt.timezone.utc)


def _did_today(agent, event):
    return bool(agent._q("SELECT 1 FROM core.audit WHERE agent=%s AND event=%s AND ts >= %s LIMIT 1",
                         (agent.name, event, _today_start_utc()), True))


def _last_run(agent, event):
    r = agent._q("SELECT ts, detail FROM core.audit WHERE agent=%s AND event=%s ORDER BY ts DESC LIMIT 1",
                 (agent.name, event), True)
    return (r[0][0], r[0][1] or {}) if r else (None, {})


# ---------------- the duties ----------------
def priya_morning(agent):
    cal = _req(agent, "calendar.today") or "calendar unavailable"
    mail = _req(agent, "email.important") or "email unavailable"
    alm = _req(agent, "almanac.summary") or "Almanac unavailable"
    wx = _req(agent, "weather.now", {"place": HOME_CITY}) or "weather unavailable"
    plan = _think(agent, "Write Avishkar's plan for today in at most 90 words: what is scheduled, which reminders or "
                         "tasks need attention first, anything important in email, and one line on the weather. "
                         "If a source says unavailable or empty, skip it quietly.\n\n"
                         f"CALENDAR: {cal[:1200]}\nIMPORTANT EMAIL: {mail[:1500]}\nALMANAC: {alm[:1500]}\nWEATHER: {wx[:300]}")
    _report(agent, "Today's plan", plan)
    return {"chars": len(plan)}


def priya_evening(agent):
    alm = _req(agent, "almanac.summary") or "Almanac unavailable"
    room = _req(agent, "home.room") or "room sensors unavailable"
    note = _think(agent, "In at most 70 words, give Avishkar a gentle evening wellness check from his Almanac: what is "
                         "still pending today (routine, reminders, water), and one kind, practical suggestion for the "
                         "night. If the room reading is relevant (too hot, too humid), mention it in a few words. "
                         "Never diagnose anything.\n\nALMANAC: " + alm[:1800] + "\nROOM: " + room[:400])
    _report(agent, "Evening wellness check", note)
    return {"chars": len(note)}


def priya_almanac_watch(agent):
    """Every 5 min, cheap: ask Layla's gateway what changed in the Almanac since the last seen revision.
    Only when something changed does the local model run. Telegram gets titles only (note bodies stay private)."""
    _, last = _last_run(agent, "duty:almanac_watch")
    rev = last.get("rev")
    first = rev is None
    out = _req(agent, "almanac.changes", {"since": 10 ** 12 if first else int(rev)})
    if out is None:
        return {"rev": rev, "unavailable": True}
    try:
        feed = json.loads(out)
        new_rev = int(feed.get("rev") or 0)
    except Exception:  # noqa: BLE001
        return {"rev": rev, "bad_feed": True}
    if first or new_rev < int(rev):      # first run = baseline (don't replay history); lower = server was reset
        return {"rev": new_rev, "baseline": True}
    # Nitya's own home notes ("Home: ...") are already reported by Nitya; do not echo them a second time.
    items = [it for it in (feed.get("items") or []) if not str(it.get("title") or "").startswith("Home:")]
    if new_rev == int(rev) or not (items or feed.get("deleted")):
        return {"rev": new_rev, "changes": 0}
    lines = []
    for it in items:
        bit = f"{it['kind']}: {it.get('title') or '(untitled)'}"
        extra = ", ".join(f"{k} {it[k]}" for k in ("date", "time", "amount", "category", "location") if it.get(k))
        if extra:
            bit += f" ({extra})"
        if it.get("done"):
            bit += " [done]"
        if it.get("text"):
            bit += f" | note text: {it['text']}"
        lines.append("- " + bit)
    more = feed.get("more") or 0
    titles = "; ".join(f"{it['kind']}: {it.get('title') or '(untitled)'}" for it in items[:8])
    ctx = " ; ".join(lines)[:3200]
    ans = _think(agent, "Avishkar's Almanac just changed. In at most 80 words, say what changed and whether anything "
                        "needs his attention or care (health, reminders that clash, a missed medicine, a person to "
                        "call). Do not repeat private note text more than needed. If it is routine, say so in one "
                        "sentence. CHANGES: " + ctx)
    n = len(items) + more
    _report(agent, f"Almanac update: {n} change{'s' if n != 1 else ''}", ans, tg_body=titles or "entries removed")
    for it in items:
        if it["kind"] == "note" and it.get("text"):
            slug = re.sub(r"[^a-z0-9]+", "_", (it.get("title") or "note").lower())[:30]
            _req(agent, "memory.remember", {"key": "almanac_note_" + slug,
                                            "value": f"{it.get('title', '')}: {it['text']}"[:600]})
    return {"rev": new_rev, "changes": n, "deleted": feed.get("deleted", 0)}


def nitya_watch(agent):
    """Every 30 min, no LLM: deterministic rules on real device state; each alert at most once per day."""
    now = _dt.datetime.now(IST)
    fan = _req(agent, "home.fan.status") or ""
    fan_on = bool(re.search(r"'on':\s*True|\"on\":\s*true", fan))
    _, last = _last_run(agent, "duty:home_watch")
    on_since = last.get("fan_on_since")
    if fan_on:
        on_since = on_since or now.timestamp()
    else:
        on_since = None
    alerts = []
    room = _req(agent, "home.room") or ""
    empty_room = "nobody in the room" in room
    temp_m = re.search(r"temperature\s+(-?\d+(?:\.\d+)?)\s*C", room)
    temp = float(temp_m.group(1)) if temp_m else None
    lights = _req(agent, "home.light.status") or ""
    lights_on = bool(re.search(r"'on':\s*True|\"on\":\s*true", lights))
    empty_since = last.get("empty_since")
    empty_since = (empty_since or now.timestamp()) if (empty_room and (lights_on or fan_on)) else None
    if empty_since and now.timestamp() - empty_since >= 45 * 60 and not _did_today(agent, "alert:left_on"):
        what = " and ".join(x for x, on in (("lights", lights_on), ("fan", fan_on)) if on)
        alerts.append(("alert:left_on", f"The room has been empty for 45+ minutes but the {what} are still on", "warn"))
    if temp is not None and temp >= 34 and not fan_on and not empty_room and not _did_today(agent, "alert:room_hot"):
        alerts.append(("alert:room_hot", f"The room is {temp:.0f} C and the fan is off", "warn"))
    if fan_on and on_since and now.timestamp() - on_since >= 8 * 3600 and not _did_today(agent, "alert:fan_long"):
        hrs = int((now.timestamp() - on_since) // 3600)
        alerts.append(("alert:fan_long", f"Bedroom fan has been on for about {hrs} hours", "warn"))
    if fan == "":
        # An outage can last weeks (Tuya trial expiry, the fan switch dropping off Wi-Fi): say it once every 3 days,
        # not daily, and never treat the unreadable fan as "on".
        last_ts, _ = _last_run(agent, "alert:fan_unreachable")
        recent = last_ts is not None and (_dt.datetime.now(_dt.timezone.utc) - last_ts).total_seconds() < 3 * 86400
        if not recent:
            alerts.append(("alert:fan_unreachable",
                           "I can't read the bedroom fan (it is offline or Tuya is unreachable), so I can't tell if it is on", "info"))
    for ev, title, sev in alerts:
        if _report(agent, title, title + ". Checked by Nitya at " + now.strftime("%H:%M") + ".", kind="alert", severity=sev):
            agent.audit(ev, {"title": title})
            # leave the same warning where he will see it next time he opens his Almanac (a NOTE, never an alarm)
            _req(agent, "almanac.home_note", {"kind": "note", "title": ("Home: " + title)[:110],
                                              "text": "Noticed by Nitya at " + now.strftime("%d %b %H:%M") + "."})
    return {"fan_on": fan_on, "fan_on_since": on_since, "empty_since": empty_since, "alerts": len(alerts)}


_TOPICS = ["quantum computing", "fusion energy", "nanotechnology", "space exploration", "biotechnology",
           "materials science", "AI hardware and chips"]


def megha_digest(agent):
    topic = _TOPICS[_dt.datetime.now(IST).weekday() % len(_TOPICS)]
    res = _req(agent, "web.search", {"query": f"latest {topic} breakthrough this week"}) or ""
    if not res:
        _report(agent, f"Research digest: {topic}", "Web search was unavailable today; no digest.", severity="warn")
        return {"topic": topic, "ok": False}
    digest = _think(agent, f"From these search results, write a research digest on {topic} for Avishkar in at most 100 "
                           "words: the two or three most important recent developments and why they matter. Only use "
                           "what the results say.\n\nRESULTS:\n" + res[:3500])
    _report(agent, f"Research digest: {topic}", digest)
    _req(agent, "memory.remember", {"key": "research_digest_latest", "value": f"{topic}: {digest}"[:600]})
    return {"topic": topic, "ok": True}


def veda_invent(agent):
    seed = _req(agent, "memory.recall", {"query": "research digest latest breakthrough"}) or ""
    idea = _think(agent, "Invent ONE practical product idea Avishkar could actually prototype (he builds AI, home "
                         "automation and music products). In at most 110 words give: a name, the problem, how it works, "
                         "and the very first prototype step. You may build on this research note if it helps:\n" + seed[:1200],
                  max_tokens=360)
    _report(agent, "Invention of the day", idea)
    _req(agent, "memory.remember", {"key": "invention_" + _dt.datetime.now(IST).strftime("%Y%m%d"), "value": idea[:600]})
    return {"chars": len(idea)}


def lydia_check(agent):
    mail = _req(agent, "email.important") or ""
    alm = _req(agent, "almanac.summary") or ""
    text = _think(agent, "You are checking Avishkar's money for today. From the email and Almanac data below, list only "
                         "finance items (debits, credits, bills due, failed payments, unusual transactions) in at most "
                         "80 words. If there are none, say exactly: No finance items today.\n\n"
                         f"EMAIL: {mail[:2000]}\nALMANAC: {alm[:800]}")
    risky = re.search(r"\b(unknown|fraud|unauthori[sz]ed|failed|declined|overdue|suspicious)\b", text, re.I)
    _report(agent, "Finance check", text, kind="alert" if risky else "note", severity="warn" if risky else "info")
    return {"risky": bool(risky)}


def naina_watch(agent):
    res = _req(agent, "web.search", {"query": "security vulnerability advisory this week Next.js Python nginx Docker PostgreSQL"}) or ""
    text = _think(agent, "From these results, tell Avishkar in at most 100 words which security issues this week matter "
                         "for a stack of Next.js, Python, nginx, Docker and PostgreSQL, and what to update. If nothing "
                         "relevant, say so.\n\nRESULTS:\n" + res[:3500]) if res else "Web search was unavailable today."
    _report(agent, "Tech & security watch", text)
    return {"ok": bool(res)}


def naina_sitemon(agent):
    """Black-box HTTP/TLS/latency probe of the owner's public domains (sitemon.py). No LLM, no server access."""
    from . import sitemon
    rows, alerts = sitemon.run()
    for sev, title, body in alerts:
        _report(agent, title, body, kind="alert" if sev != "info" else "note", severity=sev)
    return {"checked": len(rows), "up": sum(1 for _, r in rows if r["ok"]), "alerts": len(alerts)}


def naina_site_report(agent):
    from . import sitemon
    lines, bad = sitemon.daily_summary()
    if not lines:
        return {"lines": 0}
    nl = chr(10)
    _report(agent, "Site health (last 24 h)", f"{len(lines)} sites watched, {bad} need attention." + nl + nl.join(lines),
            severity="warn" if bad else "info")
    return {"lines": len(lines), "bad": bad}


def shruti_plan(agent):
    inst = "piano" if _dt.datetime.now(IST).weekday() % 2 == 0 else "guitar"
    plan = _think(agent, f"Give Avishkar a focused 15-minute {inst} practice plan for today in at most 90 words: a "
                         "warm-up, one technique, one short piece or progression, and one theory idea. Plain sentences.")
    _report(agent, f"Today's {inst} practice", plan)
    return {"instrument": inst}


def maya_leads(agent):
    res = _req(agent, "web.search", {"query": "Hyderabad businesses adopting AI voice assistants automation 2026"}) or ""
    text = _think(agent, "From these results, name up to three potential B2B leads for an AI assistant and home-automation "
                         "startup, each with one line on why. Only real names from the results. Say clearly that no "
                         "outreach was sent.\n\nRESULTS:\n" + res[:3500]) if res else "Web search was unavailable today."
    _report(agent, "Lead scout (no outreach sent)", text)
    return {"ok": bool(res)}


def kavya_idea(agent):
    idea = _think(agent, "Create one social-media post idea for the Tryvanta brand (AI assistant Layla, smart home, "
                         "music tech): a hook, a caption under 50 words, and the visual. It is a DRAFT for Avishkar to "
                         "approve -- nothing is posted.", max_tokens=300)
    _report(agent, "Content idea (draft, not posted)", idea)
    return {"chars": len(idea)}


# All owner-facing duties run AFTER 14:00 IST (he sleeps 05:00-14:00). nitya's home watch stays 24/7
# because it is silent unless there is a real alert (and alerts are suppressed in quiet hours anyway).
DUTIES = {
    "priya": [Duty("day_plan", priya_morning, at=(14, 0)), Duty("evening_wellness", priya_evening, at=(21, 0)),
              Duty("almanac_watch", priya_almanac_watch, every_min=5)],
    "nitya": [Duty("home_watch", nitya_watch, every_min=30)],
    "megha": [Duty("research_digest", megha_digest, at=(14, 30))],
    "veda": [Duty("daily_invention", veda_invent, at=(15, 30))],
    "lydia": [Duty("finance_check", lydia_check, at=(19, 0))],
    "naina": [Duty("tech_watch", naina_watch, at=(15, 0)), Duty("site_monitor", naina_sitemon, every_min=5),
              Duty("site_report", naina_site_report, at=(15, 20))],
    "shruti": [Duty("practice_plan", shruti_plan, at=(16, 0))],
    "maya": [Duty("lead_scout", maya_leads, at=(16, 30), weekdays_only=True)],
    "kavya": [Duty("content_idea", kavya_idea, at=(17, 0))],
}


# ---------------- scheduler ----------------
def _due(agent, d):
    now = _dt.datetime.now(IST)
    if d.weekdays_only and now.weekday() >= 5:
        return False
    ev = "duty:" + d.name
    if d.every_min:
        ts, _ = _last_run(agent, ev)
        return ts is None or (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds() >= d.every_min * 60
    start = now.replace(hour=d.at[0], minute=d.at[1], second=0, microsecond=0)
    if not (start <= now <= start + _dt.timedelta(hours=d.window_h)):
        return False
    return not _did_today(agent, ev)


def run_duty(agent, d):
    """Run one duty synchronously (used by the scheduler thread and by the operator CLI)."""
    try:
        detail = d.fn(agent) or {}
        agent.audit("duty:" + d.name, detail)
        return True, detail
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        agent.audit("duty:" + d.name, {"error": f"{type(e).__name__}: {e}"[:300]})
        return False, {"error": str(e)[:200]}


def maybe_run(agent, make_agent):
    """Called each tick. Starts at most one due duty per agent, in its own thread with its own DB connection."""
    if agent.name in _running and _running[agent.name].is_alive():
        return
    st = agent.state()
    if not st["enabled"] or st["mode"] != "live":
        return
    for d in DUTIES.get(agent.name, []):
        if _due(agent, d):
            def _go(name=agent.name, duty=d):
                a = make_agent(name)
                try:
                    run_duty(a, duty)
                finally:
                    try:
                        a.conn.close()
                    except Exception:  # noqa: BLE001
                        pass
            t = threading.Thread(target=_go, daemon=True, name=f"duty-{agent.name}-{d.name}")
            _running[agent.name] = t
            t.start()
            return
