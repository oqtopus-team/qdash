"""Tests for chip router endpoints."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pymongo.errors import DuplicateKeyError

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_note import ChipNoteDocument
from qdash.dbmodel.cooldown import CooldownDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def test_project(init_db):
    """Create a test project with owner membership."""
    # Create user
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    # Create project
    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()

    # Create membership
    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="test_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture(autouse=True)
def config_tree(tmp_path):
    """Point chip creation at a temporary Qubex configuration tree."""
    from qdash.api.dependencies import get_chip_config_scaffolder
    from qdash.api.main import app
    from qdash.api.services.chip import ChipConfigScaffolder

    root = tmp_path / "qubex-config"
    wiring = root / "64Qv3" / "config" / "wiring.yaml"
    wiring.parent.mkdir(parents=True)
    wiring.write_text(yaml.safe_dump({"64Qv3": [{"mux": 0, "ctrl": ["S1R-7"]}]}))
    templates = Path(__file__).resolve().parents[4] / "config" / "domain" / "qubex-params"
    app.dependency_overrides[get_chip_config_scaffolder] = lambda: ChipConfigScaffolder(
        config_base=root, templates_dir=templates
    )
    yield root
    app.dependency_overrides.pop(get_chip_config_scaffolder, None)


@pytest.fixture
def auth_headers():
    """Get authentication headers with project context."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


class TestChipRouter:
    """Tests for chip-related API endpoints."""

    @pytest.mark.parametrize(
        "chip_id", ["../escape", "my chip", "template", "archive", "schemas", "scripts", "chip\n"]
    )
    @pytest.mark.parametrize("create_config", [True, False])
    @pytest.mark.parametrize("mounted", [True, False])
    def test_rejects_unsafe_chip_ids_before_creation(
        self, test_client, test_project, auth_headers, monkeypatch, chip_id, create_config, mounted
    ):
        from qdash.api.services.chip import ChipConfigScaffolder

        monkeypatch.setattr(ChipConfigScaffolder, "available", property(lambda self: mounted))
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": chip_id, "size": 64, "config": {"create": create_config}},
        )
        assert response.status_code == 422
        assert ChipDocument.find_one({"chip_id": chip_id}).run() is None

    def test_list_chips_empty(self, test_client, test_project, auth_headers):
        """Test listing chips when no chips exist."""
        response = test_client.get("/chips", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["chips"] == []
        assert data["total"] == 0

    def test_list_chips_with_data(self, test_client, test_project, auth_headers):
        """Test listing chips when chips exist."""
        # Arrange: Create a chip in the database
        chip = ChipDocument(
            chip_id="test_chip_001",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Create some qubits for the chip
        for i in range(3):
            qubit = QubitDocument(
                project_id="test_project",
                username="test_user",
                chip_id="test_chip_001",
                qid=str(i),
                status="pending",
                data={},
                system_info={},
            )
            qubit.insert()

        # Act
        response = test_client.get("/chips", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["chips"]) == 1
        assert data["chips"][0]["chip_id"] == "test_chip_001"
        assert data["chips"][0]["size"] == 64
        assert data["chips"][0]["activity_status"] == "active"
        assert data["chips"][0]["qubit_count"] == 3

    def test_list_chips_filters_by_project(self, test_client, test_project, auth_headers):
        """Test that listing chips only returns chips for the current project."""
        # Arrange: Create chips for different projects
        chip1 = ChipDocument(
            chip_id="chip_project1",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip1.insert()

        chip2 = ChipDocument(
            chip_id="chip_project2",
            username="test_user",
            project_id="other_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip2.insert()

        # Act
        response = test_client.get("/chips", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["chips"]) == 1
        assert data["chips"][0]["chip_id"] == "chip_project1"

    def test_get_chip_success(self, test_client, test_project, auth_headers):
        """Test fetching a specific chip by ID."""
        # Arrange
        chip = ChipDocument(
            chip_id="test_chip_fetch",
            username="test_user",
            project_id="test_project",
            size=144,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act
        response = test_client.get("/chips/test_chip_fetch", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "test_chip_fetch"
        assert data["size"] == 144
        assert data["activity_status"] == "active"

    def test_get_chip_not_found(self, test_client, test_project, auth_headers):
        """Test fetching a non-existent chip returns 404."""
        response = test_client.get("/chips/nonexistent_chip", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_chip_wrong_project(self, test_client, test_project, auth_headers):
        """Test that fetching another project's chip returns 404."""
        # Arrange: Create a chip for another project
        chip = ChipDocument(
            chip_id="other_project_chip",
            username="test_user",
            project_id="other_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act: Try to fetch from test_project
        response = test_client.get("/chips/other_project_chip", headers=auth_headers)

        # Assert: Should not find the chip (project isolation)
        assert response.status_code == 404

    def test_update_chip_activity_status(self, test_client, test_project, auth_headers):
        """Test updating a chip's activity status."""
        chip = ChipDocument(
            chip_id="test_chip_status",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        response = test_client.patch(
            "/chips/test_chip_status",
            headers=auth_headers,
            json={"activity_status": "inactive"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "test_chip_status"
        assert data["activity_status"] == "inactive"

    def test_chip_note_is_scoped_by_cooldown(self, test_client, test_project, auth_headers):
        chip = ChipDocument(
            chip_id="test_chip_note_scope",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()
        CooldownDocument(
            project_id="test_project",
            cooldown_id="cd-a",
            cryo_id="cryo-1",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            ended_at=datetime(2026, 1, 15, tzinfo=UTC),
            chip_ids=["test_chip_note_scope"],
        ).insert()
        CooldownDocument(
            project_id="test_project",
            cooldown_id="cd-b",
            cryo_id="cryo-1",
            started_at=datetime(2026, 2, 1, tzinfo=UTC),
            ended_at=None,
            chip_ids=["test_chip_note_scope"],
        ).insert()

        first = test_client.put(
            "/chips/test_chip_note_scope/note",
            headers=auth_headers,
            params={"cooldown_id": "cd-a"},
            json={"content": "first cooldown note"},
        )
        second = test_client.put(
            "/chips/test_chip_note_scope/note",
            headers=auth_headers,
            params={"cooldown_id": "cd-b"},
            json={"content": "second cooldown note"},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["content"] == "first cooldown note"
        assert second.json()["content"] == "second cooldown note"

        cd_a = test_client.get(
            "/chips/test_chip_note_scope/note",
            headers=auth_headers,
            params={"cooldown_id": "cd-a"},
        )
        cd_b = test_client.get(
            "/chips/test_chip_note_scope/note",
            headers=auth_headers,
            params={"cooldown_id": "cd-b"},
        )

        assert cd_a.status_code == 200
        assert cd_a.json()["content"] == "first cooldown note"
        assert cd_b.status_code == 200
        assert cd_b.json()["content"] == "second cooldown note"
        assert ChipNoteDocument.find({"project_id": "test_project"}).count() == 2

        reloaded_chip = ChipDocument.find_one(
            {"project_id": "test_project", "chip_id": "test_chip_note_scope"}
        ).run()
        assert reloaded_chip is not None
        assert reloaded_chip.note.content == ""

        deleted = test_client.delete(
            "/chips/test_chip_note_scope/note",
            headers=auth_headers,
            params={"cooldown_id": "cd-a"},
        )
        assert deleted.status_code == 200
        cleared = test_client.get(
            "/chips/test_chip_note_scope/note",
            headers=auth_headers,
            params={"cooldown_id": "cd-a"},
        )
        assert cleared.status_code == 200
        assert cleared.json()["content"] == ""
        assert ChipNoteDocument.find({"project_id": "test_project"}).count() == 1

    def test_update_chip_topology_creates_missing_target_skeletons(
        self, test_client, test_project, auth_headers
    ):
        """Test topology update backfills empty qubit/coupling target rows."""
        chip = ChipDocument(
            chip_id="test_chip_topology",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        response = test_client.patch(
            "/chips/test_chip_topology",
            headers=auth_headers,
            json={"topology_id": "square-lattice-mux-64"},
        )

        assert response.status_code == 200
        assert (
            QubitDocument.find(
                {"project_id": "test_project", "chip_id": "test_chip_topology"}
            ).count()
            == 64
        )
        assert (
            CouplingDocument.find(
                {"project_id": "test_project", "chip_id": "test_chip_topology"}
            ).count()
            > 0
        )

    def test_create_chip_success(self, test_client, test_project, auth_headers):
        """Test creating a new chip."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "new_chip", "size": 64},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "new_chip"
        assert data["size"] == 64
        assert data["activity_status"] == "active"
        assert data["config"]["status"] == "created"

    def test_create_chip_creates_config_with_chip_id_as_system_id(
        self, test_client, test_project, auth_headers, config_tree
    ):
        """The new chip's directory copies wiring from the named system."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "64Qv4", "size": 64, "config": {"source_system_id": "64Qv3"}},
        )

        assert response.status_code == 200
        config = response.json()["config"]
        assert config["status"] == "created"
        assert config["source_system_id"] == "64Qv3"
        wiring = yaml.safe_load((config_tree / "64Qv4/config/wiring.yaml").read_text())
        assert wiring == {"64Qv4": [{"mux": 0, "ctrl": ["S1R-7"]}]}
        system = yaml.safe_load((config_tree / "64Qv4/config/system.yaml").read_text())
        assert system["64Qv4"]["chip_id"] == "64Qv4"

    def test_create_chip_without_config(self, test_client, test_project, auth_headers, config_tree):
        """config.create=false registers the chip only."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "db_only", "size": 64, "config": {"create": False}},
        )

        assert response.status_code == 200
        assert response.json()["config"] is None
        assert not (config_tree / "db_only").exists()

    def test_create_chip_unknown_config_source(
        self, test_client, test_project, auth_headers, config_tree
    ):
        """An unknown source system is a 400 and creates nothing."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "64Qv4", "size": 64, "config": {"source_system_id": "nope"}},
        )

        assert response.status_code == 400
        assert not (config_tree / "64Qv4").exists()
        assert ChipDocument.find_one({"chip_id": "64Qv4"}).run() is None

    def test_list_chip_config_sources(self, test_client, test_project, auth_headers):
        """Systems with a wiring file are offered as sources."""
        response = test_client.get("/chips/config-sources", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert [source["system_id"] for source in data["sources"]] == ["64Qv3"]

    def test_list_chip_config_sources_offers_no_preset_on_hardware_backend(
        self, test_client, test_project, auth_headers, monkeypatch
    ):
        """The fake preset stays hidden unless the deployment backend is fake."""
        monkeypatch.setenv("DEFAULT_BACKEND", "qubex")
        response = test_client.get("/chips/config-sources", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["presets"] == []
        assert response.json()["deployment_backend"] == "qubex"

    def test_list_chip_config_sources_offers_fake_preset_on_fake_backend(
        self, test_client, test_project, auth_headers, monkeypatch
    ):
        monkeypatch.setenv("DEFAULT_BACKEND", "fake")
        response = test_client.get("/chips/config-sources", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["deployment_backend"] == "fake"
        [preset] = body["presets"]
        assert preset["preset_id"] == "fake"
        assert preset["topology_id"] == "square-lattice-mux-64"
        assert preset["n_qubits"] == 64
        assert preset["mux_count"] == 16
        assert preset["workflow_template_id"] == "fake_calibration"

    def test_create_chip_with_fake_preset(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch
    ):
        monkeypatch.setenv("DEFAULT_BACKEND", "fake")
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={
                "chip_id": "fake-64q",
                "size": 64,
                "topology_id": "square-lattice-mux-64",
                "config": {"preset": "fake"},
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["topology_id"] == "square-lattice-mux-64"
        assert data["size"] == 64
        assert data["config"]["status"] == "created"
        assert data["config"]["preset"] == "fake"
        wiring = yaml.safe_load((config_tree / "fake-64q/config/wiring.yaml").read_text())
        assert [row["mux"] for row in wiring["fake-64q"]] == list(range(16))
        assert (
            QubitDocument.find({"project_id": "test_project", "chip_id": "fake-64q"}).count() == 64
        )

    def test_create_chip_with_qibocal_preset_writes_no_configuration(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch
    ):
        """A qibocal chip is the one-qubit emulator; the Qubex tree is left alone."""
        monkeypatch.setenv("DEFAULT_BACKEND", "qibocal")
        sources = test_client.get("/chips/config-sources", headers=auth_headers).json()
        [preset] = sources["presets"]
        assert preset["preset_id"] == "qibocal"
        assert preset["n_qubits"] == 1
        assert preset["requires_config_tree"] is False

        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={
                "chip_id": "QIBOCAL",
                "size": 1,
                "topology_id": "qibocal-emulator-1",
                "config": {"preset": "qibocal"},
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["topology_id"] == "qibocal-emulator-1"
        assert data["config"]["status"] == "skipped"
        assert data["config"]["preset"] == "qibocal"
        assert not (config_tree / "QIBOCAL").exists()
        qids = [
            doc.qid
            for doc in QubitDocument.find(
                {"project_id": "test_project", "chip_id": "QIBOCAL"}
            ).run()
        ]
        assert qids == ["0"]

    def test_create_chip_with_qibocal_preset_outside_qibocal_backend_is_rejected(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch
    ):
        monkeypatch.setenv("DEFAULT_BACKEND", "fake")
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={
                "chip_id": "QIBOCAL",
                "size": 1,
                "topology_id": "qibocal-emulator-1",
                "config": {"preset": "qibocal"},
            },
        )

        assert response.status_code == 400
        assert ChipDocument.find_one({"chip_id": "QIBOCAL"}).run() is None

    def test_create_chip_with_fake_preset_on_hardware_backend_is_rejected(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch
    ):
        monkeypatch.setenv("DEFAULT_BACKEND", "qubex")
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={
                "chip_id": "fake-64q",
                "size": 64,
                "topology_id": "square-lattice-mux-64",
                "config": {"preset": "fake"},
            },
        )

        assert response.status_code == 400
        assert "deployment backend" in response.json()["detail"]
        assert not (config_tree / "fake-64q").exists()
        assert ChipDocument.find_one({"chip_id": "fake-64q"}).run() is None

    @pytest.mark.parametrize(
        ("size", "topology_id"),
        [(64, "square-lattice-mux-64-x"), (16, "square-lattice-mux-16"), (144, None)],
    )
    def test_create_chip_with_fake_preset_needs_preset_topology(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch, size, topology_id
    ):
        monkeypatch.setenv("DEFAULT_BACKEND", "fake")
        payload = {"chip_id": "fake-chip", "size": size, "config": {"preset": "fake"}}
        if topology_id:
            payload["topology_id"] = topology_id
        response = test_client.post("/chips", headers=auth_headers, json=payload)

        assert response.status_code == 400
        assert not (config_tree / "fake-chip").exists()
        assert ChipDocument.find_one({"chip_id": "fake-chip"}).run() is None

    def test_create_chip_with_fake_preset_without_config_tree_is_rejected(
        self, test_client, test_project, auth_headers, monkeypatch, tmp_path
    ):
        """A fake chip is never created without its configuration."""
        from qdash.api.dependencies import get_chip_config_scaffolder
        from qdash.api.main import app
        from qdash.api.services.chip import ChipConfigScaffolder

        monkeypatch.setenv("DEFAULT_BACKEND", "fake")
        app.dependency_overrides[get_chip_config_scaffolder] = lambda: ChipConfigScaffolder(
            config_base=tmp_path / "missing"
        )
        try:
            sources = test_client.get("/chips/config-sources", headers=auth_headers).json()
            assert sources["available"] is False
            assert [preset["preset_id"] for preset in sources["presets"]] == ["fake"]

            response = test_client.post(
                "/chips",
                headers=auth_headers,
                json={
                    "chip_id": "fake-64q",
                    "size": 64,
                    "topology_id": "square-lattice-mux-64",
                    "config": {"preset": "fake"},
                },
            )
        finally:
            app.dependency_overrides.pop(get_chip_config_scaffolder, None)

        assert response.status_code == 400
        assert "No Qubex configuration tree is mounted" in response.json()["detail"]
        assert ChipDocument.find_one({"chip_id": "fake-64q"}).run() is None

    @pytest.mark.parametrize(
        "config",
        [
            {"preset": "fake", "source_system_id": "64Qv3"},
            {"preset": "fake", "backend": "quel1"},
            {"preset": "fake", "create": False},
        ],
    )
    def test_create_chip_rejects_preset_combined_with_other_options(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch, config
    ):
        monkeypatch.setenv("DEFAULT_BACKEND", "fake")
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "fake-64q", "size": 64, "config": config},
        )

        assert response.status_code == 422
        assert not (config_tree / "fake-64q").exists()

    def test_create_chip_invalid_size(self, test_client, test_project, auth_headers):
        """Test creating a chip with invalid size returns 400."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "invalid_chip", "size": 100},  # Invalid size
        )

        assert response.status_code == 400

    @pytest.mark.parametrize("username", ["test_user", "another_user"])
    def test_create_chip_duplicate(
        self, test_client, test_project, auth_headers, config_tree, username, monkeypatch
    ):
        """Test creating a duplicate chip returns 400."""
        # Arrange: Create initial chip
        chip = ChipDocument(
            chip_id="existing_chip",
            username=username,
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        def unexpected_scaffold(*args, **kwargs):
            pytest.fail("Duplicate chips must be rejected before filesystem work")

        monkeypatch.setattr(
            "qdash.api.services.chip.config_scaffold.ChipConfigScaffolder.scaffold",
            unexpected_scaffold,
        )

        # Act: Try to create duplicate
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "existing_chip", "size": 64},
        )

        # Reject duplicates regardless of the creator, before touching the tree.
        assert response.status_code == 400
        assert not (config_tree / "existing_chip").exists()

    def test_create_chip_duplicate_save_returns_validation_error(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch
    ):
        def duplicate_save(self, *args, **kwargs):
            raise DuplicateKeyError("concurrent insert")

        monkeypatch.setattr(ChipDocument, "save", duplicate_save)
        response = test_client.post(
            "/chips", headers=auth_headers, json={"chip_id": "racing_chip", "size": 64}
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]
        # The winning creator may already use the shared configuration.
        assert (config_tree / "racing_chip/config/wiring.yaml").exists()

    def test_create_chip_failure_rolls_back_config(
        self, test_client, test_project, auth_headers, config_tree, monkeypatch
    ):
        def failed_save(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(ChipDocument, "save", failed_save)
        response = test_client.post(
            "/chips", headers=auth_headers, json={"chip_id": "failed_chip", "size": 64}
        )
        assert response.status_code == 500
        assert not (config_tree / "failed_chip").exists()

    def test_list_chips_requires_authentication(self, test_client, test_project):
        """Test that listing chips without auth returns 401."""
        # Act: Request without Authorization header
        response = test_client.get("/chips")

        # Assert
        assert response.status_code == 401

    def test_list_chips_invalid_token(self, test_client, test_project):
        """Test that listing chips with invalid token returns 401."""
        # Act: Request with invalid token
        headers = {
            "Authorization": "Bearer invalid_token",
            "X-Project-Id": "test_project",
        }
        response = test_client.get("/chips", headers=headers)

        # Assert
        assert response.status_code == 401

    def test_admin_cannot_list_chips_for_project_without_membership(self, test_client, init_db):
        """System admins do not bypass project membership for project data APIs."""
        admin = UserDocument(
            username="admin",
            hashed_password="hashed",
            access_token="admin_token",
            default_project_id=None,
            system_role=SystemRole.ADMIN,
            system_info=SystemInfoModel(),
        )
        admin.insert()

        owner = UserDocument(
            username="owner",
            hashed_password="hashed",
            access_token="owner_token",
            default_project_id="owner_project",
            system_info=SystemInfoModel(),
        )
        owner.insert()

        project = ProjectDocument(
            project_id="owner_project",
            name="Owner Project",
            owner_user_id=owner.user_id,
            owner_username="owner",
            system_info=SystemInfoModel(),
        )
        project.insert()

        ProjectMembershipDocument(
            project_id="owner_project",
            user_id=owner.user_id,
            username="owner",
            role=ProjectRole.OWNER,
            status="active",
            invited_by_user_id=owner.user_id,
            invited_by="owner",
        ).insert()

        ChipDocument(
            chip_id="private_chip",
            username="owner",
            project_id="owner_project",
            size=64,
            system_info=SystemInfoModel(),
        ).insert()

        response = test_client.get(
            "/chips",
            headers={
                "Authorization": "Bearer admin_token",
                "X-Project-Id": "owner_project",
            },
        )

        assert response.status_code == 403
