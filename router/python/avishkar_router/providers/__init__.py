"""Reference provider adapters for the AI Router Framework.

`MockProvider` has zero dependencies and zero network calls -- it is the
default for tests and the quickstart example. `AnthropicProvider` calls
the real Anthropic API via the official `anthropic` SDK and requires the
`avishkar-router[anthropic]` extra (or a bare `pip install anthropic`)
plus a real API key; import it explicitly, it is not re-exported here to
keep the zero-dependency default import path clean.
"""

from .mock import MockProvider

__all__ = ["MockProvider"]
