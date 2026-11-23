# Chat Streaming

QDash translates the Agent Runtime's NDJSON event stream into Server-Sent Events (SSE) consumed
by the chat UI.

## Responsibility Boundary

The Agent Runtime owns model and tool execution. `pi_chat_service.py` owns the HTTP bridge,
keepalive handling, event translation, evaluation recording, and the final block response.
`chat_turn_runs.py` owns each turn's stream in the API and records the turn in its chat session,
whoever watches it (see [Recording a Turn on the Server](#recording-a-turn-on-the-server)). The
browser hook owns SSE parsing and the live transcript it shows.

```text
Agent Runtime NDJSON
        ↓
src/qdash/api/services/pi_chat_service.py
        ↓
src/qdash/api/services/chat_turn_runs.py ──→ copilot_chat_session (recorded turn)
        ↓
QDash SSE endpoint (one subscriber per response)
        ↓
ui/src/hooks/useCopilotChat.ts
```

## Event Translation

| Runtime event | SSE event | UI purpose |
| --- | --- | --- |
| `text_delta` | `delta` | Append assistant text. |
| `thinking_delta` | `thinking` | Show live reasoning progress. |
| `tool_draft` | `tool_draft` | Add a collapsed tool row while the model is still writing the call (`index`: the call's position in the message). |
| `tool_args_delta` | `tool_args_delta` | Append text to one argument (`path`, such as `["content"]`) of the call being written; an expanded tool row shows code as it is typed. |
| `tool_start` | `tool_start`, `status` | The call runs: the drafted row gets its validated arguments and progress. |
| `tool_end` | `tool_end`, `status` | Complete the tool row and attach figures, evaluation details, a `classify` call's `classification`, a workspace tool's `output` and `exit_code`, or a `codemode` script's `output` followed by one line per tool call it made. The runtime adds `entry_id`, the result's durable entry, and `before_turn` for a result committed before the turn's own message. |
| `chart` | Included in final `result` | Render a collected chart. |
| `ask` | Included in final `result` | Render a question card. |
| `approval` | Included in final `result` | Render an approval card. |
| `edit` | Included in final `result` | Render a proposed change from `propose_code_edit`, with Apply and Discard. The proposal's `target` and `pagePath` must match the open editor before applying, with `flowName` and `chipId` for a flow, `scriptId` for a metric script, or `dashboardId` (null for a new dashboard) for a dashboard draft. |
| `steer` (`applied`) | `steer` with `result` | A message sent during the answer landed in the transcript as `entry_id`. `result` holds the blocks streamed before it, with `answer`, the text it follows when it came after the run's last tool round; the API starts collecting blocks anew. The UI closes the answer so far, inserts the message, and goes on. `before_turn: true` marks a steer a recovered run placed before this turn's message (see below). |
| `steer` (`withdrawn`) | `steer` | The run failed or was stopped before placing the message; the UI says it was not delivered. |
| `turn_start` | `turn_start` with `result` | The turn's own message was placed. What streamed before it came from a run recovered after the runtime died, answering a steer of an earlier turn; `result` holds those blocks, with `answer`, the text that run ended with. `answer` holds only an answer committed after the stream started, so on an ordinary turn it is empty and the UI adds nothing. The UI keeps them with the earlier turn, before the new message. |
| `done` | `status`, `result` | Finish the turn with renderable blocks; `entry_id` names the answer's durable entry. |
| `noop` | `noop` | A continue found nothing to answer; no model request was sent. The UI keeps the chat as it was and shows a notice. |
| `error` | `error` | Stop the stream with a user-visible failure; a runtime `code` (`compaction_failed`, `turn_not_started`) is passed on. |
| `ping` | SSE comment | Keep idle proxy connections open, and tell the UI the stream is alive. |

Malformed runtime events become an `error` event. A completed turn with no renderable text, chart,
question, or approval also becomes an error so the UI does not appear to hang. A stream that ends
before the turn did, a failed connection to the runtime, or a `502`, `503`, or `504` from it
becomes an `error` with `code: "stream_lost"`, which the UI answers with a reattach (see
[Reattaching to a Turn](#reattaching-to-a-turn)) rather than a failed answer.

## Durable Turns and Cancellation

Closing the browser stream does not cancel work in the Agent Runtime. The Stop action calls the
separate cancellation path for the active turn: `POST /copilot/chat/stop` with the turn's
`turn_request_id` (`ChatStopRequest`), sent on to the runtime's `/chat/abort`, which answers `404`
when the chat's running turn has another request ID, so a stop that arrives late never stops a
newer turn. A stop without it, from an older client, stops whatever turn the chat runs. A stop reaches the turn as soon as it holds the
store, also while its own message is still being admitted: `ActiveChat.stop` records it, and the
turn aborts again once its submission is in, before it admits any steer. Request IDs let a
reattach recover a turn whose stream dropped (see [Reattaching to a Turn](#reattaching-to-a-turn)). A parked `qdash_wait_execution` or
`qdash_wait_agent_action` call stays a running tool in the stream until it ends, and a stop ends it
without stopping the execution in QDash (see
[Copilot Architecture](./architecture.md#code-mode-and-deferred-tools)).

One turn runs per user and store, so per conversation and across a chat's [branches](#branches); a second `/chat` request gets `409`. A message sent
while the turn runs goes to `POST /copilot/chat/steer` instead, which the runtime's `/chat/steer`
hands to the turn's `ActiveChat` in `agent-runtime/src/chat-control.ts`:

- The steer goes to the harness the turn already has open, with the turn's QDash credentials; it
  never opens the session store a second time. The runtime finds the turn by owner, store, and
  exact chat and refuses a request naming another project with `403`.
- A steer names the turn it was sent to (`turn_request_id`, the turn's own request ID), and only
  that turn admits it (`ActiveChat.admits`); a steer for any other turn is `rejected`.
- It is submitted with `whenBusy: "steer"` and `whenIdle: "reject"`, as a `qdash.steer` entry that
  carries its request ID. Its durable request key is `steerKey(projectId, requestId)`, so a
  receipt belongs to one owner, conversation, project, and request. Pi places it after the current tool round, where the model reads it
  before deciding on more tools. When nothing runs any more, Pi refuses it and writes nothing, and
  the API answers `rejected`: the steer never starts a run of its own.
- A steer that arrives after the run's last tool round is placed after that answer and starts
  the next run. `settleChat` waits for every run the turn's steers started, and steers sent
  meanwhile, before the stream ends and the harness closes; `done` then reports the answer of
  the last run. Only a steer submitted after the turn's own submission, and placed after its
  message, can end the turn: a request ID retried from an earlier turn finds that turn's older
  submission (durable IDs grow in creation order), which never replaces the answer, also for a
  continue, which places no message of its own.
- The same request ID returns the same submission, so a retried steer is placed once. When no
  turn runs, or the turn no longer accepts steers, the runtime reads the steer from the store
  (`readSteerReceipt`) and reports it, also after the turn ended or the runtime restarted; only a
  request ID the store has never seen is `rejected`. A delayed copy of it cannot steer a later
  turn, because every turn request has its own ID and the copy names the turn it was sent for.
- `CHAT_QUEUE_SETTINGS` places every queued steer at the end of a tool round. When a run fails or
  is stopped while the runtime is up, it settles a steer still queued as `withdrawn` instead of
  keeping it for the user's next message.
- A runtime that dies mid-run (killed, out of memory) settles nothing: the steer stays `queued`
  in the store. `openSession` opens the harness with scheduling paused, and `handleChat` calls
  `harness.resume()` only once it watches the conversation. Pi then recovers the interrupted run,
  which places the steer and answers it before the new request's own message. The stream reports
  that steer with `before_turn: true`: its entry precedes the turn's own input entry, or the input
  is not placed yet. A continue has no input entry, so its steers are never marked. When the
  turn's own input entry is placed, the stream reports `turn_start`, so what the recovered run
  answered stays with the earlier turn. The stream recognizes that entry only as the one the
  turn's own submission placed: it waits for the submit to return and compares the submission's
  `entry`, which the placing commit sets together with the entry. A plain user message a recovered
  run places first, such as an earlier turn's wrap-up, is not the turn's own.
- After a restart, the store hold is gone, and only the store itself shows work another
  conversation left unfinished. `handleChat` reads `unfinishedWork` (`branch.ts`, from
  `Harness.inspect()`) before it resumes scheduling, and refuses a turn of a chat while another
  conversation of the same store has a queued submission or a live task (`409`,
  `reason: "store_busy"`). The chat's own unfinished work is recovered as before; the other
  branch's next request recovers its own. A stop is applied to the turn's conversation only after
  this check and `harness.resume()` (`ActiveChat.opened`): `Conversation.abort()` starts the
  store's scheduling, so a stop that came while the check ran stays remembered and is applied
  after the turn's input is admitted. Work that only winds down (`windsDown`: every live task
  carries an abort mark, no input queued) does not refuse a turn; it runs only abort handlers.
- A deleted chat's work a crash left behind is reached by no later turn. Deleting the chat stops
  it from the store (`stored-stop.ts`): `/chat/abort` with `include_stored: true` and the user's
  QDash credentials, when no turn of that chat runs, holds the store, opens it with scheduling
  paused and no extension (`openStoreForCleanup`), withdraws the chat's queued inputs
  (`Harness.abortSubmission()`), and commits an abort mark on each of its live tasks
  (`Harness.abortTask()`), which starts nothing. A marked built-in task runs only its abort
  handler, which records the run and its unfinished calls as aborted and calls no model and runs
  no tool; a task kind no definition takes is orphaned. Only when no other conversation of the
  store has runnable work does the request start scheduling and wait, up to
  `STORED_STOP_SETTLE_MS` (5 seconds), for the work to end (`200`, `settled: true`); otherwise
  the marks stay and the work winds down with the store's next turn (`settled: false`). No
  unfinished work is `404`; another hold on the store is `409`, which the API keeps as
  `stop_pending`.

`POST /copilot/chat/steer/status` (runtime `/chat/steer/status`) reports where a steer stands
without sending it: `queued`, `applied` with `entry_id`, `withdrawn`, or `not_found`. It reads
the session's SQLite store over its own connection without opening a harness, so it runs no
recovery, task, or admission beside the turn's writer. It is not a pure read for SQLite: opening
the storage checks the schema version in a `BEGIN IMMEDIATE` transaction, which takes the write
lock, and closing it checkpoints the write-ahead log. Both wait at most
`STEER_RECEIPT_BUSY_TIMEOUT_MS` (1 second) for the lock; past that the route answers `503`, which
the UI treats as unconfirmed, never as `not_found`. A steer stored under another project's key
is refused with `403`. Before reading, it fences the steer durably: it appends the conversation,
project, and request ID to `<store>.steer-fences` beside the store (`fenceSteer` in
`store-identity.ts`) and syncs the file, then fences it in the running turn of that chat, if one
runs, and lets submits already in flight finish. Every request of the turn the steer was sent to
checks the file before it admits a steer (`ActiveChat.admits`), also a request that repeats the
turn's request ID to recover it, after a dropped stream or a restart. Only that turn could admit
the steer, so `not_found` is final: a steer request still on its way is not admitted afterwards.
The fence is written whatever the read finds; a steer the store holds is still reported from the
store when it is sent again. The file is no second writer of the SQLite store and goes with it.

The UI (`CopilotChatSessionContext` with `ui/src/lib/copilotSteer.ts`) treats only a runtime
answer as settling a steer:

- When the stream ends before it placed a steer (Stop, a dropped connection), a queued steer
  becomes `unconfirmed`, never `withdrawn`, and the UI asks the status route, again while it
  answers `queued`. A steer whose request has not replied yet is settled by that reply.
- A steer request that got no reply, or a `5xx`, is `unconfirmed` too. Only `rejected`,
  `withdrawn`, `not_found`, and a `4xx` from the API offer **Send as new message**; an
  unconfirmed steer offers **Check again**, which calls the status route only. Continue waits
  until no steer is unconfirmed. A steer placed after a stopped answer, as the last message, is
  part of that answer's turn: Continue stays available (`canContinueMessages`) and sends it in the
  history; question, approval, and edit cards still block it.
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
  not know, just before the new message; both are saved as `approximate`. The blocks the
  recovered run streamed before it go right before it, and what it answered, closed by
  `turn_start`, right after it.
- A steer the runtime applied that no stream placed is saved once into the session's messages
  with `steer: { request_id, entry_id, placement: "approximate" }` by `placeLateSteer`. The answer
  it interrupted was saved as one message, so the steer goes right after it, ordered by `entry_id`
  among the turn's steers and before the next turn. A steer the stream placed is saved with
  `placement: "exact"`. While another stream runs in the session, placing waits for its end.
- The server saves a steer a stream placed with the turn (see
  [Recording a Turn on the Server](#recording-a-turn-on-the-server)); the UI drops its receipt once
  the turn's saved run holds it. When the UI saves its own copy instead, it saves a session's
  transcript one `PATCH` at a time: a newer snapshot waits for the save in flight and replaces any
  snapshot still waiting, so an older one never commits last. A save is sent only for the user who
  wrote it. A placed steer keeps its stored receipt (`saving`, out of the pending list) until a save
  holding it is acknowledged; when saving fails, a reload restores it as applied and places it
  again.

A continue is a `/chat` request with `continue: true` (`continue_run` in the API request). The
runtime submits Pi's `{ type: "continue" }`, which starts a run on the conversation as it is
without a user message, with the model and thinking level of the request. A request ID it has
seen returns its submission before any check, so a retry recovers the original continue. A new
continue is refused with `409` and a `reason` unless nothing runs, the newest run ended without
an answer (`aborted`, `model_error`, and similar `RunFailureReason`s), and no `ask_user`,
`propose_code_edit`, or approval result since the last user message waits for the user. A
continue that still finds nothing to answer ends in `noop`, not in an error.

The chat session's messages and the durable transcript are kept separately: the session stores
what the chat shows, and Retry and Edit send `conversation_history` that the runtime does not replay into the
durable conversation, which keeps every earlier message. Steers and Continue add nothing to that
divergence: a steer is stored once, where the stream placed it or after the answer it
interrupted, and a continue adds no user message.

The runtime sends a keepalive every `CHAT_PING_MS` (15 seconds by default) for the whole turn,
also while a tool is quiet. The API converts them to SSE comments, which preserve the connection
without creating transcript entries.

## Recording a Turn on the Server

The API records every chat turn in its chat session as the runtime streams it, so the saved chat
holds the turn's progress and its end whether or not a browser watches it. `chat_stream` in
`src/qdash/api/routers/copilot.py` passes the request to `stream_turn` in
`src/qdash/api/services/chat_turn_runs.py`, which runs the turn's stream in a background task
(`TurnRun`), keyed by user, session, and request ID. The HTTP response only subscribes: it gets
the turn's events so far, then the live ones. Closing the response, or every window, ends the
subscription, never the stream or the turn. Another request of the same turn on the same API
process, a retry or a reattach, subscribes to the running task instead of opening a second
stream, so nothing runs twice; a request of it from another project gets an SSE `error` with
`code: "wrong_project"`.

Before anything reaches the runtime, the task claims the turn (`claim_turn` in
`copilot_chat_session_service.py`). The saved chat must hold the start the window sent the turn
from (`turn_start`, see [Following a Turn From Another Window](#following-a-turn-from-another-window)):
`index` messages whose digest, with the turn's own message, is `digest`. The server computes the
digest as the page does (`transcript_digest` in `src/qdash/api/services/chat_transcript.py`). The
chat then becomes those messages and the user's message, which the server saves itself, and
`turn` (`CopilotChatServerTurn`) names the recorded turn: its request ID, project, status
(`running`, `completed`, `failed`, `stopped`, or `noop`), and start. Each message of the turn
carries its request ID (`turn_request_id`). When the saved chat does not hold that start, the
task waits up to about 2.4 seconds for a save still on its way, then answers with an SSE `error`
with `code: "transcript_conflict"` and sends nothing; the page shows the saved chat and a notice.
A start that cannot be stored is an SSE `error` too, and the turn is not sent. A request ID the
chat records already (`same_turn`) is a retry and is not claimed again. While another recorded
turn of the chat is still `running`, the claim is refused with `code: "turn_running"` and nothing
is sent, so the running turn keeps its record. When the runtime cannot say whether it runs
(`turn_running` gives None for an `unavailable` reply), the claim is `unknown`: the new turn is
refused the same way and the recorded turn and its saved progress stay as they are. When
neither this process nor the runtime (`/chat/active`) runs that turn any more, for example after the API restarted, the new turn
replaces it, and the progress the replaced turn saved stays in the chat marked `interrupted: true`
instead of `in_progress: true` (`interrupted_content`), with its open steps closed as for a stop.

The digest counts an answer of a recorded turn by its request ID, not by its text: the server and
each window fold the same answer with their own timings, and a rating changes its text, so a
window's copy of the previous answer still matches the server's.

`TurnTranscript` in `chat_transcript.py` folds the turn's SSE events into the turn's run the way
`runTurn` folds them for display (`ui/src/lib/copilotChatStream.ts`): the same trace steps and
stored limits, each part of the answer a steer closed off followed by the steer, and the answer.
Progress is written at most once a second (`PROGRESS_INTERVAL`), and at once for a placed steer,
as an answer marked `in_progress: true`, without holding up the stream. Progress keeps a step that
still runs, or is still being written, open (`running`, `drafting`); only the end closes such
steps (a call still being written becomes `cancelled`). The end is written as the
answer with its `entry_id`, `Error: <detail>` for a failure, a stopped answer, or nothing for a
`noop` or a refused continue. `POST /copilot/chat/stop` sets `turn.stop_requested` before it asks
the runtime to stop, and the in-process task's flag, so the runtime's error after a stop is
recorded as `stopped`. A write of the end is tried again after 0.5, 1, 2, and 4 seconds.

Both folds bound what a stored trace keeps: 20,000 characters of thinking per answer, the last
2,000 characters of a tool's output, 12,000 characters of an evaluation prompt, and a call's
arguments cut to a 4,000-character JSON prefix.
Finished `write` calls share a further 64,000 characters, counted as `JSON.stringify` length, in
which their arguments stay whole, so the chat can offer a written file's content after a reload
(`writtenFiles` in `ui/src/lib/chatDownloads.ts`). A call still running when the turn ended, or
when `interrupted_content` closes the saved progress of a replaced turn, is stored `done` with
`interrupted: true`; its arguments are cut as usual and the chat does not offer its content.
Progress keeps such a call `running`, without `interrupted`.

After the end is written, the task sends an SSE `transcript` event, the last of the stream:
`saved: true` with the turn's run as stored (`messages`), or `saved: false` when it could not be
written. When the runtime stream drops (`stream_lost`, `turn_boundary_unknown`), the task
attaches to the turn again with `reattach` after 1, 2, 4, 8, 16, and then every 30 seconds, up to
25 attempts, after which it records the turn as failed with a lost-connection message. It sends
keepalive comments meanwhile, and a `restart` event before the replay, on which subscribers fold
the turn again from its start.

Every write of a session's `messages` is conditional on its `revision`, which it bumps; a write
based on an older copy reads the session again and is merged again. `write_turn` writes only
while the turn runs, so a late progress write or a second stream of the turn never replaces its
end. A client save (`PATCH /copilot/chat/sessions/{session_id}`) is merged by
`merge_saved_messages`. A message that carries the `turn_request_id` of a turn the chat records,
the latest or an earlier one, is durable; every other message, such as a legacy message, a steer
the page placed, or a client-only error, is client-owned. The merge keeps these rules for any copy:

- The durable messages are exactly the stored ones, in the stored order, each once. A copy that
  omits, repeats, reorders, or holds only part of a recorded turn cannot remove, repeat, move, or
  change one. A new turn sent from an earlier point truncates the chat when `claim_turn` records
  it.
- Of a durable message, only an answer's rating (`feedback`) comes from the copy, from the copy's
  version of the same answer (`_stored_copy`): the answer with the same `entry_id`, else the
  stored answer it equals without the rating, else the answer at the same place in the turn
  (before a given steer, before the turn's message, or last). The index in the turn is never
  used, since the server and each window fold a turn differently. When the copy's versions of an
  answer disagree, or none is identified, the stored rating stays. A copy of an answer without a
  rating clears it; the last save wins, also against a rating set in another window.
- Client-owned messages keep the copy's order, each once, and each follows every durable message
  that preceded it in the copy. Between two durable messages that the copy holds next to each
  other, the client-owned messages are the copy's. Where the copy lacks durable messages, such as
  a save queued before a turn started, it did not see that part of the chat: the stored
  client-owned messages there that the copy does not hold are kept, a copy's equal message takes
  the stored one's place, and the copy's other messages go before its next such message or, after
  the last one, at the end of that part, as a message queued after the turn would.
- While the latest recorded turn runs, nothing from its start on comes from the copy.

A reattach of a turn the chat records writes only while the turn
runs, and only for the turn's own project; one that ended reports its stored run in
`transcript` without writing.

The page (`runTurn`) saves nothing of a turn while it streams. When the stream ends, it shows the
run the `transcript` event reported over the messages before the turn, keeping this window's
attachment thumbnails (`withLocalAttachments`), and removes the turn's pointer. Without that event,
after a Stop, a dropped stream, or `saved: false` (with a notice), the window that sent the turn
saves its own copy, which the server merges under what it recorded, and loads the saved chat
again shortly after. The task survives a browser disconnect, not a restart of the API process;
after one, the next reattach, from the restored pointer or from a following window, starts a task
that records the turn again.

## Reattaching to a Turn

A turn outlives its stream. A tool parked on an expert's answer or a calibration can keep a turn
quiet for an hour, and a proxy, the network, or a restarting API can drop the stream meanwhile;
the turn runs on in the runtime. The UI then reattaches with a `/chat` request that repeats the
turn's `request_id` with `reattach: true` (`ChatRequest.reattach`, sent on as `reattach`). A
reattach submits nothing, so it never asks the model again or runs a tool twice:

- **Turn still running.** Every event the turn wrote is kept in its `TurnFeed`
  (`agent-runtime/src/turn-feed.ts`), held with the store. The reattached stream gets the whole
  turn from its start, appends to one text, thinking, or argument block merged, then the live
  events and the terminal event, exactly as the original stream would have. Only the turn's own
  owner, chat, and project reach it (`403` for another project); a reattach naming another turn of
  a busy chat is `409`. A turn that ends without a terminal event refused its request before it
  started, and the reattached stream ends with an `error` with `code: "turn_not_started"`.
- **Turn ended, or the runtime restarted.** `handleChat` finds the submission by request ID
  (`submissionByRequest`), skips the approval check and the submit, and replays the turn's entries
  from the store before `done`; a runtime restart recovers the run as for any request. A request
  ID the store has never seen is `404` with `reason: "turn_not_found"`, an SSE `error` with
  `code: "turn_not_found"`: the message never arrived, and the UI asks the user to send it again
  rather than resending it itself.

The replay covers the turn only, from its own message to where the store's submissions say it
ends (`readStoredTurn` and `storedTurn` in `chat-control.ts`). A steer has a `steer:` request key
and the runtime's wrap-up steer has none; every other input, and every continue, starts a turn.
The next turn's message bounds the turn exactly: `ViewEventStream` translates no entry from it on
and ignores the live state, which belongs to whatever runs now. After a continue, which places no
entry, the turn ends at the last message or answer its own submissions placed, so a failed
attempt after that is not replayed. With no later turn, every later entry is the turn's. Of the
turn's own submission and the steers it placed, the one placed last gives `done` its answer
(`storedTurnFinal`), as `settleChat` does for a live turn. A later message still queued for
placement, or a continue after an unsettled steer, leaves the end unknown: the reattach is `409`
with `reason: "turn_boundary_unknown"` and replays nothing rather than another turn's events. The
API passes it on as an SSE `error` with `code: "turn_boundary_unknown"`, which the UI treats as a
dropped stream and reattaches again later.

The API builds no task or investigation context for a reattach, but it records evaluations from
the replayed `tool_end` events as it does for the original stream, so a `qcal_evaluate` result
that reached only the reattached stream is still filed. What a call is filed under comes from the
turn, not from the request that reports it: the turn's first request stores its project, planner
model, and task once in `copilot_chat_turn` (`EvaluationService.chat_turn_recorder`) before it
reaches the runtime, and a retry or a reattach of the turn reads that record and ignores the model
and task it sends itself. A request of the turn from another project gets an SSE `error` with
`code: "wrong_project"` and nothing is streamed. The runtime itself checks the project only for a running
turn, so for an ended turn this record is the project check. A reattach of a turn with no
record, such as one sent before records were kept or whose record could not be written, streams
but files nothing, since what the turn was sent with, its project included, is not known.

`translate` names each call by its result's durable entry (`entry:<entry_id>`), which every
stream of the turn reports the same way whatever ID the model gave the call; a local model may
give every call of a turn the same ID, and each such call still starts, ends, and is filed on
its own. `ChatCallKey` derives the run and evaluation IDs from that name, the project, the user,
the chat session, and the turn's `request_id`. A call that the original stream, a concurrent
stream, or an earlier replay already stored keeps its first record, and the stream reports that
record's IDs; a write that stopped between the run and the evaluation is completed under the
turn's record. A result with no entry, or one marked `before_turn` (a run recovered after a
restart committed it before this turn's message), is shown without IDs and filed by no stream of
this turn. Whichever stream reaches `done` attaches the answer to the evaluations it filed. An
evaluation that could not be stored is reported without IDs. These guarantees hold for every
stream of one turn that reports a result; a result no stream of the turn reports is not filed.

In the UI (`runTurn` in `CopilotChatSessionContext.tsx`, which `sendMessage` and a restore
start), every request of a turn, its reattaches and its Stop included, names the project the
turn was sent from (`X-Project-Id`), not the project stored at the time, so a reattach is never
refused as `wrong_project` because the user switched projects. A stream counts as dropped when the
request or a read fails, the stream ends without `result` or `noop`, an SSE `error` has
`code: "stream_lost"`, the response is `502`, `503`, or `504`, or no byte, keepalive included,
arrives for `STREAM_SILENCE_MS` (60 seconds). The UI then reattaches at once, and again after 1,
2, 4, 8, 16, and then every 30 seconds, up to 25 attempts, after which it shows an error saying
the assistant may still be working. A reattached stream folds the turn again from its start, so
the live trace is rebuilt rather than doubled and a steer it placed is placed again. Stop ends
the reattaching and the turn. `SessionRun.connection` keeps the stream's health apart from what
the turn does: `live` or `reconnecting`, and `lastUpdateAt`, the time of the turn's last event,
which a keepalive does not change. `TurnActivity` (`ChatTrace.tsx`) shows **Connected · last
update … ago** once the turn has sent nothing for 30 seconds (`QUIET_AFTER_MS`), and **Connection
lost, reconnecting** in place of the last activity while reattaching. The waiting tools'
rows say what the turn waits for (`stepTitle`), such as **Waiting for the expert's answer**.

### Restoring a Turn After a Reload or a Remount

The provider keeps a pointer to each turn it started in the tab's `sessionStorage`
(`ui/src/lib/copilotTurnStore.ts`), one per session and user (`owner`), at most
`MAX_STORED_TURNS` (20): the session, the turn's request ID, its project, where it starts in the
transcript (`start`), whether it is a continue, when it started, and the last activity the chat
showed (a tool name and label, or a phrase such as "Thinking", from `activitySnapshot` in
`ui/src/lib/chatActivity.ts`) with its time. It holds no message text, tool argument, result, or
credential. The pointer is written before the turn's request goes out, after the transcript save
that holds the user's message is queued. Updates and removals name the turn's request ID, so a
late one never touches a newer turn's pointer. When the stream ends, the pointer is marked
`ended` and removed once a transcript save that holds the turn's end is acknowledged
(`transcriptSeq`); a reload before that replays the turn instead of losing its answer. A turn whose
stream reported the server's saved run removes the pointer at once.

Moving between pages keeps the provider, so a stream goes on whatever surface shows it. When the
provider mounts again, after a reload or after it unmounted, its restore effect reads the
pointers once the user, their session list, and the open project are known. A pointer of a
session the list does not hold is removed. A pointer of the open project is restored with
`resumeTurn`: the session's saved messages are loaded and the turn is found in them by its
identity, never by the pointer's `start`, which a steer, a recovered run, or another window's
later turn can move. `recordedTurnPlacement` (`ui/src/lib/copilotObservedTurn.ts`) looks for the
messages that carry the turn's `turn_request_id` and reads the session's `turn` (the latest turn
the server records: its request ID, project, `status`, `start_index`, and whether it is a
continue). `GET /copilot/chat/sessions/{session_id}` names `turn` only to a request made in the
project the turn was sent from, like `/chat/active`: the project of `X-Project-Id`, else the
user's default, and only one the user may read (`get_project_context`); otherwise `turn` is null
while the messages are returned as usual. The reply carries `Cache-Control: private, no-store`
and `Vary: Authorization, X-Project-Id`. The provider keeps each loaded `turn` with the project
it was asked from and uses it only while that project is open (`recordedTurnOf`):

- **Running.** The transcript before the turn's first message and its own message become the
  turn's start (shown without saving until the stream says more); the progress the server saved
  after it is left out, and the turn is reattached with its request ID (`reattachStored`). The
  runtime streams a running turn from its start, replays an ended one from its store, or answers
  `turn_not_found`, which removes the pointer and asks the user to send the message again.
- **Ended,** or replaced by a later recorded turn: the saved transcript already shows it. The
  pointer is removed, nothing is replayed, and the chat looks up whatever turn runs now, so a
  newer turn from another window is followed live rather than an older question replayed.
- **Not in the saved transcript.** `locateTurn` asks the runtime (`/chat/active`). When it runs
  the turn, the saved transcript is loaded again and the turn placed by identity or by its
  `turn_start`; a turn sent less than `RESTORE_GRACE_MS` (10 seconds) ago, whose start may still be
  on its way to the server, is asked about again after 1, 2, and 4 seconds. When another turn
  runs, the pointer is removed and that turn is followed. Only when nothing of the turn was saved
  and the runtime answers that nothing runs is the pointer removed with a notice that the answer
  cannot be shown. A lookup that fails or comes back `unavailable` keeps the pointer and what the
  chat shows, and asks again after 2, 5, and 10 seconds (`UNKNOWN_RETRY_DELAYS_MS`), then every
  15 seconds while the pointer remains valid and the provider is mounted. **Reconnecting** stays
  visible until the lookup resolves. A lookup runs only in the project the turn was sent from,
  and a reply that arrives
  after a project switch, even once the user is back in that project, is dropped unread
  (`projectEpoch`); the restore then parks the turn or looks it up again.

A pointer whose saved messages carry no request ID at all, from a turn an older page saved, is
still placed by its `start`, and only over a transcript with no recorded turn from there on.
When the reattach
attempts run out, as for a live turn, the pointer stays for the next restore. Any other error
leaves the saved transcript as it was, shows a notice, and removes the pointer. While the session loads,
`detachedTurns` holds the turn as `restoring` with its last known activity and time, which
`ChatStatusLine` (`ChatTurnStatus.tsx`) shows as stale, also while `locateTurn` asks the
runtime. A send in that session is refused until the turn streams.

The provider receives the open project from `AppLayout` (`project`). On a switch it aborts the
streams of turns sent from another project with the reason `detached`, which neither stops the
turn nor saves anything, and lists them in `detachedTurns` as `other_project`; nothing of them is
shown in the other project, and a send in that session is refused. Switching back restores them
as above. A turn whose pointer could not be stored, because storage is unavailable, keeps its
stream across a switch. When the owner changes or signs out, the provider aborts every stream
without stopping its turn, and signing out removes the user's pointers; `removeAuth` in
`AuthContext.tsx` also clears every user's pointers and steers in the tab
(`forgetChatTabState`) before the page leaves.

The chat's header (`SurfaceTitle`, and the **Agent** page header) shows `chatStatus`: the live
turn's activity or its waiting tool, `reconnecting`, a detached turn, or how the last saved answer
ended. The closed sidebar's tab shows a dot while any turn runs or is restored, and
`openGeneralChat` reopens an active task or investigation chat with a turn going instead of
creating an empty chat. A tab that was closed has no pointers, and a reload in another tab does
not see this tab's; that tab finds a running turn from the runtime instead (see
[Following a Turn From Another Window](#following-a-turn-from-another-window)).

### Following a Turn From Another Window

A window or tab that did not start a turn learns about it from the runtime and follows it by
reattaching; it never submits anything and never saves the turn. The lookup is
`POST /copilot/chat/active` (`ChatActiveRequest`, `ChatActiveResponse`, not in the OpenAPI
schema), which `active_runtime_turn` in `pi_chat_service.py` forwards to the runtime's
`POST /chat/active` (`handleActiveChat` in `agent-runtime/src/server.ts`). The runtime answers from
its in-memory store holds: it opens no store and starts nothing. `owner_id` is the signed-in user,
so only that user's own chat is looked up. A turn sent from another project is reported only as
`other_project`, without its request ID, and a turn that already wrote its last event is not
reported. `running: false` is only the runtime's own answer that nothing runs. When the runtime
cannot be reached, answers with an error status, or answers without a boolean `running` (or a
running turn without its request ID), the API reports `running: false` with `unavailable: true`;
so does a chat whose runtime target is still being created or cleaned up (any
`ChatUnavailableError` but 404). No caller takes an unavailable reply for an ended turn: the
window's `apiActiveTurn` treats it as a failed lookup, the claim does not replace a recorded turn
on it, and the orphan check below does not reattach on it.

The window that starts a turn sends its start in the saved transcript as `turn_start`
(`ChatTurnStart`): `index`, the number of messages before the turn, and `digest`, a 64-bit hash
of the role, text, and steer flag of those messages and, unless the turn is a continue, the turn's
own message (`turnStartOf` and `transcriptDigest` in `ui/src/lib/copilotObservedTurn.ts`); an
answer of a recorded turn counts by its `turn_request_id` instead of its text. The API claims the
turn against it before sending it (see
[Recording a Turn on the Server](#recording-a-turn-on-the-server)). The runtime keeps it with the
running turn and reports it unchanged; a reattach sends none. The other window places the turn
only over a saved transcript that holds exactly that start (`observedTurnPlacement`), so the
replayed answer never appears under an earlier question from a copy loaded before the server saved
the turn's message; a turn the server recorded is placed by its `turn_request_id` first
(`recordedTurnPlacement`), as for a restore. When a loaded copy does not hold the start yet, the
window asks again after
1, 2, and 4 seconds (`FOLLOW_RETRY_DELAYS_MS`), then at the regular checks. A turn reported
without `turn_start`, sent by an older version of the page, is not followed.

The lookup only finds the turn: once followed, every tool start and end, status, wait, and the
end reach the window as the turn's live SSE events. The provider checks the active chat when it
opens, when the window is focused or shown again, and every `ACTIVE_TURN_POLL_MS` (15 seconds)
while the document is visible. Windows of the same browser do not wait for that check: the window
whose stream of a turn connects (sending it or reattaching to it) posts `{ owner, sessionId }` on
the `BroadcastChannel` `qdash.copilot.turns.v1` (`announceTurn`), and a window of the same user
showing that chat checks at once. The message names no turn and holds no text. It does not check a
chat that this tab streams, restores, holds a pointer for, or is still creating. A followed turn
runs as a `TurnPlan` with `observe` set: the stream folds the turn and its steers into the shown
transcript, as for a reattach, but saves nothing, stores no pointer, and raises no notification;
the server records the turn, and the starting window notifies. **Stop** in the following window stops the turn it follows.
`followedTurns` keeps a turn that was followed to its end from being followed again while the
runtime still reports it.

When the runtime answers that it runs nothing (not an `unavailable` reply) but the session's
`turn` is still `running` and started more than
`ORPHANED_TURN_MS` (60 seconds) ago in the open project, no API process records it any more: its
process restarted mid-turn and nobody reattached. The window then reattaches to it once
(`healedTurns`), which submits nothing, so the API records its end from the runtime's store, or
that the runtime never got it, instead of the chat showing its saved progress as running.

After a followed turn ends, the window shows the run the stream's `transcript` event reported;
without one, it loads the saved transcript after 1.5 and 5 seconds
(`OBSERVED_REFRESH_DELAYS_MS`). While no turn runs, each check also loads the saved transcript
(`refreshIdle`) and takes it when it differs, so a turn that started and ended between two checks
still appears. Neither load replaces a copy that holds something unsaved: a stream, a restore, a
pointer, a queued save, a steer, or a save that was not acknowledged (`transcriptSeq` against
`savedSeq`). The thumbnails of this window's own attachments are kept on the messages that did
not change (`withLocalAttachments`). A followed answer no saved copy holds yet is not replaced by
a shorter saved transcript (`unconfirmedFold`).

### Chat Notifications

`runTurn` raises a `ChatTurnEvent` through `subscribeChatEvents` at a turn's notable moments,
from its own stream only: `expert` on a `qdash_wait_agent_intervention` start or a successful
`qdash_request_agent_human`, then at the final `result` one of `approval`, `question`, or
`edit` when its blocks ask that of the user (`answerEventKind`), else `answer`, and `failed`
when the turn ends in an error. A stop the user made, a `noop`, a refused continue, and tool
steps or text as they stream raise nothing, nor does history loaded from the server. Each kind is
raised once per turn: the kinds raised are kept in the turn's pointer (`notified`) and seed the
next stream of the turn, so a reattach or a restore that replays the turn raises only what it had
not. A detached stream is not read, so a turn of another project raises nothing there.
Listeners run inside the stream's read loop, each in its own `try`: one that throws is logged and
skipped, so a failing notification never ends the turn or replaces its answer with an error.
Closing the sidebar or the floating window only unmounts that surface; the turn's stream belongs
to `CopilotChatSessionProvider` in `AppLayout`, and that is also when `ChatNotifier` starts
showing toasts for it.

`ChatNotifier` (mounted in `AppLayout` inside `ChatDockProvider`) turns an event into a Ding
toast (`@yusufceng1z/ding-react`, pinned in `ui/package.json`) with the ID
`chat:<request_id>:<kind>`, so a repeat updates the toast instead of adding one. It drops an
event of another owner or project, and one whose chat is on screen in a visible tab (the
**Agent** page, or the sidebar or floating window showing the active chat), and closes a chat's
toasts once that chat comes on screen. **Open chat** switches to the chat and opens the sidebar
off the **Agent** page; it checks the owner and that the chat still exists, and sends nothing.
Input needed (`approval`, `question`) and `failed` stay until dismissed.

`ChatToaster` (`ui/src/components/ui/Toast/ChatToaster.tsx`), mounted once by `ToastContainer`
beside the app's Sonner toaster, renders only chat notifications, at the top center. Its colors
come from the DaisyUI theme (`body .tst-viewport` in `globals.css`); Ding handles reduced motion,
Escape, and Alt+T. Sound is Ding's `toast.configure({ sound, volume })` from
`ui/src/lib/chatNotificationSettings.ts`: off by default and kept per browser in local storage,
set under **Settings → Copilot** (`ChatNotificationSettings`, whose **Preview** plays Ding's
`chime`).

### Calibration Session State in the Chat

A chat stores no link to an agent session. `linkedAgentSessions` in
`ui/src/lib/chatAgentSession.ts` reads it from the chat's own session-scoped agent tool calls,
saved in the answers' traces or in the live turn, that QDash completed or that still run, by
their `sessionId` argument; never from the model's text or a failed call. The last one is shown.
`ChatAgentSessionStatus` reads that session, its active intervention, its actions, and the
candidates of its latest completed measurement through the generated agent session hooks, under
the open project (in the request header and the query key), and shows nothing when QDash does not
find it there. `agentSessionStatus` derives the phase from those records only: an `active`
session without a running measurement waits for the agent's next decision, which only a chat
turn makes, and an intervention in `resume_authorized` is an expert's answer waiting for it. With
no turn running, the card says so and offers **Continue session**, which sends an ordinary
message under the user's model and approvals; nothing starts a turn on a reload or an expert's
answer. A session a codemode script touched without a direct tool call, or one a chat named
before traces kept arguments, is not found this way.

## Branches

A branch is a chat session that continues another one from one of its answers. It is a Pi fork
(`Conversation.fork(at)`) in the source chat's SQLite store, not a copy of the store: Pi 1.6 has no
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
| `stop_pending` | Set on a tombstone whose turn the runtime could not confirm stopped |
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
so nothing runs. `branchFrom` in `agent-runtime/src/branch.ts` refuses a source with a run, and
a store with queued submissions or live tasks in any conversation (also those a crash left,
which would resume beside the branch's first turn), and accepts only an entry visible from the
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

One writer per store: `server.ts` keeps one hold per owner and store (a chat turn, a fork, a
stop of stored work, or a deletion), so a turn in one branch refuses a turn in another (`409`,
`reason: "store_busy"`), a fork (`busy`), and a store deletion. Each `ActiveChat` records its QDash
session, conversation, and store generation; a steer, a steer status, and a stop reach a turn only
when they name exactly that chat (`ActiveChat.runs`), so a request for one branch, or for an
earlier chat of the same ID, never steers or stops another.

Every incarnation of a store has a *generation*. The API creates one per owner and store in the
`copilot_store_generation` collection (`store_generation`) the first time a request needs the
store, and sends it as `store_generation` with every runtime request about the store. While it
holds the store, the runtime records the generation in `<store>.generation` when it creates the
store, and checks it before it opens the store for a turn, fork, or stop (`claimStore` in
`store-identity.ts`); another generation is refused with `409`, `reason: "stale_store"`.
`DELETE /session` removes the store only for its generation (`removeStore`), and retires that
generation first, so a delayed request of a removed generation cannot create the store again.
A removal for an older generation answers `200` with `outcome: "stale"` and removes nothing. A
store from before generations is adopted by the first request that names one.
`readSteerReceipt` reads the named conversation's receipts. The owner and project checks for
steers are unchanged.

The workspace belongs to the store (see [Workspace](./workspace.md)): a branch shares the current
files, not a snapshot. `DELETE /copilot/chat/sessions/{session_id}` (`delete_session`) works in
this order:

1. Marks the session `deleted_at`, a tombstone that is hidden from the list, from reads, and from
   `resolve_runtime_target`, and that no save can bring back.
2. Stops the chat's own turn by its exact target (`abort_runtime_turn`), and, when no turn of it
   runs, the work its store kept for it from before a restart (`include_stored`, see above); a
   turn of another branch of the store keeps running. The outcome is `stopped`, `not_running`
   (`404`), or `unknown` (no answer, or another status); `unknown` marks the tombstone
   `stop_pending`.
3. If another session of the user that is not deleted, a pending branch included, uses the
   store, removes the store's tombstones, except `stop_pending` ones, and keeps the store. Its
   conversations stay in it. A `stop_pending` tombstone stays so that deleting the chat again,
   or `reclaim`, can stop exactly that chat; a confirmed stop clears it.
4. Otherwise calls `remove_runtime_store` with the store's generation: the runtime's
   `DELETE /session` removes that generation of the store,
   every branch conversation in it, and the workspace. The runtime refuses while a turn, a fork,
   or another deletion holds the store; the API then stops the turns of the store's deleted chats
   and tries again, three times in all. Only once the runtime confirmed the removal are the
   tombstones dropped.

Each request marks its tombstone before it checks for other users, so of two last sessions
deleted at once at least one removes the store. Steps 3 and 4 run under the store's teardown, a
lease (`TEARDOWN_LEASE`, 5 minutes) in the `copilot_store_teardown` collection that one request
holds at a time; another request leaves the store to it. While the teardown is held, the store's
name counts as taken, so no chat recreated under the same ID can write a new store meanwhile. A
teardown reads whether the store is used only once it holds the lease, and calls the runtime only
while tombstones remain. The lease is not what keeps a late teardown safe: its runtime calls and
retries can outlast it. The generation is. A teardown removes the generation it read, then drops
only the tombstones it read and forgets only that generation, so a teardown that outlived its
lease never removes, or forgets the tombstone or generation of, a chat recreated under the same
ID. When the removal still fails, the response is
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
`agent-runtime/test/chat-recovery-server.test.mjs` covers `turn_start` after history and a
recovered wrap-up, a stop during the recovery check, stopping a deleted branch's stored work,
store generations, and durable steer fences; `agent-runtime/test/store-identity.test.mjs` covers
generations and fences;
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
uv run pytest tests/qdash/copilot/test_pi_chat_service.py tests/qdash/api/routers/test_copilot_auth.py tests/qdash/api/services/test_copilot_chat_session_service.py tests/qdash/api/services/test_chat_turn_runs.py tests/qdash/api/services/test_chat_transcript.py -v
cd ui && bun run test:run src/hooks/__tests__/useCopilotChat.test.tsx src/hooks/__tests__/useCopilotChatSteerReload.test.tsx src/hooks/__tests__/useCopilotChatServerTranscript.test.tsx
task ci-agent-runtime
```

`agent-runtime/test/chat-control.test.mjs` runs steer and continue on real harnesses with a
scripted model, and `chat-steer-server.test.mjs` runs them over the runtime's HTTP routes.
`chat-reattach-server.test.mjs` drops a turn's stream while a tool parks on an expert's answer,
reattaches, answers, and checks that the resumed turn reaches the new stream with each step run
once, and that a reattach to a finished turn replays that turn and not the turn after it;
`stored-turn.test.mjs` covers the turn boundaries, and `turn-feed.test.mjs` the feed.
`tests/qdash/api/routers/test_evaluation.py` replays turns through `translate` against the
ledger, including a reattach that names another model and task. `ui/src/hooks/__tests__/useCopilotChatReattach.test.tsx`
and `ui/src/components/features/chat/__tests__/ChatTurnConnection.test.tsx` cover the browser
side.
`chat-steer-crash.test.mjs` kills a runtime process with a steer queued and checks that the next
process places it before the new message and reports `before_turn`.
`ui/src/hooks/__tests__/useCopilotChatSteerReload.test.tsx` covers restoring steers across a
reload, user isolation, and placing a `before_turn` steer.
`ui/src/hooks/__tests__/useCopilotChatRestore.test.tsx` covers a surface closing and reopening
over one stream, a provider remount that reattaches and resumes a turn waiting on the expert, an
ended turn restored from its record, `turn_not_found`, an unsaved message, a turn that cannot be
followed, switching projects and back, the turn's own project on every reattach and Stop, and
user isolation and sign-out; `ui/src/lib/__tests__/copilotTurnStore.test.ts` covers the stored
pointers, and `ChatTurnStatus.test.tsx`, `ChatAgentSessionStatus.test.tsx`, and
`ui/src/lib/__tests__/chatAgentSession.test.ts` the status shown.
`ui/src/hooks/__tests__/useCopilotChatLiveSync.test.tsx` runs a fake API that fans one turn's
events out to every stream of it: the sending window and a late window following a multi-tool
turn through waiting, running, and its end with one submission, a stop from the following window
shown in both, the same-browser announcement, a reload whose pointer's position no longer fits,
a continue, a stale pointer of an ended turn while a newer turn runs, a reload before the start
was saved, a turn nothing saved or runs, an orphaned recorded turn reattached so its end is
recorded, a lookup that is unavailable, fails, or is malformed (the pointer kept and the turn
followed once the runtime answers, and no orphan reattach), and lookups whose replies arrive after
a project switch (A to B, and A to B and back) or after a newer pointer was stored.
`ui/src/hooks/__tests__/useCopilotChatObserve.test.tsx` covers following a turn from another
window: a late lookup, a copy loaded before the turn's message was saved, a continue, a steered
turn, a turn without its start, the end taken from the `transcript` event or the saved transcript,
and a turn that ended between checks.
`tests/qdash/api/services/test_chat_turn_runs.py` covers the recorded turn: a turn whose only
response closes runs to its end and is saved, with its start and progress saved meanwhile; a
second request of the turn follows it without a second stream, and another project is refused; a
stop recorded from another process; a dropped runtime stream attached again; a stale start
refused unsent; a turn refused while another runs, and a turn left running by a restarted process
replaced, its saved progress marked interrupted, but kept as it is when the runtime cannot say;
a stale save that keeps the recorded turn and its rating; a stale save after a later turn started, which keeps every recorded turn; a rating of an earlier turn's answer that keeps
its stored payload; and a reattach after the end that writes nothing.
`test_chat_session_merge.py` covers the merge itself with exact ordered results: every in-order
subset and every order of a chat's durable messages, shuffled and repeated copies, a steered turn
and a continue, legacy messages and a late steer, a rating found by entry or place when folds
differ, an ambiguous rating, clearing a rating, a running or just-claimed turn, and a client-only
error. `tests/qdash/api/routers/test_copilot_chat_turn_http.py`
drives `/copilot/chat/stream` over ASGI: a response that disconnects (ASGI 2.3 and 2.4) leaves the
turn running with no subscriber, its progress and end are saved, and the owner reads the complete
chat from the session endpoint while another user cannot; only the owner's Stop ends a
disconnected turn as stopped, and a request of the turn from another project is refused; the
session's `turn` is named only in the turn's project, for a member, with or without
`X-Project-Id`, and not to a user in no project or whose membership ended.
`test_pi_chat_service.py` and `test_copilot_auth.py` cover `unavailable` for an unreachable,
failing, or malformed runtime and for a chat still being created. `test_chat_transcript.py` covers the fold and the digest's parity with
the page. `ui/src/hooks/__tests__/useCopilotChatServerTranscript.test.tsx` covers the page taking
the server's saved run, a `restart`, a failure read past its error, its own save when the server
could not save, `transcript_conflict`, `turn_running`, and Stop. `ui/src/lib/__tests__/copilotObservedTurn.test.ts` covers the
start and its placement, and the last two tests of `chat-reattach-server.test.mjs` cover the
runtime's lookup. The notification events are
covered in `useCopilotChatRestore.test.tsx` (once per turn across a reattach and a restore,
approval apart from a final answer, none for history or another project, a failure), and the
toasts in `ChatNotifier.test.tsx`, `ChatToaster.test.tsx`, and
`ChatNotificationSettings.test.tsx` (sound off by default). Run
the complete `task test-ui` suite when event rendering changes.
