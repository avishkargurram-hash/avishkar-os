"""FastAPI application for Scientist OS (P7).

Serves mission lifecycle endpoints, evidence queries, reports, metrics,
and real-time server-sent events (SSE) over PostgreSQL LISTEN/NOTIFY.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..domain import Depth, profile
from ..events import CHANNEL, list_events, to_sse
from ..mission import (
    MissionError,
    cancel,
    create_mission,
    decide_approval,
    get_mission,
    pause,
    resume,
)
from ..runtime import Runtime, build_runtime
from ..storage.db import J
from .auth import Caller, get_runtime_ctx, require_role

app = FastAPI(
    title="Avishkar Scientist OS API",
    version="1.0.0",
    description="Durable autonomous scientific research subsystem for Avishkar OS",
)

# CORS middleware for local web UI and external dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Request Models ----------------------------------------------------------

class CreateMissionRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)
    depth: str = Field("STANDARD")
    demo: bool = Field(False)
    user_id: Optional[str] = Field(None)
    priority: int = Field(5, ge=1, le=10)


class DecideApprovalRequest(BaseModel):
    approve: bool


class CancelMissionRequest(BaseModel):
    reason: str = Field("cancelled by user")


class EntityUpsertRequest(BaseModel):
    kind: str = Field(..., description="Entity category: SERVER, DEVICE, PROJECT, AGENT, SERVICE, INFRA")
    name: str = Field(..., description="Display name of entity")
    state: Dict[str, Any] = Field(default_factory=dict, description="Live state attributes")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Static/config metadata")


class WorkflowUpsertRequest(BaseModel):
    goal: str = Field(..., description="Goal of the multi-day / multi-step workflow")
    status: str = Field("ACTIVE", description="ACTIVE, PAUSED, COMPLETED, FAILED")
    initiator: str = Field("avishkar", description="Who or what launched the workflow")
    assigned_node: str = Field("oracle", description="Target execution node: oracle, tv-mum-01, pc")
    context: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary workflow context/state")
    step_progress: int = Field(0, description="Completed step counter")
    total_steps: Optional[int] = Field(None, description="Total expected steps if known")


class ToolOutcomeLogRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Session or conversation ID")
    tool_name: str = Field(..., description="Exact tool name executed")
    input_params: Dict[str, Any] = Field(default_factory=dict, description="Input arguments passed to tool")
    output_status: str = Field(..., description="SUCCESS, ERROR, TIMEOUT")
    error_message: Optional[str] = Field(None, description="Error trace or message if failed")
    latency_ms: Optional[float] = Field(None, description="Execution duration in milliseconds")


class ReflectionRuleCreateRequest(BaseModel):
    domain: str = Field("general", description="Operational domain: science, hardware, browser, code, system, general")
    pattern: str = Field(..., description="Keyword or regex pattern triggering this reflection")
    intent: str = Field(..., description="Summary of intent / action attempted")
    trigger_condition: str = Field(..., description="Failure mode or anti-pattern observed")
    lesson: str = Field(..., description="Actionable instruction to prevent recurrence")


class BrowseRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL")
    timeout_s: float = Field(30.0, description="Max seconds to wait")
    wait_until: str = Field("domcontentloaded", description="Navigation wait condition")
    capture_screenshot: bool = Field(False, description="Whether to capture a JPEG screenshot")
    max_chars: int = Field(4000, description="Max characters of extracted text to return")


class BrowserSearchRequest(BaseModel):
    query: str = Field(..., description="Search query string")
    max_results: int = Field(5, ge=1, le=15, description="Max search results to retrieve")


class BrowserActionsRequest(BaseModel):
    steps: List[Dict[str, Any]] = Field(..., description="List of sequential UI actions (goto, click, fill, press, wait, extract)")
    start_url: Optional[str] = Field(None, description="Initial URL to open")
    timeout_s: float = Field(35.0, description="Max duration in seconds")


class InterpreterRunRequest(BaseModel):
    command: str = Field(..., description="Command or code snippet to execute")
    language: str = Field("bash", description="Execution language: bash or python")
    max_retries: int = Field(3, ge=1, le=5, description="Max self-healing retry iterations")
    timeout_s: float = Field(30.0, ge=1.0, le=120.0, description="Max timeout per execution attempt")
    cwd: Optional[str] = Field(None, description="Working directory")


class CoderTaskRequest(BaseModel):
    description: str = Field(..., description="Coding task description")
    target_dir: str = Field("/opt/scientist/src", description="Target repository or working directory")
    test_command: Optional[str] = Field(None, description="Automated test verification command")
    max_iterations: int = Field(3, ge=1, le=5, description="Max diagnostic iteration attempts")


class DspyCompileRequest(BaseModel):
    domain: str = Field("all", description="Target domain to optimize or 'all'")


class RsiProposeRequest(BaseModel):
    target_component: str = Field(..., description="Component target (e.g. prompt, router, tool, plugin)")
    title: str = Field(..., description="Short summary of the improvement")
    rationale: str = Field(..., description="Reasoning and benchmark backing")
    code_diff: str = Field(..., description="Unified diff or new code snippet")


class RsiDecideRequest(BaseModel):
    proposal_id: str = Field(..., description="Proposal ID to approve or reject")
    decision: str = Field(..., description="APPROVE or REJECT")
    auth_token: str = Field(..., description="Creator cryptographic approval token")
    rejection_reason: Optional[str] = Field(None, description="Optional explanation for rejection")


# -- Lifecycle & Runtime -----------------------------------------------------

@app.on_event("startup")
def startup_event():
    # Cache singleton runtime instance on the app state
    ctx = build_runtime()
    app.state.runtime = ctx
    get_runtime_ctx._instance = ctx


# -- Public Endpoints --------------------------------------------------------

@app.get("/healthz", tags=["System"])
def healthz(ctx: Runtime = Depends(get_runtime_ctx)):
    """Health check endpoint; unauthenticated."""
    db_ok = True
    try:
        ctx.db.one("SELECT 1")
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "service": "avishkar-scientist"}


@app.get("/api/estimate", tags=["Missions"])
def estimate_cost(
    question: str = Query("", description="Research question"),
    depth: str = Query("STANDARD", description="Research depth profile"),
    caller: Caller = Depends(require_role("viewer", "owner")),
):
    """Estimate time and resource parameters for a depth profile without creating a mission."""
    try:
        d = Depth(depth.strip().upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid depth; must be one of {[x.value for x in Depth]}",
        )
    p = profile(d)
    return {
        "depth": str(d),
        "estimate": p.estimate,
        "max_tasks": p.max_tasks,
        "time_budget_s": p.time_budget_s,
        "premium_calls": p.premium_calls,
        "premium_usd": float(p.premium_usd),
    }


# -- Mission Endpoints -------------------------------------------------------

@app.post("/api/missions", status_code=status.HTTP_201_CREATED, tags=["Missions"])
def api_create_mission(
    req: CreateMissionRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Create a new research mission and enqueue initial scoping."""
    user = req.user_id or caller.name
    try:
        mid = create_mission(
            ctx.db,
            ctx.engine,
            req.question,
            depth=req.depth,
            user_id=user,
            source="api",
            demo=req.demo,
            priority=req.priority,
        )
    except MissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"id": mid, "status": "CREATED"}


@app.get("/api/missions", tags=["Missions"])
def list_recent_missions(
    limit: int = Query(50, ge=1, le=200),
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """List recent missions ordered by creation date."""
    rows = ctx.db.all(
        """SELECT id, question, status, current_phase, research_depth, confidence,
                  iteration, stop_reason, demo, created_at, updated_at
           FROM missions
           ORDER BY created_at DESC
           LIMIT %s""",
        (limit,),
    )
    return rows


@app.get("/api/missions/{mission_id}", tags=["Missions"])
def get_mission_detail(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve full mission record."""
    row = get_mission(ctx.db, mission_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"mission {mission_id} not found")
    return row


@app.get("/api/missions/{mission_id}/status", tags=["Missions"])
def get_mission_status(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve live status, progress metrics, and confidence."""
    row = get_mission(ctx.db, mission_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"mission {mission_id} not found")
    return {
        "id": row["id"],
        "status": row["status"],
        "phase": row["current_phase"],
        "stage": row["stage"],
        "iteration": row["iteration"],
        "confidence": row["confidence"],
        "rqs": row["rqs"],
        "stop_reason": row["stop_reason"],
        "paused": row["paused"],
        "cancel_requested": row["cancel_requested"],
    }


@app.get("/api/missions/{mission_id}/evidence", tags=["Evidence"])
def list_mission_evidence(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve evidence records extracted for this mission."""
    return ctx.db.all(
        "SELECT * FROM evidence WHERE mission_id=%s ORDER BY id",
        (mission_id,),
    )


@app.get("/api/missions/{mission_id}/claims", tags=["Evidence"])
def list_mission_claims(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve verified and candidate claims for this mission."""
    return ctx.db.all(
        "SELECT * FROM claims WHERE mission_id=%s ORDER BY id",
        (mission_id,),
    )


@app.get("/api/missions/{mission_id}/experiments", tags=["Evidence"])
def list_mission_experiments(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve computational experiments and execution runs."""
    return ctx.db.all(
        "SELECT * FROM experiments WHERE mission_id=%s ORDER BY id",
        (mission_id,),
    )


@app.get("/api/missions/{mission_id}/verdict", tags=["Results"])
def get_mission_verdict(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve synthesized scientific verdict."""
    row = ctx.db.one(
        "SELECT * FROM verdicts WHERE mission_id=%s ORDER BY id DESC LIMIT 1",
        (mission_id,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="verdict not ready")
    return row


@app.get("/api/missions/{mission_id}/report", tags=["Results"])
def get_mission_report(
    mission_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve comprehensive research report in Markdown."""
    row = ctx.db.one(
        "SELECT * FROM reports WHERE mission_id=%s ORDER BY id DESC LIMIT 1",
        (mission_id,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not ready")
    return Response(
        content=row["body"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="report-{mission_id}.md"'},
    )


# -- Realtime SSE Events Stream ----------------------------------------------

@app.get("/api/missions/{mission_id}/events", tags=["Realtime"])
def stream_mission_events(
    mission_id: str,
    last_event_id_header: Optional[str] = Header(None, alias="Last-Event-ID"),
    last_event_id_query: Optional[int] = Query(None, alias="last_event_id"),
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Server-Sent Events (SSE) stream for live mission progress updates.
    
    Replays historic events if Last-Event-ID header or last_event_id query is provided,
    then listens to PostgreSQL NOTIFY events on 'sci_events'.
    """
    row = get_mission(ctx.db, mission_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"mission {mission_id} not found")

    after_id = 0
    if last_event_id_header and last_event_id_header.strip().isdigit():
        after_id = int(last_event_id_header.strip())
    elif last_event_id_query is not None and last_event_id_query >= 0:
        after_id = last_event_id_query

    def event_generator():
        last_seen = after_id

        # 1. Replay historical events
        past = list_events(ctx.db, mission_id, after_id=last_seen, limit=500)
        for ev in past:
            yield to_sse(ev)
            last_seen = max(last_seen, ev["id"])

        # 2. Connect to live Postgres LISTEN
        conn = ctx.db.connect_autocommit()
        try:
            conn.execute(f"LISTEN {CHANNEL}")
            while True:
                # Polling notifies generator with 15s timeout for keepalive
                got_any = False
                for notify in conn.notifies(timeout=15.0):
                    got_any = True
                    try:
                        p = json.loads(notify.payload)
                    except Exception:
                        continue
                    if p.get("m") == mission_id:
                        # Fetch any new events after last_seen
                        fresh = list_events(ctx.db, mission_id, after_id=last_seen, limit=50)
                        for ev in fresh:
                            yield to_sse(ev)
                            last_seen = max(last_seen, ev["id"])
                if not got_any:
                    # Keepalive comment heartbeat
                    yield ": ping\n\n"
        except (GeneratorExit, asyncio.CancelledError):
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- Control Actions ---------------------------------------------------------

@app.post("/api/missions/{mission_id}/pause", tags=["Control"])
def api_pause_mission(
    mission_id: str,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Pause an active mission."""
    try:
        return pause(ctx.db, mission_id, actor=caller.name)
    except MissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/missions/{mission_id}/resume", tags=["Control"])
def api_resume_mission(
    mission_id: str,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Resume a paused mission."""
    try:
        return resume(ctx.db, mission_id, actor=caller.name)
    except MissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/missions/{mission_id}/cancel", tags=["Control"])
def api_cancel_mission(
    mission_id: str,
    req: CancelMissionRequest = CancelMissionRequest(),
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Cancel a mission and abort pending tasks."""
    try:
        return cancel(ctx.db, ctx.engine, mission_id, actor=caller.name, reason=req.reason)
    except MissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/approvals/{approval_id}/decide", tags=["Control"])
def api_decide_approval(
    approval_id: int,
    req: DecideApprovalRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Decide a pending human-in-the-loop approval gate."""
    try:
        return decide_approval(ctx.db, approval_id, req.approve, actor=caller.name)
    except MissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -- Metrics -----------------------------------------------------------------

@app.get("/metrics", tags=["System"])
def get_metrics(
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """System-level operational metrics and costs."""
    active_missions = ctx.db.one(
        "SELECT count(*) as c FROM missions WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')"
    )["c"]
    total_missions = ctx.db.one("SELECT count(*) as c FROM missions")["c"]
    tasks_by_status = ctx.db.all("SELECT status, count(*) as count FROM tasks GROUP BY status")
    todays_cost = ctx.db.one(
        "SELECT coalesce(sum(cost_usd), 0) as cost, count(*) as calls FROM model_calls WHERE created_at >= current_date"
    )
    total_evidence = ctx.db.one("SELECT count(*) as c FROM evidence")["c"]
    total_verdicts = ctx.db.one("SELECT count(*) as c FROM verdicts")["c"]

    return {
        "active_missions": active_missions,
        "total_missions": total_missions,
        "tasks_by_status": {r["status"]: r["count"] for r in tasks_by_status},
        "today_model_calls": todays_cost["calls"],
        "today_model_cost_usd": float(todays_cost["cost"]),
        "total_evidence_collected": total_evidence,
        "total_verdicts_rendered": total_verdicts,
    }


# -- WorldState (Pillar 7) ---------------------------------------------------

@app.get("/api/world/entities", tags=["WorldState"])
def list_world_entities(
    kind: Optional[str] = Query(None, description="Optional kind filter: SERVER, DEVICE, PROJECT, AGENT, SERVICE, INFRA"),
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve digital reality graph entities (servers, IoT devices, services)."""
    if kind:
        return ctx.db.all(
            "SELECT id, kind, name, state, metadata, updated_at, created_at FROM world_entities WHERE upper(kind)=upper(%s) ORDER BY id",
            (kind,),
        )
    return ctx.db.all(
        "SELECT id, kind, name, state, metadata, updated_at, created_at FROM world_entities ORDER BY kind, id"
    )


@app.get("/api/world/entities/{entity_id}", tags=["WorldState"])
def get_world_entity(
    entity_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Retrieve a single entity from the digital reality graph."""
    row = ctx.db.one(
        "SELECT id, kind, name, state, metadata, updated_at, created_at FROM world_entities WHERE id=%s",
        (entity_id,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"entity '{entity_id}' not found")
    return row


@app.post("/api/world/entities/{entity_id}", tags=["WorldState"])
def upsert_world_entity(
    entity_id: str,
    req: EntityUpsertRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Register or update an entity's live state in the digital reality graph."""
    row = ctx.db.one(
        """
        INSERT INTO world_entities (id, kind, name, state, metadata, updated_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            kind = EXCLUDED.kind,
            name = EXCLUDED.name,
            state = EXCLUDED.state,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        RETURNING id, kind, name, state, metadata, updated_at
        """,
        (entity_id, req.kind.upper(), req.name, J(req.state), J(req.metadata)),
    )
    return {"status": "ok", "entity": row}


@app.get("/api/world/summary", tags=["WorldState"])
def get_world_summary(
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Aggregated ecosystem status summary for conversational injection and situational awareness."""
    servers = ctx.db.all(
        "SELECT id, name, state, metadata, updated_at FROM world_entities WHERE kind='SERVER' ORDER BY id"
    )
    devices = ctx.db.all(
        "SELECT id, name, state, metadata, updated_at FROM world_entities WHERE kind='DEVICE' ORDER BY id"
    )
    workflows = ctx.db.all(
        "SELECT id, goal, status, initiator, assigned_node, step_progress, total_steps, updated_at FROM active_workflows WHERE status='ACTIVE' ORDER BY updated_at DESC"
    )
    active_missions = ctx.db.all(
        "SELECT id, question, status, current_phase, confidence FROM missions WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED') ORDER BY created_at DESC LIMIT 5"
    )

    server_parts = []
    for s in servers:
        st = s.get("state") or {}
        role = st.get("role", "Node")
        ip = st.get("ip", "")
        ip_str = f" ({ip})" if ip else ""
        stat = st.get("status", "ONLINE")
        server_parts.append(f"{s['name']}{ip_str}: {role} [{stat}]")

    device_parts = []
    for d in devices:
        st = d.get("state") or {}
        stat = st.get("status", "ONLINE")
        device_parts.append(f"{d['name']} [{stat}]")

    wf_parts = []
    for w in workflows:
        prog = f"{w['step_progress']}/{w['total_steps']}" if w.get("total_steps") else f"step {w['step_progress']}"
        wf_parts.append(f"[{w['id']}] {w['goal']} ({prog} on {w['assigned_node']})")

    narrative = (
        f"Ecosystem Status: {len(servers)} servers active ({'; '.join(server_parts)}). "
        f"{len(devices)} IoT devices monitored ({', '.join(device_parts)}). "
        f"{len(workflows)} active multi-day workflows ({'; '.join(wf_parts) if wf_parts else 'None'}). "
        f"{len(active_missions)} scientific research missions in progress."
    )

    return {
        "status": "ok",
        "narrative": narrative,
        "servers": servers,
        "devices": devices,
        "active_workflows": workflows,
        "active_missions": active_missions,
    }


# -- Workflows (Long-running Tasks) -------------------------------------------

@app.get("/api/workflows", tags=["Workflows"])
def list_workflows(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: ACTIVE, PAUSED, COMPLETED, FAILED"),
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """List persistent multi-day workflows."""
    if status_filter:
        return ctx.db.all(
            "SELECT * FROM active_workflows WHERE upper(status)=upper(%s) ORDER BY updated_at DESC",
            (status_filter,),
        )
    return ctx.db.all("SELECT * FROM active_workflows ORDER BY updated_at DESC LIMIT 100")


@app.post("/api/workflows/{workflow_id}", tags=["Workflows"])
def upsert_workflow(
    workflow_id: str,
    req: WorkflowUpsertRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Create or update a long-running multi-day workflow."""
    row = ctx.db.one(
        """
        INSERT INTO active_workflows (id, goal, status, initiator, assigned_node, context, step_progress, total_steps, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            goal = EXCLUDED.goal,
            status = EXCLUDED.status,
            initiator = EXCLUDED.initiator,
            assigned_node = EXCLUDED.assigned_node,
            context = EXCLUDED.context,
            step_progress = EXCLUDED.step_progress,
            total_steps = EXCLUDED.total_steps,
            updated_at = NOW()
        RETURNING *
        """,
        (
            workflow_id,
            req.goal,
            req.status.upper(),
            req.initiator,
            req.assigned_node,
            J(req.context),
            req.step_progress,
            req.total_steps,
        ),
    )
    return {"status": "ok", "workflow": row}


# -- Hindsight (Pillar 1) ----------------------------------------------------

@app.get("/api/hindsight/reflections", tags=["Hindsight"])
def get_reflections(
    domain: Optional[str] = Query(None, description="Domain filter: science, hardware, browser, code, system, general"),
    q: Optional[str] = Query(None, description="Text match against pattern, intent, or trigger condition"),
    caller: Caller = Depends(require_role("viewer", "owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Fetch learned experiential lessons and anti-patterns."""
    clauses = ["active = TRUE"]
    params: list[Any] = []

    if domain:
        clauses.append("upper(domain) = upper(%s)")
        params.append(domain)
    if q:
        clauses.append("(pattern ILIKE %s OR intent ILIKE %s OR trigger_condition ILIKE %s)")
        pattern_arg = f"%{q}%"
        params.extend([pattern_arg, pattern_arg, pattern_arg])

    query_str = f"SELECT * FROM reflection_rules WHERE {' AND '.join(clauses)} ORDER BY success_count DESC, id ASC"
    return ctx.db.all(query_str, tuple(params) if params else None)


@app.post("/api/hindsight/reflections", status_code=status.HTTP_201_CREATED, tags=["Hindsight"])
def create_reflection_rule(
    req: ReflectionRuleCreateRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Record a newly distilled operational lesson learned from execution."""
    row = ctx.db.one(
        """
        INSERT INTO reflection_rules (domain, pattern, intent, trigger_condition, lesson, success_count, failure_count, active, updated_at)
        VALUES (%s, %s, %s, %s, %s, 1, 0, TRUE, NOW())
        RETURNING *
        """,
        (req.domain.lower(), req.pattern, req.intent, req.trigger_condition, req.lesson),
    )
    return {"status": "ok", "rule": row}


@app.post("/api/hindsight/outcomes", tags=["Hindsight"])
def log_tool_outcome(
    req: ToolOutcomeLogRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Log tool execution result and update reflection rule success/failure counters."""
    row = ctx.db.one(
        """
        INSERT INTO tool_outcomes (session_id, tool_name, input_params, output_status, error_message, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            req.session_id,
            req.tool_name,
            J(req.input_params),
            req.output_status.upper(),
            req.error_message,
            req.latency_ms,
        ),
    )

    # Correlate outcome with reflection rules
    is_err = req.output_status.upper() in ("ERROR", "TIMEOUT")
    try:
        if is_err:
            ctx.db.run(
                "UPDATE reflection_rules SET failure_count = failure_count + 1, updated_at = NOW() WHERE active = TRUE AND (pattern ILIKE %s OR intent ILIKE %s)",
                (f"%{req.tool_name}%", f"%{req.tool_name}%"),
            )
        else:
            ctx.db.run(
                "UPDATE reflection_rules SET success_count = success_count + 1, updated_at = NOW() WHERE active = TRUE AND (pattern ILIKE %s OR intent ILIKE %s)",
                (f"%{req.tool_name}%", f"%{req.tool_name}%"),
            )
    except Exception:
        pass

# -- Browser-Use (Pillar 2) --------------------------------------------------

@app.post("/api/browser/browse", tags=["Browser"])
def api_browse_page(
    req: BrowseRequest,
    caller: Caller = Depends(require_role("viewer", "owner")),
):
    """Headless browser worker: navigates, renders JS, extracts clean markdown and links."""
    from ..tools.browser import browse_page
    res = browse_page(
        req.url,
        timeout_s=req.timeout_s,
        wait_until=req.wait_until,
        capture_screenshot=req.capture_screenshot,
        max_chars=req.max_chars,
    )
    if res.get("status") in ("error", "timeout"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=res.get("error", "browser error"))
    return res


@app.post("/api/browser/search", tags=["Browser"])
def api_browser_search(
    req: BrowserSearchRequest,
    caller: Caller = Depends(require_role("viewer", "owner")),
):
    """Headless search worker: performs web search via headless Chromium without API keys."""
    from ..tools.browser import search_web_headless
    res = search_web_headless(req.query, max_results=req.max_results)
    if res.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=res.get("error", "search failed"))
    return res


@app.post("/api/browser/interact", tags=["Browser"])
def api_browser_interact(
    req: BrowserActionsRequest,
    caller: Caller = Depends(require_role("owner")),
):
    """Interactive browser worker: executes multi-step click/fill/extract operations."""
    from ..tools.browser import execute_browser_actions
    res = execute_browser_actions(req.steps, start_url=req.start_url, timeout_s=req.timeout_s)
    if res.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=res.get("error", "action failed"))
    return res


# -- Interpreter Loop (Pillar 8) ---------------------------------------------

@app.post("/api/interpreter/run", tags=["Interpreter"])
def api_interpreter_run(
    req: InterpreterRunRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Self-healing command execution loop: runs commands and auto-repairs runtime failures."""
    from ..tools.interpreter import self_healing_command_loop
    res = self_healing_command_loop(
        req.command,
        language=req.language,
        max_retries=req.max_retries,
        timeout_s=req.timeout_s,
        cwd=req.cwd,
    )
    try:
        ctx.db.one(
            """
            INSERT INTO tool_outcomes (session_id, tool_name, input_params, output_status, error_message, latency_ms)
            VALUES ('interpreter', %s, %s, %s, %s, %s)
            """,
            (
                f"interpreter:{req.language}",
                J({"command": req.command, "attempts": res.get("attempts")}),
                res.get("status", "SUCCESS").upper(),
                res.get("error"),
                res.get("latency_ms"),
            ),
        )
    except Exception:
        pass
    return res


# -- OpenHands Coder (Pillar 6) -----------------------------------------------

@app.post("/api/coder/task", tags=["Coder"])
def api_coder_dispatch(
    req: CoderTaskRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Dispatches an autonomous software engineering iteration loop."""
    from ..tools.coder import run_coder_task
    return run_coder_task(
        req.description,
        target_dir=req.target_dir,
        test_command=req.test_command,
        max_iterations=req.max_iterations,
        router=ctx.router,
    )


@app.get("/api/coder/task/{task_id}", tags=["Coder"])
def api_coder_status(
    task_id: str,
    caller: Caller = Depends(require_role("viewer", "owner")),
):
    """Retrieves coding task status, iteration count, and logs."""
    from ..tools.coder import get_coder_task
    res = get_coder_task(task_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=res.get("error"))
    return res


# -- DSPy Optimizer (Pillar 3) ------------------------------------------------

@app.post("/api/dspy/compile", tags=["DSPy"])
def api_dspy_compile(
    req: DspyCompileRequest,
    caller: Caller = Depends(require_role("owner")),
    ctx: Runtime = Depends(get_runtime_ctx),
):
    """Compiles optimized few-shot exemplars and routing prompt signatures."""
    from ..tools.dspy_optimizer import compile_prompts
    return compile_prompts(domain=req.domain, router=ctx.router)


@app.get("/api/dspy/prompts", tags=["DSPy"])
def api_dspy_get_prompts(
    domain: str = Query("all", description="Domain name or all"),
    caller: Caller = Depends(require_role("viewer", "owner")),
):
    """Retrieves compiled prompt configurations and quantitative evaluation metrics."""
    from ..tools.dspy_optimizer import get_compiled_prompts
    return get_compiled_prompts(domain=domain)


# -- RSI Approval Gate (Pillar 9) ---------------------------------------------

@app.post("/api/rsi/propose", tags=["RSI"])
def api_rsi_propose(
    req: RsiProposeRequest,
    caller: Caller = Depends(require_role("owner")),
):
    """Drafts an improvement proposal in the staging sandbox, requiring human sign-off."""
    from ..tools.rsi import propose_improvement
    return propose_improvement(
        target_component=req.target_component,
        title=req.title,
        rationale=req.rationale,
        code_diff=req.code_diff,
    )


@app.get("/api/rsi/proposals", tags=["RSI"])
def api_rsi_list_proposals(
    status_filter: Optional[str] = Query(None, alias="status"),
    caller: Caller = Depends(require_role("viewer", "owner")),
):
    """Lists self-improvement proposals in staging."""
    from ..tools.rsi import list_proposals
    return list_proposals(status=status_filter)


@app.post("/api/rsi/decide", tags=["RSI"])
def api_rsi_decide(
    req: RsiDecideRequest,
    caller: Caller = Depends(require_role("owner")),
):
    """Cryptographic human approval gate to approve or reject a proposed improvement."""
    from ..tools.rsi import decide_proposal
    res = decide_proposal(
        proposal_id=req.proposal_id,
        decision=req.decision,
        auth_token=req.auth_token,
        rejection_reason=req.rejection_reason,
    )
    if res.get("status") == "denied":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=res.get("error"))
    return res


# -- Web Dashboard (P8 static index) -----------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["Web"])
def serve_dashboard():
    """Serves the single-page static web dashboard."""
    index_file = Path(__file__).parent.parent / "web" / "index.html"
    if index_file.is_file():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Scientist OS API is active. Web dashboard will appear once web/index.html is created.</h2>")
