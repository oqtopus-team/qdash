"""Deployment-specific Agent model profiles.

``QDASH_AGENT_PROFILE`` selects which ``chat.yaml`` and ``evaluation.yaml``
Agent uses. Unset or empty keeps ``config/agent/chat.yaml`` and
``config/agent/evaluation.yaml``. A name selects
``config/agent/profiles/<name>/chat.yaml`` and ``evaluation.yaml``, which
must both exist and be valid: a named profile never falls back to the default
files. ``config.yaml`` and ``classifier.yaml`` are shared by every profile.

``config.yaml`` is ``config/agent/config.yaml`` unless ``AGENT_CONFIG_PATH``
names another file; the default files and ``profiles/`` are read next to it
(``resolve_agent_config_path``, ``resolve_agent_model_files``).

The legacy names ``QDASH_COPILOT_PROFILE`` and ``COPILOT_CONFIG_PATH`` and a
``config/copilot`` directory are still accepted for now
(``renamed_env_value``); setting both names of a variable to different
non-empty values is an error.

A profile file is parsed as YAML 1.2 core and each model entry is checked field
by field (``validate_agent_profile_document``); the default files keep their
lenient loading.

The Pi Agent Runtime applies the same rules in
``agent-runtime/src/agent-profile.ts``; keep the two in step.
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

AGENT_PROFILE_ENV = "QDASH_AGENT_PROFILE"
"""Environment variable that names the Agent profile."""

LEGACY_AGENT_PROFILE_ENV = "QDASH_COPILOT_PROFILE"
"""Name of ``AGENT_PROFILE_ENV`` before the Copilot -> Agent rename, accepted temporarily."""

AGENT_CONFIG_PATH_ENV = "AGENT_CONFIG_PATH"
"""Environment variable that names the shared ``config.yaml``."""

LEGACY_AGENT_CONFIG_PATH_ENV = "COPILOT_CONFIG_PATH"
"""Name of ``AGENT_CONFIG_PATH_ENV`` before the Copilot -> Agent rename, accepted temporarily."""

CHAT_CONFIG_PATH_ENV = "CHAT_CONFIG_PATH"
"""Environment variable that names the default ``chat.yaml``; conflicts with a profile."""

EVALUATION_CONFIG_PATH_ENV = "EVALUATION_CONFIG_PATH"
"""Environment variable that names the default ``evaluation.yaml``; conflicts with a profile."""

AGENT_CONFIG_DIRNAME = "agent"
"""Directory under the configuration root that holds the Agent configuration."""

LEGACY_AGENT_CONFIG_DIRNAME = "copilot"
"""Name of ``config/agent`` before the Copilot -> Agent rename."""

PROFILES_DIRNAME = "profiles"
"""Directory under ``config/agent`` that holds one directory per profile."""

PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
"""Lowercase letters, digits, ``-`` and ``_``; no separators or dots."""

ProfileFileKind = Literal["chat", "evaluation"]

# The one top-level key each profile file may set. Shared settings stay in
# config.yaml, so a profile cannot change them by accident.
PROFILE_FILE_KEYS: dict[ProfileFileKind, str] = {
    "chat": "chat_models",
    "evaluation": "evaluation_models",
}


class AgentProfileError(ValueError):
    """A selected Agent profile is invalid, incomplete, or unreadable."""


def renamed_env_value(env: Mapping[str, str], name: str, legacy: str) -> tuple[str, str] | None:
    """The value of a renamed variable and the name it was read from.

    ``None`` when neither name is set. When only one is set, its value is used,
    empty or not. When both are set, equal values are fine and an empty value
    gives way to a non-empty one; two different non-empty values are an error,
    so a stale legacy line cannot silently win or lose. The runtime applies the
    same rules in ``renamedEnvValue``.
    """
    current, old = env.get(name), env.get(legacy)
    if old is None:
        return None if current is None else (name, current)
    if current is None or (current == "" and old != ""):
        return legacy, old
    if old != "" and old != current:
        raise AgentProfileError(
            f"{name}={current!r} conflicts with the legacy {legacy}={old!r}; set only {name}"
        )
    return name, current


def selected_agent_profile(environ: Mapping[str, str] | None = None) -> str | None:
    """The validated profile name, or ``None`` when the variable is unset or empty.

    An empty value means the default files, as an empty ``KEY=`` line in a
    Compose ``env_file`` passes an empty string. Any other value must be a
    valid name; surrounding whitespace is not stripped. ``QDASH_COPILOT_PROFILE``
    is read as a legacy alias (see ``renamed_env_value``).
    """
    env = os.environ if environ is None else environ
    selected = renamed_env_value(env, AGENT_PROFILE_ENV, LEGACY_AGENT_PROFILE_ENV)
    if selected is None or selected[1] == "":
        return None
    source, name = selected
    if source == LEGACY_AGENT_PROFILE_ENV:
        logger.warning("%s is deprecated; rename it to %s", source, AGENT_PROFILE_ENV)
    if not PROFILE_NAME_PATTERN.fullmatch(name):
        raise AgentProfileError(
            f"{source}={name!r} is not a valid profile name: use 1-63 "
            "lowercase letters, digits, '-' or '_', starting with a letter or digit"
        )
    return name


def resolve_agent_config_path(config_root: Path, environ: Mapping[str, str] | None = None) -> Path:
    """The shared ``config.yaml`` of the Agent.

    ``AGENT_CONFIG_PATH`` (or the legacy ``COPILOT_CONFIG_PATH``, see
    ``renamed_env_value``) names it and is used as given; unset or empty means
    ``<config_root>/agent/config.yaml``. A configuration root that has only the
    pre-rename ``copilot/`` directory is read from there, with a warning. The
    runtime applies the same rules in ``resolveAgentConfigPaths``.
    """
    env = os.environ if environ is None else environ
    explicit = renamed_env_value(env, AGENT_CONFIG_PATH_ENV, LEGACY_AGENT_CONFIG_PATH_ENV)
    if explicit is not None and explicit[1] != "":
        source, value = explicit
        if source == LEGACY_AGENT_CONFIG_PATH_ENV:
            logger.warning("%s is deprecated; rename it to %s", source, AGENT_CONFIG_PATH_ENV)
        return Path(value)
    return default_agent_config_dir(config_root) / "config.yaml"


def default_agent_config_dir(config_root: Path) -> Path:
    """``<config_root>/agent``, or a legacy ``<config_root>/copilot`` when only that exists."""
    agent_dir = config_root / AGENT_CONFIG_DIRNAME
    legacy_dir = config_root / LEGACY_AGENT_CONFIG_DIRNAME
    if not agent_dir.exists() and legacy_dir.is_dir():
        logger.warning("%s is deprecated; rename it to %s", legacy_dir, agent_dir)
        return legacy_dir
    return agent_dir


@dataclass(frozen=True)
class AgentModelFiles:
    """The chat and evaluation files Agent reads, and the profile they belong to."""

    chat: Path
    evaluation: Path
    profile: str | None = None
    """The selected profile; ``None`` for the default files."""


def resolve_agent_model_files(
    agent_config_path: Path, environ: Mapping[str, str] | None = None
) -> AgentModelFiles:
    """Where the chat and evaluation models come from.

    The default files and ``profiles/`` sit next to ``agent_config_path``.
    ``CHAT_CONFIG_PATH`` and ``EVALUATION_CONFIG_PATH`` replace the default
    files when set and non-empty, and conflict with a named profile. The
    runtime applies the same rules in ``resolveAgentModelFiles``.
    """
    env = os.environ if environ is None else environ
    agent_dir = agent_config_path.parent
    profile = selected_agent_profile(env)
    if profile is None:
        return AgentModelFiles(
            chat=Path(env.get(CHAT_CONFIG_PATH_ENV) or agent_dir / "chat.yaml"),
            evaluation=Path(env.get(EVALUATION_CONFIG_PATH_ENV) or agent_dir / "evaluation.yaml"),
        )
    overrides = [
        name for name in (CHAT_CONFIG_PATH_ENV, EVALUATION_CONFIG_PATH_ENV) if env.get(name)
    ]
    if overrides:
        raise AgentProfileError(
            f"{AGENT_PROFILE_ENV}={profile} conflicts with {' and '.join(overrides)}; "
            "set one or the other"
        )
    files = agent_profile_files(agent_dir, profile)
    return AgentModelFiles(chat=files["chat"], evaluation=files["evaluation"], profile=profile)


def agent_profile_files(agent_dir: Path, profile: str) -> dict[ProfileFileKind, Path]:
    """The chat and evaluation files of a profile, which must exist inside its directory."""
    if not PROFILE_NAME_PATTERN.fullmatch(profile):
        raise AgentProfileError(f"invalid Agent profile name {profile!r}")
    profiles_root = (agent_dir / PROFILES_DIRNAME).resolve()
    profile_dir = agent_dir / PROFILES_DIRNAME / profile
    if not profile_dir.is_dir():
        # A profile added under the pre-rename config/copilot is not read from there.
        legacy_dir = agent_dir.parent / LEGACY_AGENT_CONFIG_DIRNAME / PROFILES_DIRNAME / profile
        hint = f"; move {legacy_dir} there" if legacy_dir.is_dir() else ""
        raise AgentProfileError(
            f"Agent profile {profile!r} not found: {profile_dir} is not a directory "
            f"(set by {AGENT_PROFILE_ENV}){hint}"
        )
    files: dict[ProfileFileKind, Path] = {}
    for kind in PROFILE_FILE_KEYS:
        path = profile_dir / f"{kind}.yaml"
        if not path.is_file():
            raise AgentProfileError(
                f"Agent profile {profile!r} is missing {path}; a profile needs both "
                "chat.yaml and evaluation.yaml"
            )
        # A symlinked profile directory or file must still resolve under profiles/.
        if not path.resolve().is_relative_to(profiles_root):
            raise AgentProfileError(
                f"Agent profile {profile!r}: {path} resolves outside {profiles_root}"
            )
        files[kind] = path
    return files


def load_agent_profile_file(kind: ProfileFileKind, path: Path) -> dict[str, Any]:
    """Parse and validate one profile file; the result is the raw YAML mapping."""
    try:
        data = parse_agent_profile_yaml(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise AgentProfileError(f"cannot read Agent profile file {path}: {e}") from e
    return validate_agent_profile_document(kind, data, path)


# --- YAML -------------------------------------------------------------------
#
# The runtime reads profile files with the `yaml` package's default YAML 1.2
# core schema, PyYAML implements YAML 1.1. The two disagree on plain scalars
# such as `yes` (a boolean in 1.1), `1_000` (an integer in 1.1), `1e3` (a
# string to PyYAML) or `010` (octal in 1.1), on `<<` merge keys, and PyYAML
# silently keeps the last of duplicate keys where the runtime refuses the file.
# Profile files are therefore parsed here with the 1.2 core schema and without
# merge keys or duplicate keys, so both runtimes see the same values.

_CORE_NULL = re.compile(r"^(?:~|null|Null|NULL|)$")
_CORE_BOOL = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_CORE_INT = re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$")
_CORE_FLOAT = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.nan|\.NaN|\.NAN)$"
)


class _ProfileYamlLoader(yaml.SafeLoader):
    """SafeLoader restricted to the YAML 1.2 core schema the runtime uses."""

    yaml_implicit_resolvers: dict[Any, Any] = {}

    def construct_mapping(self, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
        if isinstance(node, yaml.MappingNode):
            seen: set[Any] = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key {key!r}",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)  # type: ignore[arg-type]

    def construct_core_bool(self, node: yaml.ScalarNode) -> bool:
        return str(self.construct_scalar(node)).lower() == "true"

    def construct_core_int(self, node: yaml.ScalarNode) -> int:
        value = str(self.construct_scalar(node))
        if value.startswith("0o"):
            return int(value[2:], 8)
        if value.startswith("0x"):
            return int(value[2:], 16)
        return int(value, 10)


_ProfileYamlLoader.add_implicit_resolver("tag:yaml.org,2002:null", _CORE_NULL, ["~", "n", "N", ""])
_ProfileYamlLoader.add_implicit_resolver("tag:yaml.org,2002:bool", _CORE_BOOL, list("tTfF"))
_ProfileYamlLoader.add_implicit_resolver("tag:yaml.org,2002:int", _CORE_INT, list("-+0123456789"))
_ProfileYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float", _CORE_FLOAT, list("-+0123456789.")
)
_ProfileYamlLoader.add_constructor(
    "tag:yaml.org,2002:bool",
    _ProfileYamlLoader.construct_core_bool,
)
_ProfileYamlLoader.add_constructor(
    "tag:yaml.org,2002:int",
    _ProfileYamlLoader.construct_core_int,
)


def parse_agent_profile_yaml(text: str) -> object:
    """Parse a profile file as the runtime does: YAML 1.2 core, unique keys, no merges."""
    return yaml.load(text, Loader=_ProfileYamlLoader)  # noqa: S506


# --- Model entries ----------------------------------------------------------
#
# A named profile's model entries are checked field by field before either
# runtime builds anything from them, so a wrongly typed or unsupported value
# fails with its file, entry and field instead of being coerced by the API's
# ModelConfig or dropped by the runtime's models.json generation. The default
# files are not checked here. agent-runtime/src/agent-profile.ts applies the
# same rules with the same messages.

PROFILE_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        # ModelConfig in qdash.agent.config.settings
        "provider",
        "name",
        "temperature",
        "max_output_tokens",
        "base_url",
        "api_key_env",
        "keep_alive",
        "num_ctx",
        "top_p",
        "top_k",
        "sampling_params",
        "sampling_params_by_thinking_level",
        "reasoning_effort",
        "disable_thinking_instruction",
        "api_style",
        # Read only by the runtime's models.json generation
        "strict_tool_schemas",
        "prompt_cache_key_mode",
        "requires_non_null_assistant_content",
        "requires_tools_with_tool_history",
    }
)
"""Every key a profile model entry may set."""

API_STYLES = ("responses", "completion")
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high")
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
PROMPT_CACHE_KEY_MODES = ("auto", "enabled", "disabled")
# Keys the runtime writes as compat of a custom endpoint; catalog models ignore them.
BASE_URL_ONLY_FIELDS = (
    "strict_tool_schemas",
    "prompt_cache_key_mode",
    "requires_non_null_assistant_content",
    "requires_tools_with_tool_history",
)
COMPLETION_ONLY_FIELDS = (
    "requires_non_null_assistant_content",
    "requires_tools_with_tool_history",
)
_NULLABLE_FIELDS = frozenset(
    {
        "temperature",
        "base_url",
        "api_key_env",
        "keep_alive",
        "num_ctx",
        "top_p",
        "top_k",
        "reasoning_effort",
    }
)
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MAX_SAFE_INTEGER = 2**53 - 1


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _is_whole(value: object) -> bool:
    if not _is_number(value):
        return False
    assert isinstance(value, int | float)
    return float(value).is_integer() and abs(value) <= _MAX_SAFE_INTEGER


def _model_field_error(field: str, value: object) -> str | None:
    """Why one field's value is not accepted, or ``None``."""
    if value is None:
        return None if field in _NULLABLE_FIELDS else "must not be null"
    if field in ("provider", "name", "keep_alive"):
        return None if isinstance(value, str) and value else "must be a non-empty string"
    if field == "api_style":
        return None if value in API_STYLES else f"must be one of {', '.join(API_STYLES)}"
    if field == "base_url":
        if isinstance(value, str):
            if value.startswith("env:") and _ENV_NAME.fullmatch(value[4:]):
                return None
            if value.startswith(("http://", "https://")) and len(value.split("://", 1)[1]) > 0:
                return None
        return "must be an http:// or https:// URL or env:NAME"
    if field == "api_key_env":
        if isinstance(value, str) and _ENV_NAME.fullmatch(value):
            return None
        return "must be an environment variable name"
    if field == "temperature":
        if not _is_number(value):
            return "must be a finite number"
        return None if value >= 0 else "must be at least 0"  # type: ignore[operator]
    if field == "top_p":
        if not _is_number(value):
            return "must be a finite number"
        return None if 0 < value <= 1 else "must be greater than 0 and at most 1"  # type: ignore[operator]
    if field in ("max_output_tokens", "num_ctx"):
        if not _is_whole(value):
            return "must be a whole number"
        return None if value >= 1 else "must be at least 1"  # type: ignore[operator]
    if field == "top_k":
        if not _is_whole(value):
            return "must be a whole number"
        return None if value >= -1 else "must be at least -1"  # type: ignore[operator]
    if field == "reasoning_effort":
        if value in REASONING_EFFORTS:
            return None
        return f"must be one of {', '.join(REASONING_EFFORTS)}"
    if field == "prompt_cache_key_mode":
        if value in PROMPT_CACHE_KEY_MODES:
            return None
        return f"must be one of {', '.join(PROMPT_CACHE_KEY_MODES)}"
    if field in (
        "disable_thinking_instruction",
        "strict_tool_schemas",
        "requires_non_null_assistant_content",
        "requires_tools_with_tool_history",
    ):
        return None if isinstance(value, bool) else "must be true or false"
    if field == "sampling_params":
        return None if isinstance(value, dict) else "must be a mapping"
    if field == "sampling_params_by_thinking_level":
        if not isinstance(value, dict):
            return "must be a mapping"
        unknown = sorted(str(level) for level in value if level not in THINKING_LEVELS)
        if unknown:
            return f"has unknown level(s) {', '.join(unknown)}; use {', '.join(THINKING_LEVELS)}"
        for level, params in value.items():
            if not isinstance(params, dict):
                return f"{level} must be a mapping"
        return None
    return None


def _validate_profile_model(where: str, model: dict[Any, Any]) -> None:
    unknown = sorted(str(field) for field in model if field not in PROFILE_MODEL_FIELDS)
    if unknown:
        raise AgentProfileError(
            f"{where} has unknown field(s) {', '.join(unknown)}; see "
            "docs/developer-guide/agent/model-configuration.md#deployment-profiles"
        )
    for field in ("provider", "name"):
        if field not in model:
            raise AgentProfileError(f"{where}.{field} must be a non-empty string")
    for field in sorted(model):
        error = _model_field_error(field, model[field])
        if error is not None:
            raise AgentProfileError(f"{where}.{field} {error}")
    max_output, num_ctx = model.get("max_output_tokens"), model.get("num_ctx")
    if max_output is not None and num_ctx is not None and max_output >= num_ctx:
        raise AgentProfileError(f"{where}.max_output_tokens must be less than num_ctx")
    for field in BASE_URL_ONLY_FIELDS:
        if field in model and model.get("base_url") is None:
            raise AgentProfileError(f"{where}.{field} applies only to a model with base_url")
    if model.get("api_style") == "responses":
        for field in COMPLETION_ONLY_FIELDS:
            if field in model:
                raise AgentProfileError(f"{where}.{field} applies only to api_style completion")


def validate_agent_profile_document(
    kind: ProfileFileKind, data: object, path: Path
) -> dict[str, Any]:
    """Check a profile file before any model is built from it.

    The document holds only its one list; each entry is checked by
    ``_validate_profile_model`` and a provider/name pair appears once.
    """
    key = PROFILE_FILE_KEYS[kind]
    if not isinstance(data, dict):
        raise AgentProfileError(f"{path}: expected a mapping with a {key!r} list")
    unexpected = sorted(str(name) for name in data if name != key)
    if unexpected:
        raise AgentProfileError(
            f"{path}: unexpected key(s) {', '.join(unexpected)}; a profile {kind}.yaml "
            f"sets only {key!r} (shared settings stay in config/agent/config.yaml)"
        )
    models = data.get(key)
    if not isinstance(models, list):
        raise AgentProfileError(f"{path}: {key!r} must be a list")
    if kind == "chat" and not models:
        raise AgentProfileError(f"{path}: {key!r} must list at least one model")
    seen: dict[tuple[str, str], int] = {}
    for index, model in enumerate(models):
        where = f"{path}: {key}[{index}]"
        if not isinstance(model, dict):
            raise AgentProfileError(f"{where} must be a mapping")
        _validate_profile_model(where, model)
        identity = (model["provider"], model["name"])
        if identity in seen:
            raise AgentProfileError(
                f"{where} repeats the provider and name of {key}[{seen[identity]}]"
            )
        seen[identity] = index
    return data
