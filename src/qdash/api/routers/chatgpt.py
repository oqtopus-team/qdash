"""The current user's ChatGPT plan connection for Copilot chat.

Every route acts on the authenticated QDash user only; no route accepts a user
ID, and no response carries a token.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from qdash.api.dependencies import get_chatgpt_connection_service
from qdash.api.lib.auth import get_current_active_user
from qdash.api.lib.chatgpt_oauth import USAGE_URL
from qdash.api.schemas.auth import User
from qdash.api.schemas.chatgpt_connection import (
    ChatGPTConnectionStatus,
    CompleteChatGPTAuthorizationRequest,
    DisconnectChatGPTResponse,
    StartChatGPTAuthorizationRequest,
    StartChatGPTAuthorizationResponse,
)
from qdash.api.services import pi_chat_service
from qdash.api.services.chatgpt_connection_service import (
    ChatGPTConnectionError,
    ChatGPTConnectionService,
)

router = APIRouter()

Service = Annotated[ChatGPTConnectionService, Depends(get_chatgpt_connection_service)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]


def _http_error(exc: ChatGPTConnectionError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


async def _status_response(
    service: ChatGPTConnectionService, user: User
) -> ChatGPTConnectionStatus:
    status: dict[str, Any] = await asyncio.to_thread(service.status, user.user_id)
    supported = await pi_chat_service.plan_model_ids() if status["models"] else None
    models = [
        {**model, "supported": supported is None or model["slug"] in supported}
        for model in status["models"]
    ]
    return ChatGPTConnectionStatus(**{**status, "models": models, "usage_url": USAGE_URL})


@router.get(
    "/connection",
    response_model=ChatGPTConnectionStatus,
    summary="Get the current user's ChatGPT plan connection",
    operation_id="getChatGPTConnection",
)
async def get_chatgpt_connection(user: CurrentUser, service: Service) -> ChatGPTConnectionStatus:
    """Connection state, account email, models and the last problem; never tokens."""
    return await _status_response(service, user)


@router.post(
    "/authorize",
    response_model=StartChatGPTAuthorizationResponse,
    summary="Start connecting the current user's ChatGPT account",
    operation_id="startChatGPTAuthorization",
)
def start_chatgpt_authorization(
    body: StartChatGPTAuthorizationRequest, user: CurrentUser, service: Service
) -> StartChatGPTAuthorizationResponse:
    """Create a one-time attempt bound to this user and return OpenAI's sign-in URL."""
    try:
        started = service.start_authorization(
            user.user_id, new_account=body.new_account, enable_plan=body.enable_plan
        )
    except ChatGPTConnectionError as exc:
        raise _http_error(exc) from exc
    return StartChatGPTAuthorizationResponse(
        authorization_url=started.authorization_url,
        redirect_uri=started.redirect_uri,
        expires_at=started.expires_at,
    )


@router.post(
    "/callback",
    response_model=ChatGPTConnectionStatus,
    summary="Finish connecting with the address the browser landed on",
    operation_id="completeChatGPTAuthorization",
)
async def complete_chatgpt_authorization(
    body: CompleteChatGPTAuthorizationRequest, user: CurrentUser, service: Service
) -> ChatGPTConnectionStatus:
    """Validate the state against this user's attempt, exchange the code and store."""
    try:
        await asyncio.to_thread(service.complete_authorization, user.user_id, body.callback_url)
    except ChatGPTConnectionError as exc:
        raise _http_error(exc) from exc
    return await _status_response(service, user)


@router.post(
    "/models/refresh",
    response_model=ChatGPTConnectionStatus,
    summary="Reload the models the connected ChatGPT account offers",
    operation_id="refreshChatGPTModels",
)
async def refresh_chatgpt_models(user: CurrentUser, service: Service) -> ChatGPTConnectionStatus:
    """List the account's models again with its own token."""
    try:
        await asyncio.to_thread(service.list_models, user.user_id)
    except ChatGPTConnectionError as exc:
        raise _http_error(exc) from exc
    return await _status_response(service, user)


@router.post(
    "/welcome",
    response_model=ChatGPTConnectionStatus,
    summary="Dismiss the one-time ChatGPT plan confirmation",
    operation_id="acknowledgeChatGPTWelcome",
)
async def acknowledge_chatgpt_welcome(
    user: CurrentUser, service: Service
) -> ChatGPTConnectionStatus:
    """Record that the user saw that chats use their ChatGPT plan."""
    await asyncio.to_thread(service.acknowledge_welcome, user.user_id)
    return await _status_response(service, user)


@router.delete(
    "/connection",
    response_model=DisconnectChatGPTResponse,
    summary="Disconnect the current user's ChatGPT account",
    operation_id="disconnectChatGPT",
)
def disconnect_chatgpt(user: CurrentUser, service: Service) -> DisconnectChatGPTResponse:
    """Revoke the renewable session and clear the tokens; the registration is kept."""
    result = service.disconnect(user.user_id)
    return DisconnectChatGPTResponse(revocation_confirmed=result.revocation_confirmed)
