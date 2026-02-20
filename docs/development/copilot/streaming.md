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
| `resolve_knowledge` | Loading TaskKnowledge for the task |
| `load_qubit_params` | Fetching qubit parameters from DB |
| `load_task_result` | Fetching task result from DB |
| `build_context` | Constructing TaskAnalysisContext |
| `run_analysis` / `run_chat` | Starting LLM interaction |
| `tool_call` | Agent is calling a tool |
| `thinking` | Agent is processing/reasoning |
| `complete` | All processing finished |
| `load_config` | Loading copilot config (chat mode) |

## Queue + Task Pattern

The streaming endpoints use `asyncio.Queue` + `asyncio.Task` to bridge the async agent execution with the SSE generator:

```python
# In the SSE event generator (simplified):

queue: asyncio.Queue[dict] = asyncio.Queue()

# Callbacks push events into the queue
async def on_tool_call(name, args):
    label = TOOL_LABELS.get(name, name)
    await queue.put({"step": "tool_call", "tool": name, "message": f"{label}..."})

async def on_status(status):
    label = STATUS_LABELS.get(status, status)
    await queue.put({"step": status, "message": label})

# The agent runs as a background task
analysis_task = asyncio.create_task(
    run_analysis(..., on_tool_call=on_tool_call, on_status=on_status)
)

# The generator polls the queue while the task runs
while not analysis_task.done():
    try:
        event = await asyncio.wait_for(queue.get(), timeout=0.3)
        yield _sse_event("status", event)
    except asyncio.TimeoutError:
        yield ":\n\n"   # heartbeat comment

# After task completes, drain remaining events
while not queue.empty():
    event = queue.get_nowait()
    yield _sse_event("status", event)

# Send final result
result = analysis_task.result()
yield _sse_event("result", result)
```

This pattern allows the SSE generator to yield events in real-time while the agent runs asynchronously. The 0.3-second timeout ensures the generator checks for task completion regularly.

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
