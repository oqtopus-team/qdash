"""Schemas for the current user's ChatGPT plan connection. None of them carries a token."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChatGPTConnectionStatusValue = Literal[
    "not_connected", "connected", "plan_disabled", "reauth_required", "signed_out"
]


class ChatGPTConnectionError(BaseModel):
    """The last plan-usage or sign-in problem, for Settings."""

    code: str
    message: str
    at: datetime | None = None


class ChatGPTPlanModel(BaseModel):
    """A model the connected account offers."""

    slug: str = Field(description="Model ID sent as the chat model name")
    display_name: str
    supported: bool = Field(
        default=True,
        description="Whether QDash's chat runtime can run this model on the plan route",
    )


class ChatGPTConnectionStatus(BaseModel):
    """The current user's connection, as Settings and the chat model menu show it."""

    available: bool = Field(description="Whether this QDash server can store ChatGPT connections")
    status: ChatGPTConnectionStatusValue
    can_reconnect: bool = Field(description="A saved registration can be signed in to again")
    plan_usage_enabled: bool = Field(description="Chat requests can use the ChatGPT plan")
    welcome_pending: bool = Field(description="Show the one-time plan-usage confirmation")
    email: str | None = None
    connected_at: datetime | None = None
    last_error: ChatGPTConnectionError | None = None
    models: list[ChatGPTPlanModel] = Field(default_factory=list)
    usage_url: str = Field(description="Where the user reviews and limits plan usage")


class StartChatGPTAuthorizationRequest(BaseModel):
    """Start a sign-in for the current user."""

    new_account: bool = Field(
        default=False,
        description="Register a different ChatGPT account instead of the saved one",
    )
    enable_plan: bool = Field(
        default=False,
        description="Ask for ChatGPT plan permission again after it was declined",
    )


class StartChatGPTAuthorizationResponse(BaseModel):
    """Where to send the user's browser, and which address they bring back."""

    authorization_url: str
    redirect_uri: str = Field(description="The browser lands on this address after sign-in")
    expires_at: datetime


class CompleteChatGPTAuthorizationRequest(BaseModel):
    """The address the user's browser landed on after signing in."""

    callback_url: str = Field(min_length=1, max_length=8192)


class DisconnectChatGPTResponse(BaseModel):
    """Result of signing out of ChatGPT in QDash."""

    revocation_confirmed: bool = Field(
        description="OpenAI confirmed that the renewable session was revoked"
    )
