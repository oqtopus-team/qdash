# Copilot Architecture

## Overview

QDash Copilot is an AI-powered assistant that helps experimentalists interpret qubit calibration results. It provides two interaction modes:

1. **Analysis Sidebar** -- Task-scoped analysis within the metrics modal, providing contextual interpretation of individual calibration results (e.g., CheckT1, CheckRabi).
2. **Chat Page** -- A dedicated chat interface for chip-wide questions, cross-qubit comparisons, and exploratory data analysis.

Both modes use the same underlying LLM agent with tool-calling capabilities, sandboxed Python execution, and SSE streaming for real-time progress feedback.

## Component Diagram

![Copilot Architecture](../../diagrams/copilot-architecture.drawio.png)

## Key Files

| File | Responsibility |
|------|---------------|
| `src/qdash/api/routers/copilot.py` | FastAPI router with `/config`, `/analyze`, `/analyze/stream`, `/chat/stream` endpoints; SSE event generation via `SSETaskBridge` |
| `src/qdash/api/services/copilot_data_service.py` | Data loading service: `build_analysis_context()`, `build_images_sent_metadata()`, qubit/task/history queries, tool executor wiring |
| `src/qdash/api/lib/copilot_agent.py` | LLM agent: system prompt construction, OpenAI Responses API calls, tool call loop, response parsing |
| `src/qdash/copilot/` | Shared Copilot runtime used outside the API process, including workflow-side automatic review |
| `src/qdash/workflow/engine/task/ai_review.py` | Asynchronous task-result review hook that writes AI review notes to task history |
| `src/qdash/api/lib/copilot_sandbox.py` | Sandboxed Python execution: AST validation, restricted builtins, resource limits |
| `src/qdash/api/lib/copilot_analysis.py` | Pydantic models: `TaskAnalysisContext`, `AnalysisResponse`, `AnalysisContextResult`; request schemas |
| `src/qdash/api/lib/sse.py` | SSE utilities: `sse_event()` formatter, `SSETaskBridge` for queue-poll-heartbeat-drain pattern |
| `src/qdash/api/lib/copilot_config.py` | Configuration loader: `CopilotConfig`, `ModelConfig`, `ScoringThreshold` models; YAML loading with local override |
| `src/qdash/datamodel/task_knowledge.py` | `TaskKnowledge` model with domain-specific knowledge per calibration task |
| `config/copilot/config.yaml` | Shared enablement, language, and default model settings |
| `config/copilot/chat.yaml` | General chat models, prompt, initial message, and suggestions |
| `config/copilot/review.yaml` | Task result analysis models, scoring thresholds, and AI review prompts |
| `ui/src/hooks/useCopilotChat.ts` | React hook for the chat page: session management, SSE consumption, localStorage persistence |
| `ui/src/hooks/useAnalysisChat.ts` | React hook for the analysis sidebar: task-scoped SSE streaming, message management |
| `ui/src/components/features/chat/CopilotChatPage.tsx` | Chat page UI: session list, message rendering, blocks/chart display |
| `ui/src/components/features/metrics/AnalysisChatPanel.tsx` | Analysis sidebar UI within the metrics modal |

## Pi runtime authentication

The API forwards the authenticated user's access token and selected `X-Project-Id` to the Pi runtime on each chat or analysis turn, including approval responses. When no project header is supplied, it uses the user's default project. The internal `AGENT_RUNTIME_TOKEN` still authenticates API-to-runtime requests; user credentials travel in separate internal headers and are never added to model input or durable conversation state.

Each open conversation gets its own tool registry and a private temporary pi-qdash profile. Read tools, approved writes, and the Python sandbox use that user's credentials. The runtime overrides connection arguments supplied by a model or an older stored tool call and never falls back to `QDASH_API_TOKEN` or an administrator login. QDash API endpoints enforce the user's permissions.

The pinned pi-qdash version accepts a configuration file rather than an injected client. The runtime creates the profile in a private directory with a mode-0600 file and removes it when the conversation closes, including failures. Docker Compose mounts `/tmp` as tmpfs so these credentials do not enter the container's persistent filesystem. Deployments outside Compose should provide an equivalent memory-backed temporary directory. Automatic reviews use no QDash tools and need no user API token.

## Configuration

### `config/copilot/`

```yaml
# config.yaml
enabled: true
copilot_backend: pi       # Also requires COMPOSE_PROFILES=agent-runtime for Docker Compose

# Language settings
thinking_language: en      # Internal reasoning language
response_language: auto    # Follow the latest user message; use ja/en to pin it

# Model settings
model:
  provider: openai         # openai | ollama
  name: gpt-4.1
  temperature: 0.7
  max_output_tokens: 2048

# chat.yaml
chat_models:
  - provider: ollama
    name: gemma4:26b
    base_url: env:OLLAMA_BASE_URL
    api_key_env: OLLAMA_API_KEY
system_prompt: |
  You are QDash Copilot...

# review.yaml
# Metrics for chip health evaluation
evaluation_metrics:
  qubit: [qubit_frequency, anharmonicity, t1, t2_echo, ...]
  coupling: [zx90_gate_fidelity, bell_state_fidelity]

# Scoring thresholds per metric
scoring:
  t1:
    good: 50
    excellent: 100
    bad: 20
    unit: "μs"
    higher_is_better: true
  # ... (see config/copilot/review.yaml for full list)

# Task analysis settings
analysis:
  enabled: true
  multimodal: true
  max_expected_images: 2
  ai_review_max_expected_images: null
  ai_review_max_output_tokens: null
  ai_review_tasks: [CheckQubitSpectroscopy, CheckResonatorSpectroscopy]
  ai_review_message: >-
    Review this calibration result and attach a concise operational review note.
  max_conversation_turns: 10
```

Configuration is loaded via `ConfigLoader` by deep-merging `config.yaml`, `chat.yaml`, and
`review.yaml`. YAML string values support shell-style environment variable references such
as `${OPENAI_API_KEY}`, so environment-specific or sensitive values should be supplied
through environment variables instead of committed template files.

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication |
| `OLLAMA_BASE_URL` | Ollama / OpenAI-compatible server URL (default: `http://localhost:11434`) |
| `OLLAMA_API_KEY` | Optional API key for the Ollama / OpenAI-compatible server |
| `DS4_BASE_URL` | DeepSeek v4 OpenAI-compatible gateway base URL |
| `DS4_API_KEY` | DeepSeek v4 API key |
| `NEXT_PUBLIC_API_URL` | API base URL for frontend (default: `/api`) |
| `AGENT_RUNTIME_EXTENSION_PATHS` | Development only; local pi extension checkouts the Agent Runtime loads (see below) |

### Developing a pi extension against the runtime

The Agent Runtime image installs `@oqtopus-team/pi-qdash` at a pinned version
(`agent-runtime/Dockerfile`), so a published release is the only way an
extension normally reaches it. While developing another extension (for example
`pi-qcaleval`), clone it under `agent-runtime/extensions/` (gitignored) and start
the runtime with the override:

```bash
git clone https://github.com/orangekame3/pi-qcaleval.git agent-runtime/extensions/pi-qcaleval
docker compose -f compose.yaml -f compose.extensions.yaml up -d agent-runtime
```

`compose.extensions.yaml` mounts the directory at `/app/extensions` and sets
`AGENT_RUNTIME_EXTENSION_PATHS`, which the runtime passes to pi's resource loader as
additional extension paths. Any `docker compose up -d` without the `-f` pair
recreates the runtime without the checkout, so while developing an extension set
`COMPOSE_FILE=compose.yaml:compose.extensions.yaml` in `.env`; Compose then
applies the override to every invocation from the project directory. The checkout must use the pi package layout
(`package.json` with a `pi.extensions` manifest, like pi-qdash) and may depend only
on the packages the runtime already ships (`@earendil-works/pi-coding-agent`,
`typebox`), because its imports resolve from the runtime's `node_modules`.

A checkout is trusted by its path, not by tool name: every tool it defines is
offered to the model without the pi-qdash allowlist review
(`agent-runtime/src/allowed-tools.ts`), with three limits. The same trust applies
in production to the packages listed in `TRUSTED_EXTENSION_PACKAGES` (for example
`@orangekame3/pi-qcaleval`), which the image installs at a pinned version next to
pi-qdash in `agent-runtime/Dockerfile`; a package is added to that list only after
review, and the version pin is the release gate.

- An experimental write name (`EXPERIMENTAL_WRITE_TOOL_NAMES`) still needs
  `AGENT_RUNTIME_ENABLE_WRITE_TOOLS=true`, and then goes through the same
  approval card as the pinned tool.
- A checkout tool is rerun after an interrupted turn only when its pi
  `annotations.readOnlyHint` is `true`; other local tools are reported to the
  model as interrupted instead, so a side-effecting tool never runs twice.
- A checkout tool that reuses a pinned tool's name replaces the pinned
  implementation; the runtime logs the replacement at startup.

Checkout tools receive the same extension context as pi-qdash tools, including
`modelRegistry` for calling a model other than the conversation's. Their pi
`promptSnippet` and `promptGuidelines` are inlined into the system prompt under
"Additional tools", since the pi-qdash tool guide does not know them. A checkout
tool that declares an `images` parameter (for example `qcal_evaluate`) gets it
filled by the runtime when the model omits it: the newest figure in the
conversation, whether a user attachment or a figure a pi-qdash tool returned, is
taken from the durable transcript, so the model never has to copy image bytes
into a call.

The runtime's `/chat` body carries two image lists: `initial_images` (the
analysis sidebar's opening figures, attached only when the conversation is new)
and `images` (attachments of the current turn, attached every time). Restart the
runtime after editing the extension; the startup log lists the local paths and
the tools they contributed. Relative entries in `AGENT_RUNTIME_EXTENSION_PATHS`
resolve against the runtime's `AGENT_WORK_DIR`, as pi does; prefer absolute paths.

## Two Modes

### Analysis Sidebar

Activated from the metrics modal when viewing a specific task result (e.g., CheckT1 for qubit Q03).

- **Endpoint**: `POST /copilot/analyze/stream`
- **Hook**: `useAnalysisChat`
- **Context**: Full `TaskAnalysisContext` including task knowledge, qubit parameters, experiment results, historical data, neighbor qubit data, and coupling parameters
- **Use case**: "Is this T1 result normal?", "Why does the fit R² look low?"

### Chat Page

A standalone page (`/copilot`) for general questions about the calibration system.

- **Endpoint**: `POST /copilot/chat/stream`
- **Hook**: `useCopilotChat`
- **Context**: Chip ID, optional qubit ID, scoring thresholds
- **Use case**: "Compare T1 across all qubits", "Show me the frequency trend for Q16"
- **Sessions**: Persisted to localStorage with multi-session support

### Automatic AI Review

Automatic AI review attaches an LLM-generated operational review note to selected terminal task results after they are persisted. It is designed for tasks where visual or contextual review is valuable, but sending every calibration result to an LLM would be too slow or expensive.

For prompt and task-knowledge tuning, use the [AI review evaluation loop](./ai-review-evals.md) to capture a real task result once and replay it in either frozen-context or rebuilt-context mode.

- **Entry point**: `enqueue_ai_review_note()` in `src/qdash/workflow/engine/task/ai_review.py`
- **Trigger**: task-result history save paths in the workflow recorder and repository
- **Configuration**: `analysis.ai_review_tasks` and `analysis.ai_review_message` in `config/copilot/review.yaml`
- **Execution model**: asynchronous background thread pool, de-duplicated by `task_id`
- **Model selection**: `analysis_model`, then the first `analysis_models` entry, then the general `model`
- **AI review quality path**: automatic review inherits
  `analysis.max_expected_images` and the selected model's `max_output_tokens`
  by default. Set `analysis.ai_review_max_expected_images` or
  `analysis.ai_review_max_output_tokens` only for an explicit low-latency mode.
- **Storage**: task-result `user_note.content`, under a `## AI review` Markdown section
- **UI**: task detail modals render the note as Markdown; chip page badges are shown only when the review decision requires review

The hook is best effort. It must not block calibration progress and must not change the task outcome when the LLM request fails. Both successful and failed task results are eligible when the task name is listed in `ai_review_tasks`; running, pending, scheduled, and skipped results are ignored. Automatic review uses the current task result, current qubit parameters, task knowledge, figures, and reference images, but drops historical result runs from the prompt so the dashboard note is not framed as a past-history comparison.

For `CheckResonatorSpectroscopy`, QDash records one AI review note per MUX group. The representative result is the qid where `int(qid) % 4 == 0`; copied sibling resonator results are skipped to avoid duplicate LLM calls and duplicate notes.

For `CheckQubitSpectroscopy`, QDash applies a deterministic safety guard before
calling the VLM: if no f01-like output parameter is present, the note is marked
as `FAIL` / `NO_SIGNAL`. This avoids accepting an empty parameter update when a
compact local model returns an overly optimistic free-form response.

The expected review note begins with a compact review block:

```markdown
## AI review

**AI review**
- Decision: `PASS` | `PASS_WITH_NOTE` | `REVIEW` | `FAIL`
- Accepted parameter(s): ...
- Needs review: ...
- Primary reason: ...
- Recommended action: ...
```

The chip page badge logic intentionally does not mark every AI note. It marks only notes whose `Decision` is `REVIEW` or `FAIL`, or whose `Needs review` field is not `none`.
