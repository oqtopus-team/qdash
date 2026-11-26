# Agent Architecture

QDash Agent connects the chat UI to a durable Pi runtime and calls QDash tools as the signed-in user.
For operating the assistant, see [Agent](../../user-guide/ai-chat.md).

## Component Diagram

<Diagram name="agent-architecture" caption="The API forwards a chat turn to the runtime; tools call QDash with the user's project and permissions." />

## Pi runtime authentication

The API forwards the user's access token and selected project on every turn, including approval
responses. Without a project header, it uses the user's default project. A separate internal
secret authenticates API-to-runtime requests. Neither credential belongs in model input or
conversation storage.

Compose's `agent-runtime-auth` service creates the shared secret in a dedicated volume. The API
and runtime read it through `AGENT_RUNTIME_TOKEN_FILE`.

## Durable conversations

The runtime stores conversations in SQLite under `agent-runtime-state`. Branches share the source
store and workspace. Disconnecting the browser does not stop a turn; stopping and reconnecting
use explicit turn IDs. See [Chat Streaming](./chat-streaming.md).

Back up the state volume before upgrading Pi: opening an older store can migrate its schema,
and restoring an older runtime may require restoring that backup.

## Code Mode and deferred tools

`codemode` composes tool calls in JavaScript; `tool_search` discovers deferred tools. Their policy
still enforces tool visibility and write approvals. Shell and file operations run in the separate
[workspace](./workspace.md), never in the runtime process.

<a id="two-modes"></a>
<a id="chat-about-a-task-result"></a>
<a id="chat-page"></a>

## Page context and editor edits

A turn can include the open page and unsaved editor text. Proposed edits change the editor only
when accepted; saving or executing remains a separate action. Failure investigations load their
evidence through project-authorized API reads.

<a id="config-agent"></a>
<a id="presentation-classifier"></a>
<a id="on-demand-classification"></a>
<a id="cloudflare-access-authentication"></a>
<a id="environment-variables"></a>

## Configuration

Model selection belongs to [Model Configuration](./model-configuration.md). Task knowledge and
shared instructions belong to [Knowledge Layout](./knowledge-layout.md). Recorded figure
judgments belong to [Calibration Evaluation](./evaluation.md).

## Developing a pi extension against the runtime

Follow [package setup](./packages.md#development) before editing the bundled packages.
Run `task ci-pi-packages` and `task ci-agent-runtime`, then rebuild:

```bash
docker compose up -d --build agent-runtime
```

The runtime loads the bundled extensions with their tool allowlist and approval boundary.
See [Pi Extension Design](./extensions.md) before adding tools.

## Key Files

| File | Responsibility |
| --- | --- |
| `src/qdash/api/routers/agent.py` | Authenticated chat routes |
| `src/qdash/api/services/pi_chat_service.py` | API-to-runtime bridge |
| `src/qdash/api/services/runtime_presentation.py` | Validated presentation relay and evaluation recording |
| `agent-runtime/src/presentation.ts` | Chat presentation events and answer blocks |
| `agent-runtime/src/runtime.ts` | Durable sessions and runtime lifecycle |
| `agent-runtime/src/chat-registry.ts` | Per-chat tools, context, and policy |
| `agent-runtime/src/page-context.ts` | Page context and edit proposals |
