# Chat Streaming

QDash translates runtime events into Server-Sent Events (SSE) while saving each turn independently
of the browser connection.

## Responsibility Boundary

| Layer | Responsibility |
| --- | --- |
| Agent Runtime | Durable model and tool execution |
| `pi_chat_service.py` | HTTP bridge, event translation, and final response |
| `chat_turn_runs.py` | Background stream and server-side chat recording |
| Chat UI | Live rendering, reconnecting, and explicit stop requests |

## Event Translation

Text, reasoning, tool arguments, tool results, and rendered blocks stream as they become available.
`ViewEventTranslator` reads durable conversation revisions, including result entries, so skipped
intermediate updates do not lose tool output. Preserve event identity and ordering when changing
translation; the final response must agree with the streamed blocks.

## Durable Turns and Cancellation

Closing a browser stream does not cancel a turn. Stop sends `turn_request_id` through
`POST /agent/chat/stop` to the runtime's abort route. A late request cannot stop a different turn.
The API records progress and completion even when no browser watches.

## Reattaching to a Turn

Reconnect with the same request ID and `reattach: true`; never resubmit the prompt to recover a
stream. The UI stores bounded per-user turn pointers in session storage. Other windows discover
an active turn and follow it without submitting or saving another turn.

A restart or unavailable turn must produce an explicit recovery state, not silently dispatch the
same tools again. Keep cancellation, transport loss, and completion distinct.

## Branches

A branch forks a Pi conversation at a selected answer in the same SQLite store. It does not copy
the database or reconstruct a transcript. Branches share the current workspace files, not a file
snapshot from the fork point. Deleting a chat removes shared state only when no remaining chat
uses it.

## Calibration Session State in the Chat

Session links come from the chat's successful or running session-scoped tool calls, not model
text or failed calls. Read the linked session through the active project's API before displaying
its current status. Notifications describe chat events; they do not authorize calibration work.

## Change and Test Streaming

Start with these files:

| File | Responsibility |
| --- | --- |
| `agent-runtime/src/server.ts` | Runtime stream and abort routes |
| `agent-runtime/src/view-events.ts` | Durable-view translation |
| `src/qdash/api/services/pi_chat_service.py` | Runtime-to-SSE bridge |
| `src/qdash/api/services/chat_turn_runs.py` | Server recording |
| `ui/src/lib/agentTurnStore.ts` | Reload recovery pointers |

Run `task ci-agent-runtime` and the affected API/UI chat tests. Cover disconnect, reattach,
late cancellation, reload, branch sharing, tool arguments, and final-response parity.
