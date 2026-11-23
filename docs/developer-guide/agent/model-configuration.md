# Agent Model Configuration

Agent declares models in `config/agent/` and reads endpoints and credentials from the environment.
For deployment steps, see [AI Setup](../../user-guide/setup/ai.md).

## Configuration Files

| File | Purpose |
| --- | --- |
| `config.yaml` | Shared Agent settings |
| `chat.yaml` | Chat models; first entry is the default |
| `evaluation.yaml` | Figure-evaluation models |
| `classifier.yaml` | Optional classifier models |

The API and runtime read the same model declarations. The runtime builds its registry at startup;
there is no `*.local.yaml` overlay. Keep credentials out of YAML and use environment references.

## Deployment Profiles

`QDASH_AGENT_PROFILE=<name>` replaces chat and evaluation files with
`config/agent/profiles/<name>/chat.yaml` and `evaluation.yaml`. Unset or empty selects the defaults.
Shared configuration and classifier settings do not change.

A profile must exist, remain within the profiles directory, and pass strict YAML/model validation.
It never falls back to defaults. Do not combine it with `CHAT_CONFIG_PATH` or
`EVALUATION_CONFIG_PATH`. Recreate the API and runtime together after changing profiles.

### Add a Profile

Copy `config/agent/profiles/oqtopus/`, choose a deployment name, and replace both model lists.
The supplied profile is a configuration example, not a tested serving deployment. Check its model
names, image support, context window, and output limits against your endpoint.

### Profile Model Rules

Use non-empty `provider` and `name`, numeric context/token limits, and actual YAML booleans.
`max_output_tokens` must be less than `num_ctx` when both are set. Duplicate model identities,
unknown fields, malformed documents, and missing chat models fail validation. An empty evaluation
list is allowed. Keep API and runtime validation aligned through `tests/data/agent_profile_cases.json`.

## Endpoint URLs and Provider Names

Custom API base URLs include `/v1`, not `/chat/completions` or `/responses`. Reference matching
`OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>` and `OPENAI_COMPATIBLE_API_KEY_<SUFFIX>` variables from each
model. Catalog providers use their own credentials; missing credentials never select another model.

## Gateway Compatibility Keys

Set compatibility flags only for a custom endpoint that needs them.

| Key | Purpose |
| --- | --- |
| `strict_tool_schemas` | Enable strict tool schemas on a compatible endpoint |
| `prompt_cache_key_mode` | `auto`, `enabled`, or `disabled` |
| `requires_non_null_assistant_content` | Send empty content for tool-only assistant messages |
| `requires_tools_with_tool_history` | Include an empty tools list when history contains tools |

The last two apply to completion-style APIs. Catalog models ignore custom gateway overrides.

## Presentation Classifier

The first usable model in `classifier.yaml` supplies `present_results` and `classify`. With no
usable declared model, neither tool is offered. Classification errors or ambiguous answers leave
the assistant to use text or another renderer; they do not authorize writes.

`present_results` chooses a layout from record shapes. `classify` answers a bounded choice question
from supplied facts. Neither verifies a model-authored fact against its original tool response.

## Cloudflare Access Authentication

Set both `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET`, or neither. The runtime applies them
to supported environment-referenced custom endpoints while preserving origin authentication.
Generated configuration stores environment references, never secret values.

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `QDASH_AGENT_PROFILE` | Select deployment profile |
| `AGENT_CONFIG_PATH` | Shared config path; defaults to `/app/config/agent/config.yaml` |
| `CHAT_CONFIG_PATH`, `EVALUATION_CONFIG_PATH` | Override default model paths; conflict with profiles |
| `CLASSIFIER_CONFIG_PATH` | Classifier file; defaults to `/app/config/agent/classifier.yaml` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Catalog provider credentials |
| `OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>`, `OPENAI_COMPATIBLE_API_KEY_<SUFFIX>` | Custom endpoint and key |
| `CLASSIFIER_BASE_URL`, `CLASSIFIER_API_KEY` | Supplied classifier endpoint and key; suffixed variants supported |

### Rename Earlier Variables

Rename `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` to their `_CHAT` variants,
and `VLLM_BASE_URL` / `VLLM_API_KEY` to the corresponding `OPENAI_COMPATIBLE_*_EVALUATION` names.
Add `/v1` to base URLs. Old `OLLAMA_*` variables have no special handling; reference a named
OpenAI-compatible endpoint instead.

### Rename Copilot Settings

Rename `QDASH_COPILOT_PROFILE` to `QDASH_AGENT_PROFILE`, `COPILOT_CONFIG_PATH` to
`AGENT_CONFIG_PATH`, and `config/copilot/` to `config/agent/`. Update explicit paths too.
Legacy names warn; conflicting non-empty old/new values fail. When `agent/` exists, it takes
precedence over `copilot/`.

## Implementation Files

Model translation lives in `agent-runtime/src/models-config.ts`. Profile rules live in
`agent-runtime/src/agent-profile.ts` and `src/qdash/common/config/agent_profile.py`.
Classifier loading lives in `agent-runtime/src/classifier-models.ts`.

Run `task ci-agent-runtime` and
`uv run pytest tests/qdash/common/config/test_agent_profile.py` after configuration changes. Include missing
credentials, invalid profiles, compatibility flags, and API/runtime parity.
