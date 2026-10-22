"""Wires every layer into one `Runtime` context object (spec section 47).

The API process, the worker processes, the CLI and the test-suite all
build one of these and pass it to `agents.handlers`, `core.cycle` and
`demo.run_demo*` -- nothing in this codebase reaches `os.environ` except
`config.Settings.from_env`.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .config import Settings
from .models.router import TierRouter
from .orchestration.engine import PgWorkflowEngine
from .storage.db import Database
from .storage.objects import ObjectStore
from .tools import Registry, build_registry
from .tools.sandbox import Sandbox


@dataclasses.dataclass
class Runtime:
    settings: Settings
    db: Database
    objects: ObjectStore
    engine: PgWorkflowEngine
    registry: Registry
    router: TierRouter
    sandbox: Sandbox


def build_runtime(settings: Optional[Settings] = None, *, router: Optional[TierRouter] = None) -> Runtime:
    settings = settings or Settings.from_env()
    db = Database(settings.database_url)
    objects = ObjectStore(settings.object_dir)
    engine = PgWorkflowEngine(db)
    sandbox = Sandbox(settings.sandbox_cmd, settings.sandbox_jobs_dir)
    router = router or TierRouter(db, settings)
    registry = build_registry(settings, db, objects, embedder=router.embedder, sandbox=sandbox)
    return Runtime(settings, db, objects, engine, registry, router, sandbox)
