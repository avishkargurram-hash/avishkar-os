import copy
import os
import pathlib

import yaml

ROOT = pathlib.Path(os.environ.get("L365_ROOT", "/opt/layla365/app"))
PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DB = os.environ.get("PG_DB", "layla365")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    with open(ROOT / "agents.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    defaults = raw.get("defaults", {})
    test_actions = raw.get("test_actions", {})
    agents = {}
    for name, spec in raw["agents"].items():
        merged = _merge(defaults, spec)
        merged["name"] = name
        merged["actions"] = {**test_actions, "layla.request": "A1", **spec.get("actions", {})}
        merged["caps"] = {**{"test.capped": {"per_day": 2}}, **spec.get("caps", {})}
        agents[name] = merged
    return {"agents": agents, "core_services": raw.get("core_services", [])}


def pg_password(role_name: str) -> str:
    return os.environ["PGPASS_" + role_name.upper()]
