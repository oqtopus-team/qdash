"""QDASH_COPILOT_PROFILE selection through ConfigLoader and load_copilot_config."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from qdash.common.config.copilot_profile import (
    COPILOT_PROFILE_ENV,
    PROFILE_MODEL_FIELDS,
    CopilotProfileError,
    parse_copilot_profile_yaml,
    selected_copilot_profile,
    validate_copilot_profile_document,
)
from qdash.common.config.loader import ConfigLoader
from qdash.copilot.config import clear_copilot_config_cache, load_copilot_config
from qdash.copilot.config.settings import ModelConfig

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_CONFIG = REPO_ROOT / "config"
CASES = json.loads((REPO_ROOT / "tests" / "data" / "copilot_profile_cases.json").read_text())

CONFIG_YAML = "enabled: true\nresponse_language: auto\ntask_chat:\n  multimodal: true\n"
DEFAULT_CHAT = "chat_models:\n  - provider: openai-compatible-chat\n    name: default-chat\n"
DEFAULT_EVALUATION = (
    "evaluation_models:\n  - provider: openai-compatible-evaluation\n    name: default-eval\n"
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
    clear_copilot_config_cache()


@pytest.fixture
def config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A config directory with default files and a `site` profile."""
    root = tmp_path / "config"
    _write(root / "copilot" / "config.yaml", CONFIG_YAML)
    _write(root / "copilot" / "chat.yaml", DEFAULT_CHAT)
    _write(root / "copilot" / "evaluation.yaml", DEFAULT_EVALUATION)
    _write(root / "copilot" / "profiles" / "site" / "chat.yaml", _chat("site-chat"))
    _write(root / "copilot" / "profiles" / "site" / "evaluation.yaml", _evaluation("site-eval"))
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", root)
    monkeypatch.delenv(COPILOT_PROFILE_ENV, raising=False)
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
        monkeypatch.setenv(COPILOT_PROFILE_ENV, value)

    config = ConfigLoader.load_copilot()

    assert config == {
        **yaml.safe_load(CONFIG_YAML),
        **yaml.safe_load(DEFAULT_CHAT),
        **yaml.safe_load(DEFAULT_EVALUATION),
    }


def test_default_files_keep_their_lenient_loading(config_dir: Path) -> None:
    """Without a profile, a missing evaluation.yaml still means no evaluation models."""
    (config_dir / "copilot" / "evaluation.yaml").unlink()

    config = load_copilot_config()

    assert [model.name for model in config.chat_models] == ["default-chat"]
    assert config.evaluation_models == []


def test_named_profile_replaces_chat_and_evaluation_but_keeps_shared_config(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    config = load_copilot_config()

    assert config.enabled is True
    assert config.response_language == "auto"
    assert [model.name for model in config.chat_models] == ["site-chat"]
    assert config.model.name == "site-chat"
    assert [model.name for model in config.evaluation_models] == ["site-eval"]


def test_profile_files_are_independent(monkeypatch: pytest.MonkeyPatch, config_dir: Path) -> None:
    """A profile's chat and evaluation lists are each taken whole, never merged with defaults."""
    profile = config_dir / "copilot" / "profiles" / "split"
    _write(profile / "chat.yaml", _chat("split-chat"))
    _write(profile / "evaluation.yaml", "evaluation_models: []\n")
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "split")

    config = ConfigLoader.load_copilot()

    assert _model_names(config, "chat_models") == ["split-chat"]
    assert config["evaluation_models"] == []


def test_clear_cache_picks_up_a_changed_selection(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    assert _model_names(ConfigLoader.load_copilot(), "chat_models") == ["default-chat"]

    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")
    # Still cached until the reload endpoint (or a restart) clears it.
    assert _model_names(ConfigLoader.load_copilot(), "chat_models") == ["default-chat"]
    _reset()
    assert _model_names(ConfigLoader.load_copilot(), "chat_models") == ["site-chat"]
    assert [model.name for model in load_copilot_config().chat_models] == ["site-chat"]

    monkeypatch.delenv(COPILOT_PROFILE_ENV)
    _reset()
    assert _model_names(ConfigLoader.load_copilot(), "chat_models") == ["default-chat"]


def test_profile_preserves_environment_variable_strings(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv("SITE_MODEL", "from-env")
    _write(
        config_dir / "copilot" / "profiles" / "site" / "chat.yaml",
        "chat_models:\n  - provider: openai-compatible-chat\n    name: ${SITE_MODEL}\n",
    )
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    assert _model_names(ConfigLoader.load_copilot(), "chat_models") == ["${SITE_MODEL}"]


def test_local_yaml_files_are_not_read(monkeypatch: pytest.MonkeyPatch, config_dir: Path) -> None:
    """Neither the default files nor a profile take a `*.local.yaml` overlay."""
    copilot = config_dir / "copilot"
    _write(copilot / "chat.local.yaml", _chat("local-chat"))
    _write(copilot / "evaluation.local.yaml", _evaluation("local-eval"))
    _write(copilot / "profiles" / "site" / "chat.local.yaml", _chat("site-local-chat"))
    _write(copilot / "profiles" / "site" / "evaluation.local.yaml", _evaluation("site-local"))

    config = ConfigLoader.load_copilot()
    assert _model_names(config, "chat_models") == ["default-chat"]
    assert _model_names(config, "evaluation_models") == ["default-eval"]

    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")
    _reset()
    config = ConfigLoader.load_copilot()
    assert _model_names(config, "chat_models") == ["site-chat"]
    assert _model_names(config, "evaluation_models") == ["site-eval"]


def test_missing_profile_fails_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "osaka")

    with pytest.raises(CopilotProfileError, match="'osaka' not found"):
        ConfigLoader.load_copilot()
    # The failure is not cached into a fallback: it repeats on every load.
    with pytest.raises(ValueError, match="'osaka' not found"):
        load_copilot_config()


@pytest.mark.parametrize("missing", ["chat.yaml", "evaluation.yaml"])
def test_profile_missing_a_file_fails(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, missing: str
) -> None:
    (config_dir / "copilot" / "profiles" / "site" / missing).unlink()
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    with pytest.raises(CopilotProfileError, match=f"missing .*{missing}"):
        ConfigLoader.load_copilot()


def test_profile_with_malformed_yaml_fails(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    _write(
        config_dir / "copilot" / "profiles" / "site" / "evaluation.yaml", "evaluation_models: [\n"
    )
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    with pytest.raises(CopilotProfileError, match="cannot read Copilot profile file"):
        ConfigLoader.load_copilot()


@pytest.mark.parametrize("value", ["lots", "'4096'", "true", "4096.5", "0"])
def test_profile_with_invalid_model_settings_fails_with_its_location(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, value: str
) -> None:
    """A setting ModelConfig would coerce, or the runtime would drop, fails at load time."""
    chat_path = config_dir / "copilot" / "profiles" / "site" / "chat.yaml"
    _write(
        chat_path, f"chat_models:\n  - provider: p\n    name: m\n    max_output_tokens: {value}\n"
    )
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    location = f"{chat_path}: chat_models[0].max_output_tokens must be"
    with pytest.raises(CopilotProfileError) as error:
        ConfigLoader.load_copilot()
    assert location in str(error.value)
    with pytest.raises(ValueError, match="chat_models\\[0\\]\\.max_output_tokens must be"):
        load_copilot_config()


def test_default_files_are_not_checked_field_by_field(config_dir: Path) -> None:
    """Without a profile, unknown keys and runtime-only values load as before."""
    _write(
        config_dir / "copilot" / "chat.yaml",
        "chat_models:\n  - provider: p\n    name: m\n    unknown_key: 1\n"
        "    reasoning_effort: xhigh\n    max_output_tokens: '4096'\n",
    )

    config = load_copilot_config()

    assert config.chat_models[0].max_output_tokens == 4096
    assert config.chat_models[0].reasoning_effort == "xhigh"


def test_valid_profile_fields_reach_model_config(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    full = next(case for case in CASES["documents"] if "strict_tool_schemas" in case["yaml"])
    assert full["valid"]
    _write(config_dir / "copilot" / "profiles" / "site" / "chat.yaml", full["yaml"])
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    model = load_copilot_config().chat_models[0]

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
    assert parse_copilot_profile_yaml(text) == {"a": expected}


@pytest.mark.parametrize("name", CASES["invalid_names"])
def test_invalid_profile_names_are_rejected(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, name: str
) -> None:
    if "\x00" in name:
        pytest.skip("the OS environment cannot hold a NUL byte")
    monkeypatch.setenv(COPILOT_PROFILE_ENV, name)

    with pytest.raises(CopilotProfileError, match="not a valid profile name"):
        ConfigLoader.load_copilot()


@pytest.mark.parametrize("name", CASES["invalid_names"])
def test_invalid_profile_names_are_rejected_by_the_selector(name: str) -> None:
    with pytest.raises(CopilotProfileError, match="not a valid profile name"):
        selected_copilot_profile({COPILOT_PROFILE_ENV: name})


@pytest.mark.parametrize("name", CASES["valid_names"])
def test_valid_profile_names_are_accepted(name: str) -> None:
    assert selected_copilot_profile({COPILOT_PROFILE_ENV: name}) == name


def test_traversal_outside_profiles_is_rejected(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, tmp_path: Path
) -> None:
    """A profile directory that is a symlink out of profiles/ is refused."""
    outside = tmp_path / "outside"
    _write(outside / "chat.yaml", _chat("outside-chat"))
    _write(outside / "evaluation.yaml", _evaluation("outside-eval"))
    (config_dir / "copilot" / "profiles" / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "escape")

    with pytest.raises(CopilotProfileError, match="resolves outside"):
        ConfigLoader.load_copilot()


@pytest.mark.parametrize(
    "case", CASES["documents"], ids=lambda case: f"{case['kind']}:{case.get('error', 'ok')}"
)
def test_profile_documents_match_the_shared_cases(case: dict[str, Any]) -> None:
    data = parse_copilot_profile_yaml(case["yaml"])
    path = Path(f"{case['kind']}.yaml")
    if case["valid"]:
        validate_copilot_profile_document(case["kind"], data, path)
    else:
        with pytest.raises(CopilotProfileError) as error:
            validate_copilot_profile_document(case["kind"], data, path)
        assert case["error"] in str(error.value)


@pytest.mark.parametrize("case", CASES["documents"], ids=lambda case: case.get("error", "ok"))
def test_profile_documents_fail_through_the_loader(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, case: dict[str, Any]
) -> None:
    _write(config_dir / "copilot" / "profiles" / "site" / f"{case['kind']}.yaml", case["yaml"])
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    if case["valid"]:
        ConfigLoader.load_copilot()
    else:
        with pytest.raises(CopilotProfileError) as error:
            ConfigLoader.load_copilot()
        assert case["error"] in str(error.value)


@pytest.mark.parametrize("case", CASES["unreadable_documents"])
def test_unreadable_profile_documents_fail_through_the_loader(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, case: dict[str, Any]
) -> None:
    """Duplicate keys, extra documents and broken syntax are refused, as the runtime does."""
    _write(config_dir / "copilot" / "profiles" / "site" / f"{case['kind']}.yaml", case["yaml"])
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")

    with pytest.raises(CopilotProfileError, match="cannot read Copilot profile file"):
        ConfigLoader.load_copilot()


def test_committed_oqtopus_profile_uses_qwen_for_chat_and_evaluation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "config"
    shutil.copytree(REPO_CONFIG / "copilot", root / "copilot")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", root)
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "oqtopus")
    _reset()
    try:
        config = load_copilot_config()
        default_config = yaml.safe_load((REPO_CONFIG / "copilot" / "config.yaml").read_text())
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
    """The default models stay those of config/copilot/chat.yaml and evaluation.yaml."""
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", REPO_CONFIG)
    monkeypatch.delenv(COPILOT_PROFILE_ENV, raising=False)
    _reset()
    try:
        config = load_copilot_config()
    finally:
        _reset()
    chat = yaml.safe_load((REPO_CONFIG / "copilot" / "chat.yaml").read_text())
    evaluation = yaml.safe_load((REPO_CONFIG / "copilot" / "evaluation.yaml").read_text())

    assert [m.name for m in config.chat_models] == [m["name"] for m in chat["chat_models"]]
    assert [m.name for m in config.evaluation_models] == [
        m["name"] for m in evaluation["evaluation_models"]
    ]


def test_the_default_chat_model_is_native_openai_gpt_6_sol_and_qwen_stays_selectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The committed default chat runs GPT-6 Sol on OpenAI's own API, from the catalog."""
    from qdash.api.services import pi_chat_service
    from qdash.api.services.evaluation_service import planner_model_config
    from qdash.api.services.pi_chat_service import _request_payload
    from qdash.copilot.config.settings import select_chat_model
    from qdash.copilot.contracts.models import ChatRequest

    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", REPO_CONFIG)
    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: "")
    monkeypatch.delenv(COPILOT_PROFILE_ENV, raising=False)
    _reset()
    try:
        config = load_copilot_config()
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
    raw = yaml.safe_load((REPO_CONFIG / "copilot" / "chat.yaml").read_text())["chat_models"][0]
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
    raw_opus = yaml.safe_load((REPO_CONFIG / "copilot" / "chat.yaml").read_text())["chat_models"]
    assert [(m["provider"], m["name"]) for m in raw_opus] == [
        ("openai", "gpt-6-sol"),
        ("openai-compatible-chat", "qwen3.8-flash-next"),
        ("anthropic", "claude-opus-5-5"),
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

    # Planner-mode evaluations follow the default chat model; the evaluators do not change.
    assert planner == ({"provider": "openai", "name": "gpt-6-sol"}, "medium")
    assert config.evaluation_models[0].name == "nvidia/Ising-Calibration-1.5-31B-NVFP4"


def test_profile_model_strings_stay_literal(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(COPILOT_PROFILE_ENV, "site")
    monkeypatch.setenv("PROFILE_TEST_MODEL", "expanded-model")
    _write(
        config_dir / "copilot" / "profiles" / "site" / "chat.yaml",
        _chat("${PROFILE_TEST_MODEL}"),
    )

    assert load_copilot_config().chat_models[0].name == "${PROFILE_TEST_MODEL}"
