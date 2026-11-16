# Copilot Model Configuration

Copilot reads its chat, evaluation, and classifier models from `config/copilot/`, and their
endpoints and credentials from the environment. The Pi runtime turns these into its model
registry at startup. Operators set the endpoints as described in
[AI Setup](../../user-guide/setup/ai.md); the runtime that uses the models is described in
[Copilot Architecture](./architecture.md).

## Configuration Files

`ConfigLoader` deep-merges `config.yaml`, `chat.yaml`, and `evaluation.yaml` for the API; the Pi
runtime reads the same `chat.yaml` and `evaluation.yaml` for its models. A
[deployment profile](#deployment-profiles) replaces `chat.yaml` and `evaluation.yaml`. Neither
reads a `*.local.yaml` overlay. The runtime reads `classifier.yaml` separately; see
[Presentation Classifier](#presentation-classifier).

```yaml
# config.yaml
enabled: true
thinking_language: en      # Internal reasoning language
response_language: auto    # Follow the latest user message; use ja/en to pin it
task_chat:                 # How a chat about a task result opens
  multimodal: true
  max_expected_images: 2

# chat.yaml: the planner models every chat can use; the first is the default
chat_models:
  - provider: openai-compatible-chat
    name: qwen3.8-flash-next
    api_style: completion
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT
    api_key_env: OPENAI_COMPATIBLE_API_KEY_CHAT

# evaluation.yaml: models pi-qcaleval can use to judge calibration plots
evaluation_models:
  - provider: openai-compatible-evaluation
    name: nvidia/Ising-Calibration-1.5-31B-NVFP4
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_EVALUATION
    api_key_env: OPENAI_COMPATIBLE_API_KEY_EVALUATION
  - provider: openai-compatible-chat
    name: qwen3.8-flash-next
    base_url: env:OPENAI_COMPATIBLE_BASE_URL_CHAT
    api_key_env: OPENAI_COMPATIBLE_API_KEY_CHAT
```

YAML string values support shell-style environment variable references such as
`${OPENAI_API_KEY}`, so environment-specific or sensitive values come from environment
variables instead of committed files. The Pi runtime builds its `models.json` from `chat_models`
and `evaluation_models` at startup.

## Deployment Profiles

A deployment profile is a named pair of `chat.yaml` and `evaluation.yaml` that one deployment
uses instead of the default files, so sites that serve different models share one checkout.
`QDASH_COPILOT_PROFILE` selects it; the API and the Pi runtime resolve it with the same rules:

| `QDASH_COPILOT_PROFILE` | Chat and evaluation models from |
| --- | --- |
| Unset or empty | `config/copilot/chat.yaml` and `config/copilot/evaluation.yaml` |
| A profile name, such as `oqtopus` | `config/copilot/profiles/<name>/chat.yaml` and `evaluation.yaml` |

An empty value selects the defaults because a Compose `env_file` line `QDASH_COPILOT_PROFILE=`
passes an empty string. `config.yaml` and `classifier.yaml` stay shared by every profile. A
profile is named after the deployment, not after its models, and its files replace the default
files as a whole: no list is merged with the default one.

A named profile never falls back to the default files. The API and the runtime both fail with
a `CopilotProfileError` that names the variable or file when:

- the name does not match `^[a-z0-9][a-z0-9_-]{0,62}$`, which also rules out `/`, `..`, and
  surrounding whitespace;
- `profiles/<name>/` or either of its two files is missing;
- a file, after following symbolic links, lies outside `config/copilot/profiles/`;
- a file is not valid YAML, holds more than one document, or repeats a key;
- a file sets a top-level key other than `chat_models` (in `chat.yaml`) or `evaluation_models`
  (in `evaluation.yaml`);
- `chat_models` is empty. An empty `evaluation_models: []` is allowed and offers no evaluation
  model;
- an entry breaks a [profile model rule](#profile-model-rules), or repeats the `provider` and
  `name` of an earlier entry in the same file.

The error names the file, the entry index, and the field, such as
`chat_models[0].max_output_tokens must be a whole number`. The runtime fails at startup, before
it writes `models.json`; the API fails every Copilot request until the profile is fixed. The
default files keep their earlier handling: they are not checked field by field, and a missing
`evaluation.yaml` means no evaluation models. The runtime's `CHAT_CONFIG_PATH` and
`EVALUATION_CONFIG_PATH` overrides apply to the default files only and conflict with a profile.

The API reads the variable each time its cached configuration is rebuilt: at startup and after
`POST /admin/config/reload`. The runtime reads it once, at startup. A changed value reaches a
container only when the container is recreated, so both services are recreated together.

### Profile Model Rules

Without these checks, the API's `ModelConfig` coerces some values, such as the string `"4096"`,
that the runtime's `models.json` generation silently drops, so the two would run with different
settings. Every entry in a profile is therefore checked against one set of rules in both
runtimes, before either builds a model from it:

| Field | Accepted value |
| --- | --- |
| `provider`, `name` | Required non-empty string |
| `api_style` | `responses` or `completion` |
| `base_url` | `http://` or `https://` URL, or `env:NAME` |
| `api_key_env` | Environment variable name, such as `OPENAI_COMPATIBLE_API_KEY_CHAT` |
| `max_output_tokens` | Whole number of at least 1; less than `num_ctx` when both are set |
| `num_ctx` | Whole number of at least 1 |
| `temperature` | Finite number of at least 0 |
| `top_p` | Finite number greater than 0 and at most 1 |
| `top_k` | Whole number of at least -1 |
| `keep_alive` | Non-empty string, such as `30m` |
| `reasoning_effort` | `none`, `minimal`, `low`, `medium`, or `high` |
| `disable_thinking_instruction`, `strict_tool_schemas`, `requires_non_null_assistant_content`, `requires_tools_with_tool_history` | `true` or `false` |
| `prompt_cache_key_mode` | `auto`, `enabled`, or `disabled` |
| `sampling_params` | Mapping, passed to the request unchanged |
| `sampling_params_by_thinking_level` | Mapping from `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max` to a mapping |

A whole number may be written as `4096`, `4096.0`, or `4.096e3`, but not as a string, a boolean,
or a value beyond 2^53 - 1. Fields that `ModelConfig` allows to be null (`temperature`,
`base_url`, `api_key_env`, `keep_alive`, `num_ctx`, `top_p`, `top_k`, `reasoning_effort`) may be
left empty; any other empty field is an error. Any field not in the table is an error, which
catches a misspelled key such as `max_output_token`. `strict_tool_schemas` and the
[gateway compatibility keys](#gateway-compatibility-keys) require a `base_url`, and the two
`requires_*` keys are refused with `api_style: responses`.

The runtime parses YAML with the YAML 1.2 core schema; PyYAML implements YAML 1.1. The API
therefore reads profile files with a YAML 1.2 core loader that also refuses duplicate keys and
`<<` merge keys, so both runtimes see the same values: `yes` and `1_000` are strings, `010` is
ten, and `1e3` is a number. Profile strings are literal: shell-style variable
interpolation is not performed. Use `base_url: env:NAME` and `api_key_env: NAME` for endpoint
and credential references in both runtimes.

The rules check a profile's settings, not the serving API. Whether an endpoint serves the model
name, accepts images, or supports the configured context length and output limit is for the
operator to confirm against the deployment.

### Sample Profile

The supplied `profiles/oqtopus/` profile is a sample that names `Qwen/Qwen3.8-27B` for chat and
evaluation through `api_style: completion`, on the `CHAT` and `EVALUATION` endpoint variables.
No serving API has been tested with it. Its comments list what the deployment must provide: an
OpenAI-compatible Chat Completions API for that model name, image input for evaluation, and a
context length and output limit that cover `num_ctx` and `max_output_tokens`. Its
`temperature: 0.0` requests greedy sampling for evaluation; whether repeated runs then agree is
not verified. The profile sets no `reasoning_effort`, so the runtime does not mark the model as
a reasoning model or apply the Qwen chat-template thinking format to it. pi-qcaleval uses a
model whose id contains `Ising-Calibration` when the chat planner evaluates without naming a
model; in a profile without one, that evaluation runs on the conversation's model and is marked
as a fallback. Runs started from **AI Evaluations** pass the
selected model explicitly.

### Add a Profile

To add a profile for another deployment, such as `osaka`:

1. Copy `config/copilot/profiles/oqtopus/` to `config/copilot/profiles/osaka/`.
2. Replace the models in both files with the ones the deployment serves, and set `num_ctx` and
   `max_output_tokens` to what that deployment supports. Keep endpoints and keys in
   `OPENAI_COMPATIBLE_*_<SUFFIX>` variables; the files hold only their names.
3. Commit the directory with the rest of `config/`, or keep it untracked in the deployment's
   checkout: Compose mounts `./config`, so both work.
4. Select it as described in [AI Setup](../../user-guide/setup/ai.md#select-a-deployment-profile).

## Endpoint URLs and Provider Names

Custom OpenAI-compatible API base URLs must include `/v1`, for example
`https://models.example.com/v1`. Do not include an operation path such as
`/chat/completions` or `/responses`. The runtime passes the configured path to the model client
without adding `/v1`.

Name OpenAI-compatible endpoint variables with a descriptive suffix:
`OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>` and `OPENAI_COMPATIBLE_API_KEY_<SUFFIX>`.
The suffix is not predefined; choose one that identifies the endpoint or its purpose, then use
the exact variable names in `base_url: env:...` and `api_key_env`. The supplied templates use
`CHAT` and `EVALUATION`.

Give each endpoint a matching identifier with the form `openai-compatible-<suffix>` in its
`provider` field. This value is an endpoint identifier, not the serving software name: Pi uses it
as a key in the generated configuration. Endpoints with different base URLs must not share an
identifier. The supplied templates use `openai-compatible-chat` and
`openai-compatible-evaluation`.

The default chat model also appears in `evaluation_models`, which makes its evaluation role
explicit. When the same endpoint identifier and model name appear in both lists, the runtime keeps
the full definition from `chat_models`. Qwen reasoning models receive the Qwen chat-template
thinking format on that model only; other models sharing the endpoint keep their own response
format.

## Strict Tool Schemas

The `render_ui` tool asks Pi for strict JSON-schema sampling of its arguments with
`strict: "prefer"`. Catalog models whose Pi model data marks strict tools as supported, such as
OpenAI `gpt-5.4` and Bedrock Claude models, get `strict: true` and the strict schema. Pi
assumes custom OpenAI-compatible endpoints lack strict tools, so they get the schema without
enforcement and no `strict` field. Set `strict_tool_schemas: true` on a `chat_models` entry
with a `base_url` only when its server enforces OpenAI `strict` function schemas; the runtime
then writes `compat.supportsStrictMode: true` for that model. An endpoint that rejects the
`strict` field fails requests with the setting enabled, so leave it unset when support is
unknown.

## Gateway Compatibility Keys

Gateways and proxies in front of a custom endpoint sometimes expect a request shape that differs
from Pi's defaults. Three optional keys on a `chat_models` or `evaluation_models` entry with a
`base_url` set the matching Pi compat field for that model only. An unset key keeps Pi's
default, an explicit `false` is written as `false`, and catalog models ignore all three:

| Key | Values | Pi compat field | Effect |
| --- | --- | --- | --- |
| `prompt_cache_key_mode` | `auto`, `enabled`, `disabled` | `promptCacheKeyMode` | Whether requests carry `prompt_cache_key`, the conversation's provider session ID |
| `requires_non_null_assistant_content` | `true`, `false` | `requiresNonNullAssistantContent` | Replays an assistant message that holds only tool calls with `""` content instead of `null` |
| `requires_tools_with_tool_history` | `true`, `false` | `requiresToolsWithToolHistory` | Sends `"tools": []` when a request offers no tools but the history has tool calls, as some proxies in front of Anthropic require |

With `auto`, completions-style requests send `prompt_cache_key` only to `api.openai.com`, and
responses-style requests always send it. Use `enabled` for a proxy that routes or caches on the
key and `disabled` for an endpoint that rejects the field. Pi omits an empty `tools` array by
default because vLLM 0.20 and later reject it; set `requires_tools_with_tool_history: true` only
for a proxy that needs it. The two `requires_*` keys exist only for `api_style: completion`; the
runtime drops them on a responses-style endpoint. In the default files, an invalid value is
dropped with a startup warning that names the key and the model, not the value; a
[deployment profile](#profile-model-rules) refuses it.

## Presentation Classifier

`present_results` (`agent-runtime/src/presentation-tool.ts`) shows values the chat already read
as one of three fixed layouts, chosen by a classifier model through pi-ai `Models.classify`. The
chat passes the user's request, the names of the tools the values came from, and one record per
qubit, coupling, or execution. The classifier sees the request and the shape of the records
(subjects, value names, statuses, counts), never a value, and answers one choice question:

| Category | Layout built from the records |
| --- | --- |
| `calibration_summary` | Metric cards for one record; a table of records by value otherwise |
| `execution_comparison` | A table with one column per record and one row per value; needs 2 to 11 records |
| `failure_list` | An alert and a table of the records with status `failed` or `warning` |
| `text` | No UI; the chat answers in text |

The layout shows only the values passed, unchanged: a value name with one unit becomes a column
header such as `t1 (us)`, and mixed units stay with each cell. A muted line names the source
tools as reported by the chat; the runtime checks that they are tools the chat offers, not that
each value appears in their results. The block goes out as `details.ui`, the same `ui` event and
stored block `render_ui` produces.

The chosen category must have probability ≥0.6 and lead the runner-up by ≥0.2. These fixed
heuristics use `probabilities`, not the service-defined `confidence` score. Errors, cancellation,
a 5-second timeout, invalid or ambiguous answers, and incompatible records return no UI and tell
the chat to use `render_ui` or text.

The classifier runs as a nested call, `qdash.presentation.classify`, under a fixed key of the
replay-safe `present_results` call, so its result is journaled with the call. After a restart
the call reruns, gets the committed classification back, and rebuilds the same layout. The
nested tool is not replay-safe, so a classification a restart interrupted ends as an error and
falls back instead of asking the classifier again. The model is never offered the nested tool.

The classifier model comes from `config/copilot/classifier.yaml`, which lists the classifier
models any QDash feature can use, as `chat.yaml` and `evaluation.yaml` list theirs.
`agent-runtime/src/classifier-models.ts` reads the file at startup; a
missing file declares no models. A self-hosted System One (TypeSafe Jev) endpoint is declared
like an OpenAI-compatible model entry:

```yaml
classifier_models:
  - provider: system-one-classifier
    name: ZefanCai/Open-Jev-2B
    base_url: env:CLASSIFIER_BASE_URL
    api_key_env: CLASSIFIER_API_KEY
```

The runtime registers it as a Pi provider with pi-ai's `typesafe-system-one` API, which posts
`{ model, state, questions }` to `<base_url>/systemone` with `Authorization: Bearer` and takes
`name` as `model`. The base URL ends at the API version, such as
`https://classifier.example/v1`. Both `CLASSIFIER_BASE_URL` and `CLASSIFIER_API_KEY` come only
from `.env`; the repository sets no default endpoint. Name further endpoints' variables
`CLASSIFIER_BASE_URL_<SUFFIX>` and `CLASSIFIER_API_KEY_<SUFFIX>` and their provider
`system-one-<suffix>`; a provider id Pi already has is refused, so an endpoint never replaces or
falls through to a catalog provider. A classifier from Pi's catalog names only `provider` and
`name`, such as `typesafe` and `jev-latest`, and uses that provider's own credentials. A model
is unavailable, with the reason logged, when a variable is unset, the catalog model is unknown,
or its provider has no credentials. An invalid file is logged and declares nothing. Neither
stops the runtime. Variables are read for each request and never logged.

The runtime offers `present_results` and [`classify`](#on-demand-classification) with the
first model in `classifier_models` that is usable, in the listed order; a model the file does
not declare is never used. When the file is missing or invalid, or no declared model is usable,
the runtime registers neither tool and adds no prompt guideline, and the chat renders with
`render_ui` as before. No other setting turns the tools on or off. The supplied file declares
the System One model, so the tools are offered once `CLASSIFIER_BASE_URL` and
`CLASSIFIER_API_KEY` are set. The classifier is called only when the chat calls one of them, not
on every turn.

`agent-runtime/test/classifier-models.test.mjs` covers `classifier_models` without any feature.
`agent-runtime/test/presentation-tool.test.mjs` runs `present_results` in a Harness with a
mocked classifier for each outcome and across a restart, checks the supplied configuration, and
sends a System One request through a mocked `fetch` to check the URL, headers, and parsing of a
response the endpoint returned.

## On-demand Classification

`classify` (`agent-runtime/src/classify-tool.ts`) lets the chat ask the classifier model a
question it cannot settle from tool results or a simple rule. The prompt guideline,
`CLASSIFY_GUIDELINE`, tells the chat to call it at four kinds of decision point instead of
guessing:

| Use | Example question |
| --- | --- |
| Intent | Is an ambiguous message a status lookup, a trend, a comparison, or troubleshooting? |
| Cause triage | Do the statuses, messages, and values read point to readout, drive, frequency drift, or a fit failure? |
| Next investigation | Which of a few possible checks is most likely to explain the problem? |
| Presentation | Does a custom `render_ui` view, `render_chart`, or text suit values the fixed layouts do not cover? |

Skip classification when tool results, a threshold, status, or the user's words already decide.
Use `present_results` directly for its fixed layouts. Pass observed facts only; treat the
classification as evidence and disclose reliance on it. Ambiguity can prompt `ask_user`; errors
leave the decision with the chat. Classification neither renders a view nor approves a write.

| Argument | Bounds |
| --- | --- |
| `question` | 1 to 300 characters; sent as the choice question's `instructions` |
| `categories` | 2 to 8 entries of a snake_case `name` (up to 40 characters, distinct) and a `description` (up to 200 characters); sent as its `criteria` |
| `context` | 1 to 4,000 characters of facts from tool results or the user; sent as `state.context` |

`classify` uses the same probability and lead thresholds as `present_results`. It returns
`classified` or `ambiguous`, with the selected category, probability, lead, and all category
probabilities. An ambiguous answer remains available as weak evidence.

Failures return `failed` with one fixed reason: `classifier unavailable`,
`classifier request failed`, `cancelled`, `timed out after 5 s`, or `invalid classifier answer`.
Provider messages go only to runtime logs. The tool is not replay-safe; a restart-interrupted
call fails instead of requesting another classification.

The result's `details.classification` holds the classifier's `provider/model`, the outcome, and
those numbers, never the classifier's input. `events.ts` copies it onto the `classify` call's
`tool_end` as `classification`, and the API passes only the known fields, bounded. The chat
shows the call as an ordinary tool row: "Classifying" while it runs, then "Classified as
`<category>`", "Classification unclear", or "Classification failed", with an outcome badge, the
probability, the model, and every category's share on request. The question, categories, and
context appear in the row's details as the arguments. The trace stored with the answer keeps the
decision for a reload.

`agent-runtime/test/classify-tool.test.mjs` runs `classify` in a Harness with a mocked
classifier for each outcome and checks the stream and the bounds.

## Cloudflare Access Authentication

`agent-runtime/src/models-config.ts` maps the shared `CF_ACCESS_CLIENT_ID` and
`CF_ACCESS_CLIENT_SECRET` environment variables to Pi provider headers. It applies them to
endpoints whose `base_url` references `env:OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>`, for both chat
and evaluation, and to a [classifier model](#presentation-classifier) whose `base_url`
references `env:CLASSIFIER_BASE_URL` or `env:CLASSIFIER_BASE_URL_<SUFFIX>`. Literal URLs and catalog providers are unaffected.

The generated `models.json` stores environment references, not credential values. Pi
resolves these headers when making requests through `ModelRuntime`, including evaluation calls
through the model registry. Both Chat Completions and Responses preserve the origin server's
Bearer authentication alongside the two Access headers. With Access configured and no origin
API key, the runtime supplies Pi's required placeholder key automatically.

Setting only one Access variable, or a whitespace-only value, fails configuration rather than
sending partial authentication. Leaving both unset or empty preserves existing behavior.
`agent-runtime/test/cloudflare-access.test.mjs` captures requests from the installed Pi runtime
for both API styles and both model roles. Deployment steps are in
[Authenticate AI Endpoints with Cloudflare Access](../../user-guide/setup/ai.md#authenticate-ai-endpoints-with-cloudflare-access).

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `QDASH_COPILOT_PROFILE` | [Deployment profile](#deployment-profiles) for chat and evaluation models; unset or empty uses the default files |
| `OPENAI_API_KEY` | OpenAI API authentication |
| `OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>` | OpenAI-compatible API base URL through `/v1`; the suffix is operator-defined |
| `OPENAI_COMPATIBLE_API_KEY_<SUFFIX>` | API key for the endpoint with the matching suffix; it can be a placeholder for a keyless endpoint |
| `CLASSIFIER_BASE_URL` / `CLASSIFIER_BASE_URL_<SUFFIX>` | Classifier endpoint base URL through the API version, for `classifier.yaml`; no default. The supplied entry uses `CLASSIFIER_BASE_URL` |
| `CLASSIFIER_API_KEY` / `CLASSIFIER_API_KEY_<SUFFIX>` | Bearer token for the classifier endpoint with the matching name |
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | Shared Cloudflare Access service token for configured OpenAI-compatible and classifier endpoints; optional, set both |
| `NEXT_PUBLIC_API_URL` | API base URL for frontend (default: `/api`) |

### Rename Earlier Variables

Existing deployments must rename the earlier fixed variables and add `/v1` to each base URL:

| Earlier variable | Replacement in the supplied configuration |
| --- | --- |
| `OPENAI_COMPATIBLE_BASE_URL` | `OPENAI_COMPATIBLE_BASE_URL_CHAT` |
| `OPENAI_COMPATIBLE_API_KEY` | `OPENAI_COMPATIBLE_API_KEY_CHAT` |
| `VLLM_BASE_URL` | `OPENAI_COMPATIBLE_BASE_URL_EVALUATION` |
| `VLLM_API_KEY` | `OPENAI_COMPATIBLE_API_KEY_EVALUATION` |

`OLLAMA_BASE_URL` and `OLLAMA_API_KEY` no longer have special meaning. If that endpoint remains
in use, choose a suffix such as `OLLAMA`, name its variables
`OPENAI_COMPATIBLE_BASE_URL_OLLAMA` and `OPENAI_COMPATIBLE_API_KEY_OLLAMA`, and reference them from
the corresponding YAML model. Variable renaming does not transform the URL: for example, migrate
`http://ollama:11434` to `http://ollama:11434/v1`.

## Implementation Files

- `src/qdash/copilot/config/settings.py`: `CopilotConfig` and `ModelConfig`
- `src/qdash/common/config/loader.py` and `copilot_profile.py`: `ConfigLoader.load_copilot` and
  profile selection for the API
- `agent-runtime/src/copilot-profile.ts`: profile selection and validation for the runtime; keep
  its rules and messages in step with `copilot_profile.py`.
  `tests/data/copilot_profile_cases.json` holds the names, model fields, and documents both test
  suites check
- `agent-runtime/src/models-config.ts`: `models.json` generation, compat fields, and Cloudflare
  Access headers
- `agent-runtime/src/classifier-models.ts`: `classifier_models` loading and selection
- `agent-runtime/src/presentation-tool.ts`: `present_results`
- `agent-runtime/src/classify-tool.ts`: `classify`
- `config/copilot/config.yaml`, `chat.yaml`, `evaluation.yaml`, `classifier.yaml`,
  `profiles/oqtopus/`: supplied configuration
