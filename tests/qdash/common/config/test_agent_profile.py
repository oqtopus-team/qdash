"""QDASH_AGENT_PROFILE selection through ConfigLoader and load_agent_config."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from qdash.agent.config import clear_agent_config_cache, load_agent_config
from qdash.agent.config.settings import ModelConfig
from qdash.common.config.agent_profile import (
    AGENT_CONFIG_PATH_ENV,
    AGENT_PROFILE_ENV,
    CHAT_CONFIG_PATH_ENV,
    EVALUATION_CONFIG_PATH_ENV,
    LEGACY_AGENT_CONFIG_PATH_ENV,
    LEGACY_AGENT_PROFILE_ENV,
    PROFILE_MODEL_FIELDS,
    AgentProfileError,
    parse_agent_profile_yaml,
    selected_agent_profile,
    validate_agent_profile_document,
)
from qdash.common.config.loader import ConfigLoader

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_CONFIG = REPO_ROOT / "config"
CASES = json.loads((REPO_ROOT / "tests" / "data" / "agent_profile_cases.json").read_text())

CONFIG_YAML = "enabled: true\nresponse_language: auto\ntask_chat:\n  multimodal: true\n"
DEFAULT_CHAT = "chat_models:\n  - provider: openai-compatible-chat\n    name: default-chat\n"
DEFAULT_EVALUATION = (
    "evaluation_models:\n  - provider: openai-compatible-evaluation\n    name: default-eval\n"
)


# Every variable that changes which Agent files are read.
SELECTION_ENV = (
    AGENT_PROFILE_ENV,
    LEGACY_AGENT_PROFILE_ENV,
    AGENT_CONFIG_PATH_ENV,
    LEGACY_AGENT_CONFIG_PATH_ENV,
    CHAT_CONFIG_PATH_ENV,
    EVALUATION_CONFIG_PATH_ENV,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _chat(name: str) -> str:
    return f"chat_models:\n  - provider: openai-compatible-chat\n    name: {name}\n"


def _evaluation(name: str) -> str:
    return f"evaluation_models:\n  - provider: openai-compatible-evaluation\n    name: {name}\n"


def _reset() -> None:
    ConfigLoader.clear_cache()
    clear_agent_config_cache()


@pytest.fixture
def config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A config directory with default files and a `site` profile."""
    root = tmp_path / "config"
    _write(root / "agent" / "config.yaml", CONFIG_YAML)
    _write(root / "agent" / "chat.yaml", DEFAULT_CHAT)
    _write(root / "agent" / "evaluation.yaml", DEFAULT_EVALUATION)
    _write(root / "agent" / "profiles" / "site" / "chat.yaml", _chat("site-chat"))
    _write(root / "agent" / "profiles" / "site" / "evaluation.yaml", _evaluation("site-eval"))
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", root)
    for name in SELECTION_ENV:
        monkeypatch.delenv(name, raising=False)
    _reset()
    yield root
    _reset()


def _model_names(config: dict[str, Any], key: str) -> list[str]:
    return [model["name"] for model in config.get(key, [])]


@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_empty_profile_reads_default_files(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, value: str | None
) -> None:
    if value is not None:
        monkeypatch.setenv(AGENT_PROFILE_ENV, value)

    config = ConfigLoader.load_agent()

    assert config == {
        **yaml.safe_load(CONFIG_YAML),
        **yaml.safe_load(DEFAULT_CHAT),
        **yaml.safe_load(DEFAULT_EVALUATION),
    }


def test_default_files_keep_their_lenient_loading(config_dir: Path) -> None:
    """Without a profile, a missing evaluation.yaml still means no evaluation models."""
    (config_dir / "agent" / "evaluation.yaml").unlink()

    config = load_agent_config()

    assert [model.name for model in config.chat_models] == ["default-chat"]
    assert config.evaluation_models == []


def test_named_profile_replaces_chat_and_evaluation_but_keeps_shared_config(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    config = load_agent_config()

    assert config.enabled is True
    assert config.response_language == "auto"
    assert [model.name for model in config.chat_models] == ["site-chat"]
    assert config.model.name == "site-chat"
    assert [model.name for model in config.evaluation_models] == ["site-eval"]


def test_profile_files_are_independent(monkeypatch: pytest.MonkeyPatch, config_dir: Path) -> None:
    """A profile's chat and evaluation lists are each taken whole, never merged with defaults."""
    profile = config_dir / "agent" / "profiles" / "split"
    _write(profile / "chat.yaml", _chat("split-chat"))
    _write(profile / "evaluation.yaml", "evaluation_models: []\n")
    monkeypatch.setenv(AGENT_PROFILE_ENV, "split")

    config = ConfigLoader.load_agent()

    assert _model_names(config, "chat_models") == ["split-chat"]
    assert config["evaluation_models"] == []


def test_clear_cache_picks_up_a_changed_selection(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    assert _model_names(ConfigLoader.load_agent(), "chat_models") == ["default-chat"]

    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")
    # Still cached until the reload endpoint (or a restart) clears it.
    assert _model_names(ConfigLoader.load_agent(), "chat_models") == ["default-chat"]
    _reset()
    assert _model_names(ConfigLoader.load_agent(), "chat_models") == ["site-chat"]
    assert [model.name for model in load_agent_config().chat_models] == ["site-chat"]

    monkeypatch.delenv(AGENT_PROFILE_ENV)
    _reset()
    assert _model_names(ConfigLoader.load_agent(), "chat_models") == ["default-chat"]


def test_profile_preserves_environment_variable_strings(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv("SITE_MODEL", "from-env")
    _write(
        config_dir / "agent" / "profiles" / "site" / "chat.yaml",
        "chat_models:\n  - provider: openai-compatible-chat\n    name: ${SITE_MODEL}\n",
    )
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    assert _model_names(ConfigLoader.load_agent(), "chat_models") == ["${SITE_MODEL}"]


def test_local_yaml_files_are_not_read(monkeypatch: pytest.MonkeyPatch, config_dir: Path) -> None:
    """Neither the default files nor a profile take a `*.local.yaml` overlay."""
    agent = config_dir / "agent"
    _write(agent / "chat.local.yaml", _chat("local-chat"))
    _write(agent / "evaluation.local.yaml", _evaluation("local-eval"))
    _write(agent / "profiles" / "site" / "chat.local.yaml", _chat("site-local-chat"))
    _write(agent / "profiles" / "site" / "evaluation.local.yaml", _evaluation("site-local"))

    config = ConfigLoader.load_agent()
    assert _model_names(config, "chat_models") == ["default-chat"]
    assert _model_names(config, "evaluation_models") == ["default-eval"]

    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")
    _reset()
    config = ConfigLoader.load_agent()
    assert _model_names(config, "chat_models") == ["site-chat"]
    assert _model_names(config, "evaluation_models") == ["site-eval"]


def test_missing_profile_fails_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(AGENT_PROFILE_ENV, "osaka")

    with pytest.raises(AgentProfileError, match="'osaka' not found"):
        ConfigLoader.load_agent()
    # The failure is not cached into a fallback: it repeats on every load.
    with pytest.raises(ValueError, match="'osaka' not found"):
        load_agent_config()


@pytest.mark.parametrize("missing", ["chat.yaml", "evaluation.yaml"])
def test_profile_missing_a_file_fails(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, missing: str
) -> None:
    (config_dir / "agent" / "profiles" / "site" / missing).unlink()
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    with pytest.raises(AgentProfileError, match=f"missing .*{missing}"):
        ConfigLoader.load_agent()


def test_profile_with_malformed_yaml_fails(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    _write(config_dir / "agent" / "profiles" / "site" / "evaluation.yaml", "evaluation_models: [\n")
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    with pytest.raises(AgentProfileError, match="cannot read Agent profile file"):
        ConfigLoader.load_agent()


@pytest.mark.parametrize("value", ["lots", "'4096'", "true", "4096.5", "0"])
def test_profile_with_invalid_model_settings_fails_with_its_location(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, value: str
) -> None:
    """A setting ModelConfig would coerce, or the runtime would drop, fails at load time."""
    chat_path = config_dir / "agent" / "profiles" / "site" / "chat.yaml"
    _write(
        chat_path, f"chat_models:\n  - provider: p\n    name: m\n    max_output_tokens: {value}\n"
    )
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    location = f"{chat_path}: chat_models[0].max_output_tokens must be"
    with pytest.raises(AgentProfileError) as error:
        ConfigLoader.load_agent()
    assert location in str(error.value)
    with pytest.raises(ValueError, match="chat_models\\[0\\]\\.max_output_tokens must be"):
        load_agent_config()


def test_default_files_are_not_checked_field_by_field(config_dir: Path) -> None:
    """Without a profile, unknown keys and runtime-only values load as before."""
    _write(
        config_dir / "agent" / "chat.yaml",
        "chat_models:\n  - provider: p\n    name: m\n    unknown_key: 1\n"
        "    reasoning_effort: xhigh\n    max_output_tokens: '4096'\n",
    )

    config = load_agent_config()

    assert config.chat_models[0].max_output_tokens == 4096
    assert config.chat_models[0].reasoning_effort == "xhigh"


def test_valid_profile_fields_reach_model_config(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    full = next(case for case in CASES["documents"] if "strict_tool_schemas" in case["yaml"])
    assert full["valid"]
    _write(config_dir / "agent" / "profiles" / "site" / "chat.yaml", full["yaml"])
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    model = load_agent_config().chat_models[0]

    assert (model.api_style, model.temperature, model.top_p, model.top_k) == (
        "completion",
        0,
        1,
        -1,
    )
    assert (model.num_ctx, model.max_output_tokens) == (65536, 8192)
    assert model.reasoning_effort == "medium"
    assert model.sampling_params_by_thinking_level == {
        "low": {"temperature": 1.0},
        "xhigh": {"top_p": 0.95},
    }


def test_profile_model_fields_match_the_shared_cases() -> None:
    assert sorted(PROFILE_MODEL_FIELDS) == CASES["model_fields"]
    assert set(ModelConfig.model_fields) <= PROFILE_MODEL_FIELDS


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: 010", 10),
        ("a: 0o17", 15),
        ("a: 0x1F", 31),
        ("a: 1e3", 1000.0),
        ("a: 1_000", "1_000"),
        ("a: yes", "yes"),
        ("a: TRUE", True),
        ("a: 1:20", "1:20"),
        ("a: 2001-12-14", "2001-12-14"),
        ("a: ~", None),
    ],
)
def test_profile_yaml_uses_the_core_schema(text: str, expected: object) -> None:
    """Scalars resolve as the runtime's YAML 1.2 parser resolves them, not as YAML 1.1."""
    assert parse_agent_profile_yaml(text) == {"a": expected}


@pytest.mark.parametrize("name", CASES["invalid_names"])
def test_invalid_profile_names_are_rejected(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, name: str
) -> None:
    if "\x00" in name:
        pytest.skip("the OS environment cannot hold a NUL byte")
    monkeypatch.setenv(AGENT_PROFILE_ENV, name)

    with pytest.raises(AgentProfileError, match="not a valid profile name"):
        ConfigLoader.load_agent()


@pytest.mark.parametrize("name", CASES["invalid_names"])
def test_invalid_profile_names_are_rejected_by_the_selector(name: str) -> None:
    with pytest.raises(AgentProfileError, match="not a valid profile name"):
        selected_agent_profile({AGENT_PROFILE_ENV: name})


@pytest.mark.parametrize("case", CASES["renamed_env"])
def test_legacy_profile_variable_is_still_accepted(case: dict[str, Any]) -> None:
    """QDASH_COPILOT_PROFILE works until removed; a conflicting pair is refused."""
    if "error" in case:
        with pytest.raises(AgentProfileError, match=case["error"]):
            selected_agent_profile(case["env"])
    else:
        assert selected_agent_profile(case["env"]) == case["profile"]


def test_legacy_profile_variable_selects_a_profile_through_the_loader(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(LEGACY_AGENT_PROFILE_ENV, "site")

    config = ConfigLoader.load_agent()

    assert _model_names(config, "chat_models") == ["site-chat"]


def test_legacy_config_directory_is_read_when_agent_is_missing(
    config_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An externally mounted config that still has only copilot/ keeps working."""
    (config_dir / "agent").rename(config_dir / "copilot")

    config = ConfigLoader.load_agent()

    assert _model_names(config, "chat_models") == ["default-chat"]
    assert "copilot is deprecated" in caplog.text


def test_agent_config_directory_wins_over_a_legacy_one(config_dir: Path) -> None:
    _write(config_dir / "copilot" / "chat.yaml", _chat("legacy-chat"))

    assert _model_names(ConfigLoader.load_agent(), "chat_models") == ["default-chat"]


@pytest.mark.parametrize("name", CASES["valid_names"])
def test_valid_profile_names_are_accepted(name: str) -> None:
    assert selected_agent_profile({AGENT_PROFILE_ENV: name}) == name


def test_traversal_outside_profiles_is_rejected(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, tmp_path: Path
) -> None:
    """A profile directory that is a symlink out of profiles/ is refused."""
    outside = tmp_path / "outside"
    _write(outside / "chat.yaml", _chat("outside-chat"))
    _write(outside / "evaluation.yaml", _evaluation("outside-eval"))
    (config_dir / "agent" / "profiles" / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv(AGENT_PROFILE_ENV, "escape")

    with pytest.raises(AgentProfileError, match="resolves outside"):
        ConfigLoader.load_agent()


@pytest.mark.parametrize(
    "case", CASES["documents"], ids=lambda case: f"{case['kind']}:{case.get('error', 'ok')}"
)
def test_profile_documents_match_the_shared_cases(case: dict[str, Any]) -> None:
    data = parse_agent_profile_yaml(case["yaml"])
    path = Path(f"{case['kind']}.yaml")
    if case["valid"]:
        validate_agent_profile_document(case["kind"], data, path)
    else:
        with pytest.raises(AgentProfileError) as error:
            validate_agent_profile_document(case["kind"], data, path)
        assert case["error"] in str(error.value)


@pytest.mark.parametrize("case", CASES["documents"], ids=lambda case: case.get("error", "ok"))
def test_profile_documents_fail_through_the_loader(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, case: dict[str, Any]
) -> None:
    _write(config_dir / "agent" / "profiles" / "site" / f"{case['kind']}.yaml", case["yaml"])
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    if case["valid"]:
        ConfigLoader.load_agent()
    else:
        with pytest.raises(AgentProfileError) as error:
            ConfigLoader.load_agent()
        assert case["error"] in str(error.value)


@pytest.mark.parametrize("case", CASES["unreadable_documents"])
def test_unreadable_profile_documents_fail_through_the_loader(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, case: dict[str, Any]
) -> None:
    """Duplicate keys, extra documents and broken syntax are refused, as the runtime does."""
    _write(config_dir / "agent" / "profiles" / "site" / f"{case['kind']}.yaml", case["yaml"])
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")

    with pytest.raises(AgentProfileError, match="cannot read Agent profile file"):
        ConfigLoader.load_agent()


def test_committed_oqtopus_profile_uses_qwen_for_chat_and_evaluation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "config"
    shutil.copytree(REPO_CONFIG / "agent", root / "agent")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", root)
    monkeypatch.setenv(AGENT_PROFILE_ENV, "oqtopus")
    _reset()
    try:
        config = load_agent_config()
        default_config = yaml.safe_load((REPO_CONFIG / "agent" / "config.yaml").read_text())
    finally:
        _reset()

    assert config.enabled is default_config["enabled"]
    assert config.response_language == default_config["response_language"]
    assert [(m.provider, m.name, m.api_style) for m in config.chat_models] == [
        ("openai-compatible-chat", "Qwen/Qwen3.8-27B", "completion")
    ]
    assert config.chat_models[0].base_url == "env:OPENAI_COMPATIBLE_BASE_URL_CHAT"
    assert config.chat_models[0].api_key_env == "OPENAI_COMPATIBLE_API_KEY_CHAT"
    assert [(m.provider, m.name, m.api_style) for m in config.evaluation_models] == [
        ("openai-compatible-evaluation", "Qwen/Qwen3.8-27B", "completion")
    ]
    assert config.evaluation_models[0].base_url == "env:OPENAI_COMPATIBLE_BASE_URL_EVALUATION"
    assert config.evaluation_models[0].api_key_env == "OPENAI_COMPATIBLE_API_KEY_EVALUATION"


def test_committed_default_files_are_unchanged_without_a_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default models stay those of config/agent/chat.yaml and evaluation.yaml."""
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", REPO_CONFIG)
    monkeypatch.delenv(AGENT_PROFILE_ENV, raising=False)
    _reset()
    try:
        config = load_agent_config()
    finally:
        _reset()
    chat = yaml.safe_load((REPO_CONFIG / "agent" / "chat.yaml").read_text())
    evaluation = yaml.safe_load((REPO_CONFIG / "agent" / "evaluation.yaml").read_text())

    assert [m.name for m in config.chat_models] == [m["name"] for m in chat["chat_models"]]
    assert [m.name for m in config.evaluation_models] == [
        m["name"] for m in evaluation["evaluation_models"]
    ]


def test_the_default_chat_model_is_native_openai_gpt_6_sol_and_qwen_stays_selectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The committed default chat runs GPT-6 Sol on OpenAI's own API, from the catalog."""
    from qdash.agent.config.settings import select_chat_model
    from qdash.agent.contracts.models import ChatRequest
    from qdash.api.services import pi_chat_service
    from qdash.api.services.evaluation_service import planner_model_config
    from qdash.api.services.pi_chat_service import _request_payload

    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", REPO_CONFIG)
    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: "")
    monkeypatch.delenv(AGENT_PROFILE_ENV, raising=False)
    _reset()
    try:
        config = load_agent_config()
        planner = planner_model_config()
    finally:
        _reset()

    default = config.chat_models[0]
    assert (default.provider, default.name, default.api_style) == (
        "openai",
        "gpt-6-sol",
        "responses",
    )
    assert default.reasoning_effort == "medium"
    # A catalog model: no endpoint of its own, and no sampling copied from another model.
    # The runtime builds models.json from these YAML keys, not from ModelConfig defaults.
    raw = yaml.safe_load((REPO_CONFIG / "agent" / "chat.yaml").read_text())["chat_models"][0]
    assert raw == {
        "provider": "openai",
        "name": "gpt-6-sol",
        "api_style": "responses",
        "reasoning_effort": "medium",
    }
    assert (config.model.provider, config.model.name) == ("openai", "gpt-6-sol")
    # Qwen is still offered, unchanged.
    qwen = [m for m in config.chat_models if m.name == "qwen3.8-flash-next"]
    assert [(m.provider, m.api_style) for m in qwen] == [("openai-compatible-chat", "completion")]

    # A chat without a choice asks the runtime for exactly openai/gpt-6-sol; a choice of Qwen
    # asks for Qwen.
    request = ChatRequest(message="hi", session_id="s1")
    chosen = config.model_copy(update={"model": select_chat_model(config)})
    payload = _request_payload(request, chosen, "alice")
    assert payload["model"] == {"provider": "openai", "name": "gpt-6-sol"}
    assert payload["thinking_level"] == "medium"
    qwen_chat = config.model_copy(update={"model": select_chat_model(config, qwen[0])})
    assert _request_payload(request, qwen_chat, "alice")["model"] == {
        "provider": "openai-compatible-chat",
        "name": "qwen3.8-flash-next",
    }
    # Claude Opus 5.5 on Anthropic's own API is offered too, with nothing but its effort: no
    # api_style, sampling, or endpoint copied from the other models.
    raw_opus = yaml.safe_load((REPO_CONFIG / "agent" / "chat.yaml").read_text())["chat_models"]
    assert [(m["provider"], m["name"]) for m in raw_opus] == [
        ("openai", "gpt-6-sol"),
        ("openai-compatible-chat", "qwen3.8-flash-next"),
        ("anthropic", "claude-opus-5-5"),
        ("openai-compatible-deepseek", "preview/DeepSeek-V4.1-Flash-1017"),
    ]
    assert raw_opus[2] == {
        "provider": "anthropic",
        "name": "claude-opus-5-5",
        "reasoning_effort": "medium",
    }
    opus = config.chat_models[2]
    opus_chat = config.model_copy(update={"model": select_chat_model(config, opus)})
    opus_payload = _request_payload(request, opus_chat, "alice")
    assert opus_payload["model"] == {"provider": "anthropic", "name": "claude-opus-5-5"}
    assert opus_payload["thinking_level"] == "medium"

    # DeepSeek V4.1 Flash is offered on its own endpoint and key, with the endpoint's
    # documented limits and no thinking control it does not document.
    assert raw_opus[3] == {
        "provider": "openai-compatible-deepseek",
        "name": "preview/DeepSeek-V4.1-Flash-1017",
        "api_style": "completion",
        "base_url": "env:OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK",
        "api_key_env": "OPENAI_COMPATIBLE_API_KEY_DEEPSEEK",
        "num_ctx": 1048575,
        "max_output_tokens": 32000,
    }
    deepseek = config.chat_models[3]
    deepseek_chat = config.model_copy(update={"model": select_chat_model(config, deepseek)})
    deepseek_payload = _request_payload(request, deepseek_chat, "alice")
    assert deepseek_payload["model"] == {
        "provider": "openai-compatible-deepseek",
        "name": "preview/DeepSeek-V4.1-Flash-1017",
    }
    assert deepseek_payload["thinking_level"] is None

    # Planner-mode evaluations follow the default chat model; the evaluators do not change.
    assert planner == ({"provider": "openai", "name": "gpt-6-sol"}, "medium")
    assert config.evaluation_models[0].name == "nvidia/Ising-Calibration-1.5-31B-NVFP4"


def test_profile_model_strings_stay_literal(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(AGENT_PROFILE_ENV, "site")
    monkeypatch.setenv("PROFILE_TEST_MODEL", "expanded-model")
    _write(
        config_dir / "agent" / "profiles" / "site" / "chat.yaml",
        _chat("${PROFILE_TEST_MODEL}"),
    )

    assert load_agent_config().chat_models[0].name == "${PROFILE_TEST_MODEL}"


@pytest.mark.parametrize(
    "case", CASES["config_paths"], ids=lambda case: f"{case.get('layout', 'agent')}:{case['env']}"
)
def test_config_paths_select_the_files_the_runtime_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: dict[str, Any],
) -> None:
    """AGENT_CONFIG_PATH, its legacy name and the model overrides, as in agent-profile.test.mjs.

    The loaded settings and model names prove which config.yaml, chat.yaml and
    evaluation.yaml were read, not only which paths were resolved.
    """
    for relative, content in CASES["config_path_files"].items():
        _write(tmp_path / relative, content)
    if case.get("layout") == "legacy":
        (tmp_path / "config" / "agent").rename(tmp_path / "config" / "copilot")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path / "config")
    for name in SELECTION_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in case["env"].items():
        monkeypatch.setenv(name, value.replace("{root}", str(tmp_path)))
    _reset()
    try:
        if "error" in case:
            with pytest.raises(AgentProfileError, match=re.escape(case["error"])):
                load_agent_config()
            return
        config = load_agent_config()
        raw = ConfigLoader.load_agent()
    finally:
        _reset()

    assert raw["response_language"] == case["language"]
    assert config.response_language == case["language"]
    assert [model.name for model in config.chat_models] == case["chat"]
    assert [model.name for model in config.evaluation_models] == case["evaluation"]
    if "warning" in case:
        assert case["warning"] in caplog.text
