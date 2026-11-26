"""Tests for the shared write-time document lookups."""

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.lookups import current_cooldown_id, user_id_for_username
from qdash.dbmodel.user import UserDocument


def test_user_id_for_username_resolves_known_users_only(init_db) -> None:
    user = UserDocument(
        username="alice",
        hashed_password="hashed",
        access_token="token",
        system_info=SystemInfoModel(),
    )
    user.insert()

    assert user_id_for_username("alice") == user.user_id
    assert user_id_for_username("bob") is None
    assert user_id_for_username("") is None
    assert user_id_for_username(None) is None


def test_current_cooldown_id_reads_the_chip_in_its_project(init_db) -> None:
    ChipDocument(
        project_id="project-1",
        username="alice",
        chip_id="chip-1",
        size=64,
        current_cooldown_id="cd-1",
        system_info=SystemInfoModel(),
    ).insert()
    ChipDocument(
        project_id="project-1",
        username="alice",
        chip_id="chip-2",
        size=64,
        system_info=SystemInfoModel(),
    ).insert()

    assert current_cooldown_id(project_id="project-1", chip_id="chip-1") == "cd-1"
    assert current_cooldown_id(project_id="project-1", chip_id="chip-2") == ""
    assert current_cooldown_id(project_id="project-2", chip_id="chip-1") == ""
    assert current_cooldown_id(project_id=None, chip_id="chip-1") == ""
    assert current_cooldown_id(project_id="project-1", chip_id=None) == ""
