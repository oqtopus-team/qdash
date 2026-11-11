"""Tests for initial admin creation when several API workers start at once."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pymongo.errors import DuplicateKeyError

from qdash.api.db.session import create_initial_admin
from qdash.api.lib.project_service import ProjectService
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from pymongo.database import Database

ADMIN = "admin"
PROJECT_NAME = f"{ADMIN}'s project"


@pytest.fixture
def admin_db(
    init_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> Generator[Database[Any], None, None]:
    """Provide a database with unique indexes and admin env vars set."""
    # Bunnet creates the production unique indexes on the mongomock collections,
    # so duplicate inserts raise DuplicateKeyError as they do against MongoDB.
    assert init_db["user"].index_information()["username_1"]["unique"]
    monkeypatch.setenv("QDASH_ADMIN_USERNAME", ADMIN)
    monkeypatch.setenv("QDASH_ADMIN_PASSWORD", "admin-password")
    # bcrypt is slow and irrelevant to the race handling.
    monkeypatch.setattr("qdash.api.lib.auth.get_password_hash", lambda p: f"hashed-{p}")
    yield init_db


def _other_worker_user() -> None:
    UserDocument(
        user_id="other-worker-user",
        username=ADMIN,
        hashed_password="hashed",
        access_token="other-token",
        display_name="Administrator",
        system_role=SystemRole.ADMIN,
        system_info=SystemInfoModel(),
    ).insert()


def _run_before_first_call(
    monkeypatch: pytest.MonkeyPatch,
    cls: type,
    method: str,
    other_worker: Callable[[], None],
) -> None:
    """Run ``other_worker`` just before this worker's first ``cls.method`` call."""
    original = getattr(cls, method)
    state = {"done": False}

    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not state["done"]:
            state["done"] = True
            other_worker()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cls, method, wrapper)


def _assert_single_admin_with_default_project() -> UserDocument:
    users: list[UserDocument] = UserDocument.find({"username": ADMIN}).run()
    assert len(users) == 1
    user = users[0]
    projects = ProjectDocument.find({"owner_username": ADMIN}).run()
    assert len(projects) == 1
    assert user.default_project_id == projects[0].project_id
    memberships = ProjectMembershipDocument.find({"username": ADMIN}).run()
    assert len(memberships) == 1
    assert memberships[0].project_id == projects[0].project_id
    assert memberships[0].role == "owner"
    assert memberships[0].status == "active"
    return user


def test_creates_admin_with_default_project(admin_db: Database[Any]) -> None:
    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.system_role == SystemRole.ADMIN


def test_repeated_startup_is_idempotent(admin_db: Database[Any]) -> None:
    create_initial_admin()
    first = _assert_single_admin_with_default_project()

    create_initial_admin()

    second = _assert_single_admin_with_default_project()
    assert second.user_id == first.user_id
    assert second.default_project_id == first.default_project_id


def test_reuses_admin_inserted_by_concurrent_worker(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both workers saw no admin; the other worker inserts first.
    _run_before_first_call(monkeypatch, UserDocument, "insert", _other_worker_user)

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.user_id == "other-worker-user"


def test_reuses_project_created_by_concurrent_worker(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_worker_user()
    created: dict[str, str] = {}

    def other_worker_creates_project() -> None:
        project = ProjectService().create_project(owner_username=ADMIN, name=PROJECT_NAME)
        created["project_id"] = project.project_id

    _run_before_first_call(monkeypatch, ProjectDocument, "insert", other_worker_creates_project)

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.default_project_id == created["project_id"]


def test_reuses_membership_created_by_concurrent_worker(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_worker_user()
    project = ProjectDocument(
        owner_user_id="other-worker-user", owner_username=ADMIN, name=PROJECT_NAME
    )
    project.insert()

    def other_worker_creates_membership() -> None:
        ProjectMembershipDocument(
            project_id=project.project_id,
            user_id="other-worker-user",
            username=ADMIN,
            role="owner",
            status="active",
        ).insert()

    _run_before_first_call(
        monkeypatch, ProjectMembershipDocument, "insert", other_worker_creates_membership
    )

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.default_project_id == project.project_id


def test_repairs_admin_left_without_default_project(admin_db: Database[Any]) -> None:
    # A previous worker stopped after inserting the user.
    _other_worker_user()

    create_initial_admin()

    _assert_single_admin_with_default_project()


def test_unrelated_duplicate_user_key_is_raised(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    UserDocument(
        user_id="someone-else",
        username="someone-else",
        hashed_password="hashed",
        access_token="colliding-token",
        system_info=SystemInfoModel(),
    ).insert()
    monkeypatch.setattr("secrets.token_urlsafe", lambda _n: "colliding-token")

    with pytest.raises(DuplicateKeyError):
        create_initial_admin()

    assert UserDocument.find_one({"username": ADMIN}).run() is None


def test_persistent_duplicate_project_error_is_raised(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_worker_user()
    attempts = {"count": 0}

    def always_conflicts(self: ProjectDocument, *args: Any, **kwargs: Any) -> None:
        attempts["count"] += 1
        raise DuplicateKeyError("E11000 duplicate key error")

    monkeypatch.setattr(ProjectDocument, "insert", always_conflicts)

    with pytest.raises(DuplicateKeyError):
        create_initial_admin()

    assert attempts["count"] == 3


def _admin_with_project(membership_status: str | None) -> tuple[UserDocument, ProjectDocument]:
    """Create the admin, its default project and optionally an owner membership."""
    _other_worker_user()
    project = ProjectDocument(
        owner_user_id="other-worker-user", owner_username=ADMIN, name=PROJECT_NAME
    )
    project.insert()
    UserDocument.get_motor_collection().update_one(
        {"username": ADMIN}, {"$set": {"default_project_id": project.project_id}}
    )
    if membership_status is not None:
        ProjectMembershipDocument(
            project_id=project.project_id,
            user_id="other-worker-user",
            username=ADMIN,
            role="viewer",
            status=membership_status,
        ).insert()
    user = UserDocument.find_one({"username": ADMIN}).run()
    assert user is not None
    return user, project


def _other_user(user_id: str) -> None:
    UserDocument(
        user_id=user_id,
        username=user_id,
        hashed_password="hashed",
        access_token=f"{user_id}-token",
        system_info=SystemInfoModel(),
    ).insert()


def test_restores_missing_owner_membership_of_existing_default_project(
    admin_db: Database[Any],
) -> None:
    before, project = _admin_with_project(membership_status=None)

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.default_project_id == project.project_id
    assert user.access_token == before.access_token


@pytest.mark.parametrize("membership_status", ["revoked", "pending"])
def test_reactivates_inactive_owner_membership_of_existing_default_project(
    admin_db: Database[Any], membership_status: str
) -> None:
    _, project = _admin_with_project(membership_status=membership_status)

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.default_project_id == project.project_id


def test_repairs_stale_user_id_on_owner_membership(admin_db: Database[Any]) -> None:
    _, project = _admin_with_project(membership_status="active")
    ProjectMembershipDocument.get_motor_collection().update_one(
        {"project_id": project.project_id}, {"$set": {"user_id": "deleted-account"}}
    )

    create_initial_admin()

    _assert_single_admin_with_default_project()


def test_keeps_default_project_of_another_owner_when_admin_is_member(
    admin_db: Database[Any],
) -> None:
    _other_worker_user()
    _other_user("alice")
    shared = ProjectService().create_project(owner_username="alice", name="shared")
    ProjectMembershipDocument(
        project_id=shared.project_id,
        user_id="other-worker-user",
        username=ADMIN,
        role="editor",
        status="active",
    ).insert()
    UserDocument.get_motor_collection().update_one(
        {"username": ADMIN}, {"$set": {"default_project_id": shared.project_id}}
    )

    create_initial_admin()

    user = UserDocument.find_one({"username": ADMIN}).run()
    assert user is not None
    assert user.default_project_id == shared.project_id
    membership = ProjectMembershipDocument.find_one(
        {"project_id": shared.project_id, "username": ADMIN}
    ).run()
    assert membership is not None
    assert membership.role == "editor"
    assert ProjectDocument.find({"owner_username": ADMIN}).run() == []


def test_never_grants_ownership_of_another_owners_default_project(
    admin_db: Database[Any],
) -> None:
    _other_worker_user()
    _other_user("alice")
    foreign = ProjectService().create_project(owner_username="alice", name="alice's project")
    UserDocument.get_motor_collection().update_one(
        {"username": ADMIN}, {"$set": {"default_project_id": foreign.project_id}}
    )

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.default_project_id != foreign.project_id
    assert (
        ProjectMembershipDocument.find_one(
            {"project_id": foreign.project_id, "username": ADMIN}
        ).run()
        is None
    )


def test_does_not_adopt_same_named_project_of_a_different_owner_id(
    admin_db: Database[Any],
) -> None:
    _other_worker_user()
    # Left by a deleted account that had the same username.
    orphan = ProjectDocument(
        owner_user_id="deleted-account", owner_username=ADMIN, name=PROJECT_NAME
    )
    orphan.insert()

    create_initial_admin()

    user = UserDocument.find_one({"username": ADMIN}).run()
    assert user is not None
    assert user.default_project_id is None
    assert ProjectMembershipDocument.find({"project_id": orphan.project_id}).run() == []


def test_preserves_user_fields_updated_concurrently(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_worker_user()

    def other_request_updates_profile() -> None:
        UserDocument.get_motor_collection().update_one(
            {"username": ADMIN},
            {"$set": {"display_name": "Renamed", "organization": "QDash Lab"}},
        )

    # The profile changes after this worker read the user document.
    _run_before_first_call(monkeypatch, ProjectDocument, "insert", other_request_updates_profile)

    create_initial_admin()

    user = _assert_single_admin_with_default_project()
    assert user.display_name == "Renamed"
    assert user.organization == "QDash Lab"


def test_respects_default_project_chosen_concurrently(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_worker_user()
    chosen: dict[str, str] = {}

    def other_request_sets_default() -> None:
        project = ProjectService().create_project(owner_username=ADMIN, name="chosen")
        UserDocument.get_motor_collection().update_one(
            {"username": ADMIN}, {"$set": {"default_project_id": project.project_id}}
        )
        chosen["project_id"] = project.project_id

    _run_before_first_call(monkeypatch, ProjectDocument, "insert", other_request_sets_default)

    create_initial_admin()

    user = UserDocument.find_one({"username": ADMIN}).run()
    assert user is not None
    assert user.default_project_id == chosen["project_id"]


def test_unrelated_duplicate_membership_error_is_raised(
    admin_db: Database[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin_with_project(membership_status=None)

    def always_conflicts(self: ProjectMembershipDocument, *args: Any, **kwargs: Any) -> None:
        raise DuplicateKeyError("E11000 duplicate key error")

    monkeypatch.setattr(ProjectMembershipDocument, "insert", always_conflicts)

    with pytest.raises(DuplicateKeyError):
        create_initial_admin()
