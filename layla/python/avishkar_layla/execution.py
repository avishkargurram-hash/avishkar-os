"""ExecutionTracker -- idempotency and side-effect safety for
externally consequential operations. See CONTRACT.md SS16, ADR-0022.

Persisted through the same LaylaMemoryPolicy every other Layla
component uses (kind="long_term", keys namespaced
execution:{idempotency_key}) -- one storage mechanism, not a second
one. Reused directly by DelegationEngine; not a parallel workflow
engine.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
import threading
import time
from typing import Any, Callable, Mapping, Optional

from .errors import IdempotencyConflictError
from .memory_policy import LaylaMemoryPolicy

_KIND = "long_term"

# --- Operation classification (Priority 17.2) -------------------------
# A distinct axis from risk.classify_risk: risk asks "how much harm can
# this cause" (approval-worthiness); this asks "does retrying this
# risk duplicating a real-world effect" (idempotency-worthiness). A
# LOW-risk action can still be a WRITE that must never be silently
# retried (e.g. "send a routine status email").

OP_READ = "READ"
OP_WRITE = "WRITE"
OP_HIGH_RISK = "HIGH_RISK"

_READ_PATTERN = re.compile(r"\b(search|inspect|retrieve|analyz\w*|review|summarize|look up|check)\b", re.IGNORECASE)
_WRITE_PATTERN = re.compile(
    r"\b(send (an? )?(email|message)|create (a |an )?(record|issue|github issue)|"
    r"modify (a |the )?record|deploy|purchase|schedule|delete|publish)\b",
    re.IGNORECASE,
)
_HIGH_RISK_OP_PATTERN = re.compile(
    r"\b(financial transaction|wire transfer|legal commitment|sign(ing)? (a |the )?contract|"
    r"irreversibl\w* delet\w*|external publication|security[- ]sensitive)\b",
    re.IGNORECASE,
)


def classify_operation(description: str) -> str:
    """READ | WRITE | HIGH_RISK. Fail-closed default: text matching
    neither a recognized READ nor WRITE/HIGH_RISK verb is classified
    WRITE, not READ -- an unrecognized action is treated as
    idempotency-sensitive until proven otherwise, never assumed safe
    to blindly retry. See README.md Limitations.
    """
    if _HIGH_RISK_OP_PATTERN.search(description):
        return OP_HIGH_RISK
    if _WRITE_PATTERN.search(description):
        return OP_WRITE
    if _READ_PATTERN.search(description) and not _WRITE_PATTERN.search(description):
        return OP_READ
    return OP_WRITE


# --- Execution lifecycle (Priority 17.2 SS5) --------------------------

EXEC_REQUESTED = "REQUESTED"
EXEC_AUTHORIZED = "AUTHORIZED"
EXEC_APPROVED = "APPROVED"
EXEC_EXECUTING = "EXECUTING"
EXEC_COMPLETED = "COMPLETED"
EXEC_REJECTED = "REJECTED"
EXEC_CANCELLED = "CANCELLED"
EXEC_FAILED = "FAILED"
EXEC_EXPIRED = "EXPIRED"
# Deliberately NOT in TERMINAL_EXECUTION_STATES: an UNKNOWN outcome
# (e.g. a timeout after a provider may have already accepted a write)
# requires an explicit resolve_unknown() call, never a silent retry.
EXEC_UNKNOWN = "UNKNOWN"

TERMINAL_EXECUTION_STATES = frozenset({EXEC_COMPLETED, EXEC_REJECTED, EXEC_CANCELLED, EXEC_FAILED, EXEC_EXPIRED})


def _iso(epoch_seconds: float) -> str:
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat()


@dataclasses.dataclass
class ExecutionRecord:
    idempotency_key: str
    operation_kind: str
    description: str
    status: str = EXEC_REQUESTED
    result: Optional[Mapping[str, Any]] = None
    error: Optional[str] = None
    attempts: int = 0
    created_at: str = ""
    updated_at: str = ""


class ExecutionTracker:
    def __init__(self, memory: LaylaMemoryPolicy, *, clock: Callable[[], float] = time.time) -> None:
        self._memory = memory
        self._clock = clock
        # Priority 17.4 (ADR-0024): a single, coarse-grained lock over
        # every mutating operation on this tracker instance. begin()'s
        # get-then-create is a real check-then-act race under real
        # concurrency (two threads both see "no record," both create
        # one) -- the exact thing idempotency exists to prevent.
        # Coarse rather than per-key: these are fast, local-memory-
        # backend calls (no network I/O), so a single lock is simple
        # and correct rather than needing per-key lock lifecycle
        # management; see CONTRACT.md SS18 and README.md's concurrency
        # model for why this is the deliberate tradeoff, not an
        # oversight. The lock is held only across the read+create/
        # read+modify step, never across the actual delegated work
        # (DelegationEngine calls the orchestrator between begin() and
        # the final transition(), entirely unlocked).
        # RLock, not Lock: resolve_unknown() holds the lock across its
        # own read-and-check, then calls transition() (which also takes
        # the lock) to perform the actual write -- a plain Lock would
        # deadlock on that re-entry from the same thread.
        self._lock = threading.RLock()

    def get(self, idempotency_key: str) -> Optional[ExecutionRecord]:
        record = self._memory.recall(_KIND, f"execution:{idempotency_key}")
        return ExecutionRecord(**record.value) if record is not None else None

    def begin(self, idempotency_key: str, operation_kind: str, description: str) -> ExecutionRecord:
        """Idempotent: if this key already has a record, returns the
        EXISTING record unchanged rather than resetting it -- the
        caller inspects `.status` to decide what to do (CONTRACT.md
        SS16). A brand-new key gets a fresh REQUESTED record, and that
        creation is atomic with respect to other begin() calls on the
        same tracker (Priority 17.4): only one concurrent caller ever
        observes "no existing record" for a given key.

        Raises IdempotencyConflictError if the same key was already
        used for a *different* operation (mismatched description) --
        a key-collision bug or an attempted reuse of one operation's
        idempotency key for another must never silently return the
        wrong cached result.

        The returned record also carries a `claimed_this_call`
        attribute (Priority 17.4; not a persisted dataclass field --
        never round-trips through get()/dataclasses.asdict) that is
        `True` only for the caller whose begin() actually created the
        record, and `False` for every other caller (concurrent or
        sequential) who found one already there. `DelegationEngine`
        uses this to distinguish "I own this key, proceed" from "this
        key is already claimed, refuse" -- both cases return a record
        with `status == EXEC_REQUESTED` and would be indistinguishable
        by status alone.
        """
        with self._lock:
            existing = self.get(idempotency_key)
            if existing is not None:
                if existing.description != description:
                    raise IdempotencyConflictError(
                        f"idempotency_key {idempotency_key!r} was already used for a different operation "
                        f"(original: {existing.description!r}, this call: {description!r})"
                    )
                existing.claimed_this_call = False
                return existing
            now = _iso(self._clock())
            record = ExecutionRecord(
                idempotency_key=idempotency_key, operation_kind=operation_kind, description=description,
                status=EXEC_REQUESTED, created_at=now, updated_at=now,
            )
            record.claimed_this_call = True
            self._save(record)
        return record

    def transition(
        self, idempotency_key: str, new_status: str, *,
        result: Optional[Mapping[str, Any]] = None, error: Optional[str] = None, increment_attempts: bool = False,
    ) -> ExecutionRecord:
        with self._lock:
            record = self.get(idempotency_key)
            if record is None:
                raise KeyError(f"no ExecutionRecord for idempotency_key {idempotency_key!r} -- call begin() first")
            record.status = new_status
            if result is not None:
                record.result = dict(result)
            if error is not None:
                record.error = error
            if increment_attempts:
                record.attempts += 1
            record.updated_at = _iso(self._clock())
            self._save(record)
            return record

    def resolve_unknown(self, idempotency_key: str, resolved_status: str, *, note: str = "") -> ExecutionRecord:
        """The explicit, human/caller-driven resolution path for an
        UNKNOWN outcome -- e.g. "I checked the provider's dashboard,
        the email was never sent" (resolved_status=EXEC_FAILED, safe to
        retry) or "it was sent" (resolved_status=EXEC_COMPLETED, never
        retry). Refuses to resolve anything other than an UNKNOWN
        record, so it can't be used to silently overwrite a real
        COMPLETED/FAILED outcome.
        """
        with self._lock:
            record = self.get(idempotency_key)
            if record is None:
                raise KeyError(f"no ExecutionRecord for idempotency_key {idempotency_key!r}")
            if record.status != EXEC_UNKNOWN:
                raise ValueError(
                    f"resolve_unknown() called on a record with status {record.status!r}, not UNKNOWN -- "
                    f"only an uncertain outcome needs manual resolution"
                )
            return self.transition(idempotency_key, resolved_status, error=note or record.error)

    def _save(self, record: ExecutionRecord) -> None:
        self._memory.remember(
            _KIND, f"execution:{record.idempotency_key}", dataclasses.asdict(record),
            provenance="execution-tracker", importance="high",
        )
