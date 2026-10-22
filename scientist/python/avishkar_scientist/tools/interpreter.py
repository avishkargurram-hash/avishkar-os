"""Self-Healing Terminal & Code Interpreter Loop (Pillar 8: Open Interpreter Loop).

Executes commands and code snippets with autonomous error detection,
friction diagnosis, and single-step repair loops (up to 3 bounded retries)
before returning verified execution outputs.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Execution working directory for commands
DEFAULT_CWD = "/opt/scientist/src" if os.path.isdir("/opt/scientist/src") else os.getcwd()
PYTHON_BIN = "/opt/scientist/venv/bin/python" if os.path.isfile("/opt/scientist/venv/bin/python") else sys.executable


def _run_single_command(command: str, language: str = "bash", timeout_s: float = 30.0, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Executes a single command or Python script block and captures stdio."""
    t0 = time.perf_counter()
    work_dir = cwd or DEFAULT_CWD

    if language.lower() in ("python", "py"):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as tf:
            tf.write(command)
            script_path = tf.name
        cmd_args = [PYTHON_BIN, script_path]
    else:
        cmd_args = ["/bin/bash", "-c", command]

    try:
        proc = subprocess.run(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            cwd=work_dir,
            errors="replace",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "timeout": False,
            "latency_ms": round(elapsed_ms, 2),
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout_s}s",
            "timeout": True,
            "latency_ms": round(elapsed_ms, 2),
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Execution error: {type(exc).__name__}: {exc}",
            "timeout": False,
            "latency_ms": round(elapsed_ms, 2),
        }
    finally:
        if language.lower() in ("python", "py") and os.path.exists(script_path):
            try:
                os.remove(script_path)
            except Exception:
                pass


def _diagnose_and_repair(command: str, stderr: str, language: str = "bash") -> tuple[Optional[str], Optional[str]]:
    """Analyzes stderr output and synthesizes an automated repair action."""
    # 1. Missing Python Package: ModuleNotFoundError: No module named 'xyz'
    mod_match = re.search(r"ModuleNotFoundError:\s+No module named\s+['\"]([^'\"]+)['\"]", stderr)
    if mod_match:
        pkg = mod_match.group(1).split(".")[0]
        # Common mapping adjustments
        if pkg == "yaml": pkg = "pyyaml"
        elif pkg == "cv2": pkg = "opencv-python"
        elif pkg == "PIL": pkg = "pillow"
        install_cmd = f"{PYTHON_BIN} -m pip install {pkg}"
        try:
            res = subprocess.run(["/bin/bash", "-c", install_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            if res.returncode == 0:
                return command, f"Auto-installed missing dependency '{pkg}'"
        except Exception:
            pass

    # 2. Directory does not exist error (FileNotFoundError in Python or directory missing)
    dir_match = re.search(r"FileNotFoundError:.*No such file or directory:\s+['\"]([^'\"]+)['\"]", stderr)
    if dir_match:
        missing_path = dir_match.group(1)
        parent_dir = os.path.dirname(missing_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
                return command, f"Created missing parent directory '{parent_dir}'"
            except Exception as e:
                logger.warning(f"Failed to create directory {parent_dir}: {e}")

    # 3. Command not found in shell: bash: foo: command not found
    cmd_match = re.search(r"(?:command not found|([^\s:]+):\s+command not found)", stderr)
    if cmd_match:
        missing_bin = cmd_match.group(1) or "unknown"
        return None, f"Command '{missing_bin}' is not installed on this system."

    return None, None


def self_healing_command_loop(
    command: str,
    language: str = "bash",
    max_retries: int = 3,
    timeout_s: float = 30.0,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Executes a command or code snippet, repairing runtime failures in a tight loop."""
    current_command = command
    history = []
    t_start = time.perf_counter()

    for attempt in range(1, max_retries + 1):
        res = _run_single_command(current_command, language=language, timeout_s=timeout_s, cwd=cwd)
        step_record = {
            "attempt": attempt,
            "command": current_command,
            "returncode": res["returncode"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "latency_ms": res["latency_ms"],
        }
        history.append(step_record)

        if res["returncode"] == 0:
            total_elapsed_ms = (time.perf_counter() - t_start) * 1000
            output_text = res["stdout"] or "(command completed successfully with no stdout)"
            return {
                "status": "success",
                "attempts": attempt,
                "command": current_command,
                "output": output_text,
                "history": history,
                "latency_ms": round(total_elapsed_ms, 2),
            }

        # Failure occurred -- attempt diagnosis and repair
        repaired_cmd, diagnosis = _diagnose_and_repair(current_command, res["stderr"], language=language)
        if repaired_cmd and attempt < max_retries:
            step_record["repair_action"] = diagnosis
            current_command = repaired_cmd
            logger.info("Self-healing repair applied on attempt %d: %s", attempt, diagnosis)
            time.sleep(0.5)
            continue
        else:
            step_record["repair_action"] = diagnosis or "No automated patch available for this error."
            break

    total_elapsed_ms = (time.perf_counter() - t_start) * 1000
    final_err = history[-1]["stderr"] or history[-1]["stdout"] or "Unknown execution failure"
    return {
        "status": "error",
        "attempts": len(history),
        "command": command,
        "error": final_err,
        "history": history,
        "latency_ms": round(total_elapsed_ms, 2),
    }
