"""Config -- layered configuration loading and an immutable resolved Config.

Layers, in increasing precedence: defaults < config file (JSON) <
environment variables < explicit overrides. See CONTRACT.md SS1 for the
full language-agnostic contract this module implements, and
schemas/config.schema.json for the shape each layer is validated against.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union

from .errors import ConfigError

ConfigDocument = Mapping[str, Any]

_RESERVED_PREFIX = "__"
_MISSING = object()


def _validate_document(doc: Any, *, path: str = "") -> None:
    """Validate a raw config document against config.schema.json's shape:
    string keys not starting with '__', JSON-compatible values, arbitrary
    nesting depth.
    """
    if not isinstance(doc, dict):
        raise ConfigError(
            f"Config document at '{path or '<root>'}' must be an object, "
            f"got {type(doc).__name__}"
        )
    for key, value in doc.items():
        if not isinstance(key, str):
            raise ConfigError(f"Config key at '{path}' must be a string, got {type(key).__name__}")
        if key.startswith(_RESERVED_PREFIX):
            raise ConfigError(f"Config key '{path}{key}' starts with reserved prefix '__'")
        _validate_value(value, path=f"{path}{key}.")


def _validate_value(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        _validate_document(value, path=path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_value(item, path=f"{path}[{index}].")
    elif value is None or isinstance(value, (str, int, float, bool)):
        return
    else:
        raise ConfigError(f"Config value at '{path.rstrip('.')}' has unsupported type {type(value).__name__}")


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge `override` into `base`, returning a new dict. Nested
    dicts are merged key-by-key; every other type (including lists) is
    replaced wholesale by the override's value -- see CONTRACT.md SS1.
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _unfreeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {k: _unfreeze(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze(v) for v in value]
    return value


def _coerce_env_value(raw: str) -> Any:
    """Try to decode an env var's raw string as JSON; fall back to the raw
    string if it isn't valid JSON.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _env_layer(env_prefix: str, environ: Mapping[str, str]) -> dict:
    """Build a config document from every env var starting with
    `env_prefix`, mapping `PREFIX_ROUTER__TIMEOUT` -> {"router": {"timeout": ...}}.
    """
    layer: dict = {}
    for env_key, raw_value in environ.items():
        if not env_key.startswith(env_prefix):
            continue
        path = env_key[len(env_prefix):].lower().split("__")
        if any(segment == "" for segment in path):
            continue  # malformed key (e.g. trailing '__') -- skip rather than guess
        cursor = layer
        for segment in path[:-1]:
            next_cursor = cursor.setdefault(segment, {})
            if not isinstance(next_cursor, dict):
                raise ConfigError(
                    f"Environment variable '{env_key}' conflicts with another "
                    f"variable at the same config path"
                )
            cursor = next_cursor
        cursor[path[-1]] = _coerce_env_value(raw_value)
    return layer


class Config:
    """An immutable, resolved configuration. Construct via load_config(),
    never directly.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict) -> None:
        self._data = _freeze(data)

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-separated key access, e.g. get("router.timeout")."""
        cursor: Any = self._data
        for segment in key.split("."):
            if isinstance(cursor, MappingProxyType) and segment in cursor:
                cursor = cursor[segment]
            else:
                return default
        return cursor

    def require(self, key: str) -> Any:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise ConfigError(f"Required config key '{key}' is not set")
        return value

    def as_dict(self) -> dict:
        """A plain, mutable snapshot -- for passing to code outside Core
        Engine's own type system (e.g. a third-party library's config).
        """
        return _unfreeze(self._data)

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"Config({self.as_dict()!r})"


def load_config(
    defaults: Optional[ConfigDocument] = None,
    config_path: Optional[Union[str, Path]] = None,
    env_prefix: str = "AVISHKAR_",
    overrides: Optional[ConfigDocument] = None,
) -> Config:
    """Resolve a Config by layering, in increasing precedence:
    defaults < config file (JSON) < environment variables < overrides.

    Raises ConfigError if any layer is malformed or fails validation.
    See CONTRACT.md SS1.
    """
    resolved: dict = {}

    defaults_doc = dict(defaults or {})
    _validate_document(defaults_doc)
    resolved = _deep_merge(resolved, defaults_doc)

    if config_path is not None:
        path = Path(config_path)
        try:
            file_contents = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Could not read config file '{config_path}': {exc}") from exc
        try:
            file_doc = json.loads(file_contents)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config file '{config_path}' is not valid JSON: {exc}") from exc
        _validate_document(file_doc)
        resolved = _deep_merge(resolved, file_doc)

    env_doc = _env_layer(env_prefix, os.environ)
    _validate_document(env_doc)
    resolved = _deep_merge(resolved, env_doc)

    overrides_doc = dict(overrides or {})
    _validate_document(overrides_doc)
    resolved = _deep_merge(resolved, overrides_doc)

    return Config(resolved)
