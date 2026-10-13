from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KNOWLEDGE = Path(__file__).with_name("knowledge.md")


@dataclass
class Config:
    owner_name: str = "Avishkar"
    business_name: str = "Tryvanta"
    knowledge: str = ""
    per_caller_per_hour: int = 30
    global_per_hour: int = 300

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ
        d = Path(e["BIZ_DIR"]) if e.get("BIZ_DIR") else DEFAULT_KNOWLEDGE.parent
        k = d / "knowledge.md"
        if not k.exists():
            k = DEFAULT_KNOWLEDGE
        return cls(owner_name=e.get("OWNER_NAME", "Avishkar"),
                   business_name=e.get("BIZ_NAME", "Tryvanta"),
                   knowledge=k.read_text(encoding="utf-8"))
