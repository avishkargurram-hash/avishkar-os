"""Executors registered with the framework. Real ones are added per agent later;
only harmless self-test kinds exist today."""
from .agent import executor


@executor("test.noop")
def _noop(agent, params):
    return {"ok": True, "echo": params}


@executor("test.capped")
def _capped(agent, params):
    return {"ok": True}


@executor("layla.request")
def _layla_request(agent, params):
    """One request to Layla's gateway. She enforces the allowlist; a refusal comes back as ok=False."""
    from . import gateway
    code, out = gateway.request(agent.name, params.get("action", ""), params.get("args") or {})
    if code == 200:
        return {"ok": bool(out.get("ok")), "output": out.get("output"), "error": None if out.get("ok") else out.get("output")}
    return {"ok": False, "output": None, "error": f"gateway {code}: {out.get('error')}"}
