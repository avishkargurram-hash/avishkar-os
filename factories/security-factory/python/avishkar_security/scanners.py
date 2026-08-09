"""Secret scanning. See CONTRACT.md SS1.

Regex-based detection of common committed-secret shapes -- real and
useful for what pattern matching can actually catch, with no claim to
catch every possible secret (see README.md Limitations).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Sequence, Tuple

from .types import RepositoryFinding, SecretMatch

_PATTERNS: Dict[str, re.Pattern] = {
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "anthropic_api_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "generic_api_key_assignment": re.compile(
        r"""api[_-]?key\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]""", re.IGNORECASE
    ),
    "private_key_header": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic_bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{20,}"),
}


def _preview(text: str) -> str:
    if len(text) <= 10:
        return "*" * len(text)
    return f"{text[:6]}...{text[-4:]}"


def scan_for_secrets(text: str) -> Tuple[SecretMatch, ...]:
    matches = []
    for name, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append(SecretMatch(pattern_name=name, start=m.start(), end=m.end(), preview=_preview(m.group())))
    return tuple(sorted(matches, key=lambda sm: sm.start))


def redact_secrets(text: str) -> str:
    result = text
    # Replace from the end backwards so earlier spans' offsets stay valid.
    for match in sorted(scan_for_secrets(text), key=lambda sm: sm.start, reverse=True):
        result = result[: match.start] + f"[REDACTED:{match.pattern_name}]" + result[match.end :]
    return result


def scan_repository_for_secrets(
    root_dir: Path,
    *,
    extensions: Sequence[str] = (".py", ".md", ".json", ".toml", ".txt"),
    exclude_dirs: Sequence[str] = (".git", "__pycache__", "node_modules", ".venv"),
) -> Tuple[RepositoryFinding, ...]:
    root_dir = Path(root_dir)
    findings = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for filename in filenames:
            if not filename.endswith(tuple(extensions)):
                continue
            path = Path(dirpath) / filename
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for match in scan_for_secrets(text):
                findings.append(RepositoryFinding(path=path, match=match))
    return tuple(findings)
