# Copilot Architecture

QDash Copilot is the chat assistant that helps experimentalists interpret qubit calibration
results. It owns the chat request path from the UI through the API to the Pi Agent Runtime
(`agent-runtime/`), the pi-qdash tools the runtime calls back into the API with, and the per-chat
[workspace](./workspace.md). Recorded figure judgments belong to
[Calibration Evaluation](./evaluation.md), agent-run calibration to the
[Agent Platform](./agent-platform.md), and model and endpoint settings to
[Copilot Model Configuration](./model-configuration.md).

<a id="two-modes"></a>
<a id="chat-about-a-task-result"></a>
<a id="chat-page"></a>

Every chat is the same planner on the same runtime, streamed to the browser over SSE. Chats differ
only in what they open with:

| Entry point | Request | Opening context | Typical question |
| --- | --- | --- | --- |
| Chat about a task result (**Ask AI** in a metrics modal, task history, or execution detail) | `POST /copilot/chat/stream` with `task: {task_name, chip_id, qid, execution_id, task_id}` | `TaskContext` (knowledge, qubit and coupling parameters, results, history, neighbors) and figures in the opening message | "Is this T1 result normal?" |
| Chat page (`/copilot`, `useCopilotChat`) | `POST /copilot/chat/stream` | Chip ID, optional qubit ID, scoring thresholds | "Compare T1 across all qubits" |
| Failure investigation | `POST /copilot/chat/stream` with `investigation` | Error message, stack trace, and source roots; see [Failure Investigations and Source Access](#failure-investigations-and-source-access) | "Why did this run fail?" |
| Forum AI reply | `thread_reply` / `complete_once` in `pi_chat_service.py` | The thread's history and its latest post | One planner turn per reply |

## Component Diagram

<Diagram name="copilot-architecture" caption="A Copilot turn: the API forwards it to the Agent runtime, whose tools call back into the API as the signed-in user." />

## Key Files

| File | Responsibility |
| --- | --- |
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
| `agent-runtime/src/evaluate.ts` | Planner-less evaluation of one task result: evidence tool, then `qcal_evaluate`, as one record |
| `src/qdash/api/services/evaluation_service.py` | Bulk evaluation runs: selection per chip, background execution through the runtime, records and verdicts |
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

`qdash_query` reads calibration configuration through `FileService`, not source. It redirects
source-looking requests to the source tools: `files_tree` with a path returns search guidance;
`file_content` returns read guidance only after HTTP 400 or 404. Config reads, other misses,
403, and server errors retain their behavior. See
[Fallback tools](../../reference/pi-qdash.md#fallback-tools) for the contract.

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

<a id="config-copilot"></a>
<a id="presentation-classifier"></a>
<a id="on-demand-classification"></a>
<a id="cloudflare-access-authentication"></a>
<a id="environment-variables"></a>

[Copilot Model Configuration](./model-configuration.md) covers models, endpoints, classifier tools,
gateway compatibility, and Cloudflare Access authentication.

## Developing a pi extension against the runtime

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

Checkout tools receive `modelRegistry` and the same context as pi-qdash tools. Their
`promptSnippet` and `promptGuidelines` appear under "Additional tools" in the system prompt.

For tools declaring `images`, the runtime supplies the newest durable conversation figure,
replacing any model-copied bytes. Supplied bytes are kept only when the conversation has no
figure.

For tools declaring `task_name` and `knowledge`, a named task without a supplied reference
triggers an authenticated `GET /tasks/{task_name}/knowledge`. The runtime fills `knowledge`
and, when declared, `criteria` from the derived reference, falling back to `prompt_text` cut
at 6000 characters. See [Calibration Evaluation](./evaluation.md#from-task-knowledge-to-the-prompt)
for derivation. `details.prompt` records the text sent to the evaluation model.

The runtime's `/chat` body carries two image lists: `initial_images` (the
task chat's opening figures, attached only when the conversation is new)
and `images` (attachments of the current turn, attached every time). The startup log lists loaded
extension paths and tools. Anything placed under `agent-runtime/extensions/` on the host is trusted
the same way, so keep that directory empty on production hosts.

## Evaluation runs

The chat is one entry point to the evaluation model; a bulk request from the
chip page is another, and a single task result a third. All three leave the
same record. The runtime's `POST /evaluate` route, the reference and examples
it fills in from the task knowledge, the record, runs and their comparison are
described in [Calibration Evaluation](./evaluation.md).
