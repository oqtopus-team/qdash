"""The calibration context is resolved and authorized like an API run."""

from __future__ import annotations

import pickle
from typing import Any

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument
from qdash.workflow.service.context import (
    AccessDecision,
    CalibContext,
    CalibContextError,
    CalibContextResolver,
    MongoProjectAccessDirectory,
    resolve_calib_context,
)
from tests.qdash.workflow.context_helpers import GrantingDirectory


def _user(username: str, *, default_project_id: str | None = None, disabled: bool = False) -> Any:
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=f"{username}-token",
        default_project_id=default_project_id,
        disabled=disabled,
        system_info=SystemInfoModel(),
    )
    user.insert()
    return user


def _project(project_id: str, owner: Any) -> None:
    ProjectDocument(
        project_id=project_id,
        name=project_id,
        owner_user_id=owner.user_id,
        owner_username=owner.username,
    ).insert()


def _member(project_id: str, user: Any, role: ProjectRole, status: str = "active") -> None:
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=role,
        status=status,
    ).insert()


class TestResolver:
    def test_direct_construction_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="resolve_calib_context"):
            CalibContext("alice", "chip-1", "project-1", "qubex")

    def test_default_project_is_used_and_checked(self) -> None:
        directory = GrantingDirectory(default_project_id="home")

        context = CalibContextResolver(directory).resolve("alice", "chip-1")

        assert (context.username, context.chip_id, context.project_id) == (
            "alice",
            "chip-1",
            "home",
        )
        assert directory.checked == [("alice", "home")]

    def test_missing_default_project_keeps_the_existing_message(self) -> None:
        with pytest.raises(CalibContextError, match="default_project_id is not set"):
            CalibContextResolver(GrantingDirectory(default_project_id=None)).resolve(
                "alice", "chip-1"
            )

    def test_explicit_project_is_checked_not_trusted(self) -> None:
        directory = GrantingDirectory()

        CalibContextResolver(directory).resolve("alice", "chip-1", project_id="other")

        assert directory.checked == [("alice", "other")]

    @pytest.mark.parametrize(
        ("decision", "message"),
        [
            (AccessDecision.UNKNOWN_USER, "does not exist"),
            (AccessDecision.DISABLED_USER, "is disabled"),
            (AccessDecision.UNKNOWN_PROJECT, "not found"),
            (AccessDecision.DENIED, "editor or owner"),
        ],
    )
    def test_denials_are_reported(self, decision: AccessDecision, message: str) -> None:
        class Directory(GrantingDirectory):
            def write_access(self, username: str, project_id: str) -> AccessDecision:
                return decision

        with pytest.raises(CalibContextError, match=message):
            CalibContextResolver(Directory()).resolve("alice", "chip-1", project_id="p")

    @pytest.mark.parametrize(("username", "chip_id"), [("", "chip-1"), ("alice", " ")])
    def test_blank_identity_is_rejected(self, username: str, chip_id: str) -> None:
        with pytest.raises(CalibContextError, match="required"):
            CalibContextResolver(GrantingDirectory()).resolve(username, chip_id)

    def test_backend_defaults_to_the_configuration_and_is_validated(self) -> None:
        from qdash.common.config.backend import get_available_backends, get_default_backend

        resolver = CalibContextResolver(GrantingDirectory())
        assert resolver.resolve("alice", "chip-1").backend_name == get_default_backend()
        assert "fake" in get_available_backends()
        assert resolver.resolve("alice", "chip-1", backend="fake").backend_name == "fake"
        with pytest.raises(CalibContextError, match="not configured"):
            resolver.resolve("alice", "chip-1", backend="nonexistent")

    def test_contexts_survive_process_boundaries(self) -> None:
        context = CalibContextResolver(GrantingDirectory()).resolve("alice", "chip-1")

        assert pickle.loads(pickle.dumps(context)) == context  # noqa: S301


class TestMongoDirectoryMatchesTheApiRule:
    """Editors and owners may run calibrations; viewers and strangers may not."""

    @pytest.mark.parametrize(
        ("role", "allowed"),
        [(ProjectRole.OWNER, True), (ProjectRole.EDITOR, True), (ProjectRole.VIEWER, False)],
    )
    def test_membership_role_decides(self, init_db: Any, role: ProjectRole, allowed: bool) -> None:
        owner = _user("owner")
        member = _user("member")
        _project("p1", owner)
        _member("p1", member, role)

        decision = MongoProjectAccessDirectory().write_access("member", "p1")

        assert (decision is AccessDecision.GRANTED) is allowed

    def test_inactive_membership_does_not_count(self, init_db: Any) -> None:
        owner = _user("owner")
        member = _user("member")
        _project("p1", owner)
        _member("p1", member, ProjectRole.EDITOR, status="pending")

        assert MongoProjectAccessDirectory().write_access("member", "p1") is AccessDecision.DENIED

    def test_project_owner_without_membership_is_granted(self, init_db: Any) -> None:
        owner = _user("owner")
        _project("p1", owner)

        assert MongoProjectAccessDirectory().write_access("owner", "p1") is AccessDecision.GRANTED

    def test_unknown_and_disabled_users_and_projects(self, init_db: Any) -> None:
        owner = _user("owner")
        _user("gone", disabled=True)
        _project("p1", owner)
        directory = MongoProjectAccessDirectory()

        assert directory.write_access("nobody", "p1") is AccessDecision.UNKNOWN_USER
        assert directory.write_access("gone", "p1") is AccessDecision.DISABLED_USER
        assert directory.write_access("owner", "missing") is AccessDecision.UNKNOWN_PROJECT

    def test_resolve_calib_context_uses_mongo_by_default(self, init_db: Any) -> None:
        owner = _user("owner", default_project_id="p1")
        stranger = _user("stranger", default_project_id="p1")
        _project("p1", owner)
        assert stranger.user_id

        assert resolve_calib_context("owner", "chip-1").project_id == "p1"
        with pytest.raises(CalibContextError, match="editor or owner"):
            resolve_calib_context("stranger", "chip-1")
