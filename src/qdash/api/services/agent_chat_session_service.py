"""Service for persisted agent chat sessions.

A chat session names where its runtime state lives: the store (one SQLite file
and one workspace per owner and store session) and its conversation there. A
chat that was never branched uses its own session ID and the root. A branch
uses the store of the chat it was branched from and the conversation the
runtime forked. Only this service sets those fields; no client request can.

A store is removed with the last session that uses it, and two lifecycles keep
that count honest when a request fails halfway:

- A branch is recorded *pending* before the runtime forks it, held by the
  request creating it (``branch.operation_id``) for a bounded lease
  (``BRANCH_LEASE``). Only that request finishes or removes it; a duplicate
  request is refused while the lease runs. A request that failed without
  knowing whether the runtime forked leaves it pending and counted. Once the
  lease is over, the same request again takes it over, and the cleanup
  (``AgentChatSessionService.reclaim``) removes one nobody retried.
- A deleted chat that was the last user of its store stays as a hidden
  *tombstone* (``deleted_at``) until the runtime confirms the store is gone;
  deleting it again, or the cleanup, retries the removal. A deleted chat whose
  turn could not be confirmed stopped (``stop_pending``) stays too, also while
  a branch still uses the store, until a retry confirms that nothing of it runs.

Removing a store is a *teardown* held by one request at a time, for a bounded
lease (``TEARDOWN_LEASE``), in the ``copilot_store_teardown`` collection. While
it is held, the store's name is taken, so no chat recreated under the same ID
can write a new store that the teardown would then remove. A request reads
whether the store is in use only after it holds the teardown, and calls the
runtime only while tombstones remain: once a teardown removed the store and its
tombstones, a later one finds nothing to remove and never calls the runtime.

The lease only keeps teardowns from running at once; it is not what keeps a
late one from removing a newer store. Every incarnation of a store has its own
*generation* (``copilot_store_generation``), created when a request first
needs the store and sent with every runtime request about it. The runtime
creates, opens, stops, and removes a store only for the generation it was
created with, and remembers the generations it removed (see the agent
runtime's ``store-identity.ts``). A teardown removes the generation it read,
then forgets that generation and only the tombstones it read, so a teardown
that outlived its lease, or a retry of one, never removes or forgets a chat
created again under the same ID.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise
from typing import Any, Literal

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.agent_chat_session import (
    AgentChatBranchSchema,
    AgentChatMessageSchema,
    AgentChatSessionResponse,
    AgentChatSessionSummary,
    AgentChatSteerSchema,
    AgentChatTurnSchema,
    CreateAgentChatBranchRequest,
    CreateAgentChatSessionRequest,
    ListAgentChatSessionsResponse,
    UpdateAgentChatSessionRequest,
)
from qdash.api.services.chat_transcript import interrupted_content, to_json, transcript_digest
from qdash.common.utils.datetime import now
from qdash.dbmodel.agent_chat_session import (
    AgentChatBranchOrigin,
    AgentChatMessage,
    AgentChatServerTurn,
    AgentChatSessionDocument,
    AgentChatSteer,
    TurnStatus,
)

logger = logging.getLogger(__name__)

# Sessions a client can see: a branch the runtime has not forked yet, and a deleted
# chat kept until its store is removed, are hidden.
_VISIBLE: dict[str, Any] = {"branch.status": {"$ne": "pending"}, "deleted_at": None}
# Sessions that still use their store: every one but a tombstone.
_LIVE: dict[str, Any] = {"deleted_at": None}
_TOMBSTONE: dict[str, Any] = {"deleted_at": {"$ne": None}}

BRANCH_LEASE = timedelta(minutes=2)
# How often a write of messages is tried again after another write landed first.
_WRITE_ATTEMPTS = 8
"""How long a branch request holds its pending branch: longer than its runtime fork call."""

RECLAIM_LIMIT = 20
"""At most this many pending branches and stores are cleaned up per ``reclaim`` call."""

TEARDOWN_LEASE = timedelta(minutes=5)
"""How long a request holds a store's teardown: longer than its runtime calls, which time out."""

StopOutcome = Literal["stopped", "not_running", "unknown"]
"""What stopping a chat's turn did: stopped it, found none running, or could not tell."""


def _to_doc_message(msg: AgentChatMessageSchema) -> AgentChatMessage:
    return AgentChatMessage(
        role=msg.role,
        content=msg.content,
        attached_image=msg.attached_image,
        steer=AgentChatSteer(**msg.steer.model_dump()) if msg.steer else None,
        entry_id=msg.entry_id,
        turn_request_id=msg.turn_request_id,
        created_at=msg.created_at or now(),
    )


def _to_schema_message(msg: AgentChatMessage) -> AgentChatMessageSchema:
    return AgentChatMessageSchema(
        role=msg.role,
        content=msg.content,
        attached_image=msg.attached_image,
        steer=AgentChatSteerSchema(**msg.steer.model_dump()) if msg.steer else None,
        entry_id=msg.entry_id,
        turn_request_id=msg.turn_request_id,
        created_at=msg.created_at,
    )


def _to_branch_schema(doc: AgentChatSessionDocument) -> AgentChatBranchSchema | None:
    if doc.branch is None:
        return None
    return AgentChatBranchSchema(
        source_session_id=doc.branch.source_session_id,
        source_entry_id=doc.branch.source_entry_id,
    )


def store_of(doc: AgentChatSessionDocument) -> str:
    """The session whose runtime store the chat uses."""
    return doc.store_session_id or doc.session_id


def _store_users(username: str, store: str) -> dict[str, Any]:
    """Every session of ``username`` that uses ``store``, pending branches included."""
    return {
        "username": username,
        "$or": [
            {"store_session_id": store},
            {"session_id": store, "store_session_id": None},
        ],
    }


def store_in_use(username: str, store: str) -> bool:
    """Whether the store's name is taken: a session, pending or deleted but kept, names it,
    or a request is tearing the store down."""
    return AgentChatSessionDocument.find_one(
        _store_users(username, store)
    ).run() is not None or _teardown_held(username, store)


def _teardowns() -> Any:
    """The store teardowns being run: one per owner and store at most (``_id``)."""
    # Legacy physical name kept from the Copilot era; renaming would drop live leases.
    return _collection().database["copilot_store_teardown"]


def _teardown_key(username: str, store: str) -> str:
    return f"{username}\x00{store}"


def _teardown_held(username: str, store: str) -> bool:
    """Whether a request holds the store's teardown now."""
    held = _teardowns().find_one(
        {"_id": _teardown_key(username, store), "lease_expires_at": {"$gt": now()}}
    )
    return held is not None


def _acquire_teardown(username: str, store: str, operation_id: str) -> bool:
    """Hold the store's teardown for ``operation_id``; False while another request holds it.

    One atomic upsert on the store's own ``_id``: it takes a teardown whose lease
    ran out, and fails on the duplicate ``_id`` of one still held.
    """
    timestamp = now()
    try:
        _teardowns().find_one_and_update(
            {"_id": _teardown_key(username, store), "lease_expires_at": {"$lte": timestamp}},
            {
                "$set": {
                    "username": username,
                    "store_session_id": store,
                    "operation_id": operation_id,
                    "lease_expires_at": timestamp + TEARDOWN_LEASE,
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        return False
    return True


def _holds_teardown(username: str, store: str, operation_id: str) -> bool:
    """Whether ``operation_id`` still holds the store's teardown, its lease not over."""
    held = _teardowns().find_one(
        {
            "_id": _teardown_key(username, store),
            "operation_id": operation_id,
            "lease_expires_at": {"$gt": now()},
        }
    )
    return held is not None


def _release_teardown(username: str, store: str, operation_id: str) -> None:
    _teardowns().delete_one({"_id": _teardown_key(username, store), "operation_id": operation_id})


def _generations() -> Any:
    """The current generation of each store: one per owner and store (``_id``)."""
    # Legacy physical name kept from the Copilot era; renaming would reset generations.
    return _collection().database["copilot_store_generation"]


def store_generation(username: str, store: str) -> str:
    """The generation of the store's current incarnation, created when it has none.

    One atomic upsert on the store's own ``_id``, so concurrent requests agree on
    one generation. A store created before generations existed gets one here,
    and the runtime adopts it with the first request that names it.
    """
    key = _teardown_key(username, store)
    for _ in range(2):
        try:
            doc = _generations().find_one_and_update(
                {"_id": key},
                {
                    "$setOnInsert": {
                        "username": username,
                        "store_session_id": store,
                        "generation": uuid.uuid4().hex,
                        "created_at": now(),
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Another request inserted it first; read theirs.
            continue
        return str(doc["generation"])
    doc = _generations().find_one({"_id": key})
    if doc is None:
        msg = f"Could not record a generation for store {store}"
        raise RuntimeError(msg)
    return str(doc["generation"])


def _forget_generation(username: str, store: str, generation: str) -> None:
    """Forget ``generation`` once its store is removed; a newer one is kept."""
    _generations().delete_one({"_id": _teardown_key(username, store), "generation": generation})


def _store_live(username: str, store: str) -> bool:
    """Whether a session that is not deleted, a pending branch included, still uses the store."""
    query = {**_store_users(username, store), **_LIVE}
    return AgentChatSessionDocument.find_one(query).run() is not None


def _collection() -> Any:
    return AgentChatSessionDocument.get_motor_collection()


def _reload(doc_id: Any) -> AgentChatSessionDocument:
    doc = AgentChatSessionDocument.find_one({"_id": doc_id}).run()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return doc


@dataclass(frozen=True)
class RuntimeTarget:
    """Where the runtime keeps one chat: its store and its conversation there (None: root).

    ``generation`` names the store's incarnation (see the module docstring); None
    only for a store that is not a chat's, such as a one-off analysis.
    """

    store_session_id: str
    conversation_id: str | None = None
    generation: str | None = None

    def payload(self) -> dict[str, str]:
        """The runtime request fields that name it."""
        return {
            "store_session_id": self.store_session_id,
            **(
                {"store_conversation_id": self.conversation_id}
                if self.conversation_id is not None
                else {}
            ),
            **({"store_generation": self.generation} if self.generation is not None else {}),
        }


class ChatUnavailableError(Exception):
    """The chat cannot reach the runtime: a branch still being created, or a deleted chat."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def resolve_runtime_target(username: str, session_id: str) -> RuntimeTarget:
    """Where the runtime keeps this user's chat, from the stored session only.

    A chat with no stored session yet (a new one, saved after its first turn)
    is its own store's root. A deleted chat whose store its branches still use
    is not reopened under its old ID.
    """
    doc = AgentChatSessionDocument.find_one(
        AgentChatSessionDocument.username == username,
        AgentChatSessionDocument.session_id == session_id,
    ).run()
    if doc is not None:
        if doc.deleted_at is not None:
            raise ChatUnavailableError(404, f"Chat session {session_id} not found")
        if doc.branch is not None and doc.branch.status == "pending":
            raise ChatUnavailableError(409, "This branch is still being created; try again")
        store = store_of(doc)
        return RuntimeTarget(store, doc.conversation_id, store_generation(username, store))
    in_use = AgentChatSessionDocument.find_one(
        {"username": username, "store_session_id": session_id}
    ).run()
    if in_use is not None:
        raise ChatUnavailableError(404, f"Chat session {session_id} not found")
    if _teardown_held(username, session_id):
        # A store of this name is being removed: a new chat must not write it meanwhile.
        raise ChatUnavailableError(409, "This chat ID is being cleaned up; try again shortly")
    return RuntimeTarget(session_id, generation=store_generation(username, session_id))


async def runtime_target(username: str, session_id: str) -> RuntimeTarget:
    """``resolve_runtime_target`` off the event loop."""
    return await asyncio.to_thread(resolve_runtime_target, username, session_id)


@dataclass(frozen=True)
class ForkedBranch:
    """What the runtime answered for a fork: the branch conversation, and whether it is new."""

    conversation_id: str
    created: bool


class BranchRefusedError(Exception):
    """The runtime answered and refused the fork; it created nothing."""

    def __init__(self, status_code: int, detail: str, reason: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.reason = reason


class ForkSettledError(RuntimeError):
    """The fork request ended without a usable answer: the runtime failed it, or never got it.

    Whether the runtime forked is not known, but nothing runs for the request any
    more, so a retry need not wait for the request's lease.
    """


# Fork one branch in the runtime: (store, source conversation or None for the root,
# entry, target session) -> the branch. Raises BranchRefusedError when the runtime
# refused it, ForkSettledError when the request is over and it is not known whether
# the runtime forked, anything else when the request may still be running there.
ForkRuntime = Callable[[str, str | None, str, str], Awaitable[ForkedBranch]]
# Remove a store no session uses any more from the runtime: (store, the generation to
# remove, the deleted chats in it, whose turns may be stopped when they hold it) ->
# whether that generation of the store is gone.
ReleaseStore = Callable[[str, str, list[tuple[str, RuntimeTarget]]], Awaitable[bool]]
# Stop the turn of exactly one chat, if one runs: (session, where it lives) -> what it did.
StopChat = Callable[[str, RuntimeTarget], Awaitable[StopOutcome]]


@dataclass(frozen=True)
class _BegunBranch:
    """The target session a branch request works on, and whether its source is gone."""

    doc: AgentChatSessionDocument
    source_missing: bool = False


class _NoTurn:
    """A response that names no recorded turn: its reader's project is not known."""


NO_TURN = _NoTurn()


def _to_turn_schema(
    doc: AgentChatSessionDocument, project_id: str | None
) -> AgentChatTurnSchema | None:
    """The session's recorded turn, named only to a reader in the project it was sent from.

    A reader in no project (``project_id`` None) is named no turn, even one recorded
    without a project.
    """
    turn = doc.turn
    if turn is None or project_id is None or turn.project_id != project_id:
        return None
    return AgentChatTurnSchema(
        request_id=turn.request_id,
        project_id=turn.project_id,
        status=turn.status,
        start_index=turn.start_index,
        continuing=turn.continuing,
        started_at=turn.started_at,
    )


def _to_response(
    doc: AgentChatSessionDocument, *, turn_project: str | None | _NoTurn = NO_TURN
) -> AgentChatSessionResponse:
    """The session as returned to its owner; ``turn`` only for a reader in ``turn_project``."""
    return AgentChatSessionResponse(
        session_id=doc.session_id,
        title=doc.title,
        context=doc.context,
        messages=[_to_schema_message(m) for m in doc.messages],
        branch=_to_branch_schema(doc),
        turn=None if isinstance(turn_project, _NoTurn) else _to_turn_schema(doc, turn_project),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_summary(doc: AgentChatSessionDocument) -> AgentChatSessionSummary:
    return AgentChatSessionSummary(
        session_id=doc.session_id,
        title=doc.title,
        context=doc.context,
        message_count=len(doc.messages),
        branch=_to_branch_schema(doc),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class AgentChatSessionService:
    """CRUD for per-user agent chat sessions."""

    def list_sessions(self, *, username: str) -> ListAgentChatSessionsResponse:
        docs = (
            AgentChatSessionDocument.find(AgentChatSessionDocument.username == username, _VISIBLE)
            .sort("-updated_at")
            .to_list()
        )
        return ListAgentChatSessionsResponse(sessions=[_to_summary(d) for d in docs])

    def get_session(
        self, *, username: str, session_id: str, project_id: str | None
    ) -> AgentChatSessionResponse:
        """The session; its recorded turn only when it was sent from ``project_id``.

        ``project_id`` is the project the reader is in and may read (None: none).
        """
        doc = self._require_session(username=username, session_id=session_id)
        return _to_response(doc, turn_project=project_id)

    def create_session(
        self,
        *,
        username: str,
        request: CreateAgentChatSessionRequest,
    ) -> AgentChatSessionResponse:
        if self._taken(username, request.session_id):
            # The ID of a deleted chat whose store is still used or not removed yet.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {request.session_id} already exists",
            )
        timestamp = now()
        doc = AgentChatSessionDocument(
            username=username,
            session_id=request.session_id,
            title=request.title,
            context=request.context,
            messages=[_to_doc_message(m) for m in request.messages],
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            doc.insert()
        except DuplicateKeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {request.session_id} already exists",
            ) from exc
        return _to_response(doc)

    def update_session(
        self,
        *,
        username: str,
        session_id: str,
        request: UpdateAgentChatSessionRequest,
    ) -> AgentChatSessionResponse:
        incoming = (
            [_to_doc_message(m) for m in request.messages] if request.messages is not None else None
        )
        for _ in range(_WRITE_ATTEMPTS):
            doc = self._require_session(username=username, session_id=session_id)
            changes: dict[str, Any] = {"updated_at": now()}
            if request.title is not None:
                changes["title"] = request.title
            if request.context is not None:
                changes["context"] = request.context
            query: dict[str, Any] = {"_id": doc.id, **_VISIBLE}
            update: dict[str, Any] = {"$set": changes}
            if incoming is not None:
                # The messages of the turn the server records are its own: a save made
                # from an older copy keeps them, and is merged again if a server write
                # lands in between (``revision``).
                merged = merge_saved_messages(doc, incoming)
                changes["messages"] = [m.model_dump() for m in merged]
                query.update(_at_revision(doc.revision))
                update["$inc"] = {"revision": 1}
            # Never a whole-document save: a save racing a delete would bring the chat back.
            result = _collection().update_one(query, update)
            if result.matched_count:
                return _to_response(_reload(doc.id))
            if self._find(username, session_id) is None:
                break
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The chat changed while it was saved; try again",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session {session_id} not found",
        )

    async def delete_session(
        self,
        *,
        username: str,
        session_id: str,
        stop_chat: StopChat,
        release_store: ReleaseStore,
    ) -> bool:
        """Delete the session; return whether the runtime state it leaves is settled.

        The session is hidden at once, as a tombstone, and its own turn is
        stopped, never one of another branch of its store. A store holds a chat
        and every branch of it: while another session, a pending branch
        included, uses it, the tombstone goes and the store stays. Otherwise the
        runtime removes the store, and the tombstone stays until it confirmed
        that, so a failure is retried by deleting the session again or by
        ``reclaim``. When the runtime could not say whether it stopped the turn,
        the tombstone stays even while the store is used, so that a retry can
        still find the chat and stop it.
        """
        doc = await asyncio.to_thread(self._tombstone_session, username, session_id)
        store = store_of(doc)
        if doc.branch is None or doc.branch.status == "ready":
            await self._stop_deleted(doc, stop_chat)
        return await self._settle_store(username, store, release_store)

    async def reclaim(
        self,
        *,
        username: str,
        release_store: ReleaseStore,
        stop_chat: StopChat | None = None,
    ) -> None:
        """Clean up what failed requests of the user left behind.

        A pending branch whose request lease is over is taken over and removed:
        its request failed, or the client lost it, and nobody retried. The
        runtime may have forked it, and that conversation stays in the store
        until the store is removed. A deleted chat whose turn was not confirmed
        stopped is stopped again (with ``stop_chat``). A store whose removal
        failed is removed again. Bounded by ``RECLAIM_LIMIT`` per call.
        """
        for doc in await asyncio.to_thread(self._expired_pending, username):
            operation = uuid.uuid4().hex
            claimed = await asyncio.to_thread(self._try_claim, doc, operation)
            if claimed is not None:
                await self._abandon_branch(claimed, operation, release_store)
        if stop_chat is not None:
            for doc in await asyncio.to_thread(self._unstopped, username):
                await self._stop_deleted(doc, stop_chat)
        for store in await asyncio.to_thread(self._tombstoned_stores, username):
            await self._settle_store(username, store, release_store)

    async def _stop_deleted(self, doc: AgentChatSessionDocument, stop_chat: StopChat) -> None:
        """Stop exactly this deleted chat's turn; keep it findable while that is unconfirmed.

        Also work the runtime's store kept for it from before a restart: no
        later turn of a deleted chat would recover it, and until it is stopped
        the store's other branches cannot start.
        """
        store = store_of(doc)
        generation = await asyncio.to_thread(store_generation, doc.username, store)
        outcome = await stop_chat(
            doc.session_id, RuntimeTarget(store, doc.conversation_id, generation)
        )
        await asyncio.to_thread(
            _collection().update_one,
            {"_id": doc.id, **_TOMBSTONE},
            {"$set": {"stop_pending": outcome == "unknown"}},
        )

    def _taken(self, username: str, session_id: str) -> bool:
        """Whether a new chat cannot take the ID: a session, kept or not, or a store uses it."""
        doc = AgentChatSessionDocument.find_one(
            {"username": username, "session_id": session_id}
        ).run()
        return doc is not None or store_in_use(username, session_id)

    def _require_session(self, *, username: str, session_id: str) -> AgentChatSessionDocument:
        doc = self._find(username, session_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found",
            )
        return doc

    def _find(
        self, username: str, session_id: str, *, pending: bool = False
    ) -> AgentChatSessionDocument | None:
        """A session that is not deleted; a pending branch only with ``pending``."""
        return AgentChatSessionDocument.find_one(
            AgentChatSessionDocument.username == username,
            AgentChatSessionDocument.session_id == session_id,
            _LIVE if pending else _VISIBLE,
        ).run()

    # ------------------------------------------------------------ store removal

    def _tombstone_session(self, username: str, session_id: str) -> AgentChatSessionDocument:
        """Hide a visible session as deleted, or find one deleted before whose store is kept."""
        doc = self._find(username, session_id)
        if doc is not None:
            _collection().update_one({"_id": doc.id, **_LIVE}, {"$set": {"deleted_at": now()}})
            return doc
        kept = AgentChatSessionDocument.find_one(
            {"username": username, "session_id": session_id, **_TOMBSTONE}
        ).run()
        if kept is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found",
            )
        return kept

    async def _settle_store(self, username: str, store: str, release_store: ReleaseStore) -> bool:
        """Drop the store's tombstones once it is used by a live session or removed.

        Tombstones are marked before this check, so of two last sessions deleted
        at once at least one sees no live session and removes the store. The
        check and the removal run while this request holds the store's teardown
        (see the module docstring); a request that cannot get it leaves the
        store to the one that holds it and reports it unsettled.
        """
        tombstones = {**_store_users(username, store), **_TOMBSTONE}
        operation = uuid.uuid4().hex
        if not await asyncio.to_thread(_acquire_teardown, username, store, operation):
            logger.info("Store %s of %s is being torn down by another request", store, username)
            return False

        def deleted_chats() -> tuple[str, list[Any], list[tuple[str, RuntimeTarget]]] | None:
            docs = AgentChatSessionDocument.find(tombstones).to_list()
            if _store_live(username, store):
                # A concurrent deletion may mark the last live session after this check.
                # Keep its tombstone so that a failed runtime removal remains retryable,
                # and keep a chat whose turn was not confirmed stopped, to stop it later.
                settled = [doc.id for doc in docs if not doc.stop_pending]
                _collection().delete_many({**tombstones, "_id": {"$in": settled}})
                return None
            generation = store_generation(username, store)
            return (
                generation,
                [doc.id for doc in docs],
                [
                    (doc.session_id, RuntimeTarget(store, doc.conversation_id, generation))
                    for doc in docs
                    if doc.branch is None or doc.branch.status == "ready"
                ],
            )

        try:
            remaining = await asyncio.to_thread(
                lambda: AgentChatSessionDocument.find_one(tombstones).run() is not None
            )
            if not remaining:
                # An earlier teardown removed the store and its tombstones: nothing is
                # left to remove, and a store of the same name now is a new chat's.
                return True
            found = await asyncio.to_thread(deleted_chats)
            if found is None:
                return True
            generation, read, chats = found
            if not await asyncio.to_thread(_holds_teardown, username, store, operation):
                return False
            if not await release_store(store, generation, chats):
                logger.warning(
                    "Runtime store %s of %s is kept for a later removal", store, username
                )
                return False

            def forget() -> None:
                # Only what this teardown read: a call that outlived its lease must
                # not forget the tombstones or the generation of a chat created again.
                _collection().delete_many({**tombstones, "_id": {"$in": read}})
                _forget_generation(username, store, generation)

            await asyncio.to_thread(forget)
            return True
        finally:
            await asyncio.to_thread(_release_teardown, username, store, operation)

    def _unstopped(self, username: str) -> list[AgentChatSessionDocument]:
        """Deleted chats whose turn was not confirmed stopped."""
        return (
            AgentChatSessionDocument.find(
                {"username": username, **_TOMBSTONE, "stop_pending": True}
            )
            .limit(RECLAIM_LIMIT)
            .to_list()
        )

    def _tombstoned_stores(self, username: str) -> list[str]:
        docs = (
            AgentChatSessionDocument.find({"username": username, **_TOMBSTONE})
            .limit(RECLAIM_LIMIT)
            .to_list()
        )
        return list(dict.fromkeys(store_of(doc) for doc in docs))

    # ------------------------------------------------------------------ branches

    async def branch_session(
        self,
        *,
        username: str,
        source_session_id: str,
        request: CreateAgentChatBranchRequest,
        project_id: str | None,
        fork: ForkRuntime,
        release_store: ReleaseStore,
    ) -> AgentChatSessionResponse:
        """Branch a chat at one of its saved answers into a new session.

        The new session is recorded first as a pending branch held by this
        request: hidden from the chat list, but a user of the source's store, so
        deleting the source meanwhile keeps the store. The runtime then forks the
        conversation, and only then does the session become ready, with the
        conversation the runtime created.

        Sending the same request again returns the same branch once it is ready.
        While another request holds the pending branch it is refused (409) and
        changes nothing. After a failure that left the branch pending, the retry
        takes it over (at once when the runtime answered, after the lease
        otherwise) and the runtime's fork, idempotent by target, finishes it. A
        refusal by the runtime, or a source deleted meanwhile, removes the
        pending branch, and with it the store when nothing else uses it.

        The session gets a copy of the source's messages through the selected
        answer. The answer must be one the chat saved with its runtime entry ID;
        the runtime checks it is a completed answer of the source's conversation.
        """
        operation = uuid.uuid4().hex
        begun = await asyncio.to_thread(
            self._begin_branch,
            username=username,
            source_session_id=source_session_id,
            request=request,
            project_id=project_id,
            operation_id=operation,
        )
        target = begun.doc
        assert target.branch is not None
        if target.branch.status == "ready":
            return _to_response(target)
        # Read after the pending session was stored: a source deleted before that may
        # have taken its store with it, one deleted after it leaves the store.
        if begun.source_missing or (
            await asyncio.to_thread(self._find, username, source_session_id) is None
        ):
            await self._abandon_branch(target, operation, release_store)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {source_session_id} not found",
            )
        try:
            forked = await fork(
                store_of(target),
                target.branch.source_conversation_id,
                request.entry_id,
                target.session_id,
            )
        except BranchRefusedError as exc:
            await self._abandon_branch(target, operation, release_store)
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        except ForkSettledError:
            await self._release_lease(target, operation)
            raise
        try:
            finished = await asyncio.to_thread(self._finish_branch, target, forked, operation)
        except HTTPException:
            raise
        except Exception:
            # The runtime answered; only recording it failed. The retry finishes it.
            await self._release_lease(target, operation)
            raise
        return _to_response(finished)

    def _begin_branch(
        self,
        *,
        username: str,
        source_session_id: str,
        request: CreateAgentChatBranchRequest,
        project_id: str | None,
        operation_id: str,
    ) -> _BegunBranch:
        """The target session: ready from an earlier request, or pending and held by this one."""
        target_id = request.target_session_id
        if target_id == source_session_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A chat cannot be its own branch"
            )
        existing = self._find(username, target_id, pending=True)
        same_request = existing is not None and _requested_as(
            existing, source_session_id, request.entry_id
        )
        if same_request and existing is not None and existing.branch is not None:
            if existing.branch.status == "ready":
                # A replay: the branch is the user's own, whatever the source's history is now.
                return _BegunBranch(existing)
        source = self._find(username, source_session_id)
        if source is None:
            if same_request and existing is not None:
                # Its source was deleted since: the request takes the branch over to remove it.
                return _BegunBranch(self._claim(existing, operation_id), source_missing=True)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {source_session_id} not found",
            )
        cut = next(
            (
                index
                for index, message in enumerate(source.messages)
                if message.role == "assistant" and message.entry_id == request.entry_id
            ),
            None,
        )
        if cut is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This answer is not saved with its runtime entry; it cannot be branched from",
            )
        if existing is None:
            if self._taken(username, target_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Session {target_id} already exists",
                )
            timestamp = now()
            doc = AgentChatSessionDocument(
                username=username,
                session_id=target_id,
                title=source.title,
                context=source.context,
                messages=[message.model_copy(deep=True) for message in source.messages[: cut + 1]],
                store_session_id=store_of(source),
                branch=AgentChatBranchOrigin(
                    source_session_id=source.session_id,
                    source_entry_id=request.entry_id,
                    source_conversation_id=source.conversation_id,
                    project_id=project_id,
                    status="pending",
                    operation_id=operation_id,
                    lease_expires_at=timestamp + BRANCH_LEASE,
                    created_at=timestamp,
                ),
                created_at=timestamp,
                updated_at=timestamp,
            )
            try:
                doc.insert()
                return _BegunBranch(doc)
            except DuplicateKeyError:
                existing = self._find(username, target_id, pending=True)
        if existing is None or not _same_branch(existing, source, request.entry_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {target_id} already exists",
            )
        assert existing.branch is not None
        if existing.branch.status == "ready":
            return _BegunBranch(existing)
        return _BegunBranch(self._claim(existing, operation_id))

    def _claim(self, doc: AgentChatSessionDocument, operation_id: str) -> AgentChatSessionDocument:
        claimed = self._try_claim(doc, operation_id)
        if claimed is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This branch is still being created; try again in a moment",
            )
        return claimed

    def _try_claim(
        self, doc: AgentChatSessionDocument, operation_id: str
    ) -> AgentChatSessionDocument | None:
        """Take a pending branch over from a request whose lease is over; None while it runs."""
        timestamp = now()
        result = _collection().update_one(
            {
                "_id": doc.id,
                "branch.status": "pending",
                **_LIVE,
                "$or": [
                    {"branch.lease_expires_at": None},
                    {"branch.lease_expires_at": {"$lte": timestamp}},
                ],
            },
            {
                "$set": {
                    "branch.operation_id": operation_id,
                    "branch.lease_expires_at": timestamp + BRANCH_LEASE,
                }
            },
        )
        return _reload(doc.id) if result.matched_count else None

    async def _release_lease(self, target: AgentChatSessionDocument, operation_id: str) -> None:
        """Let a retry take the pending branch over at once (best effort)."""

        def release() -> None:
            _collection().update_one(
                {"_id": target.id, "branch.status": "pending", "branch.operation_id": operation_id},
                {"$set": {"branch.lease_expires_at": None}},
            )

        try:
            await asyncio.to_thread(release)
        except Exception:
            logger.warning(
                "Could not release branch %s for a retry", target.session_id, exc_info=True
            )

    def _finish_branch(
        self, target: AgentChatSessionDocument, forked: ForkedBranch, operation_id: str
    ) -> AgentChatSessionDocument:
        """Make the pending branch ready, only while this request still holds it."""
        result = _collection().update_one(
            {
                "_id": target.id,
                "branch.status": "pending",
                "branch.operation_id": operation_id,
                **_LIVE,
            },
            {
                "$set": {
                    "conversation_id": forked.conversation_id,
                    "branch.status": "ready",
                    "branch.operation_id": None,
                    "branch.lease_expires_at": None,
                    "updated_at": now(),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This branch was taken over or removed while it was created; try again",
            )
        return _reload(target.id)

    async def _abandon_branch(
        self, target: AgentChatSessionDocument, operation_id: str, release_store: ReleaseStore
    ) -> None:
        """Remove a pending branch this request holds, and its store if nothing else uses it."""

        def tombstone() -> bool:
            result = _collection().update_one(
                {
                    "_id": target.id,
                    "branch.status": "pending",
                    "branch.operation_id": operation_id,
                    **_LIVE,
                },
                {"$set": {"deleted_at": now()}},
            )
            return bool(result.matched_count)

        if await asyncio.to_thread(tombstone):
            await self._settle_store(target.username, store_of(target), release_store)

    def _expired_pending(self, username: str) -> list[AgentChatSessionDocument]:
        return (
            AgentChatSessionDocument.find(
                {
                    "username": username,
                    "branch.status": "pending",
                    **_LIVE,
                    "$or": [
                        {"branch.lease_expires_at": None},
                        {"branch.lease_expires_at": {"$lte": now()}},
                    ],
                }
            )
            .limit(RECLAIM_LIMIT)
            .to_list()
        )


def _requested_as(doc: AgentChatSessionDocument, source_session_id: str, entry_id: str) -> bool:
    """Whether ``doc`` was branched by a request for ``source_session_id`` at ``entry_id``."""
    return (
        doc.branch is not None
        and doc.branch.source_session_id == source_session_id
        and doc.branch.source_entry_id == entry_id
    )


def _same_branch(
    doc: AgentChatSessionDocument, source: AgentChatSessionDocument, entry_id: str
) -> bool:
    """Whether ``doc`` is the branch of ``source`` at ``entry_id``, in the source's store."""
    return (
        doc.branch is not None
        and doc.branch.source_session_id == source.session_id
        and doc.branch.source_entry_id == entry_id
        and doc.branch.source_conversation_id == source.conversation_id
        and store_of(doc) == store_of(source)
    )


# ---------------------------------------------------------------------------
# Server-recorded chat turns
# ---------------------------------------------------------------------------
#
# The API records a chat turn's messages itself as the runtime streams them, so
# the saved chat holds the turn's progress and its end whether or not a browser
# watches it. ``turn`` names the latest such turn; the messages of every recorded
# turn carry its request ID (``turn_request_id``), and the latest turn's sit
# together from ``turn.start_index``. A client save keeps all of them, in the
# stored order (``merge_saved_messages``). Every write of ``messages`` is
# conditional on ``revision`` and bumps it, so a write based on an older copy is
# merged again rather than replacing a newer one.


def _at_revision(revision: int) -> dict[str, Any]:
    """Match a document still at ``revision`` (a missing field is revision 0)."""
    return {"revision": revision} if revision else {"revision": {"$in": [0, None]}}


def _run_bounds(messages: list[AgentChatMessage], request_id: str) -> tuple[int, int] | None:
    """Where the messages of turn ``request_id`` are: [start, end), or None."""
    tagged = [i for i, m in enumerate(messages) if m.turn_request_id == request_id]
    return (tagged[0], tagged[-1] + 1) if tagged else None


def _feedback_of(content: str) -> tuple[bool, Any, dict[str, Any] | None]:
    """(has feedback, the feedback, the payload without it) of a blocks message."""
    try:
        payload = json.loads(content)
    except ValueError:
        return False, None, None
    if not isinstance(payload, dict) or not isinstance(payload.get("blocks"), list):
        return False, None, None
    has = "feedback" in payload
    feedback = payload.pop("feedback", None)
    return has, feedback, payload


def _with_feedback(server: AgentChatMessage, state: tuple[bool, Any]) -> AgentChatMessage:
    """The server's answer with the rating ``state`` (has a rating, the rating).

    Only the ``feedback`` key changes: the answer itself (its blocks, trace,
    entry ID, and timestamps) stays the server's.
    """
    had, previous, payload = _feedback_of(server.content)
    if payload is None or state == (had, previous):
        return server
    if state[0]:
        payload["feedback"] = state[1]
    return server.model_copy(update={"content": to_json(payload)})


_Key = tuple[str, str]


@dataclass(frozen=True)
class _Keyed:
    """A message of a recorded turn's run, with what identifies it within the turn.

    ``intrinsic``: the turn's own user message, a steer (its request ID), or an
    answer with a runtime entry. ``positional``, for an answer: the message that
    follows it in the run (a steer, the turn's user message) or ``last``; None
    when an answer follows it.
    """

    at: int
    message: AgentChatMessage
    intrinsic: _Key | None
    positional: _Key | None


def _keyed_run(run: list[tuple[int, AgentChatMessage]]) -> list[_Keyed]:
    """Key each message of one turn's run (as one copy orders it)."""
    keyed: list[_Keyed] = []
    for i, (at, m) in enumerate(run):
        rid = m.turn_request_id or ""
        if m.role == "user":
            intrinsic: _Key | None = ("steer", m.steer.request_id) if m.steer else ("user", rid)
            keyed.append(_Keyed(at, m, intrinsic, None))
            continue
        nxt = run[i + 1][1] if i + 1 < len(run) else None
        positional: _Key | None
        if nxt is None:
            positional = ("last", rid)
        elif nxt.role == "user":
            positional = (
                ("before-steer", nxt.steer.request_id) if nxt.steer else ("before-user", rid)
            )
        else:
            positional = None
        keyed.append(_Keyed(at, m, ("entry", m.entry_id) if m.entry_id else None, positional))
    return keyed


def _stored_copy(run: list[_Keyed], client: _Keyed) -> _Keyed | None:
    """The stored message of a recorded turn's ``run`` that ``client`` is a copy of.

    Known by, in order: the turn's user message or a steer by what it is; an
    answer by its runtime entry, else by being equal to one stored answer
    (without the rating), else by its place in the turn (before a steer, before
    the turn's message, or last), never by its index, which differs between
    folds. Two answers with different entries are never the same. None when no
    stored message, or more than one, fits.
    """
    m = client.message
    same_role = [s for s in run if s.message.role == m.role]
    if m.role == "user":
        found = [s for s in same_role if s.intrinsic == client.intrinsic]
    elif m.entry_id and any(s.message.entry_id == m.entry_id for s in same_role):
        found = [s for s in same_role if s.message.entry_id == m.entry_id]
    else:
        unlike = [s for s in same_role if not (s.message.entry_id and m.entry_id)]
        found = [s for s in unlike if _comparable(s.message) == _comparable(m)]
        if len(found) != 1:
            found = [
                s for s in unlike if s.positional is not None and s.positional == client.positional
            ]
    return found[0] if len(found) == 1 else None


def _comparable(m: AgentChatMessage) -> tuple[Any, ...]:
    """A client-owned message without its rating, to find it in another copy.

    A plain-text answer and the blocks form the page wraps it in to rate it
    compare equal.
    """
    content: str = m.content
    _, _, payload = _feedback_of(m.content)
    if payload is not None:
        blocks = payload["blocks"]
        block = blocks[0] if len(blocks) == 1 else None
        if (
            set(payload) <= {"blocks", "assessment"}
            and payload.get("assessment") is None
            and isinstance(block, dict)
            and set(block) <= {"type", "content", "chart"}
            and block.get("type") == "text"
            and block.get("chart") is None
            and isinstance(block.get("content"), str)
        ):
            content = block["content"]
        else:
            content = to_json(payload)
    return (m.role, content, m.steer.request_id if m.steer else None, m.turn_request_id)


def merge_saved_messages(
    doc: AgentChatSessionDocument, incoming: list[AgentChatMessage]
) -> list[AgentChatMessage]:
    """What a client save of ``incoming`` stores, keeping every server-recorded turn.

    A message is durable when it carries the request ID (``turn_request_id``) of
    a turn the chat records; every other message is client-owned. The result
    keeps these invariants, whatever the copy holds:

    1. The durable messages are exactly the stored ones, in stored order, each
       once. A copy that omits, repeats, reorders, or holds part of a recorded
       turn cannot remove, repeat, move, or change one: to change the
       conversation from an earlier point, a new turn is sent from there, which
       truncates the chat when it is claimed (``claim_turn``).
    2. Of a durable message, only an answer's rating (``feedback``) comes from
       the client, from the client's copy of that same answer
       (``_stored_copy``: its runtime entry, an equal stored answer, or its
       place in the turn, never its index). When the client's copies of it
       disagree, or none is known, the stored rating stays. A copy of it without
       a rating clears it: the last save wins, as for every client change.
    3. Client-owned messages keep the copy's order, each at most once, and each
       follows every durable message that preceded it in the copy (a durable
       copy repeated or out of order moves nothing; one not known anchors at
       the end of its turn). Between two durable messages the copy holds next
       to each other in the chat, the client-owned messages are the copy's.
       Where the copy lacks durable messages in between (a copy saved before a
       turn, or one that dropped it), it did not see that part of the chat:
       the stored client-owned messages there that the copy does not hold
       (equal by role, text without rating, steer, and request ID) are kept;
       a copy's message equal to one of them takes its place, and the copy's
       others go before the next such message or at the end of that part.
    4. While the latest recorded turn runs, nothing from its start on comes from
       the client.
    """
    turn = doc.turn
    running = turn.request_id if turn is not None and turn.status == "running" else None
    recorded = {m.turn_request_id for m in doc.messages if m.turn_request_id is not None}
    if running is not None:
        recorded.add(running)
    if not recorded:
        return incoming

    # The stored chat, with a marker (None) where a running turn that has no
    # message yet (a continue just claimed) starts. The marker is durable.
    items: list[AgentChatMessage | None] = list(doc.messages)
    if running is not None and not any(m.turn_request_id == running for m in doc.messages):
        items.insert(min(turn.start_index if turn else 0, len(items)), None)

    def durable(x: AgentChatMessage | None) -> bool:
        return x is None or x.turn_request_id in recorded

    def runs(messages: list[AgentChatMessage | None]) -> dict[str, list[_Keyed]]:
        grouped: dict[str, list[tuple[int, AgentChatMessage]]] = {}
        for at, m in enumerate(messages):
            if m is not None and m.turn_request_id in recorded:
                grouped.setdefault(m.turn_request_id, []).append((at, m))
        return {rid: _keyed_run(run) for rid, run in grouped.items()}

    server_runs = runs(items)
    ends = {rid: run[-1].at for rid, run in server_runs.items()}
    if None in items:
        ends[running or ""] = items.index(None)

    # Where each durable copy is stored, and the client's copies of each stored message.
    stored_at: dict[int, int] = {}
    copies: dict[int, list[AgentChatMessage]] = {}
    for rid, client_run in runs(list(incoming)).items():
        for c in client_run:
            found = _stored_copy(server_runs.get(rid, []), c)
            if found is not None:
                stored_at[c.at] = found.at
                copies.setdefault(found.at, []).append(c.message)
            else:
                # Not known: it stands for somewhere in its turn, so it anchors at its end.
                stored_at[c.at] = ends[rid]

    def emit(at: int) -> AgentChatMessage | None:
        m = items[at]
        if m is None or m.role != "assistant":
            return m
        states: list[tuple[bool, Any]] = []
        for c in copies.get(at, []):
            has, feedback, payload = _feedback_of(c.content)
            if payload is not None and (has, feedback) not in states:
                states.append((has, feedback))
        return _with_feedback(m, states[0]) if len(states) == 1 else m

    # The durable messages the copy holds in stored order, and the client-owned
    # messages that follow each of them (-1: before any).
    anchors = [-1]
    owned: dict[int, list[int]] = {}
    for i, m in enumerate(incoming):
        if m.turn_request_id in recorded:
            if stored_at[i] > anchors[-1]:
                anchors.append(stored_at[i])
        else:
            owned.setdefault(anchors[-1], []).append(i)
    anchors.append(len(items))

    # Which stored client-owned message each client-owned message of the copy is:
    # the first equal one not taken yet.
    unmatched: dict[tuple[Any, ...], list[int]] = {}
    for at, x in enumerate(items):
        if x is not None and not durable(x):
            unmatched.setdefault(_comparable(x), []).append(at)
    in_copy: dict[int, int] = {}
    for i, m in enumerate(incoming):
        if m.turn_request_id not in recorded and (equal := unmatched.get(_comparable(m))):
            in_copy[equal.pop(0)] = i

    merged: list[AgentChatMessage | None] = []
    for held, following in pairwise(anchors):
        if held >= 0:
            merged.append(emit(held))
        theirs = owned.get(held, [])
        part = range(held + 1, following)
        if not any(durable(items[at]) for at in part):
            # The copy saw this part of the chat as the server has it: it is the copy's.
            merged.extend(incoming[i] for i in theirs)
            continue
        # The copy lacks durable messages here: keep the stored ones and the stored
        # client-owned messages the copy does not hold, with the copy's in between.
        place = {i: k for k, i in enumerate(theirs)}
        taken = 0
        for at in part:
            x = items[at]
            if durable(x):
                merged.append(emit(at))
            elif at not in in_copy:
                merged.append(x)
            elif in_copy[at] in place:
                upto = place[in_copy[at]] + 1
                merged.extend(incoming[i] for i in theirs[taken:upto])
                taken = max(taken, upto)
        merged.extend(incoming[i] for i in theirs[taken:])

    if running is not None:
        # The running turn and its place are the server's until it ends.
        first = next(i for i, m in enumerate(merged) if m is None or m.turn_request_id == running)
        merged[first:] = [emit(s.at) for s in server_runs.get(running, [])]
    return [m for m in merged if m is not None]


ClaimOutcome = Literal["claimed", "same_turn", "conflict", "busy", "gone"]


def _interrupted(messages: list[AgentChatMessage], request_id: str) -> list[AgentChatMessage]:
    """``messages`` with the progress turn ``request_id`` saved marked interrupted."""
    out: list[AgentChatMessage] = []
    for m in messages:
        content = (
            interrupted_content(m.content)
            if m.turn_request_id == request_id and m.role == "assistant"
            else None
        )
        out.append(m if content is None else m.model_copy(update={"content": content}))
    return out


def claim_turn(
    username: str,
    session_id: str,
    *,
    request_id: str,
    project_id: str | None,
    start_index: int,
    digest: str,
    user_message: AgentChatMessage | None,
    replace_running: bool = False,
) -> ClaimOutcome:
    """Record that turn ``request_id`` starts, before anything is sent to the runtime.

    The saved chat must hold the start the client sent the turn from: the
    ``start_index`` messages before it, whose digest with the turn's own message
    (``user_message``, None for a continue) is ``digest``. The chat then becomes
    those messages and the user's message, which the server saves itself, and
    the turn its recorded turn. ``conflict``: the saved chat differs (a stale
    window, or a save still on its way); nothing is written. ``same_turn``: the
    turn was recorded before (a retried request). ``busy``: another recorded turn
    still runs; with ``replace_running`` (the caller found that it no longer runs,
    for example after the API restarted) it is replaced.
    """
    for _ in range(_WRITE_ATTEMPTS):
        doc = AgentChatSessionDocument.find_one(
            {"username": username, "session_id": session_id, **_VISIBLE}
        ).run()
        if doc is None:
            return "gone"
        if doc.turn is not None and doc.turn.request_id == request_id:
            return "same_turn"
        if doc.turn is not None and doc.turn.status == "running" and not replace_running:
            return "busy"
        if len(doc.messages) < start_index:
            return "conflict"
        prefix = doc.messages[:start_index]
        if transcript_digest([*prefix, *([user_message] if user_message else [])]) != digest:
            return "conflict"
        if doc.turn is not None and doc.turn.status == "running":
            # The turn replaced runs nowhere: what it saved stays, marked interrupted, not
            # as an answer still in progress.
            prefix = _interrupted(prefix, doc.turn.request_id)
        timestamp = now()
        turn = AgentChatServerTurn(
            request_id=request_id,
            project_id=project_id,
            start_index=start_index,
            continuing=user_message is None,
            started_at=timestamp,
            updated_at=timestamp,
        )
        changes: dict[str, Any] = {
            "messages": [
                m.model_dump() for m in [*prefix, *([user_message] if user_message else [])]
            ],
            "turn": turn.model_dump(),
            "updated_at": timestamp,
        }
        if user_message is not None and doc.title == "New Chat" and user_message.content:
            changes["title"] = user_message.content[:50]
        result = _collection().update_one(
            {"_id": doc.id, **_VISIBLE, **_at_revision(doc.revision)},
            {"$set": changes, "$inc": {"revision": 1}},
        )
        if result.matched_count:
            return "claimed"
    return "conflict"


@dataclass(frozen=True)
class RecordedTurn:
    """The recorded turn of a chat and its messages, as stored."""

    turn: AgentChatServerTurn
    messages: list[AgentChatMessage]


def recorded_turn(username: str, session_id: str, request_id: str) -> RecordedTurn | None:
    """Turn ``request_id`` when it is the chat's recorded turn, with its messages."""
    doc = AgentChatSessionDocument.find_one(
        {"username": username, "session_id": session_id, **_VISIBLE}
    ).run()
    if doc is None or doc.turn is None or doc.turn.request_id != request_id:
        return None
    bounds = _run_bounds(doc.messages, request_id)
    return RecordedTurn(
        turn=doc.turn, messages=doc.messages[bounds[0] : bounds[1]] if bounds else []
    )


@dataclass(frozen=True)
class TurnWrite:
    """What writing a turn's messages did.

    ``saved``: written. ``ended``: the turn had already ended; ``messages`` are
    its stored ones. ``gone``: the chat was deleted or records another turn now.
    """

    outcome: Literal["saved", "ended", "gone"]
    messages: list[AgentChatMessage]


def write_turn(
    username: str,
    session_id: str,
    request_id: str,
    run: list[AgentChatMessage],
    *,
    status: TurnStatus = "running",
    error: str | None = None,
) -> TurnWrite:
    """Store ``run`` as the messages of the running turn ``request_id``.

    With a ``status`` other than ``running`` the turn ends: an ended turn is
    never written again, so a write that arrives late (a second stream of the
    same turn, a progress write) cannot replace its end. Raises the database's
    errors, so the caller can try again.
    """
    for _ in range(_WRITE_ATTEMPTS):
        doc = AgentChatSessionDocument.find_one(
            {"username": username, "session_id": session_id, **_VISIBLE}
        ).run()
        if doc is None or doc.turn is None or doc.turn.request_id != request_id:
            return TurnWrite("gone", [])
        bounds = _run_bounds(doc.messages, request_id)
        if doc.turn.status != "running":
            return TurnWrite("ended", doc.messages[bounds[0] : bounds[1]] if bounds else [])
        start = bounds[0] if bounds else min(doc.turn.start_index, len(doc.messages))
        timestamp = now()
        changes: dict[str, Any] = {
            "messages": [m.model_dump() for m in [*doc.messages[:start], *run]],
            "turn.start_index": start,
            "turn.updated_at": timestamp,
            "updated_at": timestamp,
        }
        if status != "running":
            changes.update({"turn.status": status, "turn.ended_at": timestamp, "turn.error": error})
        result = _collection().update_one(
            {
                "_id": doc.id,
                **_VISIBLE,
                **_at_revision(doc.revision),
                "turn.request_id": request_id,
                "turn.status": "running",
            },
            {"$set": changes, "$inc": {"revision": 1}},
        )
        if result.matched_count:
            return TurnWrite("saved", run)
    raise RuntimeError(f"Could not write turn {request_id}: the chat kept changing")


def request_turn_stop(username: str, session_id: str, turn_request_id: str | None) -> None:
    """Note that the user stopped the running recorded turn, so it ends as stopped."""
    query: dict[str, Any] = {
        "username": username,
        "session_id": session_id,
        **_VISIBLE,
        "turn.status": "running",
    }
    if turn_request_id is not None:
        query["turn.request_id"] = turn_request_id
    _collection().update_one(query, {"$set": {"turn.stop_requested": True}})


def turn_stop_requested(username: str, session_id: str, request_id: str) -> bool:
    """Whether the user stopped turn ``request_id``, from any window or API process."""
    recorded = recorded_turn(username, session_id, request_id)
    return recorded is not None and recorded.turn.stop_requested
