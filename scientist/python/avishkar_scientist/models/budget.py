"""Premium budget governance (spec sections 9, 10, 24; decision D3).

Gemini/OpenRouter (Tier 3+) are reserved for key decisions and are capped
three ways: per-mission call count, per-mission USD, and a global per-day
USD/call cap across all missions. When any cap is reached the request is
*downgraded* to the local model, never silently failed, and the ledger
records why. BUDGET_WARNING fires once at 80% of a mission's allowance."""

from __future__ import annotations

import dataclasses

from ..events import emit


@dataclasses.dataclass
class Decision:
    allowed: bool
    reason: str = ""


def premium_decision(conn, mission_id, *, daily_usd: float, daily_calls: int, est_usd: float) -> Decision:
    day = conn.execute(
        "SELECT count(*) AS n, COALESCE(sum(cost_usd),0) AS usd FROM model_calls "
        "WHERE tier >= 3 AND status='ok' AND created_at >= date_trunc('day', now())").fetchone()
    if day["n"] >= daily_calls:
        return Decision(False, f"global daily premium call cap reached ({day['n']}/{daily_calls})")
    if float(day["usd"]) + est_usd > daily_usd:
        return Decision(False, f"global daily premium USD cap reached (${float(day['usd']):.4f}/${daily_usd:.2f})")
    if mission_id is None:
        return Decision(True)
    m = conn.execute(
        "SELECT m.premium_model_budget AS cap_calls, m.premium_usd_budget AS cap_usd, "
        "COALESCE(b.premium_calls,0) AS calls, COALESCE(b.premium_usd,0) AS usd "
        "FROM missions m LEFT JOIN budgets b ON b.mission_id=m.id WHERE m.id=%s", (mission_id,)).fetchone()
    if m is None:
        return Decision(False, "unknown mission")
    if m["calls"] >= m["cap_calls"]:
        return Decision(False, f"mission premium call budget exhausted ({m['calls']}/{m['cap_calls']})")
    if float(m["usd"]) + est_usd > float(m["cap_usd"]):
        return Decision(False, f"mission premium USD budget exhausted (${float(m['usd']):.4f}/${float(m['cap_usd']):.2f})")
    return Decision(True)


def record_usage(conn, mission_id, *, premium: bool, cost_usd: float) -> None:
    if mission_id is None:
        return
    if premium:
        conn.execute(
            "INSERT INTO budgets(mission_id, premium_calls, premium_usd) VALUES (%s,1,%s) "
            "ON CONFLICT (mission_id) DO UPDATE SET premium_calls=budgets.premium_calls+1, "
            "premium_usd=budgets.premium_usd+EXCLUDED.premium_usd, updated_at=now()",
            (mission_id, cost_usd))
    else:
        conn.execute(
            "INSERT INTO budgets(mission_id, local_calls) VALUES (%s,1) "
            "ON CONFLICT (mission_id) DO UPDATE SET local_calls=budgets.local_calls+1, updated_at=now()",
            (mission_id,))
    check_warning(conn, mission_id)


def check_warning(conn, mission_id) -> None:
    r = conn.execute(
        "SELECT m.premium_model_budget AS cap_calls, m.max_tasks, b.premium_calls, b.tasks_used, b.warned "
        "FROM missions m JOIN budgets b ON b.mission_id=m.id WHERE m.id=%s", (mission_id,)).fetchone()
    if not r or r["warned"]:
        return
    hit = []
    if r["cap_calls"] and r["premium_calls"] >= 0.8 * r["cap_calls"]:
        hit.append(f"premium calls {r['premium_calls']}/{r['cap_calls']}")
    if r["max_tasks"] and r["tasks_used"] >= 0.8 * r["max_tasks"]:
        hit.append(f"tasks {r['tasks_used']}/{r['max_tasks']}")
    if hit:
        conn.execute("UPDATE budgets SET warned=true WHERE mission_id=%s", (mission_id,))
        emit(conn, mission_id, "BUDGET_WARNING", {"used": hit, "threshold": 0.8})
