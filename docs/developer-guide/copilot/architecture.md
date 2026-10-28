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
| `config/copilot/evaluation.yaml` | Evaluation model (calibration VLM) |
| `agent-runtime/src/evaluate.ts`                           | Planner-less evaluation of one task result: evidence tool, then `qcal_evaluate`, as one record                                     |
| `src/qdash/api/services/evaluation_service.py`             | Bulk evaluation runs: selection per chip, background execution through the runtime, records and verdicts                          |
| `ui/src/hooks/useCopilotChat.ts` | React hook for the chat page: session management, SSE consumption, localStorage persistence |
| `ui/src/contexts/ChatDockContext.tsx` | Where the chat is shown outside the chat page: the docked sidebar (`ChatSidebar`) or the floating window, and opening a chat about a task result |
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
Pi 1.3 cannot reopen an upgraded store. Back up the stopped volume before upgrading, and restore
that backup before a rollback to Pi 1.3. See [System Updates](../../user-guide/system-updates.md#deploy-the-release).

Each chat model in `config/copilot/chat.yaml` gets compaction thresholds based on its own context
window and output limit. `agent-runtime/src/models-config.ts` resolves those models at startup,
and `agent-runtime/src/budget.ts` calculates their thresholds. The runtime gives Pi 1.4 a
`modelOverrides` entry for each resolved model, so a resumed task uses the budget of the model it
started with even if the next request selects another model. The selected request model also gets
an entry when it is absent from the startup list.

Pi reports session failures, faulted or parked tasks, migrations, and extension errors through
`onReport`. `agent-runtime/src/durable-report.ts` logs the report type, task and extension names,
and error type under the hashed session filename. It omits error messages, prompts, tool
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

YAML string values support shell-style environment variable references such
as `${OPENAI_API_KEY}`, so environment-specific or sensitive values should be supplied
through environment variables instead of committed template files. The Pi runtime
builds its `models.json` from `chat_models` and `evaluation_models` at startup.

### Cloudflare Access Authentication

`agent-runtime/src/models-config.ts` maps the shared `CF_ACCESS_CLIENT_ID` and
`CF_ACCESS_CLIENT_SECRET` environment variables to Pi provider headers. It applies them to
endpoints whose `base_url` references `env:OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>`, for both chat
and evaluation. Literal URLs and catalog providers are unaffected.

The generated `models.json` stores environment references, not credential values. Pi 1.4.0
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
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | Shared Cloudflare Access service token for configured OpenAI-compatible endpoints; optional, set both |

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
