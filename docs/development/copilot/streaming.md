# SSE Streaming

## Overview

The Copilot uses Server-Sent Events (SSE) to stream progress updates from the backend to the frontend during LLM interactions. This provides real-time feedback as the system loads context, calls tools, and generates responses -- operations that can take several seconds to complete.

SSE was chosen over WebSockets because:
- Communication is unidirectional (server to client)
- Built-in reconnection in the browser's `EventSource` API
- Simple integration with FastAPI's `StreamingResponse`
- No need for persistent bidirectional connections

## Event Types

All events follow the SSE format: `event: <type>\ndata: <json>\n\n`

| Event | Format | Description |
|-------|--------|-------------|
| `status` | `{"step": string, "message": string}` | Progress update (loading data, calling tools, thinking) |
| `status` (tool) | `{"step": "tool_call", "tool": string, "message": string}` | Agent is executing a tool |
| `result` | `{"blocks": [...], "assessment": ...}` | Final response in blocks format |
| `error` | `{"step": string, "detail": string}` | Error occurred at a specific step |

### Status Step Values

| Step | When |
|------|------|
| `build_context` | Building a task chat's context (knowledge, qubit params, task result, images) |
| `load_images` | Sending experiment/reference images to AI |
| `run_chat` | Starting LLM interaction |
| `tool_call` | Agent is calling a tool |
| `thinking` | Agent is processing/reasoning |
| `complete` | All processing finished |
| `load_config` | Loading copilot config (chat mode) |
| `load_qubit_params` | Fetching qubit parameters from DB (chat mode) |
| `load_issue` | Loading issue thread (issue AI reply) |
| `build_history` | Building conversation history from thread (issue AI reply) |
| `load_context` | Loading task context (issue AI reply) |
| `save_reply` | Saving AI reply as issue (issue AI reply) |

## Runtime turns

Every streaming endpoint (`/copilot/chat/stream`, `/issues/{id}/ai-reply/stream`,
`/forum/posts/{id}/ai-reply/stream`) proxies one planner turn through the Pi Agent
Runtime: `pi_chat_service.stream_payload` POSTs the turn and `translate` turns the
runtime's NDJSON events into the SSE events above. Issue and forum replies use
`pi_chat_service.thread_reply`, which runs the turn in a throwaway conversation
and yields the final blocks result for the router to save.

## Frontend Integration

### `useCopilotChat` (Chat Page)

Located in `ui/src/hooks/useCopilotChat.ts`. Handles:
- Session management with localStorage persistence
- SSE consumption via `fetch` + `ReadableStream`
- Buffer-based SSE parsing with `consumeSSEEvents()`
- Status message display during streaming
- Blocks result storage as JSON string in message content

```typescript
// SSE event handling loop (simplified):
const reader = response.body.getReader();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const { events, remainder } = consumeSSEEvents(buffer);
  buffer = remainder;

  for (const evt of events) {
    if (evt.event === "status") {
      setStatusMessage(JSON.parse(evt.data).message);
    } else if (evt.event === "result") {
      // Store blocks result as JSON string in message
      const result = JSON.parse(evt.data);
      addAssistantMessage(JSON.stringify(result));
    } else if (evt.event === "error") {
      throw new Error(JSON.parse(evt.data).detail);
    }
  }
}
```

### Chats about a task result

A chat opened from a task result uses the same hook and the same endpoint, with
`task: {task_name, chip_id, qid, execution_id, task_id}` in the request body. The
API builds the result's context and figures (`build_context`, `load_images`
status events) and the Pi runtime attaches them to the first turn only; the
final `result` event carries `images_sent`.

### SSE Parser: `consumeSSEEvents`

Every chat surface shares the same SSE parsing logic:

1. Find the last `\n\n` boundary in the buffer (complete events only)
2. Split the complete portion into blocks by `\n\n`
3. For each block, extract `event:` and `data:` lines
4. Return parsed events and the unparsed remainder

This ensures partial SSE events are never processed.

## Heartbeat

The SSE generator sends an SSE comment (`:\n\n`) every 0.3 seconds when no events are available. This serves two purposes:

1. **Connection keepalive**: Prevents proxies and load balancers from closing idle connections
2. **Task completion check**: The timeout loop naturally checks `analysis_task.done()` on each iteration

The SSE comment format (`:\n\n`) is part of the SSE specification and is silently ignored by compliant clients.

## Response Headers

SSE responses include:
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache` -- Prevents caching of streamed events
- `X-Accel-Buffering: no` -- Disables Nginx buffering for real-time delivery
