"""Mission lifecycle (spec sections 6, 7, 43, 45).

create / pause / resume / cancel / decide_approval, plus the mission's
versioned research state (one jsonb document per mission). Every mutation
writes the audit log and emits an event inside the same transaction, so
the SSE stream never shows a state the database does not hold.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .domain import (DEPTH_PROFILES, TERMINAL_STATUSES, Depth, MissionStatus, profile)
from .events import emit
from .orchestration.engine import TaskSpec
from .storage.db import J
from .tools.mock import DEMO_MISSION_ID

QUESTION_MIN, QUESTION_MAX = 10, 4000


class MissionError(ValueError):
    pass


def audit(conn, actor: str, action: str, target: str, detail: Optional[dict] = None) -> None:
    conn.execute("INSERT INTO audit_log(actor, action, target, detail) VALUES (%s,%s,%s,%s)",
                 (actor, action, target, J(detail or {})))


def _policy(p) -> dict:
    d = dataclasses.asdict(p)
    d["depth"] = str(p.depth)
    d["critics"] = list(p.critics)
    return d


def create_mission(db, engine, question: str, depth: str = "STANDARD", *, user_id: str = "owner",
                   source: str = "api", demo: bool = False, priority: int = 5) -> str:
    question = (question or "").strip()
    if not (QUESTION_MIN <= len(question) <= QUESTION_MAX):
        raise MissionError(f"question must be {QUESTION_MIN}-{QUESTION_MAX} characters")
    try:
        d = Depth(str(depth).upper())
    except ValueError:
        raise MissionError(f"depth must be one of {', '.join(x.value for x in DEPTH_PROFILES)}")
    p = profile(d)
    with db.tx() as c:
        if demo:
            mid = DEMO_MISSION_ID
            c.execute("DELETE FROM missions WHERE id=%s", (mid,))     # children cascade
        else:
            mid = "SCI-%06d" % c.execute("SELECT nextval('mission_seq') AS n").fetchone()["n"]
        c.execute(
            """INSERT INTO missions(id, user_id, question, original_prompt, research_depth, status, priority,
                                    time_budget_s, compute_budget, premium_model_budget, premium_usd_budget,
                                    evidence_threshold, max_tasks, max_experiments, termination_policy,
                                    source, demo)
               VALUES (%s,%s,%s,%s,%s,'CREATED',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (mid, user_id, question, question, str(d), priority, p.time_budget_s, p.max_tasks, p.premium_calls,
             p.premium_usd, p.evidence_threshold, p.max_tasks, p.max_experiments, J(_policy(p)), source, demo))
        c.execute("INSERT INTO research_states(mission_id, state) VALUES (%s, '{}'::jsonb)", (mid,))
        c.execute("INSERT INTO budgets(mission_id) VALUES (%s) ON CONFLICT (mission_id) DO NOTHING", (mid,))
        audit(c, user_id, "mission.create", mid, {"depth": str(d), "source": source, "demo": demo})
        emit(c, mid, "MISSION_CREATED", {"question": question, "depth": str(d), "estimate": p.estimate,
                                         "demo": demo})
        engine.enqueue(c, mid, TaskSpec("plan.scope", "research", {"question": question}, priority=1,
                                        dedupe_key="plan.scope"))
    return mid


def get_mission(db, mid: str):
    return db.one("SELECT * FROM missions WHERE id=%s", (mid,))


def _locked(c, mid):
    row = c.execute("SELECT * FROM missions WHERE id=%s FOR UPDATE", (mid,)).fetchone()
    if row is None:
        raise MissionError(f"mission {mid} not found")
    return row


def pause(db, mid: str, actor: str = "owner") -> dict:
    with db.tx() as c:
        m = _locked(c, mid)
        if m["status"] in TERMINAL_STATUSES:
            raise MissionError(f"mission is {m['status']}")
        if not m["paused"]:
            c.execute("UPDATE missions SET paused=true, status='PAUSED', updated_at=now() WHERE id=%s", (mid,))
            audit(c, actor, "mission.pause", mid)
            emit(c, mid, "MISSION_PAUSED", {"previous_status": m["status"]})
    return {"id": mid, "status": "PAUSED"}


def resume(db, mid: str, actor: str = "owner") -> dict:
    with db.tx() as c:
        m = _locked(c, mid)
        if m["status"] in TERMINAL_STATUSES:
            raise MissionError(f"mission is {m['status']}")
        if m["paused"]:
            c.execute("UPDATE missions SET paused=false, status='RUNNING', updated_at=now() WHERE id=%s", (mid,))
            audit(c, actor, "mission.resume", mid)
            emit(c, mid, "MISSION_RESUMED", {})
    return {"id": mid, "status": "RUNNING"}


def cancel(db, engine, mid: str, actor: str = "owner", reason: str = "cancelled by user") -> dict:
    with db.tx() as c:
        m = _locked(c, mid)
        if m["status"] in TERMINAL_STATUSES:
            return {"id": mid, "status": m["status"]}
        c.execute("UPDATE missions SET cancel_requested=true, status='CANCELLED', stop_reason=COALESCE(stop_reason,%s), "
                  "completed_at=now(), updated_at=now() WHERE id=%s", ("CANCELLED", mid))
        engine.cancel_mission(c, mid)
        c.execute("UPDATE approvals SET status='REJECTED', decided_by=%s, decided_at=now() "
                  "WHERE mission_id=%s AND status='PENDING'", (actor, mid))
        audit(c, actor, "mission.cancel", mid, {"reason": reason})
        emit(c, mid, "MISSION_CANCELLED", {"reason": reason})
    return {"id": mid, "status": "CANCELLED"}


def decide_approval(db, approval_id: int, approve: bool, actor: str = "owner") -> dict:
    """Spec 43: the supervisor's next tick picks the decision up and resumes the mission."""
    with db.tx() as c:
        a = c.execute("SELECT * FROM approvals WHERE id=%s FOR UPDATE", (approval_id,)).fetchone()
        if a is None:
            raise MissionError("approval not found")
        if a["status"] != "PENDING":
            return {"id": approval_id, "status": a["status"]}
        st = "APPROVED" if approve else "REJECTED"
        c.execute("UPDATE approvals SET status=%s, decided_by=%s, decided_at=now() WHERE id=%s",
                  (st, actor, approval_id))
        audit(c, actor, f"approval.{st.lower()}", a["mission_id"], {"approval_id": approval_id, "kind": a["kind"]})
    return {"id": approval_id, "status": st, "mission_id": a["mission_id"]}


# -- research state ----------------------------------------------------------
def load_state(conn, mid: str) -> dict:
    row = conn.execute("SELECT state FROM research_states WHERE mission_id=%s", (mid,)).fetchone()
    return dict(row["state"] or {}) if row else {}


def save_state(conn, mid: str, state: dict, *, announce: bool = True) -> None:
    row = conn.execute("UPDATE research_states SET state=%s, version=version+1, updated_at=now() "
                       "WHERE mission_id=%s RETURNING version", (J(state), mid)).fetchone()
    if row is None:
        conn.execute("INSERT INTO research_states(mission_id, state) VALUES (%s,%s)", (mid, J(state)))
    if announce:
        emit(conn, mid, "STATE_UPDATED", {"version": row["version"] if row else 1,
                                          "keys": sorted(state.keys())[:20]})


def set_phase(conn, mid: str, phase) -> None:
    row = conn.execute("SELECT current_phase FROM missions WHERE id=%s", (mid,)).fetchone()
    if row and row["current_phase"] != str(phase):
        conn.execute("UPDATE missions SET current_phase=%s, updated_at=now() WHERE id=%s", (str(phase), mid))
        emit(conn, mid, "PHASE_CHANGED", {"from": row["current_phase"], "to": str(phase)})


def is_active(status: str) -> bool:
    return status not in TERMINAL_STATUSES and status != MissionStatus.PAUSED
