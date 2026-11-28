"""Read-only snapshots of agent chats shared with a project.

A chat stays private to its owner. Sharing copies what the conversation showed into a
separate snapshot that every member of one project may read; later changes to the chat
reach the snapshot only when the owner updates it. The copy keeps the user's messages and
the answers' text, charts and composed UIs, and leaves out what belongs to the owner's
runtime: tool steps and their output, workspace files, figure paths, interactive cards,
attachments, and every store, conversation, entry or turn identifier.

A chat is not bound to one project, but each of its turns is admitted in one
(``AgentChatTurnDocument``). A chat whose recorded turns, those inherited from the chats
it was branched from included, ran in another project is not shared, so a snapshot never carries one project's answers to the members of another.
Messages without a recorded turn (saved before turns were recorded) cannot be checked;
the owner reviews them before sharing.

The chat's owner shares, updates and stops sharing; a project owner may also stop sharing,
as a project owner may delete any dashboard of the project.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from pymongo.errors import DuplicateKeyError
from starlette import status
from starlette.exceptions import HTTPException

from qdash.api.schemas.agent_chat_session import (
    AgentChatShareBlockSchema,
    AgentChatShareBlockType,
    AgentChatShareMessageSchema,
    AgentChatShareResponse,
    AgentChatShareStatusResponse,
    AgentChatShareSummary,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.common.utils.datetime import now
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.agent_chat_session import AgentChatSessionDocument
from qdash.dbmodel.agent_chat_share import (
    AgentChatShareBlock,
    AgentChatShareDocument,
    AgentChatShareMessage,
)
from qdash.dbmodel.agent_chat_turn import AgentChatTurnDocument

if TYPE_CHECKING:
    from qdash.api.lib.project import ProjectContext
    from qdash.dbmodel.agent_chat_session import AgentChatMessage

SHARE_NOT_FOUND = "Shared chat not found"
ERROR_PREFIX = "Error: "
# Session lookups match the chat service: a deleted chat or a pending branch is not shared.
_VISIBLE: dict[str, Any] = {"branch.status": {"$ne": "pending"}, "deleted_at": None}


def _answer_blocks(content: str) -> dict[str, Any] | None:
    """The JSON blocks payload of a structured answer, or None for plain Markdown."""
    if not content.startswith("{"):
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("blocks"), list):
        return data
    return None


def _shared_block(raw: Any) -> AgentChatShareBlock | None:
    """The user-facing part of one answer block; None for what a snapshot leaves out."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    content = raw.get("content") if isinstance(raw.get("content"), str) else None
    if kind == "text":
        return AgentChatShareBlock(type="text", content=content) if content else None
    if kind == "chart":
        chart = raw.get("chart")
        if not isinstance(chart, dict) or not isinstance(chart.get("data"), list):
            return None
        layout = chart.get("layout")
        return AgentChatShareBlock(
            type="chart",
            chart={"data": chart["data"], "layout": layout if isinstance(layout, dict) else {}},
        )
    if kind == "ui":
        ui = raw.get("ui")
        if not isinstance(ui, dict) and not content:
            return None
        return AgentChatShareBlock(
            type="ui", content=content, ui=ui if isinstance(ui, dict) else None
        )
    return None


def _has_sent_images(payload: dict[str, Any]) -> bool:
    images = payload.get("images_sent")
    if not isinstance(images, dict):
        return False
    return bool(images.get("experiment_figure")) or bool(images.get("expected_images"))


def _has_trace(payload: dict[str, Any]) -> bool:
    trace = payload.get("trace")
    return isinstance(trace, dict) and bool(trace.get("steps"))


def snapshot_message(message: AgentChatMessage) -> AgentChatShareMessage | None:
    """One chat message as a snapshot keeps it; None for a message it leaves out."""
    if message.role == "user":
        return AgentChatShareMessage(
            role="user",
            blocks=[AgentChatShareBlock(type="text", content=message.content)],
            figures_attached=bool(message.attached_image),
            created_at=message.created_at,
        )
    if message.role != "assistant":
        return None
    if message.content.startswith(ERROR_PREFIX):
        return AgentChatShareMessage(
            role="assistant",
            blocks=[AgentChatShareBlock(type="text", content=message.content[len(ERROR_PREFIX) :])],
            is_error=True,
            created_at=message.created_at,
        )
    payload = _answer_blocks(message.content)
    if payload is None:
        return AgentChatShareMessage(
            role="assistant",
            blocks=[AgentChatShareBlock(type="text", content=message.content)],
            created_at=message.created_at,
        )
    raw_blocks: list[Any] = payload["blocks"]
    blocks = [block for raw in raw_blocks if (block := _shared_block(raw)) is not None]
    incomplete: Literal["stopped", "interrupted"] | None = None
    if payload.get("stopped"):
        incomplete = "stopped"
    elif payload.get("interrupted") or payload.get("in_progress"):
        # Not running any more when shared (a running turn is refused), so it never ended.
        incomplete = "interrupted"
    return AgentChatShareMessage(
        role="assistant",
        blocks=blocks,
        incomplete=incomplete,
        omitted_content=(
            len(blocks) < len(raw_blocks) or _has_trace(payload) or _has_sent_images(payload)
        ),
        created_at=message.created_at,
    )


def _to_block_schema(block: AgentChatShareBlock) -> AgentChatShareBlockSchema:
    return AgentChatShareBlockSchema(
        type=AgentChatShareBlockType(block.type),
        content=block.content,
        chart=block.chart,
        ui=block.ui,
    )


def _to_message_schema(message: AgentChatShareMessage) -> AgentChatShareMessageSchema:
    return AgentChatShareMessageSchema(
        role=message.role,
        blocks=[_to_block_schema(b) for b in message.blocks],
        is_error=message.is_error,
        figures_attached=message.figures_attached,
        incomplete=message.incomplete,
        omitted_content=message.omitted_content,
        created_at=message.created_at,
    )


def _to_summary(doc: AgentChatShareDocument) -> AgentChatShareSummary:
    return AgentChatShareSummary(
        share_id=doc.share_id,
        project_id=doc.project_id,
        title=doc.title,
        message_count=len(doc.messages),
        created_at=doc.created_at,
        snapshot_at=doc.snapshot_at,
    )


# How many chats a branch's lineage is followed through before it counts as unknown.
_MAX_LINEAGE = 64


def _lineage(chat: AgentChatSessionDocument) -> tuple[list[str], bool]:
    """The chat's session and those of the chats it was branched from, nearest first.

    A branch copies the messages of its source up to the answer it was branched at,
    each with its ``turn_request_id``, so an inherited message's turn was recorded under
    the source chat, or further up when the source was itself a branch. Deleted sources
    whose document is kept still count. The lineage is complete only when every source
    is found: a source that is gone, or whose session ID was taken by a chat created
    no earlier than the branch, hides where its own messages came from. A cycle or a lineage
    longer than ``_MAX_LINEAGE`` also counts as incomplete.
    """
    sessions = [chat.session_id]
    current = chat
    while current.branch is not None:
        origin = current.branch
        source_id = origin.source_session_id
        if source_id in sessions or len(sessions) >= _MAX_LINEAGE:
            return sessions, False
        sessions.append(source_id)
        source = AgentChatSessionDocument.find_one(
            {"username": chat.username, "session_id": source_id}
        ).run()
        # A source is created before any branch of it; stored times are rounded to the
        # millisecond, so a tie also counts as a later chat that took the ID.
        if source is None or source.created_at >= origin.created_at:
            return sessions, False
        current = source
    return sessions, True


def _turn_projects(chat: AgentChatSessionDocument, request_ids: list[str]) -> set[str]:
    """The projects the chat's recorded turns, its inherited ones included, ran in.

    A turn is identified by its user, session and request ID, so while the lineage is
    complete a request ID is looked up only in the chat's lineage: another chat of the
    user with the same request ID is not one of its turns. When the lineage is
    incomplete, every request ID is looked up across all of the user's chats, even one
    also found in the lineage: a message inherited through a missing source may share
    its request ID with a turn recorded here, so a local match does not prove where
    that message came from. That may refuse a chat for an unrelated turn, never admit
    one with another project's answers.
    """
    sessions, complete = _lineage(chat)
    query: dict[str, Any] = {"username": chat.username, "request_id": {"$in": request_ids}}
    if complete:
        query["session_id"] = {"$in": sessions}
    turns = AgentChatTurnDocument.find(query).to_list()
    return {turn.project_id for turn in turns}


class AgentChatShareService:
    """Share, read, update and stop sharing chat snapshots in a project."""

    @staticmethod
    def _require_chat(username: str, session_id: str) -> AgentChatSessionDocument:
        doc = AgentChatSessionDocument.find_one(
            AgentChatSessionDocument.username == username,
            AgentChatSessionDocument.session_id == session_id,
            _VISIBLE,
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found",
            )
        return doc

    @staticmethod
    def _find_for_chat(
        project_id: str, username: str, session_id: str
    ) -> AgentChatShareDocument | None:
        return AgentChatShareDocument.find_one(
            {
                "project_id": project_id,
                "owner_username": username,
                "source_session_id": session_id,
            }
        ).run()

    @staticmethod
    def _require_share(ctx: ProjectContext, share_id: str) -> AgentChatShareDocument:
        """A share of the caller's project; another project's share is reported as missing."""
        doc = AgentChatShareDocument.find_one(
            {"share_id": share_id, "project_id": ctx.project_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SHARE_NOT_FOUND)
        return doc

    @staticmethod
    def _check_shareable(chat: AgentChatSessionDocument, project_id: str) -> None:
        """Refuse a chat that is running, empty, or has turns from another project."""
        if chat.turn is not None and chat.turn.status == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An answer is still being written; share the chat after it ends",
            )
        if not chat.messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This chat has no messages to share yet",
            )
        projects: set[str] = set()
        if chat.turn is not None and chat.turn.project_id:
            projects.add(chat.turn.project_id)
        if chat.branch is not None and chat.branch.project_id:
            projects.add(chat.branch.project_id)
        request_ids = sorted({m.turn_request_id for m in chat.messages if m.turn_request_id})
        if request_ids:
            projects.update(_turn_projects(chat, request_ids))
        if projects - {project_id}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This chat has answers from another project, so it cannot be shared with "
                    "this project"
                ),
            )

    def _require_still_visible(self, chat: AgentChatSessionDocument, *, username: str) -> None:
        """After writing a snapshot, remove it again if its chat was deleted meanwhile.

        Deleting a chat first hides it (a tombstone, ``deleted_at`` set) and only then
        removes its snapshots. A deletion that ran between reading the chat and writing
        the snapshot has removed nothing of this write, so the chat is read again, by
        its document ID so a later chat reusing the session ID does not count: hidden,
        pending or gone, the snapshots are removed here. A deletion that hides the chat
        after this read removes them itself.
        """
        still_visible = AgentChatSessionDocument.find_one({"_id": chat.id, **_VISIBLE}).run()
        if still_visible is not None:
            return
        self.delete_for_chat(username=username, session_id=chat.session_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session {chat.session_id} not found",
        )

    def get_status(self, ctx: ProjectContext, *, session_id: str) -> AgentChatShareStatusResponse:
        """Whether the caller's chat is shared with the current project."""
        username = ctx.user.username
        self._require_chat(username, session_id)
        doc = self._find_for_chat(ctx.project_id, username, session_id)
        return AgentChatShareStatusResponse(share=_to_summary(doc) if doc else None)

    def publish(self, ctx: ProjectContext, *, session_id: str) -> AgentChatShareSummary:
        """Share the caller's chat with the current project, or replace its snapshot.

        The snapshot holds the chat as it is now; later changes are not copied until the
        owner publishes again. The share keeps its ID, so a copied link stays valid.
        """
        username = ctx.user.username
        chat = self._require_chat(username, session_id)
        self._check_shareable(chat, ctx.project_id)
        messages = [m for m in (snapshot_message(msg) for msg in chat.messages) if m is not None]
        taken_at = now()
        changes: dict[str, Any] = {
            "title": chat.title,
            "messages": [m.model_dump() for m in messages],
            "snapshot_at": taken_at,
            "owner_user_id": ctx.user.user_id,
        }
        existing = self._find_for_chat(ctx.project_id, username, session_id)
        if existing is None:
            doc = AgentChatShareDocument(
                project_id=ctx.project_id,
                owner_username=username,
                owner_user_id=ctx.user.user_id,
                source_session_id=session_id,
                title=chat.title,
                messages=messages,
                created_at=taken_at,
                snapshot_at=taken_at,
            )
            try:
                doc.insert()
            except DuplicateKeyError:
                # Another request shared the same chat first; replace its snapshot instead.
                pass
            else:
                self._require_still_visible(chat, username=username)
                # Answer with the stored copy, so its timestamps read as they will later.
                stored = self._find_for_chat(ctx.project_id, username, session_id)
                return _to_summary(stored or doc)
        AgentChatShareDocument.get_motor_collection().update_one(
            {
                "project_id": ctx.project_id,
                "owner_username": username,
                "source_session_id": session_id,
            },
            {"$set": changes},
        )
        self._require_still_visible(chat, username=username)
        updated = self._find_for_chat(ctx.project_id, username, session_id)
        if updated is None:
            # Stopped sharing between the two writes.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sharing was stopped while the snapshot was updated; share it again",
            )
        return _to_summary(updated)

    def get(self, ctx: ProjectContext, *, share_id: str) -> AgentChatShareResponse:
        """A snapshot shared with the caller's project."""
        doc = self._require_share(ctx, share_id)
        is_owner = doc.owner_username == ctx.user.username
        return AgentChatShareResponse(
            share_id=doc.share_id,
            project_id=doc.project_id,
            title=doc.title,
            owner_username=doc.owner_username,
            messages=[_to_message_schema(m) for m in doc.messages],
            created_at=doc.created_at,
            snapshot_at=doc.snapshot_at,
            is_owner=is_owner,
            can_revoke=is_owner or ctx.role == ProjectRole.OWNER,
        )

    def revoke(self, ctx: ProjectContext, *, share_id: str) -> SuccessResponse:
        """Stop sharing: the chat's owner or a project owner removes the snapshot."""
        doc = self._require_share(ctx, share_id)
        if doc.owner_username != ctx.user.username and ctx.role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the chat's owner or a project owner can stop sharing this chat",
            )
        AgentChatShareDocument.get_motor_collection().delete_one(
            {"share_id": doc.share_id, "project_id": ctx.project_id}
        )
        return SuccessResponse(message="Stopped sharing the chat")

    @staticmethod
    def delete_for_chat(*, username: str, session_id: str) -> None:
        """Remove every snapshot of a chat its owner deleted, in every project."""
        AgentChatShareDocument.get_motor_collection().delete_many(
            {"owner_username": username, "source_session_id": session_id}
        )
