"""genesis_catalog -- generates Layla ToolContracts for every Genesis service
under a services root, so the whole ~235-service empire can be registered on a
UniversalToolRegistry through one GenesisServiceAdapter.

It never imports a service (which could pull heavy deps or side effects). It
statically detects each service's entrypoint style by reading the source:

    module-level `def run(` / `def execute(`   -> function style
    a `class ...Service` with a callable method  -> class style
    neither                                       -> UNMAPPED (reported, skipped)

and assigns a per-domain risk/permission profile so downstream Layla gating
(risk.classify_risk / ApprovalManager / authorization) has something to key on.
The risk profile is intentionally conservative: blackbox and machine-control
domains are tagged high-risk by default; a domain the map doesn't know falls
back to the most restrictive ("write", "external") rather than "read".
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, Tuple

from ..types import ToolContract

# domain -> (permission tags, auth_requirement). Permission tags are Layla's
# gating vocabulary; "high_risk"/"security"/"dangerous" force an approval gate.
DOMAIN_RISK: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "search":        (("read",),                     "token"),
    "intelligence":  (("read",),                     "token"),
    "shared":        (("read",),                     "none"),
    "remote_gpu":    (("read", "compute"),           "token"),
    "google":        (("write", "external"),         "oauth"),
    "communication": (("write", "external"),         "token"),
    "meta":          (("write", "external"),         "token"),
    "business":      (("write", "external"),         "oauth"),
    "integration":   (("write", "external"),         "oauth"),
    "iot":           (("write", "iot"),              "token"),
    "action":        (("write", "machine_control"),  "none"),
    "automation":    (("write", "machine_control"),  "token"),
    "security":      (("high_risk", "security"),     "owner"),
    "blackbox":      (("high_risk", "security", "dangerous"), "owner"),
}
_FALLBACK_RISK: Tuple[Tuple[str, ...], str] = (("write", "external"), "token")

_RUN_RE = re.compile(r"^def\s+run\s*\(", re.M)
_EXEC_RE = re.compile(r"^def\s+execute\s*\(", re.M)
_CLASS_RE = re.compile(r"^class\s+(\w+)\s*[\(:]", re.M)
_METHOD_RE = re.compile(r"^\s{4}def\s+(\w+)\s*\(", re.M)
_SKIP_METHODS = {"__init__", "_validate_auth", "_validate", "_headers", "_auth"}


def _detect_entrypoint(source: str) -> Dict[str, Any] | None:
    """Return the protocol_config entrypoint keys, or None if unmapped."""
    if _RUN_RE.search(source):
        return {"callable": "run", "takes_params": True}
    if _EXEC_RE.search(source):
        return {"callable": "execute", "takes_params": True}
    classes = _CLASS_RE.findall(source)
    svc_classes = [c for c in classes if c.endswith("Service") and "Error" not in c]
    target = svc_classes[0] if svc_classes else (classes[0] if classes else None)
    if target is None:
        return None
    # pick a callable method: prefer run/execute, else first public method.
    methods = [m for m in _METHOD_RE.findall(source) if m not in _SKIP_METHODS]
    method = None
    for pref in ("run", "execute"):
        if pref in methods:
            method = pref
            break
    if method is None:
        method = next((m for m in methods if not m.startswith("_")), None)
    if method is None:
        return None
    # class methods generally take no params dict (they read env); but if the
    # chosen method looks like run/execute we pass params.
    return {"class": target, "method": method, "takes_params": method in ("run", "execute")}


def build_genesis_contracts(services_root: str) -> Tuple[List[ToolContract], Dict[str, Any]]:
    contracts: List[ToolContract] = []
    report: Dict[str, Any] = {
        "total_files": 0, "mapped": 0, "unmapped": 0,
        "by_domain": {}, "by_style": {"function": 0, "class": 0},
        "by_risk": {}, "unmapped_files": [],
    }
    for dirpath, _dirs, files in os.walk(services_root):
        for fn in files:
            if not fn.endswith(".py") or fn == "__init__.py":
                continue
            report["total_files"] += 1
            path = os.path.join(dirpath, fn)
            domain = os.path.basename(dirpath)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    source = fh.read()
            except OSError:
                report["unmapped"] += 1
                report["unmapped_files"].append(path)
                continue
            entry = _detect_entrypoint(source)
            report["by_domain"].setdefault(domain, 0)
            report["by_domain"][domain] += 1
            if entry is None:
                report["unmapped"] += 1
                report["unmapped_files"].append(os.path.relpath(path, services_root))
                continue

            perms, auth = DOMAIN_RISK.get(domain, _FALLBACK_RISK)
            risk_tag = perms[0]
            report["by_risk"].setdefault(risk_tag, 0)
            report["by_risk"][risk_tag] += 1
            report["by_style"]["class" if "class" in entry else "function"] += 1
            report["mapped"] += 1

            stem = os.path.splitext(fn)[0]
            identity = f"{domain}.{stem}"
            cfg: Dict[str, Any] = {"module_path": path}
            cfg.update(entry)
            contracts.append(
                ToolContract(
                    identity=identity,
                    description=f"Genesis {domain} service: {stem.replace('_', ' ')}.",
                    protocol="genesis",
                    input_schema={"type": "object"},
                    permissions=perms,
                    auth_requirement=auth,
                    protocol_config=cfg,
                )
            )
    return contracts, report
