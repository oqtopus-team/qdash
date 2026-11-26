"""Authentication dependencies expose only public user fields."""

from collections.abc import Callable
from unittest.mock import patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from qdash.api.lib.auth import get_current_active_user, get_current_user
from qdash.api.schemas.auth import User, UserInDB


@pytest.mark.parametrize("resolve", [get_current_user, get_current_active_user])
def test_authenticated_user_does_not_retain_database_credentials(
    resolve: Callable[[HTTPAuthorizationCredentials | None], User],
) -> None:
    stored = UserInDB(
        user_id="test-user",
        username="alice",
        hashed_password="synthetic-hash",
        access_token="synthetic-token",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic-token")

    with patch("qdash.api.lib.auth.get_user_by_token", return_value=stored):
        result = resolve(credentials)

    assert type(result) is User
    assert result is not stored
    assert result.model_dump() == stored.model_dump(include=set(User.model_fields))
    assert not hasattr(result, "hashed_password")
    assert not hasattr(result, "access_token")
