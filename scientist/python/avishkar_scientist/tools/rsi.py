"""Recursive Self-Improvement approval gate (Pillar 9).

Layla may only *propose* a code change. A proposal is staged, syntax-checked
against a throwaway copy, and (if the agents Telegram bot is configured) sent
to the owner as an Allow/Deny card. Approval is enforced by a secret that lives
ONLY in the server environment (RSI_AUTH_SECRET) and is compared in constant
time; if that secret is unset the gate stays closed and every decision is
denied, so the feature is inert until the owner deliberately arms it. On a real
APPROVE the unified diff is applied to the live tree after a per-file backup,
every changed .py is recompiled, and any failure triggers an automatic rollback
from that backup. Nothing here reports success it did not perform.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import py_compile
import re
import shutil
import subprocess
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RSI_STAGING_DIR = "/opt/scientist/rsi_staging"
RSI_BACKUP_DIR = "/opt/scientist/backups/rsi"
LIVE_ROOT = os.environ.get("RSI_LIVE_ROOT", "/opt/scientist/src/scientist/python")
_DIFF_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


def _get_pg_conn():
    conn_url = os.environ.get("SCI_DATABASE_URL")
    if not conn_url:
        logger.error("SCI_DATABASE_URL not set")
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


def _changed_paths(diff: str) -> List[str]:
    return [m.group(1).strip() for m in _DIFF_PATH_RE.finditer(diff or "")]


def _syntax_check(diff: str) -> Dict[str, Any]:
    """Apply the diff to a scratch copy of LIVE_ROOT and py_compile changed files."""
    paths = _changed_paths(diff)
    if not paths:
        return {"ok": False, "detail": "diff names no target files (need '+++ b/<path>' headers)"}
    scratch = Path(RSI_STAGING_DIR) / f"check-{uuid.uuid4().hex[:8]}"
    try:
        shutil.copytree(LIVE_ROOT, scratch, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        pf = scratch / "candidate.diff"
        pf.write_text(diff, encoding="utf-8")
        proc = subprocess.run(["patch", "-p1", "--forward", "-i", str(pf)], cwd=str(scratch),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        if proc.returncode != 0:
            return {"ok": False, "detail": f"patch did not apply cleanly: {proc.stdout[-400:]} {proc.stderr[-400:]}"}
        for rel in paths:
            if rel.endswith(".py"):
                try:
                    py_compile.compile(str(scratch / rel), doraise=True)
                except py_compile.PyCompileError as exc:
                    return {"ok": False, "detail": f"{rel} fails to compile: {str(exc)[:300]}"}
        return {"ok": True, "detail": f"patch applies and {len(paths)} file(s) compile", "paths": paths}
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _tg_send_card(proposal_id: str, title: str, target: str, detail: str) -> bool:
    token = os.environ.get("TELEGRAM_AGENTS_TOKEN", "")
    owner = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")
    if not token or not owner:
        return False
    text = (f"\U0001F9EC <b>RSI self-change proposed</b>\nLayla wants to modify <b>{target}</b>\n"
            f"{title}\n\n{detail[:800]}\n\n<i>id {proposal_id}</i>")
    buttons = [[{"text": "✅ Allow", "callback_data": f"rsi:{proposal_id}:1"},
                {"text": "❌ Deny", "callback_data": f"rsi:{proposal_id}:0"}]]
    data = urllib.parse.urlencode({
        "chat_id": owner, "text": text, "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": buttons})}).encode()
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            return bool(json.loads(r.read()).get("ok"))
    except Exception as exc:
        logger.warning(f"RSI telegram card failed: {exc}")
        return False


def propose_improvement(target_component: str, title: str, rationale: str, code_diff: str,
                        run_sandbox_tests: bool = True) -> Dict[str, Any]:
    """Stage a proposal, syntax-check it, persist it PENDING_HUMAN, and send a Telegram approval card."""
    proposal_id = f"rsi-{uuid.uuid4().hex[:10]}"
    t0 = time.perf_counter()
    os.makedirs(RSI_STAGING_DIR, exist_ok=True)

    check = _syntax_check(code_diff) if (run_sandbox_tests and code_diff) else {"ok": None, "detail": "skipped"}
    sandbox_log = f"[{'PASS' if check['ok'] else 'FAIL' if check['ok'] is False else 'SKIP'}] {check['detail']}"
    (Path(RSI_STAGING_DIR) / f"{proposal_id}.diff").write_text(code_diff or "", encoding="utf-8")

    conn = _get_pg_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO rsi_proposals (id, target_component, title, rationale, code_diff,
                                   sandbox_test_output, status)
                               VALUES (%s,%s,%s,%s,%s,%s,'PENDING_HUMAN')""",
                            (proposal_id, target_component, title, rationale, code_diff, sandbox_log))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"Could not persist proposal: {exc}")

    card_sent = _tg_send_card(proposal_id, title, target_component, sandbox_log)
    return {
        "status": "success", "proposal_id": proposal_id, "title": title,
        "target_component": target_component, "proposal_status": "PENDING_HUMAN",
        "syntax_check": sandbox_log, "approval_card_sent": card_sent,
        "requires_action": ("Owner must tap Allow on Telegram." if card_sent
                            else "Owner approval required (Telegram bot not configured; approve server-side)."),
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def list_proposals(status: Optional[str] = None) -> Dict[str, Any]:
    conn = _get_pg_conn()
    if not conn:
        return {"status": "error", "error": "Database unavailable"}
    try:
        with conn.cursor() as cur:
            if status:
                cur.execute("""SELECT id, created_at, target_component, title, rationale, status, decided_at, decision_by
                               FROM rsi_proposals WHERE status=%s ORDER BY created_at DESC""", (status,))
            else:
                cur.execute("""SELECT id, created_at, target_component, title, rationale, status, decided_at, decision_by
                               FROM rsi_proposals ORDER BY created_at DESC""")
            rows = cur.fetchall()
        conn.close()
        proposals = [{"id": r[0], "created_at": r[1].isoformat() if r[1] else None, "target_component": r[2],
                      "title": r[3], "rationale": r[4], "status": r[5],
                      "decided_at": r[6].isoformat() if r[6] else None, "decision_by": r[7]} for r in rows]
        return {"status": "success", "count": len(proposals), "proposals": proposals}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _apply_diff_live(proposal_id: str, diff: str) -> Dict[str, Any]:
    """Backup changed files, apply the diff to LIVE_ROOT, recompile; roll back on any failure."""
    paths = _changed_paths(diff)
    if not paths:
        return {"ok": False, "detail": "diff names no files"}
    backup = Path(RSI_BACKUP_DIR) / f"{proposal_id}_{int(time.time())}"
    backup.mkdir(parents=True, exist_ok=True)
    live = Path(LIVE_ROOT)
    # snapshot every target file (record which existed, so rollback can delete new ones)
    existed = {}
    for rel in paths:
        src = live / rel
        existed[rel] = src.is_file()
        if src.is_file():
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    pf = backup / "applied.diff"
    pf.write_text(diff, encoding="utf-8")

    def rollback():
        for rel in paths:
            src = live / rel
            if existed[rel]:
                shutil.copy2(backup / rel, src)
            elif src.is_file():
                src.unlink()

    proc = subprocess.run(["patch", "-p1", "--forward", "-i", str(pf)], cwd=str(live),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    if proc.returncode != 0:
        rollback()
        return {"ok": False, "detail": f"patch failed, rolled back: {proc.stdout[-300:]} {proc.stderr[-300:]}",
                "backup": str(backup)}
    for rel in paths:
        if rel.endswith(".py"):
            try:
                py_compile.compile(str(live / rel), doraise=True)
            except py_compile.PyCompileError as exc:
                rollback()
                return {"ok": False, "detail": f"{rel} failed to compile after apply, rolled back: {str(exc)[:200]}",
                        "backup": str(backup)}
    return {"ok": True, "detail": f"applied {len(paths)} file(s)", "backup": str(backup), "paths": paths}


def decide_proposal(proposal_id: str, decision: str, auth_token: str,
                    rejection_reason: Optional[str] = None) -> Dict[str, Any]:
    """Approve (apply + rollback-on-failure) or reject. Secret is env-only; unset => always denied."""
    expected = os.environ.get("RSI_AUTH_SECRET", "")
    if not expected:
        return {"status": "denied", "authorized": False,
                "error": "RSI gate is disarmed: RSI_AUTH_SECRET is not set on the server."}
    if not hmac.compare_digest(str(auth_token or ""), expected):
        return {"status": "denied", "authorized": False, "error": "invalid human approval token"}

    dec = (decision or "").upper().strip()
    if dec not in ("APPROVE", "REJECT"):
        return {"status": "error", "error": "decision must be APPROVE or REJECT"}

    conn = _get_pg_conn()
    if not conn:
        return {"status": "error", "error": "Database unavailable"}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT target_component, title, code_diff, status FROM rsi_proposals WHERE id=%s",
                        (proposal_id,))
            row = cur.fetchone()
        if not row:
            conn.close()
            return {"status": "error", "error": f"Proposal {proposal_id} not found"}
        if row[3] != "PENDING_HUMAN":
            conn.close()
            return {"status": "error", "error": f"Proposal {proposal_id} is already {row[3]}"}
        title, diff = row[1], row[2]

        if dec == "REJECT":
            with conn.cursor() as cur:
                cur.execute("""UPDATE rsi_proposals SET status='REJECTED', decided_at=NOW(),
                               decision_by='Avishkar', rejection_reason=%s WHERE id=%s""",
                            (rejection_reason or "Rejected by owner", proposal_id))
            conn.commit(); conn.close()
            return {"status": "success", "proposal_id": proposal_id, "decision": "REJECTED",
                    "message": f"Proposal '{title}' rejected and discarded."}

        result = _apply_diff_live(proposal_id, diff or "")
        new_status = "APPLIED" if result["ok"] else "APPLY_FAILED"
        with conn.cursor() as cur:
            cur.execute("""UPDATE rsi_proposals SET status=%s, decided_at=NOW(), decision_by='Avishkar',
                           applied_backup_path=%s, rejection_reason=%s WHERE id=%s""",
                        (new_status, result.get("backup"), None if result["ok"] else result["detail"], proposal_id))
        conn.commit(); conn.close()
        return {"status": "success" if result["ok"] else "error", "proposal_id": proposal_id,
                "decision": new_status, "detail": result["detail"], "backup_snapshot": result.get("backup"),
                "message": (f"Proposal '{title}' applied to the live tree." if result["ok"]
                            else f"Approval accepted but the change could not be applied: {result['detail']}")}
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}
