"""Service for persisted copilot chat sessions.

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
  (``CopilotChatSessionService.reclaim``) removes one nobody retried.
- A deleted chat that was the last user of its store stays as a hidden
  *tombstone* (``deleted_at``) until the runtime confirms the store is gone;
  deleting it again, or the cleanup, retries the removal.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.copilot_chat_session import (
    CopilotChatBranchSchema,
    CopilotChatMessageSchema,
    CopilotChatSessionResponse,
    CopilotChatSessionSummary,
    CopilotChatSteerSchema,
    CreateCopilotChatBranchRequest,
    CreateCopilotChatSessionRequest,
    ListCopilotChatSessionsResponse,
    UpdateCopilotChatSessionRequest,
)
from qdash.common.utils.datetime import now
from qdash.dbmodel.copilot_chat_session import (
    CopilotChatBranchOrigin,
    CopilotChatMessage,
    CopilotChatSessionDocument,
    CopilotChatSteer,
)

logger = logging.getLogger(__name__)

# Sessions a client can see: a branch the runtime has not forked yet, and a deleted
# chat kept until its store is removed, are hidden.
_VISIBLE: dict[str, Any] = {"branch.status": {"$ne": "pending"}, "deleted_at": None}
# Sessions that still use their store: every one but a tombstone.
_LIVE: dict[str, Any] = {"deleted_at": None}
_TOMBSTONE: dict[str, Any] = {"deleted_at": {"$ne": None}}

BRANCH_LEASE = timedelta(minutes=2)
"""How long a branch request holds its pending branch: longer than its runtime fork call."""

RECLAIM_LIMIT = 20
"""At most this many pending branches and stores are cleaned up per ``reclaim`` call."""


def _to_doc_message(msg: CopilotChatMessageSchema) -> CopilotChatMessage:
    return CopilotChatMessage(
        role=msg.role,
        content=msg.content,
        attached_image=msg.attached_image,
        steer=CopilotChatSteer(**msg.steer.model_dump()) if msg.steer else None,
        entry_id=msg.entry_id,
        created_at=msg.created_at or now(),
    )


def _to_schema_message(msg: CopilotChatMessage) -> CopilotChatMessageSchema:
    return CopilotChatMessageSchema(
        role=msg.role,
        content=msg.content,
        attached_image=msg.attached_image,
        steer=CopilotChatSteerSchema(**msg.steer.model_dump()) if msg.steer else None,
        entry_id=msg.entry_id,
        created_at=msg.created_at,
    )


def _to_branch_schema(doc: CopilotChatSessionDocument) -> CopilotChatBranchSchema | None:
    if doc.branch is None:
        return None
    return CopilotChatBranchSchema(
        source_session_id=doc.branch.source_session_id,
        source_entry_id=doc.branch.source_entry_id,
    )


def store_of(doc: CopilotChatSessionDocument) -> str:
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
    """Whether the store's name is taken: a session, pending or deleted but kept, names it."""
    return CopilotChatSessionDocument.find_one(_store_users(username, store)).run() is not None


def _store_live(username: str, store: str) -> bool:
    """Whether a session that is not deleted, a pending branch included, still uses the store."""
    query = {**_store_users(username, store), **_LIVE}
    return CopilotChatSessionDocument.find_one(query).run() is not None


def _collection() -> Any:
    return CopilotChatSessionDocument.get_motor_collection()


def _reload(doc_id: Any) -> CopilotChatSessionDocument:
    doc = CopilotChatSessionDocument.find_one({"_id": doc_id}).run()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return doc


@dataclass(frozen=True)
class RuntimeTarget:
    """Where the runtime keeps one chat: its store and its conversation there (None: root)."""

    store_session_id: str
    conversation_id: str | None = None

    def payload(self) -> dict[str, str]:
        """The runtime request fields that name it."""
        return {
            "store_session_id": self.store_session_id,
            **(
                {"store_conversation_id": self.conversation_id}
                if self.conversation_id is not None
                else {}
            ),
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
    doc = CopilotChatSessionDocument.find_one(
        CopilotChatSessionDocument.username == username,
        CopilotChatSessionDocument.session_id == session_id,
    ).run()
    if doc is not None:
        if doc.deleted_at is not None:
            raise ChatUnavailableError(404, f"Chat session {session_id} not found")
        if doc.branch is not None and doc.branch.status == "pending":
            raise ChatUnavailableError(409, "This branch is still being created; try again")
        return RuntimeTarget(store_of(doc), doc.conversation_id)
    in_use = CopilotChatSessionDocument.find_one(
        {"username": username, "store_session_id": session_id}
    ).run()
    if in_use is not None:
        raise ChatUnavailableError(404, f"Chat session {session_id} not found")
    return RuntimeTarget(session_id)


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
# Remove a store no session uses any more from the runtime: (store, the deleted chats
# in it, whose turns may be stopped when they hold it) -> whether the store is gone.
ReleaseStore = Callable[[str, list[tuple[str, RuntimeTarget]]], Awaitable[bool]]
# Stop the turn of exactly one chat, if one runs: (session, where it lives).
StopChat = Callable[[str, RuntimeTarget], Awaitable[object]]


@dataclass(frozen=True)
class _BegunBranch:
    """The target session a branch request works on, and whether its source is gone."""

    doc: CopilotChatSessionDocument
    source_missing: bool = False


def _to_response(doc: CopilotChatSessionDocument) -> CopilotChatSessionResponse:
    return CopilotChatSessionResponse(
        session_id=doc.session_id,
        title=doc.title,
        context=doc.context,
        messages=[_to_schema_message(m) for m in doc.messages],
        branch=_to_branch_schema(doc),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_summary(doc: CopilotChatSessionDocument) -> CopilotChatSessionSummary:
    return CopilotChatSessionSummary(
        session_id=doc.session_id,
        title=doc.title,
        context=doc.context,
        message_count=len(doc.messages),
        branch=_to_branch_schema(doc),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class CopilotChatSessionService:
    """CRUD for per-user copilot chat sessions."""

    def list_sessions(self, *, username: str) -> ListCopilotChatSessionsResponse:
        docs = (
            CopilotChatSessionDocument.find(
                CopilotChatSessionDocument.username == username, _VISIBLE
            )
            .sort("-updated_at")
            .to_list()
        )
        return ListCopilotChatSessionsResponse(sessions=[_to_summary(d) for d in docs])

    def get_session(self, *, username: str, session_id: str) -> CopilotChatSessionResponse:
        doc = self._require_session(username=username, session_id=session_id)
        return _to_response(doc)

    def create_session(
        self,
        *,
        username: str,
        request: CreateCopilotChatSessionRequest,
    ) -> CopilotChatSessionResponse:
        if self._taken(username, request.session_id):
            # The ID of a deleted chat whose store is still used or not removed yet.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {request.session_id} already exists",
            )
        timestamp = now()
        doc = CopilotChatSessionDocument(
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
        request: UpdateCopilotChatSessionRequest,
    ) -> CopilotChatSessionResponse:
        doc = self._require_session(username=username, session_id=session_id)
        changes: dict[str, Any] = {"updated_at": now()}
        if request.title is not None:
            changes["title"] = request.title
        if request.context is not None:
            changes["context"] = request.context
        if request.messages is not None:
            changes["messages"] = [_to_doc_message(m).model_dump() for m in request.messages]
        # Never a whole-document save: a save racing a delete would bring the chat back.
        result = _collection().update_one({"_id": doc.id, **_VISIBLE}, {"$set": changes})
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found",
            )
        return _to_response(_reload(doc.id))

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
        ``reclaim``.
        """
        doc = await asyncio.to_thread(self._tombstone_session, username, session_id)
        store = store_of(doc)
        if doc.branch is None or doc.branch.status == "ready":
            await stop_chat(doc.session_id, RuntimeTarget(store, doc.conversation_id))
        return await self._settle_store(username, store, release_store)

    async def reclaim(self, *, username: str, release_store: ReleaseStore) -> None:
        """Clean up what failed requests of the user left behind.

        A pending branch whose request lease is over is taken over and removed:
        its request failed, or the client lost it, and nobody retried. The
        runtime may have forked it, and that conversation stays in the store
        until the store is removed. A store whose removal failed is removed
        again. Bounded by ``RECLAIM_LIMIT`` per call.
        """
        for doc in await asyncio.to_thread(self._expired_pending, username):
            operation = uuid.uuid4().hex
            claimed = await asyncio.to_thread(self._try_claim, doc, operation)
            if claimed is not None:
                await self._abandon_branch(claimed, operation, release_store)
        for store in await asyncio.to_thread(self._tombstoned_stores, username):
            await self._settle_store(username, store, release_store)

    def _taken(self, username: str, session_id: str) -> bool:
        """Whether a new chat cannot take the ID: a session, kept or not, or a store uses it."""
        doc = CopilotChatSessionDocument.find_one(
            {"username": username, "session_id": session_id}
        ).run()
        return doc is not None or store_in_use(username, session_id)

    def _require_session(self, *, username: str, session_id: str) -> CopilotChatSessionDocument:
        doc = self._find(username, session_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found",
            )
        return doc

    def _find(
        self, username: str, session_id: str, *, pending: bool = False
    ) -> CopilotChatSessionDocument | None:
        """A session that is not deleted; a pending branch only with ``pending``."""
        return CopilotChatSessionDocument.find_one(
            CopilotChatSessionDocument.username == username,
            CopilotChatSessionDocument.session_id == session_id,
            _LIVE if pending else _VISIBLE,
        ).run()

    # ------------------------------------------------------------ store removal

    def _tombstone_session(self, username: str, session_id: str) -> CopilotChatSessionDocument:
        """Hide a visible session as deleted, or find one deleted before whose store is kept."""
        doc = self._find(username, session_id)
        if doc is not None:
            _collection().update_one({"_id": doc.id, **_LIVE}, {"$set": {"deleted_at": now()}})
            return doc
        kept = CopilotChatSessionDocument.find_one(
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
        at once at least one sees no live session and removes the store.
        """
        tombstones = {**_store_users(username, store), **_TOMBSTONE}

        def deleted_chats() -> list[tuple[str, RuntimeTarget]] | None:
            docs = CopilotChatSessionDocument.find(tombstones).to_list()
            if _store_live(username, store):
                # A concurrent deletion may mark the last live session after this check.
                # Keep its tombstone so that a failed runtime removal remains retryable.
                _collection().delete_many({**tombstones, "_id": {"$in": [doc.id for doc in docs]}})
                return None
            return [
                (doc.session_id, RuntimeTarget(store, doc.conversation_id))
                for doc in docs
                if doc.branch is None or doc.branch.status == "ready"
            ]

        chats = await asyncio.to_thread(deleted_chats)
        if chats is None:
            return True
        if not await release_store(store, chats):
            logger.warning("Runtime store %s of %s is kept for a later removal", store, username)
            return False
        await asyncio.to_thread(_collection().delete_many, tombstones)
        return True

    def _tombstoned_stores(self, username: str) -> list[str]:
        docs = (
            CopilotChatSessionDocument.find({"username": username, **_TOMBSTONE})
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
        request: CreateCopilotChatBranchRequest,
        project_id: str | None,
        fork: ForkRuntime,
        release_store: ReleaseStore,
    ) -> CopilotChatSessionResponse:
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
        request: CreateCopilotChatBranchRequest,
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
            doc = CopilotChatSessionDocument(
                username=username,
                session_id=target_id,
                title=source.title,
                context=source.context,
                messages=[message.model_copy(deep=True) for message in source.messages[: cut + 1]],
                store_session_id=store_of(source),
                branch=CopilotChatBranchOrigin(
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

    def _claim(
        self, doc: CopilotChatSessionDocument, operation_id: str
    ) -> CopilotChatSessionDocument:
        claimed = self._try_claim(doc, operation_id)
        if claimed is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This branch is still being created; try again in a moment",
            )
        return claimed

    def _try_claim(
        self, doc: CopilotChatSessionDocument, operation_id: str
    ) -> CopilotChatSessionDocument | None:
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

    async def _release_lease(self, target: CopilotChatSessionDocument, operation_id: str) -> None:
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
        self, target: CopilotChatSessionDocument, forked: ForkedBranch, operation_id: str
    ) -> CopilotChatSessionDocument:
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
        self, target: CopilotChatSessionDocument, operation_id: str, release_store: ReleaseStore
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

    def _expired_pending(self, username: str) -> list[CopilotChatSessionDocument]:
        return (
            CopilotChatSessionDocument.find(
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


def _requested_as(doc: CopilotChatSessionDocument, source_session_id: str, entry_id: str) -> bool:
    """Whether ``doc`` was branched by a request for ``source_session_id`` at ``entry_id``."""
    return (
        doc.branch is not None
        and doc.branch.source_session_id == source_session_id
        and doc.branch.source_entry_id == entry_id
    )


def _same_branch(
    doc: CopilotChatSessionDocument, source: CopilotChatSessionDocument, entry_id: str
) -> bool:
    """Whether ``doc`` is the branch of ``source`` at ``entry_id``, in the source's store."""
    return (
        doc.branch is not None
        and doc.branch.source_session_id == source.session_id
        and doc.branch.source_entry_id == entry_id
        and doc.branch.source_conversation_id == source.conversation_id
        and store_of(doc) == store_of(source)
    )
