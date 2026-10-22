"""Authentication and RBAC dependencies for Scientist OS API (P7).

Enforces Bearer token authentication against Settings.api_tokens,
RBAC roles ('owner', 'viewer'), and in-memory token-bucket rate limiting.
"""

from __future__ import annotations

from collections import deque
import dataclasses
from threading import Lock
import time
from typing import Optional

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..runtime import Runtime

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclasses.dataclass(frozen=True)
class Caller:
    name: str
    token: str
    role: str


class TokenBucketRateLimiter:
    """Sliding-window token rate limiter (default: 60 requests/minute per token)."""

    def __init__(self, max_requests: int = 60, window_s: float = 60.0):
        self.max_requests = max_requests
        self.window_s = window_s
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._requests.setdefault(key, deque())
            cutoff = now - self.window_s
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                return False
            q.append(now)
            return True


rate_limiter = TokenBucketRateLimiter(max_requests=60, window_s=60.0)


def get_runtime_ctx() -> Runtime:
    """Dependency placeholder; overridden or populated by app.state.runtime."""
    from ..runtime import build_runtime
    # Cached per-process runtime singleton
    if not hasattr(get_runtime_ctx, "_instance"):
        get_runtime_ctx._instance = build_runtime()
    return get_runtime_ctx._instance


def require_role(*roles: str):
    """FastAPI dependency factory enforcing RBAC roles.
    
    Accepts Bearer token in 'Authorization: Bearer <token>' header,
    or via '?token=<token>' query parameter (essential for browser EventSource).
    'owner' role possesses superuser privilege over all actions including 'viewer'.
    """

    def dependency(
        auth: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
        token_query: Optional[str] = Query(None, alias="token"),
        ctx: Runtime = Depends(get_runtime_ctx),
    ) -> Caller:
        token = ""
        if auth and auth.credentials:
            token = auth.credentials.strip()
        elif token_query:
            token = token_query.strip()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token (provide in Authorization header or ?token= query)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Look up token in Settings.api_tokens: tuple of (name, token, role)
        configured_tokens = ctx.settings.api_tokens
        caller: Optional[Caller] = None

        for name, t_val, r_val in configured_tokens:
            if t_val == token:
                caller = Caller(name=name, token=token, role=r_val)
                break

        # Fallback if no tokens are configured at all in settings (dev/offline mode)
        if caller is None and not configured_tokens and ctx.settings.offline:
            caller = Caller(name="dev", token=token, role="owner")

        if caller is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Apply rate limiting
        if not rate_limiter.check(token):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded (60 requests/minute limit)",
            )

        # Enforce role hierarchy: 'owner' can access all endpoints
        if roles:
            allowed = caller.role in roles or (caller.role == "owner" and "viewer" in roles)
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"forbidden: requires role in {roles}, got {caller.role}",
                )

        return caller

    return dependency
