"""Real Home Assistant executor for EMBODIMENT_HOME_ASSISTANT. See
CONTRACT.md SS40.

STATUS: REAL CODE / ADAPTER READY. Genuine HTTP client against Home
Assistant's real REST API (`/api/states`, `/api/services/<domain>/<service>`,
`/api/config`) -- not a simulation. No live Home Assistant instance
exists in this environment, so live device/entity interaction is
untested here; instead, `test_home_assistant_executor.py` runs a real,
minimal, in-repo HTTP server implementing Home Assistant's actual REST
API request/response shape (the same "real local fixture" pattern
`test_smtp_email_transport.py` already established) -- a genuine HTTP
conversation, not a mock of `requests`.

Registered for `EMBODIMENT_HOME_ASSISTANT`, already in embodiment.py's
`_DEFAULT_HIGH_RISK_CAPABILITIES` -- every action always requires
approval before `EmbodimentController` even looks up this executor.
Directive D Part VII, verbatim: "the architecture must never permit
unrestricted autonomous physical actions" -- there is no path from a
model's output to a real service call that skips that gate.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

from ..errors import LaylaError
from .errors import UnknownActionError

_ACTIONS = ("list_states", "get_state", "call_service", "get_config")


class HomeAssistantNotConfiguredError(LaylaError):
    """No base_url/token configured, or Home Assistant rejected the
    configured token -- the documented ADAPTER READY boundary.
    """


class HomeAssistantExecutor:
    def __init__(
        self, *, base_url: Optional[str] = None, token_env: str = "HOME_ASSISTANT_TOKEN",
        base_url_env: str = "HOME_ASSISTANT_URL", timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url
        self._token_env = token_env
        self._base_url_env = base_url_env
        self._timeout_seconds = timeout_seconds

    def _resolve_base_url(self) -> str:
        base_url = self._base_url or os.environ.get(self._base_url_env)
        if not base_url:
            raise HomeAssistantNotConfiguredError(
                f"HomeAssistantExecutor requires a base_url or the {self._base_url_env} environment "
                f"variable -- this is the documented ADAPTER READY boundary (CONTRACT.md SS40); no "
                f"Home Assistant instance is configured in this environment"
            )
        return base_url.rstrip("/")

    def _headers(self) -> Mapping[str, str]:
        token = os.environ.get(self._token_env)
        if not token:
            raise HomeAssistantNotConfiguredError(
                f"HomeAssistantExecutor requires the {self._token_env} environment variable (a Home "
                f"Assistant long-lived access token) -- this is the documented ADAPTER READY boundary "
                f"(CONTRACT.md SS40); no token is configured in this environment"
            )
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def __call__(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action not in _ACTIONS:
            raise UnknownActionError(f"HomeAssistantExecutor has no action {action!r} -- expected one of {_ACTIONS}")

        import requests

        base_url = self._resolve_base_url()
        headers = self._headers()

        try:
            if action == "list_states":
                response = requests.get(f"{base_url}/api/states", headers=headers, timeout=self._timeout_seconds)
            elif action == "get_state":
                entity_id = parameters["entity_id"]
                response = requests.get(f"{base_url}/api/states/{entity_id}", headers=headers, timeout=self._timeout_seconds)
            elif action == "get_config":
                response = requests.get(f"{base_url}/api/config", headers=headers, timeout=self._timeout_seconds)
            elif action == "call_service":
                domain = parameters["domain"]
                service = parameters["service"]
                service_data = parameters.get("service_data", {})
                response = requests.post(
                    f"{base_url}/api/services/{domain}/{service}", headers=headers, json=service_data,
                    timeout=self._timeout_seconds,
                )
            else:  # pragma: no cover -- already validated above
                raise UnknownActionError(f"unhandled action {action!r}")
        except (UnknownActionError, HomeAssistantNotConfiguredError):
            raise
        except Exception as exc:
            raise ConnectionError(f"Home Assistant request for action {action!r} failed: {exc}") from exc

        if response.status_code == 401:
            raise HomeAssistantNotConfiguredError(f"Home Assistant rejected the configured token (401): {response.text[:300]}")
        if response.status_code >= 400:
            raise ConnectionError(f"Home Assistant returned {response.status_code} for action {action!r}: {response.text[:300]}")

        return response.json()
