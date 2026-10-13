"""The fixed security checklist. See CONTRACT.md SS2.

Drawn directly from STANDARDS.md SS6 and this framework's own README
responsibilities -- not invented independently of what the platform
already committed to checking.
"""

from __future__ import annotations

from .types import ChecklistItem

SECURITY_CHECKLIST = (
    ChecklistItem(
        id="no-committed-secrets",
        question="Does this module avoid committing any secret, API key, or credential?",
        why="STANDARDS.md SS6: no secrets committed, ever.",
    ),
    ChecklistItem(
        id="input-validation",
        question="Is every external-facing input validated before use?",
        why="Unvalidated input is the root cause of most injection-class vulnerabilities.",
    ),
    ChecklistItem(
        id="output-filtering",
        question="Is output filtered/sanitized before being returned or logged?",
        why="Prevents leaking secrets or internal state through error messages or responses.",
    ),
    ChecklistItem(
        id="rate-limiting",
        question="Is rate limiting configured, or explicitly not applicable?",
        why="Prevents this module from being used to overwhelm an external system.",
    ),
    ChecklistItem(
        id="pii-handling",
        question="Is PII handling documented (what's collected, how it's stored/purged)?",
        why="Undocumented PII handling is a compliance and trust liability.",
    ),
    ChecklistItem(
        id="approval-gate-for-high-risk-actions",
        question="Does an irreversible or high-risk action require human approval?",
        why="agent-factory's ApprovalGate exists for exactly this; skipping it for a risky action is a choice that needs to be visible, not silent.",
    ),
    ChecklistItem(
        id="timeout-configured",
        question="Is a timeout configured for every external call this module makes?",
        why="An unbounded call can hang a caller indefinitely.",
    ),
    ChecklistItem(
        id="retry-does-not-amplify",
        question="Does the retry policy avoid amplifying load against a struggling external system?",
        why="Naive retries can turn a transient failure into a self-inflicted denial of service.",
    ),
    ChecklistItem(
        id="least-privilege-permissions",
        question="Are declared permissions the minimum needed, not broader 'just in case'?",
        why="Matches mcp-factory's ToolContract.permissions field's own intent.",
    ),
    ChecklistItem(
        id="audit-logging",
        question="Is there an audit trail for actions this module takes?",
        why="Without logging, a real incident can't be reconstructed after the fact.",
    ),
)
