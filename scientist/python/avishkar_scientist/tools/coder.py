"""Autonomous software-engineer loop (Pillar 6).

A real model-backed coding loop: it copies the target directory into an
isolated scratch workspace, asks the Scientist model router (Gemini / OpenRouter
via the `coder_patch` purpose) for full-file rewrites, applies them in the copy,
runs the test command there, and feeds any failure back for another attempt --
up to `max_iterations`. The live source tree is never mutated: the result
carries the unified diff and whether the tests passed, so applying it is a
separate, deliberate step. With no model available it fails honestly instead
of pretending to have fixed anything.
"""

from __future__ import annotations

import datetime
import difflib
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = "/opt/scientist/openhands/workspace"
DEFAULT_TEST_DIR = "/opt/scientist/src"
MAX_FILE_BYTES = 40_000
MAX_CONTEXT_FILES = 40

SYSTEM = (
    "You are an autonomous software engineer. You are given a task, the current contents of the "
    "relevant files, and (after the first attempt) the failing test output. Return ONLY JSON: "
    '{"files":[{"path":"relative/path.py","content":"<full new file content>"}],'
    '"rationale":"one sentence","done":false}. '
    "Rewrite each file you change in full (never a diff, never a fragment). Touch the fewest files "
    "needed. Paths are relative to the workspace root. Do not invent files that were not provided "
    "unless the task is to create them. If you believe the task is already satisfied, return an "
    'empty "files" list with "done": true.'
)


def _get_pg_conn():
    conn_url = os.environ.get("SCI_DATABASE_URL")
    if not conn_url:
        return None
    try:
        try:
            import psycopg
            return psycopg.connect(conn_url)
        except ImportError:
            import psycopg2
            return psycopg2.connect(conn_url)
    except Exception as exc:
        logger.error(f"Postgres connection failed: {exc}")
        return None


def _snapshot_files(root: Path) -> Dict[str, str]:
    """Read small text files under root (code only), path -> content."""
    out: Dict[str, str] = {}
    exts = {".py", ".js", ".ts", ".json", ".txt", ".md", ".sh", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".sql"}
    for p in sorted(root.rglob("*")):
        if len(out) >= MAX_CONTEXT_FILES:
            break
        if not p.is_file() or p.suffix not in exts:
            continue
        if any(part in {"__pycache__", ".git", "node_modules", ".venv", "venv"} for part in p.parts):
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            out[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return out


def _run_tests(test_command: str, work_dir: Path, timeout_s: int = 120) -> Dict[str, Any]:
    try:
        proc = subprocess.run(["/bin/bash", "-c", test_command], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, cwd=str(work_dir), timeout=timeout_s)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"test command timed out after {timeout_s}s"}
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def _diff(before: Dict[str, str], after: Path) -> str:
    chunks: List[str] = []
    for rel, old in before.items():
        new_path = after / rel
        new = new_path.read_text(encoding="utf-8", errors="replace") if new_path.is_file() else ""
        if new != old:
            chunks.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                               fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    # files the model created that were not in the snapshot
    for p in sorted(after.rglob("*")):
        if p.is_file() and p.suffix in {".py", ".js", ".ts", ".sql", ".sh"}:
            rel = str(p.relative_to(after))
            if rel not in before and "__pycache__" not in rel:
                new = p.read_text(encoding="utf-8", errors="replace")
                chunks.extend(difflib.unified_diff([], new.splitlines(True), fromfile="/dev/null", tofile=f"b/{rel}"))
    return "".join(chunks)[:20000]


def _record(task_id, description, work_dir, test_command, status, iteration, log, error):
    conn = _get_pg_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO coding_tasks (id, description, target_dir, test_command, status, max_iterations,
                                             iterations, execution_log, error, completed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, iterations=EXCLUDED.iterations,
                       execution_log=EXCLUDED.execution_log, error=EXCLUDED.error, completed_at=NOW()""",
                (task_id, description, str(work_dir), test_command, status, iteration, iteration, log, error))
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"coding_tasks record failed: {exc}")


def run_coder_task(
    description: str,
    target_dir: str = DEFAULT_TEST_DIR,
    test_command: Optional[str] = None,
    max_iterations: int = 3,
    router: Any = None,
) -> Dict[str, Any]:
    """Real coding loop. Operates on a scratch copy of target_dir; never mutates the live tree."""
    task_id = f"coder-{uuid.uuid4().hex[:10]}"
    t0 = time.perf_counter()
    logs: List[str] = [f"Task {task_id}: {description}"]

    if router is None:
        return {"status": "error", "task_id": task_id, "error": "no model router available; coder cannot run"}
    if not getattr(router, "premium_available", False) and not getattr(router, "local_available", False):
        return {"status": "error", "task_id": task_id, "error": "no model available (local or premium)"}

    src = Path(target_dir)
    if not src.is_dir():
        return {"status": "error", "task_id": task_id, "error": f"target_dir {target_dir} not found"}

    ws_root = Path(DEFAULT_WORKSPACE)
    ws_root.mkdir(parents=True, exist_ok=True)
    work = ws_root / task_id
    try:
        shutil.copytree(src, work, ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules", "venv", ".venv"))
    except Exception as exc:
        return {"status": "error", "task_id": task_id, "error": f"could not stage workspace: {exc}"}

    before = _snapshot_files(work)
    logs.append(f"Staged {len(before)} files into scratch workspace {work}")

    from ..models.router import ModelUnavailable
    status, error, iteration, tests = "FAILED", None, 0, None
    failure_ctx = ""
    try:
        for attempt in range(1, max_iterations + 1):
            iteration = attempt
            ctx_files = _snapshot_files(work)
            file_blob = "\n\n".join(f"### FILE: {p}\n```\n{c}\n```" for p, c in list(ctx_files.items())[:MAX_CONTEXT_FILES])
            user = (f"TASK: {description}\n\nFILES:\n{file_blob}\n\n"
                    + (f"PREVIOUS ATTEMPT FAILED. Test output:\n{failure_ctx}\n\nFix it." if failure_ctx
                       else "Make the change."))
            try:
                data, res = router.complete_json("coder_patch", SYSTEM, user, max_tokens=4000, temperature=0.0)
            except ModelUnavailable as exc:
                status, error = "FAILED", f"model unavailable on attempt {attempt}: {exc}"
                logs.append(error)
                break
            if not isinstance(data, dict):
                logs.append(f"Attempt {attempt}: model reply was not valid JSON ({res.provider}:{res.model})")
                failure_ctx = "Your previous reply was not valid JSON. Return only the specified JSON object."
                continue
            files = data.get("files") or []
            logs.append(f"Attempt {attempt}: model ({res.provider}:{res.model}) proposed {len(files)} file(s): "
                        f"{data.get('rationale', '')[:160]}")
            for f in files:
                rel, content = str(f.get("path", "")).lstrip("/"), f.get("content", "")
                if not rel or ".." in Path(rel).parts:
                    continue
                dest = work / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            if not test_command:
                status = "COMPLETED" if (files or data.get("done")) else "FAILED"
                error = None if status == "COMPLETED" else "model produced no changes and no test command to verify"
                logs.append("No test command supplied; stopping after first edit (unverified).")
                break

            tests = _run_tests(test_command, work)
            if tests["returncode"] == 0:
                status, error = "COMPLETED", None
                logs.append(f"Attempt {attempt}: tests PASSED.")
                break
            failure_ctx = (tests["stdout"] + "\n" + tests["stderr"]).strip()[-3500:]
            logs.append(f"Attempt {attempt}: tests failed (rc={tests['returncode']}).")
        else:
            status = "FAILED"
            error = error or "tests did not pass within max_iterations"

        patch = _diff(before, work)
    finally:
        pass  # keep the workspace so the diff can be applied later; GC is a separate concern

    log_str = "\n".join(logs)
    _record(task_id, description, work, test_command, status, iteration, log_str, error)
    return {
        "status": status, "task_id": task_id, "description": description, "iterations": iteration,
        "tests_passed": bool(tests and tests["returncode"] == 0) if test_command else None,
        "diff": patch, "workspace": str(work), "log": log_str, "error": error,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def get_coder_task(task_id: str) -> Dict[str, Any]:
    """Retrieves coding task status and log history."""
    conn = _get_pg_conn()
    if not conn:
        return {"status": "error", "error": "Database unavailable"}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, created_at, description, target_dir, status, iterations, execution_log, error, completed_at
                FROM coding_tasks WHERE id = %s
            """, (task_id,))
            row = cur.fetchone()
        conn.close()
        if not row:
            return {"status": "error", "error": f"Task {task_id} not found"}
        return {
            "status": "success",
            "task": {
                "id": row[0], "created_at": row[1].isoformat() if row[1] else None,
                "description": row[2], "target_dir": row[3], "status": row[4], "iterations": row[5],
                "log": row[6], "error": row[7], "completed_at": row[8].isoformat() if row[8] else None,
            },
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
