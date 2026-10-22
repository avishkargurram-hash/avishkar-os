"""Command-line interface (CLI) for Scientist OS (P8).

Entry point for `sci` console script.
Subcommands: demo, worker, supervisor, migrate, mission, api.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .domain import ALL_QUEUES, Depth
from .observability import setup_logging
from .runtime import Runtime, build_runtime


def cmd_demo(args: argparse.Namespace) -> int:
    """Runs a simulated zero-LLM demo mission to completion in-process."""
    setup_logging(level=args.log_level, json_format=args.json_logs)
    ctx = build_runtime()
    print("Initiating Scientist OS simulated demonstration mission (SCI-DEMO-001)...")
    from . import demo
    m = demo.run_demo_sync(ctx, poll_s=args.poll_s, idle_limit=args.idle_limit)
    print(f"\nMission Result: {m['id']}")
    print(f"Status:       {m['status']}")
    print(f"Confidence:   {m.get('confidence', 0.0):.2f}")
    print(f"Stop Reason:  {m.get('stop_reason') or 'COMPLETED'}")

    v = ctx.db.one("SELECT label, statement FROM verdicts WHERE mission_id=%s ORDER BY id DESC LIMIT 1", (m["id"],))
    if v:
        print(f"Verdict:      {v['label']}")
        print(f"Statement:    {v['statement']}")

    r = ctx.db.one("SELECT id, format, sha256 FROM reports WHERE mission_id=%s ORDER BY id DESC LIMIT 1", (m["id"],))
    if r:
        print(f"Report:       Generated ({r['format']}, sha256: {r['sha256'][:16]}...)")

    return 0 if m["status"] == "COMPLETED" else 1


def cmd_worker(args: argparse.Namespace) -> int:
    """Runs an asynchronous queue task worker process."""
    setup_logging(level=args.log_level, json_format=args.json_logs)
    ctx = build_runtime()
    queues = [q.strip() for q in args.queues.split(",") if q.strip()] if args.queues else list(ALL_QUEUES)
    name = args.name or f"worker-{ctx.settings.worker_lease_s}"
    print(f"Starting Scientist OS Worker '{name}' on queues: {queues} (lease={ctx.settings.worker_lease_s}s)...")
    from .orchestration.worker import run_worker
    run_worker(
        ctx,
        name=name,
        queues=queues,
        poll_s=args.poll_s,
        lease_s=ctx.settings.worker_lease_s,
        stop_after=args.stop_after,
    )
    return 0


def cmd_supervisor(args: argparse.Namespace) -> int:
    """Runs the background supervisor daemon for budget tracking and approvals."""
    setup_logging(level=args.log_level, json_format=args.json_logs)
    ctx = build_runtime()
    interval = args.interval or ctx.settings.supervisor_interval_s
    print(f"Starting Scientist OS Supervisor (interval={interval}s)...")
    from .orchestration.worker import run_supervisor
    run_supervisor(ctx, interval_s=interval)
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Applies schema migrations against target database."""
    ctx = build_runtime()
    from .storage.migrate import migrate
    applied = migrate(ctx.db)
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("Database schema is up to date (no migrations applied).")
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    """Starts the FastAPI HTTP and SSE streaming server."""
    import uvicorn
    print(f"Serving Scientist OS API on {args.host}:{args.port}...")
    uvicorn.run("avishkar_scientist.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_mission(args: argparse.Namespace) -> int:
    """Manages research missions."""
    ctx = build_runtime()
    from . import mission as mission_mod

    action = args.mission_action
    if action == "create":
        mid = mission_mod.create_mission(
            ctx.db,
            ctx.engine,
            args.question,
            depth=args.depth,
            demo=args.demo,
            user_id=args.user,
            priority=args.priority,
            source="cli",
        )
        print(f"Created mission: {mid}")
        return 0

    if action == "status":
        m = mission_mod.get_mission(ctx.db, args.id)
        if not m:
            print(f"Error: Mission {args.id} not found", file=sys.stderr)
            return 1
        print(json.dumps({
            "id": m["id"],
            "status": m["status"],
            "phase": m["current_phase"],
            "iteration": m["iteration"],
            "confidence": m["confidence"],
            "rqs": m["rqs"],
            "stop_reason": m["stop_reason"],
            "paused": m["paused"],
        }, indent=2, default=str))
        return 0

    if action == "verdict":
        v = ctx.db.one("SELECT * FROM verdicts WHERE mission_id=%s ORDER BY id DESC LIMIT 1", (args.id,))
        if not v:
            print(f"No verdict rendered yet for mission {args.id}", file=sys.stderr)
            return 1
        print(f"=== Verdict for {args.id} ===")
        print(f"Label:      {v['label']}")
        print(f"Confidence: {v['confidence']:.2f} ({v['evidence_strength']})")
        print(f"Statement:  {v['statement']}")
        if v.get("narrative"):
            print(f"\nNarrative:\n{v['narrative']}")
        return 0

    if action == "report":
        r = ctx.db.one("SELECT body FROM reports WHERE mission_id=%s ORDER BY id DESC LIMIT 1", (args.id,))
        if not r:
            print(f"No report generated yet for mission {args.id}", file=sys.stderr)
            return 1
        print(r["body"])
        return 0

    if action == "pause":
        res = mission_mod.pause(ctx.db, args.id, actor=args.actor)
        print(f"Mission {args.id} paused: {res['status']}")
        return 0

    if action == "resume":
        res = mission_mod.resume(ctx.db, args.id, actor=args.actor)
        print(f"Mission {args.id} resumed: {res['status']}")
        return 0

    if action == "cancel":
        res = mission_mod.cancel(ctx.db, ctx.engine, args.id, actor=args.actor, reason=args.reason)
        print(f"Mission {args.id} cancelled: {res['status']}")
        return 0

    print("Unknown mission action. Use 'sci mission --help' for available actions.", file=sys.stderr)
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sci",
        description="Avishkar Scientist OS CLI -- Autonomous Scientific Research Subsystem",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log verbosity")
    parser.add_argument("--json-logs", action="store_true", help="Format logs as structured JSON")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # sci demo
    p_demo = subparsers.add_parser("demo", help="Run in-process simulated demo mission")
    p_demo.add_argument("--poll-s", type=float, default=0.02, help="Worker poll interval seconds")
    p_demo.add_argument("--idle-limit", type=int, default=100, help="Max idle loops before completion")
    p_demo.set_defaults(func=cmd_demo)

    # sci worker
    p_worker = subparsers.add_parser("worker", help="Start background task execution worker")
    p_worker.add_argument("--name", default=None, help="Worker instance name")
    p_worker.add_argument("--queues", default=None, help="Comma-separated queue list")
    p_worker.add_argument("--poll-s", type=float, default=1.0, help="Poll interval in seconds")
    p_worker.add_argument("--stop-after", type=int, default=None, help="Exit after N tasks")
    p_worker.set_defaults(func=cmd_worker)

    # sci supervisor
    p_sup = subparsers.add_parser("supervisor", help="Start mission supervisor daemon")
    p_sup.add_argument("--interval", type=float, default=None, help="Reconciliation interval seconds")
    p_sup.set_defaults(func=cmd_supervisor)

    # sci migrate
    p_mig = subparsers.add_parser("migrate", help="Run database migrations")
    p_mig.set_defaults(func=cmd_migrate)

    # sci api
    p_api = subparsers.add_parser("api", help="Launch FastAPI HTTP & SSE service")
    p_api.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_api.add_argument("--port", type=int, default=8095, help="Bind port")
    p_api.add_argument("--reload", action="store_true", help="Auto-reload on code change")
    p_api.set_defaults(func=cmd_api)

    # sci mission ...
    p_mis = subparsers.add_parser("mission", help="Mission lifecycle operations")
    mis_subs = p_mis.add_subparsers(dest="mission_action", required=True)

    # sci mission create "<q>"
    p_mc = mis_subs.add_parser("create", help="Create and enqueue a new mission")
    p_mc.add_argument("question", help="Scientific question or hypothesis to investigate")
    p_mc.add_argument("--depth", default="STANDARD", choices=[x.value for x in Depth], help="Research depth tier")
    p_mc.add_argument("--demo", action="store_true", help="Simulated demo mission")
    p_mc.add_argument("--user", default="owner", help="Owner identity")
    p_mc.add_argument("--priority", type=int, default=5, help="Priority 1-10")

    # sci mission status <id>
    p_ms = mis_subs.add_parser("status", help="Get current status of a mission")
    p_ms.add_argument("id", help="Mission ID (e.g. SCI-000001)")

    # sci mission verdict <id>
    p_mv = mis_subs.add_parser("verdict", help="Get verdict for a mission")
    p_mv.add_argument("id", help="Mission ID")

    # sci mission report <id>
    p_mr = mis_subs.add_parser("report", help="Print Markdown report for a mission")
    p_mr.add_argument("id", help="Mission ID")

    # sci mission pause <id>
    p_mp = mis_subs.add_parser("pause", help="Pause a running mission")
    p_mp.add_argument("id", help="Mission ID")
    p_mp.add_argument("--actor", default="owner", help="Actor identity")

    # sci mission resume <id>
    p_mres = mis_subs.add_parser("resume", help="Resume a paused mission")
    p_mres.add_argument("id", help="Mission ID")
    p_mres.add_argument("--actor", default="owner", help="Actor identity")

    # sci mission cancel <id>
    p_mcan = mis_subs.add_parser("cancel", help="Cancel an active mission")
    p_mcan.add_argument("id", help="Mission ID")
    p_mcan.add_argument("--actor", default="owner", help="Actor identity")
    p_mcan.add_argument("--reason", default="cancelled by user", help="Cancellation rationale")

    p_mis.set_defaults(func=cmd_mission)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
