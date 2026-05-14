"""Service for persisted copilot chat sessions."""

from __future__ import annotations

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.copilot_chat_session import (
    CopilotChatMessageSchema,
    CopilotChatSessionResponse,
    CopilotChatSessionSummary,
    CreateCopilotChatSessionRequest,
    ListCopilotChatSessionsResponse,
    UpdateCopilotChatSessionRequest,
)
from qdash.common.utils.datetime import now
from qdash.dbmodel.copilot_chat_session import (
    CopilotChatMessage,
    CopilotChatSessionDocument,
)


def _to_doc_message(msg: CopilotChatMessageSchema) -> CopilotChatMessage:
    return CopilotChatMessage(
        role=msg.role,
        content=msg.content,
        attached_image=msg.attached_image,
        created_at=msg.created_at or now(),
    )


def _to_schema_message(msg: CopilotChatMessage) -> CopilotChatMessageSchema:
    return CopilotChatMessageSchema(
        role=msg.role,
        content=msg.content,
        attached_image=msg.attached_image,
        created_at=msg.created_at,
    )


def _to_response(doc: CopilotChatSessionDocument) -> CopilotChatSessionResponse:
    return CopilotChatSessionResponse(
        session_id=doc.session_id,
        title=doc.title,
        context=doc.context,
        messages=[_to_schema_message(m) for m in doc.messages],
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_summary(doc: CopilotChatSessionDocument) -> CopilotChatSessionSummary:
    return CopilotChatSessionSummary(
        session_id=doc.session_id,
        title=doc.title,
        context=doc.context,
        message_count=len(doc.messages),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class CopilotChatSessionService:
    """CRUD for per-user copilot chat sessions."""

    def list_sessions(self, *, username: str) -> ListCopilotChatSessionsResponse:
        docs = (
            CopilotChatSessionDocument.find(CopilotChatSessionDocument.username == username)
            .sort(-CopilotChatSessionDocument.updated_at)
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
        if request.title is not None:
            doc.title = request.title
        if request.context is not None:
            doc.context = request.context
        if request.messages is not None:
            doc.messages = [_to_doc_message(m) for m in request.messages]
        doc.updated_at = now()
        doc.save()
        return _to_response(doc)

    def delete_session(self, *, username: str, session_id: str) -> None:
        doc = self._require_session(username=username, session_id=session_id)
        doc.delete()

    def _require_session(self, *, username: str, session_id: str) -> CopilotChatSessionDocument:
        doc = CopilotChatSessionDocument.find_one(
            CopilotChatSessionDocument.username == username,
            CopilotChatSessionDocument.session_id == session_id,
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found",
            )
        return doc
