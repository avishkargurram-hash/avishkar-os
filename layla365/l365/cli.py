"""Operator CLI:  python -m l365 <command>

  status                      agents, mode, enabled, today's usage, pending approvals
  run                         start the 24/7 runner
  enable|disable <agent>      kill switch
  mode <agent> shadow|live    shadow = record only, live = may execute
  approvals                   list pending approvals
  approve|reject <id>         decide an approval (runner executes approved ones)
  actions [agent] [n]         recent actions
"""
import sys

from . import config, db


def _core():
    return db.connect("core")


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "run":
        from .runtime import Runner
        Runner().run()
        return 0
    if cmd == "duty":
        # run one self-started duty NOW, synchronously (operator test): duty <agent> <duty_name>
        from . import duties
        from .agent import Agent
        cfg = config.load()["agents"]
        if not args or args[0] not in cfg:
            print("agents:", ", ".join(cfg)); return 2
        ds = {d.name: d for d in duties.DUTIES.get(args[0], [])}
        if len(args) < 2 or args[1] not in ds:
            print("duties for", args[0], ":", ", ".join(ds) or "(none)"); return 2
        ok, detail = duties.run_duty(Agent(args[0], cfg[args[0]]), ds[args[1]])
        print("ok" if ok else "FAILED", detail)
        return 0 if ok else 1
    c = _core()
    cur = c.cursor()
    if cmd == "status":
        cur.execute("SELECT s.agent, s.enabled, s.mode, "
                    "coalesce((SELECT sum(calls) FROM core.usage u WHERE u.agent=s.agent AND u.tier='local' AND u.day=(now() at time zone 'utc')::date),0), "
                    "coalesce((SELECT sum(calls) FROM core.usage u WHERE u.agent=s.agent AND u.tier='heavy' AND u.day=(now() at time zone 'utc')::date),0), "
                    "(SELECT count(*) FROM core.approvals p WHERE p.agent=s.agent AND p.status='pending') "
                    "FROM core.agent_state s ORDER BY s.agent")
        print(f"{'agent':8} {'enabled':8} {'mode':7} {'local':>6} {'heavy':>6} {'pending':>8}")
        for a, e, m, l, h, p in cur.fetchall():
            print(f"{a:8} {str(e):8} {m:7} {l:>6} {h:>6} {p:>8}")
        cur.execute("SELECT component, now()-ts FROM core.heartbeat WHERE component='runner'")
        for comp, age in cur.fetchall():
            print(f"\nrunner heartbeat age: {age}")
    elif cmd in ("enable", "disable"):
        cur.execute("UPDATE core.agent_state SET enabled=%s, updated_at=now() WHERE agent=%s",
                    (cmd == "enable", args[0]))
        print(cmd, args[0], "->", cur.rowcount, "row")
    elif cmd == "mode":
        if args[1] not in ("shadow", "live"):
            print("mode must be shadow|live")
            return 2
        cur.execute("UPDATE core.agent_state SET mode=%s, updated_at=now() WHERE agent=%s", (args[1], args[0]))
        print("mode", args[0], args[1], "->", cur.rowcount, "row")
    elif cmd == "approvals":
        cur.execute("SELECT id, ts, agent, kind, summary FROM core.approvals WHERE status='pending' ORDER BY id")
        for r in cur.fetchall():
            print(r)
    elif cmd in ("approve", "reject"):
        cur.execute("UPDATE core.approvals SET status=%s, decided_at=now(), decided_by='operator' "
                    "WHERE id=%s AND status='pending'",
                    ("approved" if cmd == "approve" else "rejected", int(args[0])))
        print(cmd, args[0], "->", cur.rowcount, "row")
    elif cmd == "actions":
        who = args[0] if args else None
        n = int(args[1]) if len(args) > 1 else 15
        if who:
            cur.execute("SELECT id, ts::timestamp(0), agent, kind, tier, status, reason FROM core.actions "
                        "WHERE agent=%s ORDER BY id DESC LIMIT %s", (who, n))
        else:
            cur.execute("SELECT id, ts::timestamp(0), agent, kind, tier, status, reason FROM core.actions "
                        "ORDER BY id DESC LIMIT %s", (n,))
        for r in cur.fetchall():
            print(r)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
