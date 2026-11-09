# Copilot Architecture

## Responsibility Boundary

QDash Copilot is an AI-powered assistant that helps experimentalists interpret qubit calibration results. It provides two interaction modes:

1. **Chat about a task result** (sidebar or floating window) -- Opened from a task result with that result's context and figures, for questions about one calibration result (e.g., CheckT1, CheckRabi).
2. **Chat Page** -- A dedicated chat interface for chip-wide questions, cross-qubit comparisons, and exploratory data analysis.

Both are the same chat with the same planner; the first just opens with a task result as its context. The evaluation model's recorded judgements are a separate thing (see [Calibration Evaluation](./evaluation.md)). Forum AI replies are one planner turn each on the same runtime.

Both run on the Pi Agent Runtime (`agent-runtime/`) with the pi-qdash tools, a shell and files per conversation in a separate container (the [workspace](./workspace.md)), and SSE streaming for progress.

## Component Diagram

<Diagram name="copilot-architecture" caption="A Copilot turn: the API forwards it to the Agent runtime, whose tools call back into the API as the signed-in user." />

## Key Files

| File | Responsibility |
|------|---------------|
| `src/qdash/api/routers/copilot.py` | FastAPI router with `/config`, `/chat/stream` (general and task chats), chat sessions |
| `src/qdash/copilot/runtime.py` | Data loading: `build_task_context()`, `build_images_sent_metadata()`, qubit/task/history queries |
| `src/qdash/api/services/pi_chat_service.py` | Runtime bridge: request payloads, the task chat's opening message and figures, NDJSON to SSE translation, `thread_reply` / `complete_once` for forum reply turns |
| `src/qdash/copilot/` | Shared Copilot runtime used outside the API process |
| `agent-runtime/src/exec-env.ts` | The workspace: one `agent-exec` connection per conversation behind `bash`, `read`, `write`, `edit` |
| `src/qdash/copilot/contracts/models.py` | Pydantic models: `TaskContext`, `TaskContextBundle`, `ChatRequest` (with `task`); request schemas |
| `src/qdash/api/lib/sse.py` | SSE utilities: `sse_event()` formatter |
| `src/qdash/copilot/config/settings.py` | Configuration loader: `CopilotConfig`, `ModelConfig`, `TaskChatConfig`; YAML loading with local override |
| `src/qdash/datamodel/task_knowledge.py` | `TaskKnowledge` model with domain-specific knowledge per calibration task |
| `config/copilot/config.yaml` | Enablement, languages, how a task chat opens |
| `config/copilot/chat.yaml` | Planner models for every chat |
| `config/copilot/classifier.yaml` | Optional classifier models any feature can use; the first usable one is used |
| `agent-runtime/src/classifier-models.ts` | Reads `classifier_models`, registers System One endpoints as Pi providers, and selects a feature's model |
| `agent-runtime/src/presentation-tool.ts` | `present_results`: classifier-chosen layouts of values the chat passes, offered when a classifier is usable |
| `agent-runtime/src/classify-tool.ts` | `classify`: the chat asks the classifier to pick one of the categories it defines, offered when a classifier is usable |
| `config/copilot/evaluation.yaml` | Evaluation model (calibration VLM) |
| `agent-runtime/src/evaluate.ts`                           | Planner-less evaluation of one task result: evidence tool, then `qcal_evaluate`, as one record                                     |
| `src/qdash/api/services/evaluation_service.py`             | Bulk evaluation runs: selection per chip, background execution through the runtime, records and verdicts                          |
| `ui/src/hooks/useCopilotChat.ts` | React hook for the chat page: session management, SSE consumption, localStorage persistence |
| `ui/src/contexts/ChatDockContext.tsx` | Where the chat is shown outside the chat page: the docked sidebar (`ChatSidebar`) or the floating window, and opening a chat about a task result or a failure investigation |
| `src/qdash/api/services/copilot_investigation_service.py` | An investigation's opening message from project-scoped logs |
| `src/qdash/api/services/source_access_service.py` | Read-only source roots, search, and reads for the source tools |
| `ui/src/components/features/chat/CopilotChatPage.tsx` | Chat page UI: session list, message rendering, blocks/chart display |

## Pi runtime authentication

The API forwards the authenticated user's access token and selected `X-Project-Id` to the Pi runtime on each chat or analysis turn, including approval responses. When no project header is supplied, it uses the user's default project. An internal bearer secret authenticates API-to-runtime requests; user credentials travel in separate internal headers and are never added to model input or durable conversation state.

Compose starts the runtime and workspace by default. The `agent-runtime-auth` initialization
service generates a random secret once in a dedicated volume, mounted read-only by the API and
runtime. Both read `AGENT_RUNTIME_TOKEN_FILE`; no manual secret or UI enable flag is needed.
The file is owned by the runtime user (UID 1000) with mode `0400`; the API reads it as root.
For standalone processes, provide the same credential file through `AGENT_RUNTIME_TOKEN_FILE`
or set `AGENT_RUNTIME_TOKEN` on both processes. The explicit token takes precedence for existing
deployments. Missing or empty credentials never permit unauthenticated runtime requests.

Each open conversation gets its own tool registry and a private temporary pi-qdash profile. Read tools and approved writes use that user's credentials; the workspace container never sees them. The runtime overrides connection arguments supplied by a model or an older stored tool call and never falls back to `QDASH_API_TOKEN` or an administrator login. QDash API endpoints enforce the user's permissions.

The pinned pi-qdash version accepts a configuration file rather than an injected client. The runtime creates the profile in a private directory with a mode-0600 file and removes it when the conversation closes, including failures. Docker Compose mounts `/tmp` as tmpfs so these credentials do not enter the container's persistent filesystem. Deployments outside Compose should provide an equivalent memory-backed temporary directory.

## Durable conversations

`agent-runtime/src/runtime.ts` opens one Pi SQLite store per user and session in the
`agent-runtime-state` volume. Pi 1.4 upgrades existing stores to schema version 2 on first open;
Pi 1.3 cannot reopen an upgraded store. Pi 1.5 keeps that schema but stores the `pi.live`,
`pi.tool`, and `pi.generation` documents at new versions when a conversation is next written; Pi 1.4
cannot read such a conversation and leaves its tasks blocked. Back up the stopped volume before
upgrading, and restore that backup before a rollback to the earlier Pi release. See
[System Updates](../../user-guide/system-updates.md#deploy-the-release).

Each chat model in `config/copilot/chat.yaml` gets compaction thresholds based on its own context
window and output limit. `agent-runtime/src/models-config.ts` resolves those models at startup,
and `agent-runtime/src/budget.ts` calculates their thresholds. The runtime gives Pi a
`modelOverrides` entry for each resolved model, so a resumed task uses the budget of the model it
started with even if the next request selects another model. The selected request model also gets
an entry when it is absent from the startup list.

Pi reports storage failures, faulted or interrupted tasks, migrations, and extension errors through
`onReport`. `agent-runtime/src/durable-report.ts` logs the report kind as `type`, the task and
extension names, the reason and restart count, and the error type under the hashed session filename. It omits error messages, prompts, tool
arguments, and user identifiers from these logs.

## Page context and editor edits

A chat from the sidebar or the floating window tells the assistant what the user has open.
Every turn carries `ChatRequest.page` (`PageContext`: route, title, and on the Workflow editor
the flow's name, chip, and the editor's current text, unsaved changes included); the runtime
rebuilds a system prompt section from it each turn (`agent-runtime/src/page-context.ts`,
`buildPageContextSection`). The chat page itself sends none.

Pages register what they show with the chat dock (`ChatDockContext.registerPage`): the
registration reads the page's state when a turn is sent, so an editor's buffer is current, and
may accept code back (`applyCode`). Without a registration the dock sends the route and the
document title.

On the Workflow editor the runtime also offers `propose_code_edit`: the model passes the
complete new file and a one-line summary, the call ends the turn, and the chat renders an
`edit` block (`EditProposalCard`) with a diff against what the editor holds now. **Apply to
editor** replaces the buffer and unlocks the editor; saving stays with the user and goes through
the editor's Save, so `POST /flows` validation and deployment registration are unchanged. The
runtime never writes the flow; `qdash_save_flow` stays for flows written from the chat alone.

## Failure investigations and source access

**Investigate with AI** starts a chat that diagnoses a failed execution or task. The browser only
names the failure: `ChatRequest.investigation` (`InvestigationTarget`) carries the execution ID
and, optionally, the task ID, task name, qid, and chip. `chat_stream` checks project access
with `get_project_context` before it streams. `CopilotInvestigationService.build`
(`src/qdash/api/services/copilot_investigation_service.py`) then loads the execution and task
result from that project. It builds the opening message from the error message and stack trace,
the source roots and their revisions, and the instructions: start at the raising frame, stop
once the evidence explains the error, and answer with a likely cause, evidence, and one next
step. A task without a result uses the execution's own task record. Long logs are clipped to their start and end. `pi_chat_service.stream`
sends the opening as `initial_message`, which the runtime uses only for a new conversation. An
unknown execution answers 404; `task` and `investigation` together answer 400.

The UI starts it with `ChatDockContext.investigate(target, surface)`. Execution pages, task
details, and the task result preview pass `"mini"`, the floating window, because they already
sit in a drawer or modal; the task result page uses the sidebar. The dock shows one surface at a
time: opening either closes the other. The click handler creates the session, with
`context: {investigation}` stored server-side, and sends the first turn once. A second click for
the same failure resumes that session, including after a reload, where the most recently updated
match wins. **New chat** from an investigation calls `ChatDockContext.endInvestigation`, so the
next click for that failure creates a fresh session and leaves the old one in the history; the
ended set lives in the tab and is not restored after a reload. A resumed session that loads with
no messages gets the first turn sent again. The first turn and retries of that turn carry `investigation`. Follow-ups use the existing
conversation without reloading the execution, so they can continue after the execution record is removed. The session's
`context` stays null, so task chats and their lookup are unchanged.

The model reads code through three read-only pi-qdash tools backed by `GET /copilot/source/roots`,
`/copilot/source/search`, and `/copilot/source/file`. `SourceAccessService`
(`src/qdash/api/services/source_access_service.py`) serves fixed roots and nothing else:

| Root | Location | Revision |
| --- | --- | --- |
| `qdash` | `QDASH_SOURCE_ROOT`, else the imported `qdash` package | `QDASH_SOURCE_REVISION`, else `git rev-parse HEAD` with a dirty flag, else unknown |
| Dependencies in `QDASH_SOURCE_DEPENDENCIES` (default `qubex,qubecalib`) | The package installed in the API process; reported missing when absent | `commit_id` from the distribution's `direct_url.json`, else unknown |

Paths resolve inside a root. Hidden entries, `__pycache__`, virtual environments, symlinks that
leave the root, and `workflow/user_flows` (per-project flows, read through the flow API) are
refused. Only text source suffixes (`.py`, `.toml`, `.yaml`, `.md`, and similar) are served. A
search is literal, capped at 200 matches and 20,000 files; a read returns at most 400 lines of a
file under 1 MB. The routes require a signed-in user; source is the same for every project.

`SourceAccessService.locate` maps a traceback path when `qdash_read_source` gets no root.
It first matches configured root directories, preferring the most specific directory when roots
overlap. This preserves editable dependency checkouts nested beneath a QDash checkout.
For other paths under `site-packages` or `dist-packages`, the next segment names the package;
a package that is not a root is not mapped. Elsewhere the `qdash` root is tried before dependencies, using its last
segment in the path: `/app/qdash/workflow/calibtasks/qubex/base.py` is
`qdash:workflow/calibtasks/qubex/base.py`, not a file of the qubex package.

QDash does not record the revision an execution ran with. The opening message and
`qdash_list_source_roots` say so, and the prompt tells the model not to claim that served source
matches the failed run.

The `qdash_query` actions `files_tree` and `file_content` read the calibration config directory
through `FileService`, not source. The opening message and the `qdash_query` description say so.
`qdash_query` does not read source for these actions; it returns the source tool call to use:

- `files_tree` with a `path` lists nothing. The result names `qdash_list_source_roots` and
  `qdash_search_source`. For a file path, the suggested search uses its filename across the
  source root so a missing parent directory does not exclude a relocated file. Directory paths
  retain their search prefix. A renamed file may require a different search term.
- `file_content` returns matching `qdash_read_source` arguments after HTTP 400 or 404
  only for source-looking paths: Python files, installed-package paths, paths starting with
  a source root name, or absolute paths containing a source root name.
  Config files, other misses, 403, and server errors behave as before.

When a source endpoint returns a generic 404, `qdash_read_source` reports that the endpoint
may be unavailable and suggests checking API routing, proxy configuration, and the API image
version.

Compose mounts `./src/qdash` read-only at `/app/source/qdash` on the API,
with `CALIBTASKS_PATH` over its `workflow/calibtasks`, and sets `QDASH_SOURCE_ROOT`. The API
image does not install qubex, so in Compose qubex source is reported unavailable. Set
`QDASH_SOURCE_REVISION` in `.env` to report the deployed commit, because the mount has no `.git`.

Tests: `tests/qdash/api/services/test_source_access_service.py`,
`test_copilot_investigation_service.py`, `tests/qdash/api/routers/test_copilot_investigation.py`,
`packages/pi-qdash/tests/source-code-tool.test.mjs`, `query-source-guidance.test.mjs`,
`ui/src/contexts/__tests__/ChatDockInvestigation.test.tsx`, and the execution page tests
`ExecutionPageContent.test.tsx` and `ExecutionClient.test.tsx`.

## Configuration

### `config/copilot/`

Three small files, each with an optional `*.local.yaml` overlay, deep-merged by `ConfigLoader`:

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

The `render_ui` tool asks Pi for strict JSON-schema sampling of its arguments with
`strict: "prefer"`. Catalog models whose Pi model data marks strict tools as supported, such as
OpenAI `gpt-5.4` and Bedrock Claude models, get `strict: true` and the strict schema. Pi
assumes custom OpenAI-compatible endpoints lack strict tools, so they get the schema without
enforcement and no `strict` field. Set `strict_tool_schemas: true` on a `chat_models` entry
with a `base_url` only when its server enforces OpenAI `strict` function schemas; the runtime
then writes `compat.supportsStrictMode: true` for that model. An endpoint that rejects the
`strict` field fails requests with the setting enabled, so leave it unset when support is
unknown.

YAML string values support shell-style environment variable references such
as `${OPENAI_API_KEY}`, so environment-specific or sensitive values should be supplied
through environment variables instead of committed template files. The Pi runtime
builds its `models.json` from `chat_models` and `evaluation_models` at startup.

### Presentation classifier

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

The decision reads the answer's `probabilities` only. The chosen category is accepted when its
probability is at least 0.6 and leads the runner-up by at least 0.2. With four categories an uninformed answer gives each 0.25, so the defaults ask
for a clear majority; they are heuristics, not calibrated accuracy, and are not configurable. The answer's `confidence`
is a separate service-defined score and is not used. An error, abort, or timeout
(5 seconds), an invalid answer, an ambiguous one, or records the layout cannot
hold give no UI and a result telling the chat to use `render_ui` or text; the turn continues.

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

### On-demand classification

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

The guideline keeps the rest with the chat. The chat skips `classify` when a tool result, a
threshold, a status, or the user's words already decide. It calls `present_results` directly
for the fixed layouts, so a layout is classified once. It passes only facts it read, and the
classifier supplies no value to show. The answer is evidence, not authority: the chat weighs
it against the data and says when it relies on it. An `ambiguous` answer counts as weak
evidence or prompts `ask_user`, and the chat decides itself when the call fails. A
classification never approves a write tool or replaces its approval card. The call shows nothing
but its own step and renders no view.

| Argument | Bounds |
| --- | --- |
| `question` | 1 to 300 characters; sent as the choice question's `instructions` |
| `categories` | 2 to 8 entries of a snake_case `name` (up to 40 characters, distinct) and a `description` (up to 200 characters); sent as its `criteria` |
| `context` | 1 to 4,000 characters of facts from tool results or the user; sent as `state.context` |

The decision reads the answer's `probabilities` only, as for `present_results`. The outcome is
`classified` when the chosen category's probability is at least 0.6 and leads the runner-up by
at least 0.2, and `ambiguous` otherwise; an ambiguous answer is still returned, and the result
tells the chat to treat it as weak evidence or ask the user. Either way the chat gets the
category, its probability and lead, and every category's probability. An unavailable model, an
error, cancellation, a timeout (5 seconds), or a malformed answer ends the call as an error with
outcome `failed` and one fixed reason (`classifier unavailable`, `classifier request failed`,
`cancelled`, `timed out after 5 s`, or `invalid classifier answer`). The provider's own message
goes only to the runtime log. The tool is not replay-safe, so a call a restart interrupted ends
as an error rather than asking the classifier again.

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

### Cloudflare Access Authentication

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
[Configure AI](../../user-guide/setup.md#configure-ai).

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication |
| `OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>` | OpenAI-compatible API base URL through `/v1`; the suffix is operator-defined |
| `OPENAI_COMPATIBLE_API_KEY_<SUFFIX>` | API key for the endpoint with the matching suffix; it can be a placeholder for a keyless endpoint |
| `CLASSIFIER_BASE_URL` / `CLASSIFIER_BASE_URL_<SUFFIX>` | Classifier endpoint base URL through the API version, for `classifier.yaml`; no default. The supplied entry uses `CLASSIFIER_BASE_URL` |
| `CLASSIFIER_API_KEY` / `CLASSIFIER_API_KEY_<SUFFIX>` | Bearer token for the classifier endpoint with the matching name |
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | Shared Cloudflare Access service token for configured OpenAI-compatible and classifier endpoints; optional, set both |
| `NEXT_PUBLIC_API_URL` | API base URL for frontend (default: `/api`) |

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

### Developing a pi extension against the runtime

The Agent Runtime image includes `packages/pi-qdash/` and `packages/pi-qcaleval/`
from the same QDash checkout. Edit those packages, run `task ci-pi-packages` and
`task ci-agent-runtime`, then rebuild the runtime:

```bash
bun install --frozen-lockfile
docker compose up -d --build agent-runtime
```

The root Bun workspace locks the runtime, TypeScript client, and two pi packages
together. The image builds the local client before loading the extensions.
The runtime loads their tools and skills directly; npm publication is not needed
for QDash development or deployment. [Pi packages](./packages.md) describes
independent distribution and release validation.

`compose.yaml` also mounts `agent-runtime/extensions/` at `/app/extensions`
(read-only) for additional development extensions. At startup, each subdirectory
with a `pi` manifest is loaded. A checkout whose package name matches a bundled
package replaces that package's tools and skills. Install any extra dependencies
inside the checkout before starting the container, and restart the runtime after
editing it. The image does not copy this gitignored directory.

The bundled pi-qdash package and overrides of it retain the per-name allowlist
in `agent-runtime/src/allowed-tools.ts`. The bundled pi-qcaleval package is trusted
as a whole. Additional checkouts are trusted by path, with these limits:

- Reviewed write names (`REVIEWED_WRITE_TOOL_NAMES`) still require approval of
  their arguments and execute with the requesting user's credentials.
- A checkout tool is replayed after interruption only when its
  `annotations.readOnlyHint` is `true`.
- A trusted checkout that reuses a bundled tool's name replaces it, with a
  replacement message in the startup log.

Checkout tools receive the same extension context as pi-qdash tools, including
`modelRegistry` for calling a model other than the conversation's. Their pi
`promptSnippet` and `promptGuidelines` are inlined into the system prompt under
"Additional tools", since the pi-qdash tool guide does not know them. A checkout
tool that declares an `images` parameter (for example `qcal_evaluate`) gets it
filled by the runtime: the newest figure in the conversation, whether a user
attachment or a figure a pi-qdash tool returned, is taken from the durable
transcript, so the model never has to copy image bytes into a call. Bytes the
model copies anyway are replaced by that figure, since a retyped base64 string
is usually corrupt; they are kept only when the conversation holds no figure.

A checkout tool that declares `task_name` and `knowledge` parameters (again
`qcal_evaluate`) gets `knowledge` filled the same way: when the model names the
task and passes no reference of its own, the runtime fetches the task's
knowledge from the QDash API as the user (`GET /tasks/{task_name}/knowledge`)
and passes its `reference`: the experiment background as `knowledge` (a few
sentences: what the experiment does, what the expected plot looks like) and,
when the tool declares it, `criteria` (the parameters to extract and the
status codes with their criteria, derived from the task's Common failures).
A task without a derived reference gets its full `prompt_text`, cut at 6000
characters. Every evaluation of a task is thus read against the same
host-maintained reference, kept in the task knowledge repository, rather than
against a summary the planner improvised. The exact text the evaluation model
received is stored in the tool result's `details.prompt`.

The runtime's `/chat` body carries two image lists: `initial_images` (the
task chat's opening figures, attached only when the conversation is new)
and `images` (attachments of the current turn, attached every time). Restart the
runtime after editing the extension; the startup log lists the local paths and
the tools they contributed. Anything placed under `agent-runtime/extensions/` on
the host is trusted the same way, so keep that directory empty on production hosts.

## Evaluation runs

The chat is one entry point to the evaluation model; a bulk request from the
chip page is another, and a single task result a third. All three leave the
same record. The runtime's `POST /evaluate` route, the reference and examples
it fills in from the task knowledge, the record, runs and their comparison are
described in [Calibration Evaluation](./evaluation.md).

## Two Modes

### Chat about a task result

Opened from a task result (metrics modal, task history, execution detail) with "Ask AI".

- **Endpoint**: `POST /copilot/chat/stream` with `task: {task_name, chip_id, qid, execution_id, task_id}`
- **Context**: Full `TaskContext` including task knowledge, qubit parameters, experiment results, historical data, neighbor qubit data, and coupling parameters, rendered into the opening message together with the result's figures
- **Use case**: "Is this T1 result normal?", "Why does the fit R² look low?"

### Chat Page

A standalone page (`/copilot`) for general questions about the calibration system.

- **Endpoint**: `POST /copilot/chat/stream`
- **Hook**: `useCopilotChat`
- **Context**: Chip ID, optional qubit ID, scoring thresholds
- **Use case**: "Compare T1 across all qubits", "Show me the frequency trend for Q16"
- **Sessions**: Persisted to localStorage with multi-session support
