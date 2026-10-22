"""Settings from environment (systemd EnvironmentFile on the server, the
gitignored scientist/.secrets/*.env locally). Secrets are read here and only
here; nothing else touches os.environ for credentials.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Optional, Tuple


def load_env_file(path: os.PathLike | str, *, override: bool = False) -> None:
    """Minimal KEY=VALUE loader for local dev (server uses systemd)."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if override or k not in os.environ:
            os.environ[k] = v


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclasses.dataclass(frozen=True)
class Settings:
    database_url: str
    object_dir: str
    api_tokens: Tuple[Tuple[str, str, str], ...]   # (name, token, role)
    local_llm_url: Optional[str]                    # OpenAI-compatible base, e.g. http://127.0.0.1:8081/v1
    local_llm_model: str
    embed_url: Optional[str]                        # llama.cpp embeddings base, e.g. http://127.0.0.1:8082/v1
    embed_model: str
    gemini_api_key: Optional[str]
    openrouter_api_key: Optional[str]
    daily_premium_usd: float                        # global cap across all missions per UTC day
    daily_premium_calls: int
    sandbox_cmd: Optional[str]                      # e.g. "sudo -n /usr/local/bin/sci-sandbox-run"
    sandbox_jobs_dir: str
    contact_email: str                              # polite-pool identifier for Crossref/OpenAlex
    worker_lease_s: int
    supervisor_interval_s: float
    layla_gateway_url: Optional[str]
    layla_gateway_token: Optional[str]
    layla_agent_name: str
    notify_quiet_start_h: int                       # IST hours [start, end) when notifications are held
    notify_quiet_end_h: int
    offline: bool                                   # tests/demo: never touch the network

    @classmethod
    def from_env(cls) -> "Settings":
        toks = []
        for item in os.environ.get("SCI_API_TOKENS", "").split(","):
            parts = item.strip().split(":")
            if len(parts) == 3 and all(parts):
                toks.append((parts[0], parts[1], parts[2]))
        return cls(
            database_url=os.environ.get("SCI_DATABASE_URL", "postgresql://sci@127.0.0.1:5433/scientist"),
            object_dir=os.environ.get("SCI_OBJECT_DIR", str(Path.home() / ".scientist" / "objects")),
            api_tokens=tuple(toks),
            local_llm_url=os.environ.get("SCI_LOCAL_LLM_URL") or None,
            local_llm_model=os.environ.get("SCI_LOCAL_LLM_MODEL", "local-triage"),
            embed_url=os.environ.get("SCI_EMBED_URL") or None,
            embed_model=os.environ.get("SCI_EMBED_MODEL", "local-embed"),
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            daily_premium_usd=_f("SCI_DAILY_PREMIUM_USD", 2.0),
            daily_premium_calls=_i("SCI_DAILY_PREMIUM_CALLS", 120),
            sandbox_cmd=os.environ.get("SCI_SANDBOX_CMD") or None,
            sandbox_jobs_dir=os.environ.get("SCI_SANDBOX_JOBS_DIR", "/opt/scientist/sandbox-jobs"),
            contact_email=os.environ.get("SCI_CONTACT_EMAIL", "research@tryvanta.in"),
            worker_lease_s=_i("SCI_LEASE_S", 300),
            supervisor_interval_s=_f("SCI_SUPERVISOR_INTERVAL_S", 5.0),
            layla_gateway_url=os.environ.get("SCI_LAYLA_GATEWAY_URL") or None,
            layla_gateway_token=os.environ.get("SCI_LAYLA_GATEWAY_TOKEN") or None,
            layla_agent_name=os.environ.get("SCI_LAYLA_AGENT", "megha"),
            notify_quiet_start_h=_i("SCI_QUIET_START_H", 5),
            notify_quiet_end_h=_i("SCI_QUIET_END_H", 14),
            offline=os.environ.get("SCI_OFFLINE", "0") == "1",
        )

    def replace(self, **kw) -> "Settings":
        return dataclasses.replace(self, **kw)
