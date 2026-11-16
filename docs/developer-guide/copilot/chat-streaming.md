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
| `tool_draft` | `tool_draft` | Open a tool row while the model is still writing the call (`index`: the call's position in the message). |
| `tool_args_delta` | `tool_args_delta` | Append text to one argument (`path`, such as `["content"]`) of the call being written; the chat shows code as it is typed. |
| `tool_start` | `tool_start`, `status` | The call runs: the drafted row gets its validated arguments and progress. |
| `tool_end` | `tool_end`, `status` | Complete the tool row and attach figures, evaluation details, a `classify` call's `classification`, a workspace tool's `output` and `exit_code`, or a `codemode` script's `output` followed by one line per tool call it made. |
| `chart` | Included in final `result` | Render a collected chart. |
| `ask` | Included in final `result` | Render a question card. |
| `approval` | Included in final `result` | Render an approval card. |
| `edit` | Included in final `result` | Render a proposed change from `propose_code_edit`, with Apply and Discard. The proposal's `pagePath`, `flowName`, and `chipId` must match the open editor before applying. |
| `steer` (`applied`) | `steer` with `result` | A message sent during the answer landed in the transcript as `entry_id`. `result` holds the blocks streamed before it, with `answer`, the text it follows when it came after the run's last tool round; the API starts collecting blocks anew. The UI closes the answer so far, inserts the message, and goes on. `before_turn: true` marks a steer a recovered run placed before this turn's message (see below). |
| `steer` (`withdrawn`) | `steer` | The run failed or was stopped before placing the message; the UI says it was not delivered. |
| `done` | `status`, `result` | Finish the turn with renderable blocks; `entry_id` names the answer's durable entry. |
| `noop` | `noop` | A continue found nothing to answer; no model request was sent. The UI keeps the chat as it was and shows a notice. |
| `error` | `error` | Stop the stream with a user-visible failure. |
| `ping` | SSE comment | Keep idle proxy connections open. |

Malformed runtime events become an `error` event. A completed turn with no renderable text, chart,
question, or approval also becomes an error so the UI does not appear to hang.

## Durable Turns and Cancellation

Closing the browser stream does not cancel work in the Agent Runtime. The Stop action calls the
separate cancellation path for the active turn. Request IDs let a retry recover an answer that
the runtime already committed.

One turn runs per user and store, so per conversation and across a chat's [branches](#branches); a second `/chat` request gets `409`. A message sent
while the turn runs goes to `POST /copilot/chat/steer` instead, which the runtime's `/chat/steer`
hands to the turn's `ActiveChat` in `agent-runtime/src/chat-control.ts`:

- The steer goes to the harness the turn already has open, with the turn's QDash credentials; it
  never opens the session store a second time. The runtime finds the turn by owner, store, and
  exact chat and refuses a request naming another project with `403`.
- It is submitted with `whenBusy: "steer"` and `whenIdle: "reject"`, as a `qdash.steer` entry that
  carries its request ID. Its durable request key is `steerKey(projectId, requestId)`, so a
  receipt belongs to one owner, conversation, project, and request. Pi places it after the current tool round, where the model reads it
  before deciding on more tools. When nothing runs any more, Pi refuses it and writes nothing, and
  the API answers `rejected`: the steer never starts a run of its own.
- A steer that arrives after the run's last tool round is placed after that answer and starts
  the next run. `settleChat` waits for every run the turn's steers started, and steers sent
  meanwhile, before the stream ends and the harness closes; `done` then reports the answer of
  the last run.
- The same request ID returns the same submission, so a retried steer is placed once. When no
  turn runs, or the turn no longer accepts steers, the runtime reads the steer from the store
  (`readSteerReceipt`) and reports it, also after the turn ended or the runtime restarted; only a
  request ID the store has never seen is `rejected`, and the runtime then refuses that ID for
  10 minutes so a delayed copy cannot steer a later turn. These fences live in the runtime's
  memory: a restart drops them, and they do not hold against a client that retries the same
  request ID after a restart or after they expire. The chat never retries a steer that way; it
  only asks the status route.
- `CHAT_QUEUE_SETTINGS` places every queued steer at the end of a tool round. When a run fails or
  is stopped while the runtime is up, it settles a steer still queued as `withdrawn` instead of
  keeping it for the user's next message.
- A runtime that dies mid-run (killed, out of memory) settles nothing: the steer stays `queued`
  in the store. `openSession` opens the harness with scheduling paused, and `handleChat` calls
  `harness.resume()` only once it watches the conversation. Pi then recovers the interrupted run,
  which places the steer and answers it before the new request's own message. The stream reports
  that steer with `before_turn: true`: its entry precedes the turn's own input entry, or the input
  is not placed yet. A continue has no input entry, so its steers are never marked.

`POST /copilot/chat/steer/status` (runtime `/chat/steer/status`) reports where a steer stands
without sending it: `queued`, `applied` with `entry_id`, `withdrawn`, or `not_found`. It reads
the session's SQLite store over its own connection without opening a harness, so it runs no
recovery, task, or admission beside the turn's writer. It is not a pure read for SQLite: opening
the storage checks the schema version in a `BEGIN IMMEDIATE` transaction, which takes the write
lock, and closing it checkpoints the write-ahead log. Both wait at most
`STEER_RECEIPT_BUSY_TIMEOUT_MS` (1 second) for the lock; past that the route answers `503`, which
the UI treats as unconfirmed, never as `not_found`. A steer stored under another project's key
is refused with `403`. Before reading, it lets submits already in flight finish and fences the
request ID, so `not_found` is final: a steer request still on its way is not admitted afterwards.

The UI (`CopilotChatSessionContext` with `ui/src/lib/copilotSteer.ts`) treats only a runtime
answer as settling a steer:

- When the stream ends before it placed a steer (Stop, a dropped connection), a queued steer
  becomes `unconfirmed`, never `withdrawn`, and the UI asks the status route, again while it
  answers `queued`. A steer whose request has not replied yet is settled by that reply.
- A steer request that got no reply, or a `5xx`, is `unconfirmed` too. Only `rejected`,
  `withdrawn`, `not_found`, and a `4xx` from the API offer **Send as new message**; an
  unconfirmed steer offers **Check again**, which calls the status route only. Continue waits
  until no steer is unconfirmed.
- Every request about a steer names the project it was sent from.
- `ui/src/lib/copilotSteerStore.ts` keeps every unresolved steer (sending, queued, unconfirmed,
  or applied but not yet placed) in the tab's `sessionStorage`, written before the steer request
  is sent: request ID, text, project, the turn it was sent to, and its `entry_id`. There is one
  entry per user, from the `owner` prop `AppLayout` passes. After a reload the provider restores
  them only once the user is known and the session list loaded, only into sessions that list
  holds, and removes every other user's entry; signing out removes the user's own. A restored
  steer is `unconfirmed` and is reconciled by the status route once its session's messages load,
  or dropped when the saved messages already hold its request ID; it is never sent again.
  `steersReady` stays false until the restore ran, and Continue waits for it. When storage is
  unavailable the steer is still sent, and is kept in memory only.
- A `steer` event with `before_turn` is not placed after the new message. The UI puts it into the
  earlier turn its pending steer was sent to with `placeLateSteer`, or, for a steer the chat does
  not know, just before the new message; both are saved as `approximate`. The answer the
  recovered run streams after it still shows under the new turn.
- A steer the runtime applied that no stream placed is saved once into the session's messages
  with `steer: { request_id, entry_id, placement: "approximate" }` by `placeLateSteer`. The answer
  it interrupted was saved as one message, so the steer goes right after it, ordered by `entry_id`
  among the turn's steers and before the next turn. A steer the stream placed is saved with
  `placement: "exact"`. While another stream runs in the session, placing waits for its end.

A continue is a `/chat` request with `continue: true` (`continue_run` in the API request). The
runtime submits Pi's `{ type: "continue" }`, which starts a run on the conversation as it is
without a user message, with the model and thinking level of the request. A request ID it has
seen returns its submission before any check, so a retry recovers the original continue. A new
continue is refused with `409` and a `reason` unless nothing runs, the newest run ended without
an answer (`aborted`, `model_error`, and similar `RunFailureReason`s), and no `ask_user`,
`propose_code_edit`, or approval result since the last user message waits for the user. A
continue that still finds nothing to answer ends in `noop`, not in an error.

The UI's message list and the durable transcript are kept separately: the UI stores what it
showed, and Retry and Edit send `conversation_history` that the runtime does not replay into the
durable conversation, which keeps every earlier message. Steers and Continue add nothing to that
divergence: a steer is stored once, where the stream placed it or after the answer it
interrupted, and a continue adds no user message.

The runtime sends keepalives while a tool is quiet. The API converts them to SSE comments, which
preserve the connection without creating transcript entries.

## Branches

A branch is a chat session that continues another one from one of its answers. It is a Pi fork
(`Conversation.fork(at)`) in the source chat's SQLite store, not a copy of the store: Pi 1.5 has no
per-conversation export, import, or delete, so the runtime never copies SQLite files or rebuilds a
transcript. The fork starts with what Pi copies at `at`: the transcript, `pi.agent` as of that
entry (model tools loaded through `tool_search` included), and the Code Mode store as of that
entry; `pi.live`, `pi.inbox`, `pi.usage`, and provider state start fresh.

`copilot_chat_session` maps each chat to its runtime state:

| Field | Meaning |
| --- | --- |
| `store_session_id` | Session whose store and workspace the chat uses; unset is its own `session_id` |
| `conversation_id` | Durable conversation in that store; unset is the root |
| `branch` | Source session, source entry, source conversation, project, `pending` or `ready`, and for a pending branch the request holding it (`operation_id`, `lease_expires_at`) |
| `deleted_at` | Set on a deleted chat kept as a hidden tombstone until the runtime removed its store |
| `messages[].entry_id` | An answer's durable entry, from the stream's `result` |

Only `CopilotChatSessionService` writes the first three; create and update requests have no such
fields. `resolve_runtime_target` reads them for every chat, steer, steer status, and stop
request, so the runtime is never addressed with an ID the browser chose. A chat with no stored
session is its own store's root. A deleted chat whose store its branches still use, or whose
store is not removed yet, is refused, and its ID cannot be created again.

`POST /copilot/chat/sessions/{session_id}/branches` takes `entry_id` and a client-generated
`target_session_id`, and checks the user's project membership. `branch_session` then:

1. Returns the target at once when it is already a `ready` branch of the same source and entry, a
   replay, whatever the source's messages are now.
2. Finds the source among the user's own sessions and the assistant message saved with that
   `entry_id`. An answer saved without one, from before `entry_id` existed, cannot be branched; its
   position is never used to guess one.
3. Stores the target as a `pending` branch with the source's messages through that answer, held by
   this request: a random `operation_id` and a lease of `BRANCH_LEASE` (2 minutes, longer than the
   60-second fork call). A pending branch is hidden from the session list and counts as a user of
   the store.
4. Reads the source again. If it was deleted meanwhile, the pending branch is removed with the
   store when nothing else uses it.
5. Calls the runtime's `POST /chat/branch` with the store, the source conversation, the entry, and
   the target, and marks the branch `ready` with the conversation the runtime returns.

Only the request that holds a pending branch finishes or removes it: both are conditional
updates on its `operation_id`, so a request that lost the branch gets `409` and never writes it
back. Another request for the same target while the lease runs is refused with `409` and changes
nothing; it does not reach the runtime. After the lease, a request takes the branch over by
replacing the `operation_id`, again conditionally.

How a failure ends depends on what is known about the runtime:

| Failure | Pending branch |
| --- | --- |
| Refusal from the runtime (`400`, `404`, `409`): it created nothing | Removed |
| `ForkSettledError`: the runtime answered with an error, such as `500` for a storage fault, or was not reached | Kept, lease released, so a retry takes it over at once |
| Saving the ready branch failed after the fork | Kept, lease released |
| Any other failure, such as a timeout, while the fork may still run | Kept until the lease ends |
| Source deleted, found by the request or by a retry that takes the branch over | Removed, with the store when it was the last user |

A retry with the same target reaches the runtime again, which returns the branch it already made
(`created: false`), and the session becomes ready. The same target with another source or entry
is a `409`. A branch nobody retries, because the browser reloaded and lost the target, is removed
by `CopilotChatSessionService.reclaim`, which `GET /copilot/chat/sessions` runs before listing:
it takes over each pending branch whose lease is over and removes it. A fork the runtime made
for it stays in the store, unreferenced, until the store is removed; Pi has no
per-conversation delete.

The runtime's `handleBranch` holds the store for the whole open, fork, and close.
`SharedRuntime.forkSession` opens it with the caller's credentials and never resumes scheduling,
so nothing runs. `branchFrom` in `agent-runtime/src/branch.ts` refuses a source with a run (also
one a crash left), queued submissions, or live tasks, and accepts only an entry visible from the
source (`Conversation.entries` bounded to `at`; only then is `Conversation.context({ at })` read,
so its failure is a storage fault, answered as `500`, never `entry_not_found`) that is an
assistant message with `stopReason: "stop"`,
no tool calls, and no `ask_user`, `propose_code_edit`, or approval result since the last user
message (`awaitsUser`). A historical question or approval card therefore never becomes actionable
in a branch. The fork's `init` writes the receipt into the session document `qdash.branches`, keyed
by target, in the same commit; the same target again returns that receipt, and another source or
entry for it is `conflict`. No `agent` change is applied at the fork; the next turn's
`openSession` configures the model, thinking level, and `cwd` the user chose, so the original
answer's model is not restored.

One writer per store: `server.ts` keeps one hold per owner and store (a chat turn, a fork, or a
deletion), so a turn in one branch refuses a turn in another (`409`, `reason: "store_busy"`), a
fork (`busy`), and a store deletion. Each `ActiveChat` records its QDash session and conversation;
a steer, a steer status, and a stop reach a turn only when they name exactly that chat
(`ActiveChat.runs`), so a request for one branch never steers or stops another.
`readSteerReceipt` reads the named conversation's receipts. The owner and project checks for
steers are unchanged.

The workspace belongs to the store (see [Workspace](./workspace.md)): a branch shares the current
files, not a snapshot. `DELETE /copilot/chat/sessions/{session_id}` (`delete_session`) works in
this order:

1. Marks the session `deleted_at`, a tombstone that is hidden from the list, from reads, and from
   `resolve_runtime_target`, and that no save can bring back.
2. Stops the chat's own turn by its exact target (`abort_runtime_turn`); a turn of another branch
   of the store keeps running.
3. If another session of the user that is not deleted, a pending branch included, uses the
   store, removes the store's tombstones and keeps the store. Its conversations stay in it.
4. Otherwise calls `remove_runtime_store`: the runtime's `DELETE /session` removes the store,
   every branch conversation in it, and the workspace. The runtime refuses while a turn, a fork,
   or another deletion holds the store; the API then stops the turns of the store's deleted chats
   and tries again, three times in all. Only once the runtime confirmed the removal are the
   tombstones dropped.

Each request marks its tombstone before it checks for other users, so of two last sessions
deleted at once at least one removes the store. When the removal still fails, the response is
`200` and the tombstone keeps the store and the deleted chats' targets; deleting the session
again, or the next listing of the user's chats (`reclaim`, one attempt), retries it.

The UI stores `entry_id` as `ChatMessage.entryId` and offers **Branch from here**
(`useCopilotChat.canBranchAt`) only for such an answer that is complete and not stopped, has no
question, approval, or edit block, while nothing streams and no steer is unresolved. Repeated
clicks share one request; a failed request without a server answer, a `5xx`, or a `409` (the
branch is still being created, or the chat is busy) is retried with the same target ID, so the
retry joins or takes over that branch. On success the UI switches to the new session on every chat surface. Retry and
Edit change only the UI's message list (see above), so a branch from a later answer continues the
durable conversation, replaced exchanges included.

Tests: `agent-runtime/test/branch.test.mjs` forks a real SQLite harness and checks the historical
context, deferred tools, and Code Mode store, refusals, and idempotency;
`agent-runtime/test/branch-server.test.mjs` covers the HTTP routes and store holds;
`tests/qdash/api/services/test_copilot_chat_session_service.py` covers the mapping, retries,
leases and take-over, concurrent requests for one target, the cleanup, tombstones, and store
removal; `ui/src/hooks/__tests__/useCopilotChatBranch.test.tsx` covers the browser side.

## Change and Test Streaming

`agent-runtime/src/server.ts` watches durable conversation revisions with `Conversation.watch()`.
`ViewEventTranslator` in `view-events.ts` emits unseen text and arguments from entries, and tool
completion from result entries, so skipped intermediate states do not lose output.

The view holds the newest 50–100 entries. If its window passes the stream's last entry,
`ViewEventStream` fetches the gap with `Conversation.entries()`. On settlement, `finish()` stops
the watch and translates the final view before emitting `done` or `error`. `events.ts` serializes
the translated events as NDJSON.

Update `agent-runtime/src/events.ts` when the runtime event contract changes, and
`agent-runtime/src/view-events.ts` when Pi's conversation view changes. Update
`src/qdash/api/services/pi_chat_service.py` when the SSE contract or translation changes, then
update `ui/src/hooks/useCopilotChat.ts` and its tests for browser behavior.

Run:

```bash
uv run pytest tests/qdash/copilot/test_pi_chat_service.py tests/qdash/api/routers/test_copilot_auth.py tests/qdash/api/services/test_copilot_chat_session_service.py -v
cd ui && bun run test:run src/hooks/__tests__/useCopilotChat.test.tsx src/hooks/__tests__/useCopilotChatSteerReload.test.tsx
task ci-agent-runtime
```

`agent-runtime/test/chat-control.test.mjs` runs steer and continue on real harnesses with a
scripted model, and `chat-steer-server.test.mjs` runs them over the runtime's HTTP routes.
`chat-steer-crash.test.mjs` kills a runtime process with a steer queued and checks that the next
process places it before the new message and reports `before_turn`.
`ui/src/hooks/__tests__/useCopilotChatSteerReload.test.tsx` covers restoring steers across a
reload, user isolation, and placing a `before_turn` steer. Run
the complete `task test-ui` suite when event rendering changes.
