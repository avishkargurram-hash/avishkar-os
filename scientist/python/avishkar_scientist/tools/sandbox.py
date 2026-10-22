"""Experiment sandbox (spec sections 19, 35).

Model-generated code is NEVER executed on the host. The pipeline is:

1. `validate(code)` -- static AST whitelist. Rejected code is recorded as
   REJECTED_STATIC and never runs.
2. `Sandbox.run(code, seed, timeout)` writes a job dir (prelude + code) and
   calls the configured `sandbox_cmd`, which on the server is
   `sudo -n /usr/local/bin/sci-sandbox-run <jobdir> <timeout>` -- a root-
   owned script that runs `docker run --network none --read-only
   --memory 512m --cpus 1 --pids-limit 64 --user 65534 --cap-drop ALL`.
3. With no sandbox configured, the result is SANDBOX_UNAVAILABLE. There is
   no "run it locally instead" fallback anywhere in this module.

The program reports its result by printing one line `RESULT_JSON: {...}`.
`eval_criterion` evaluates the experiment's support criterion (e.g.
`result["p_value"] < 0.05 and result["effect"] > 0`) with a tiny safe
expression evaluator -- not Python eval.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

MAX_CODE = 20_000
ALLOWED_IMPORTS = frozenset({
    "math", "cmath", "statistics", "random", "json", "itertools", "functools", "collections", "fractions",
    "decimal", "heapq", "bisect", "numpy", "scipy", "sympy", "statsmodels",
})
FORBIDDEN_NAMES = frozenset({
    "exec", "eval", "compile", "open", "__import__", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint", "memoryview", "help", "exit", "quit", "__builtins__", "__loader__",
    "__spec__", "dir", "type", "object",
})
FORBIDDEN_MODULE_ROOTS = frozenset({
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "ctypes", "multiprocessing",
    "threading", "signal", "pickle", "marshal", "builtins", "io", "urllib", "http", "requests", "httpx",
})
# numpy / scipy attributes that touch the filesystem or spawn things
FORBIDDEN_ATTRS = frozenset({
    "load", "loadtxt", "genfromtxt", "fromfile", "tofile", "save", "savez", "savetxt", "memmap",
    "system", "popen", "ctypeslib", "lib", "f2py", "testing", "distutils", "show_config", "DataSource",
})

PRELUDE = '''import random as _r
_SEED = {seed}
_r.seed(_SEED)
try:
    import numpy as _np
    _np.random.seed(_SEED)
except Exception:
    pass
'''


@dataclasses.dataclass
class Validation:
    ok: bool
    errors: list


def validate(code: str) -> Validation:
    errors = []
    if not code or not code.strip():
        return Validation(False, ["empty program"])
    if len(code) > MAX_CODE:
        return Validation(False, [f"program too long ({len(code)} > {MAX_CODE} chars)"])
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return Validation(False, [f"syntax error: {exc.msg} (line {exc.lineno})"])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    errors.append(f"import of '{a.name}' not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_IMPORTS:
                errors.append(f"import from '{node.module}' not allowed")
            for a in node.names:
                if a.name == "*":
                    errors.append("star import not allowed")
                if a.name in FORBIDDEN_ATTRS or a.name in FORBIDDEN_NAMES:
                    errors.append(f"import of '{a.name}' not allowed")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or node.id in FORBIDDEN_MODULE_ROOTS:
                errors.append(f"use of '{node.id}' not allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in FORBIDDEN_ATTRS:
                errors.append(f"attribute '{node.attr}' not allowed")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            errors.append("global/nonlocal not allowed")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            errors.append("async code not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value and len(node.value) < 64:
            if any(d in node.value for d in ("__class__", "__subclasses__", "__globals__", "__builtins__", "__import__")):
                errors.append("dunder string not allowed")
    if "RESULT_JSON" not in code:
        errors.append("program must print a line starting with RESULT_JSON:")
    return Validation(not errors, sorted(set(errors)))


@dataclasses.dataclass
class RunResult:
    status: str                 # COMPLETED | FAILED | SANDBOX_UNAVAILABLE | REJECTED_STATIC | TIMEOUT
    exit_code: Optional[int]
    duration_s: float
    stdout: str
    stderr_tail: str
    result: Optional[dict]
    sandbox: dict


def parse_result(stdout: str) -> Optional[dict]:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("RESULT_JSON:"):
            try:
                v = json.loads(line[len("RESULT_JSON:"):].strip())
            except json.JSONDecodeError:
                return None
            return v if isinstance(v, dict) else {"value": v}
    return None


class Sandbox:
    """`cmd` is a shell-split command prefix that receives `<jobdir> <timeout>`.
    None -> every run returns SANDBOX_UNAVAILABLE."""

    def __init__(self, cmd: Optional[str], jobs_dir: str):
        self.cmd = shlex.split(cmd) if cmd else None
        self.jobs_dir = Path(jobs_dir)

    @property
    def available(self) -> bool:
        return self.cmd is not None

    def run(self, code: str, *, seed: int = 0, timeout_s: int = 60) -> RunResult:
        v = validate(code)
        if not v.ok:
            return RunResult("REJECTED_STATIC", None, 0.0, "", "; ".join(v.errors), None, {"validated": False})
        if self.cmd is None:
            return RunResult("SANDBOX_UNAVAILABLE", None, 0.0, "", "no sandbox configured (SCI_SANDBOX_CMD unset)",
                             None, {"validated": True})
        timeout_s = max(5, min(int(timeout_s), 300))
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        job = self.jobs_dir / f"job-{uuid.uuid4().hex}"
        job.mkdir(mode=0o755)
        try:
            (job / "main.py").write_text(PRELUDE.format(seed=int(seed)) + "\n" + code, encoding="utf-8")
            os.chmod(job / "main.py", 0o644)
            t0 = time.monotonic()
            try:
                p = subprocess.run(self.cmd + [str(job), str(timeout_s)], capture_output=True, text=True,
                                   timeout=timeout_s + 30)
            except subprocess.TimeoutExpired:
                return RunResult("TIMEOUT", None, time.monotonic() - t0, "", "sandbox wrapper timed out", None,
                                 {"validated": True, "timeout_s": timeout_s})
            dur = time.monotonic() - t0
            out = p.stdout[-200_000:]
            res = parse_result(out)
            if p.returncode == 124:
                status = "TIMEOUT"
            elif p.returncode == 0 and res is not None:
                status = "COMPLETED"
            else:
                status = "FAILED"
            return RunResult(status, p.returncode, round(dur, 3), out, (p.stderr or "")[-2000:], res,
                             {"validated": True, "timeout_s": timeout_s, "seed": seed, "runner": os.path.basename(self.cmd[-1])})
        finally:
            shutil.rmtree(job, ignore_errors=True)


# -- support criterion -------------------------------------------------------
_CMP = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}
_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b}


def eval_criterion(expr: str, result: dict) -> Optional[bool]:
    """Evaluate e.g. `result["p"] < 0.05 and abs(result["d"]) > 0.2`.
    Supports: and/or/not, comparisons, + - * /, numbers, strings, True/False,
    `result[...]` subscripts and abs(). Anything else -> None (undecidable)."""
    if not expr or result is None:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(n) -> Any:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return not ev(n.operand)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                if type(op) not in _CMP or not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, str, bool)):
            return n.value
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "result":
            key = ev(n.slice)
            return result[key]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "abs" and len(n.args) == 1:
            return abs(ev(n.args[0]))
        raise ValueError("unsupported expression")

    try:
        return bool(ev(tree))
    except Exception:  # noqa: BLE001 -- missing key / type error -> undecidable
        return None


def make_test_sandbox_cmd() -> str:
    """For the test-suite only (fixed, human-written test programs): a
    subprocess runner with `python -I` in a temp dir. Never used in
    production config; tests construct it explicitly."""
    script = Path(tempfile.gettempdir()) / "sci_test_sandbox_runner.py"
    script.write_text(
        "import subprocess,sys\n"
        "job,t=sys.argv[1],int(sys.argv[2])\n"
        "try:\n"
        "  p=subprocess.run([sys.executable,'-I',job+'/main.py'],capture_output=True,text=True,timeout=t,cwd=job)\n"
        "  sys.stdout.write(p.stdout);sys.stderr.write(p.stderr);sys.exit(p.returncode)\n"
        "except subprocess.TimeoutExpired:\n"
        "  sys.exit(124)\n", encoding="utf-8")
    import sys
    return f'"{sys.executable}" "{script}"' if os.name == "nt" else f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
