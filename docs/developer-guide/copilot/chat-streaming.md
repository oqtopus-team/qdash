# Chat Streaming

QDash translates the Agent Runtime's NDJSON event stream into Server-Sent Events (SSE) consumed
by the chat UI.

## Responsibility Boundary

The Agent Runtime owns model and tool execution. `pi_chat_service.py` owns the HTTP bridge,
keepalive handling, event translation, evaluation recording, and the final block response. The
browser hook owns SSE parsing and live transcript state.

```text
Agent Runtime NDJSON
        ↓
src/qdash/api/services/pi_chat_service.py
        ↓
QDash SSE endpoint
        ↓
ui/src/hooks/useCopilotChat.ts
```

## Event Translation

| Runtime event | SSE event | UI purpose |
| --- | --- | --- |
| `text_delta` | `delta` | Append assistant text. |
| `thinking_delta` | `thinking` | Show live reasoning progress. |
| `tool_start` | `tool_start`, `status` | Show tool name, arguments, and progress. |
| `tool_end` | `tool_end`, `status` | Complete the tool row and attach figures or evaluation details. |
| `chart` | Included in final `result` | Render a collected chart. |
| `ask` | Included in final `result` | Render a question card. |
| `approval` | Included in final `result` | Render an approval card. |
| `done` | `status`, `result` | Finish the turn with renderable blocks. |
| `error` | `error` | Stop the stream with a user-visible failure. |
| `ping` | SSE comment | Keep idle proxy connections open. |

Malformed runtime events become an `error` event. A completed turn with no renderable text, chart,
question, or approval also becomes an error so the UI does not appear to hang.

## Durable Turns and Cancellation

Closing the browser stream does not cancel work in the Agent Runtime. The Stop action calls the
separate cancellation path for the active turn. Request IDs let a retry recover an answer that
the runtime already committed.

The runtime sends keepalives while a tool is quiet. The API converts them to SSE comments, which
preserve the connection without creating transcript entries.

## Change and Test Streaming

Update `agent-runtime/src/events.ts` when the runtime event contract changes. Update
`src/qdash/api/services/pi_chat_service.py` when the SSE contract or translation changes, then
update `ui/src/hooks/useCopilotChat.ts` and its tests for browser behavior.

Run:

```bash
uv run pytest tests/qdash/copilot/test_pi_chat_service.py -v
cd ui && bun run test:run src/hooks/__tests__/useCopilotChat.test.tsx
task ci-agent-runtime
```

Run the complete `task test-ui` suite when event rendering changes.
