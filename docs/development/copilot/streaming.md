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
| `build_context` | Building analysis context (knowledge, qubit params, task result, images) |
| `load_images` | Sending experiment/reference images to AI |
| `run_analysis` / `run_chat` | Starting LLM interaction |
| `tool_call` | Agent is calling a tool |
| `thinking` | Agent is processing/reasoning |
| `complete` | All processing finished |
| `load_config` | Loading copilot config (chat mode) |
| `load_qubit_params` | Fetching qubit parameters from DB (chat mode) |
| `load_issue` | Loading issue thread (issue AI reply) |
| `build_history` | Building conversation history from thread (issue AI reply) |
| `load_context` | Loading task context (issue AI reply) |
| `save_reply` | Saving AI reply as issue (issue AI reply) |

## SSETaskBridge

All three streaming endpoints (`/copilot/analyze/stream`, `/copilot/chat/stream`, `/issues/{id}/ai-reply/stream`) share the same queue-poll-heartbeat-drain pattern. This is encapsulated in the `SSETaskBridge` dataclass in `lib/sse.py`.

```python
from qdash.api.lib.sse import SSETaskBridge

bridge = SSETaskBridge(tool_labels=TOOL_LABELS, status_labels=STATUS_LABELS)

coro = partial(
    run_analysis,
    context=ctx.context,
    user_message=request.message,
    config=config,
    tool_executors=tool_executors,
)

result: dict[str, Any] = {}
async for event in bridge.drain(coro):
    if isinstance(event, str):
        yield event          # SSE status event or heartbeat
    else:
        result = event       # Final result dict (last yielded value)

yield sse_event("result", result)
```

### How it works

1. `SSETaskBridge` creates an `asyncio.Queue` and builds `on_tool_call` / `on_status` callbacks that push events into it.
2. `drain(coro)` calls `coro(on_tool_call=..., on_status=...)` as a background `asyncio.Task`.
3. While the task runs, `drain` polls the queue with a 0.3-second timeout. Each queued event is yielded as a formatted SSE string. On timeout, a heartbeat comment (`:\n\n`) is yielded.
4. After the task completes, remaining queue events are drained and the task result is yielded as-is (not formatted) so the caller can post-process it.

### Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tool_labels` | `dict[str, str]` | `{}` | Tool name to label mapping |
| `status_labels` | `dict[str, str]` | `{}` | Status key to label mapping |
| `heartbeat_timeout` | `float` | `0.3` | Seconds before sending heartbeat |

## Tool Progress Labels

The router maps tool names and status codes to user-facing labels:

### `TOOL_LABELS`

| Tool Name | Label |
|-----------|-------|
| `get_qubit_params` | キュービットパラメータを取得中 |
| `get_latest_task_result` | 最新タスク結果を取得中 |
| `get_task_history` | タスク履歴を取得中 |
| `get_parameter_timeseries` | パラメータ時系列を取得中 |
| `execute_python_analysis` | Python分析コードを実行中 |

### `STATUS_LABELS`

| Status | Label |
|--------|-------|
| `thinking` | AIが考え中... |

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

### `useAnalysisChat` (Analysis Sidebar)

Located in `ui/src/hooks/useAnalysisChat.ts`. Similar SSE handling but:
- Uses `flushSync` for immediate status message updates
- Requires `AnalysisContext` (taskName, chipId, qid, executionId, taskId)
- Supports `imageBase64` parameter for multimodal analysis
- No session persistence (messages reset on context switch)
- Includes legacy `AnalysisResult` fallback formatting

### SSE Parser: `consumeSSEEvents`

Both hooks share the same SSE parsing logic:

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
