"""Naina's code-change flow: propose a patch -> owner approves in Telegram -> branch + PR on GitHub.

Safety (owner decision 2026-10-13: Naina may read everything, WRITE needs a Telegram tap):
  * works only on the secrets-excluded snapshots in SNAP (never the owner's PC, never main)
  * a proposal is hash-bound: the approved sha256 must equal the sha256 of what is applied
  * approvals expire after 24 h; a restart re-arms pending ones silently
  * output is always a NEW branch `naina/<id>-<slug>` + a pull request -- the owner merges on GitHub
  * secret-looking paths / content are refused outright
"""
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

SNAP = os.environ.get("L365_SNAPSHOTS", "/opt/layla365/snapshots")
STATE = os.environ.get("L365_PATCHES", "/opt/layla365/state/patches")
OWNER_ACCT = os.environ.get("GITHUB_OWNER", "avishkargurram-hash")
TTL = 24 * 3600
MAX_FILES, MAX_BYTES = 30, 200_000

_DENY_PATH = re.compile(r"(^|/)(\.env(\..*)?|.*\.(key|pem|p12|pfx|jks|keystore|age)|id_(rsa|ed25519).*|"
                        r"ssh-keys|credentials|\.git|\.ssh|.*secret.*|.*token.*)(/|$)", re.I)
_ALLOW_PATH = re.compile(r"\.(example|template|sample)$|\.env\.example$", re.I)
_SECRET = re.compile(r"(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|gsk_[A-Za-z0-9]{30,}|csk-[A-Za-z0-9]{30,}|"
                     r"sk-[A-Za-z0-9_-]{30,}|AIza[0-9A-Za-z_-]{35}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,}|"
                     r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\d{8,10}:AA[A-Za-z0-9_-]{30,}|rzp_(live|test)_[A-Za-z0-9]{10,})")


def repos():
    try:
        return sorted(d for d in os.listdir(SNAP) if d != "incoming" and os.path.isdir(os.path.join(SNAP, d, ".git")))
    except FileNotFoundError:
        return []


def _safe_rel(path):
    p = str(path).replace("\\", "/").lstrip("/")
    if not p or ".." in p.split("/") or (_DENY_PATH.search(p) and not _ALLOW_PATH.search(p)):
        return None
    return p


def read_file(repo, path, limit=20000):
    """Read-only helper for Naina: a snapshot file (never a denied path)."""
    p = _safe_rel(path)
    if repo not in repos() or p is None:
        return None
    fp = os.path.join(SNAP, repo, p)
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def digest(repo, files):
    h = hashlib.sha256()
    h.update(repo.encode() + b"\0")
    for p in sorted(files):
        h.update(p.encode() + b"\0" + files[p].encode() + b"\0")
    return h.hexdigest()


def _path(pid):
    return os.path.join(STATE, pid + ".json")


def _save(rec):
    os.makedirs(STATE, exist_ok=True)
    tmp = _path(rec["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, _path(rec["id"]))


def _load_all():
    out = []
    try:
        for n in os.listdir(STATE):
            if n.endswith(".json"):
                try:
                    with open(os.path.join(STATE, n), encoding="utf-8") as f:
                        out.append(json.load(f))
                except Exception:  # noqa: BLE001
                    pass
    except FileNotFoundError:
        pass
    return out


def propose(agent, repo, title, files, rationale=""):
    """Validate + store a patch and ask the owner. Returns (ok, id_or_error)."""
    if repo not in repos():
        return False, f"unknown repo '{repo}'"
    if not isinstance(files, dict) or not files or len(files) > MAX_FILES:
        return False, f"files must be 1..{MAX_FILES} entries"
    clean = {}
    for p, c in files.items():
        rel = _safe_rel(p)
        if rel is None:
            return False, f"path not allowed: {p}"
        if not isinstance(c, str) or len(c.encode()) > MAX_BYTES:
            return False, f"content too large/invalid: {p}"
        if _SECRET.search(c):
            return False, f"secret-looking content refused: {p}"
        clean[rel] = c
    pid = "pt" + str(int(time.time() * 1000))[-9:]
    h = digest(repo, clean)
    rec = {"id": pid, "agent": agent, "repo": repo, "title": title[:100], "rationale": rationale[:800],
           "files": clean, "sha": h, "status": "awaiting", "created": time.time(), "pr": None}
    _save(rec)
    _ask(rec)
    return True, pid


def _ask(rec, silent=False):
    from . import telegram
    stat = "\n".join(f"• {p} ({len(c)} chars)" for p, c in rec["files"].items())
    detail = (f"{rec['agent']} wants to change repo {rec['repo']}:\n{rec['title']}\n\n{rec['rationale']}\n\n{stat}\n\n"
              f"hash {rec['sha'][:12]}  (a new branch + pull request is made; nothing is merged)")
    rec["aid"] = telegram.request_approval(f"Code change: {rec['repo']} - {rec['title']}", detail,
                              lambda ok, pid=rec["id"]: _decided(pid, ok), ttl=TTL,
                              aid=rec.get("aid"), send=not silent)
    _save(rec)


def _decided(pid, ok):
    rec = next((r for r in _load_all() if r["id"] == pid), None)
    if not rec or rec["status"] != "awaiting":
        return
    rec["status"] = "approved" if ok else "denied"
    _save(rec)


def _git(repo_dir, *args, auth=False):
    cmd = ["git"]
    if auth:
        import base64
        tok = os.environ.get("GITHUB_TOKEN", "")
        b = base64.b64encode(f"x-access-token:{tok}".encode()).decode()
        cmd += ["-c", f"http.extraheader=Authorization: Basic {b}"]
    r = subprocess.run(cmd + list(args), cwd=repo_dir, capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).replace(os.environ.get("GITHUB_TOKEN", "~~"), "***")[-300:])
    return r.stdout


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30] or "change"


def _apply(rec):
    if digest(rec["repo"], rec["files"]) != rec["sha"]:
        raise RuntimeError("hash mismatch: stored patch changed after approval request")
    d = os.path.join(SNAP, rec["repo"])
    branch = f"naina/{rec['id']}-{_slug(rec['title'])}"
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "-b", branch)
    try:
        for p, c in rec["files"].items():
            fp = os.path.join(d, p)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8", newline="\n") as f:
                f.write(c)
        _git(d, "add", "-A")
        _git(d, "-c", "user.name=Layla365 Naina", "-c", "user.email=naina@agents.tryvanta.in",
             "commit", "-q", "-m", f"{rec['title']}\n\nProposed by {rec['agent']} (approved via Telegram, hash {rec['sha'][:12]})")
        _git(d, "push", "-q", "origin", branch, auth=True)
    finally:
        try:
            _git(d, "checkout", "-q", "main")
        except Exception:  # noqa: BLE001
            pass
    body = {"title": rec["title"], "head": branch, "base": "main",
            "body": f"{rec['rationale']}\n\nProposed by **{rec['agent']}** (Layla 365). Approved by owner via Telegram, patch hash `{rec['sha'][:12]}`."}
    req = urllib.request.Request(f"https://api.github.com/repos/{OWNER_ACCT}/{rec['repo']}/pulls",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", ""),
                                          "User-Agent": "l365/1.0", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("html_url")


def tick():
    """Called each runner tick: re-arm approvals lost on restart, expire old, apply approved. Never raises."""
    from . import telegram
    now = time.time()
    live = {a for a, _ in telegram.pending_approvals()}
    for rec in _load_all():
        try:
            if rec["status"] == "awaiting":
                if now - rec["created"] > TTL:
                    rec["status"] = "expired"; _save(rec)
                elif rec.get("aid") not in live:   # process restarted: re-arm without re-sending the card
                    _ask(rec, silent=not telegram.quiet_now())
            elif rec["status"] == "approved":
                rec["status"] = "applying"; _save(rec)   # claim first so a crash never double-applies
                try:
                    rec["pr"] = _apply(rec)
                    rec["status"] = "pr_opened"
                    telegram.notify(f"✅ Pull request opened for {rec['repo']}: {rec['title']}\n{rec['pr']}")
                except Exception as e:  # noqa: BLE001
                    rec["status"] = "failed"; rec["error"] = str(e)[:300]
                    telegram.notify(f"⚠️ Patch {rec['id']} approved but failed: {rec['error']}")
                _save(rec)
            if rec["status"] in ("denied", "expired", "pr_opened", "failed") and now - rec["created"] > 7 * 86400:
                os.remove(_path(rec["id"]))
        except Exception as e:  # noqa: BLE001
            print(f"[github_flow] {rec.get('id')}: {type(e).__name__}", flush=True)
