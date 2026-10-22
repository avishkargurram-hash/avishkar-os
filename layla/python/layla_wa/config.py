from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


@dataclass
class Config:
    owner_name: str = "Avishkar"
    aliases: List[str] = field(default_factory=lambda: ["avishkar", "avi"])
    knowledge: str = ""
    style: str = ""
    reply_ttl_s: int = 600
    per_conv_per_hour: int = 6
    per_group_per_hour: int = 3
    global_per_hour: int = 60
    unknown_per_conv_per_hour: int = 3     # strangers get fewer replies than friends ever did
    unknown_global_per_hour: int = 15
    fast: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ
        base = e.get("WA_DIR", ".")
        owner = e.get("OWNER_NAME", "Avishkar")
        aliases = [a.strip().lower() for a in e.get("OWNER_ALIASES", f"{owner},Avi").split(",") if a.strip()]
        return cls(
            owner_name=owner, aliases=aliases,
            knowledge=_read(os.path.join(base, "knowledge.md")),
            style=_read(os.path.join(base, "style.md")),
            fast=e.get("WA_FAST", "0") == "1",
        )
