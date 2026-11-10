"""Tests for the Prefect access check used by the reverse proxy."""

import pytest

from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.user import UserDocument

DEPLOYMENT_ID = "123e4567-e89b-12d3-a456-426614174000"
CREATE_RUN = f"/prefect/api/deployments/{DEPLOYMENT_ID}/create_flow_run"


def _insert_user(username: str, token: str, role: SystemRole, *, disabled: bool = False) -> None:
    """Insert a user with a known access token."""
    UserDocument(
        username=username,
        display_name=username,
        hashed_password="hashed",
        access_token=token,
        disabled=disabled,
        system_role=role,
        default_project_id=None,
        system_info=SystemInfoModel(),
    ).insert()


@pytest.fixture
def users(init_db):
    """Create an admin, a regular user, and a disabled user."""
    _insert_user("admin", "admin-token", SystemRole.ADMIN)
    _insert_user("viewer", "viewer-token", SystemRole.USER)
    _insert_user("off", "off-token", SystemRole.USER, disabled=True)


def check(
    client, token: str | None, method: str | None, uri: str | None, upgrade: str | None = None
):
    """Call the access endpoint with forwarded request headers."""
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if method is not None:
        headers["X-Forwarded-Method"] = method
    if uri is not None:
        headers["X-Forwarded-Uri"] = uri
    if upgrade is not None:
        headers["X-Forwarded-Upgrade"] = upgrade
    return client.get("/auth/prefect-access", headers=headers)


def test_viewer_cannot_start_flow_run(test_client, users) -> None:
    """A non-admin user is denied state-changing Prefect operations."""
    assert check(test_client, "viewer-token", "POST", CREATE_RUN).status_code == 403


def test_admin_can_start_flow_run(test_client, users) -> None:
    """A system administrator may perform any Prefect operation."""
    assert check(test_client, "admin-token", "POST", CREATE_RUN).status_code == 204
    assert check(test_client, "admin-token", "DELETE", "/prefect/api/flows/x").status_code == 204


def test_viewer_can_read(test_client, users) -> None:
    """A non-admin user may read and run allowlisted queries."""
    assert (
        check(test_client, "viewer-token", "POST", "/prefect/api/flow_runs/filter").status_code
        == 204
    )
    assert check(test_client, "viewer-token", "GET", "/prefect/dashboard").status_code == 204


@pytest.mark.parametrize(
    ("method", "uri"),
    [
        ("POST", f"{CREATE_RUN}?x=/filter"),
        (
            "POST",
            f"/prefect/api/flow_runs/filter/../../deployments/{DEPLOYMENT_ID}/create_flow_run",
        ),
        ("POST", "/prefect/api/flow_runs%2Ffilter"),
        ("POST", "/prefect/api/flow_runs/filter/"),
        ("POST", "/prefect/API/flow_runs/filter"),
        ("PATCH", "/prefect/api/flow_runs/filter"),
        ("DELETE", "/prefect/api/flow_runs/filter"),
        ("OPTIONS", "/prefect/api/flow_runs/filter"),
        ("GET", "/prefect/api/block_documents/x?include_secrets=true"),
        ("GET", "/prefect/api/block_documents/x?include%5Fsecrets=true"),
    ],
)
def test_viewer_denied_variants(test_client, users, method: str, uri: str) -> None:
    """Evasion variants and non-read methods are denied for non-admins."""
    assert check(test_client, "viewer-token", method, uri).status_code == 403


def test_websocket_events(test_client, users) -> None:
    """Only outbound streams are open to non-admin websockets."""
    out = check(test_client, "viewer-token", "GET", "/prefect/api/events/out", "websocket")
    assert out.status_code == 204
    inbound = check(test_client, "viewer-token", "GET", "/prefect/api/events/in", "websocket")
    assert inbound.status_code == 403
    admin = check(test_client, "admin-token", "GET", "/prefect/api/events/in", "websocket")
    assert admin.status_code == 204


@pytest.mark.parametrize(
    ("method", "uri"), [(None, "/prefect/api/flows/filter"), ("POST", None), (None, None)]
)
@pytest.mark.parametrize("token", ["viewer-token", "admin-token"])
def test_missing_forwarded_headers_fail_closed(
    test_client, users, token: str, method: str | None, uri: str | None
) -> None:
    """Missing request context is denied even for administrators."""
    assert check(test_client, token, method, uri).status_code == 403


def test_authentication_errors_match_current_user(test_client, users) -> None:
    """Missing or disabled credentials keep the standard 401 and 403."""
    assert check(test_client, None, "GET", "/prefect/dashboard").status_code == 401
    assert check(test_client, "off-token", "GET", "/prefect/dashboard").status_code == 403
