"""Runs are durable on their own: launch, replay, admission, and binding with or without a session.

The ledger is driven directly with the real ``CalibrationSessionService`` and an in-memory
MongoDB; ``validate`` and ``dispatch`` are stubs that record what they were given, so a test
can tell whether anything was launched. Grouping is switched with the deployment setting, as
an operator would.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import HTTPException
from pymongo import ASCENDING

from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.api.services.run_ledger import RunLedger, run_request_hash, scoped_request_hash
from qdash.common.utils.datetime import now
from qdash.config import get_settings
from qdash.datamodel.calibration_session import CalibrationChildKind, CalibrationSessionStatus
from qdash.datamodel.run import (
    RunAdmission,
    RunAssociation,
    RunDispatchStatus,
    RunIdentity,
    RunKind,
)
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.dbmodel.migration import migrate_prepare_run_scope
from qdash.dbmodel.run import LEGACY_SESSION_KEY_INDEX, RUN_COLLECTION, RunDocument
from qdash.repository.calibration_run import automatic_session_id_for_key
from qdash.repository.run_ledger import (
    RunMismatch,
    bind_flow_run,
    key_scope,
    record_worker_run,
)

PROJECT = "p"
CHIP = "c"


@pytest.fixture
def grouping(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Set CALIBRATION_SESSION_GROUPING for the test, as the deployment would."""

    def set_mode(mode: str) -> None:
        monkeypatch.setattr(get_settings(), "calibration_session_grouping", mode)

    return set_mode


class _Launcher:
    """Calls the ledger as a router does, recording every dispatch."""

    def __init__(self) -> None:
        self.dispatched: list[RunIdentity] = []
        self.fail_with: BaseException | None = None

    async def __call__(
        self,
        *,
        username: str = "alice",
        chip_id: str = CHIP,
        key: str | None = "k-1",
        session: str | None = None,
        request: dict[str, Any] | None = None,
    ) -> Any:
        async def dispatch(_: Any, identity: RunIdentity) -> ExecuteFlowResponse:
            if self.fail_with is not None:
                raise self.fail_with
            self.dispatched.append(identity)
            flow_run_id = f"fr-{len(self.dispatched)}"
            return ExecuteFlowResponse(
                execution_id=flow_run_id,
                flow_run_id=flow_run_id,
                flow_run_url="",
                qdash_ui_url="",
                message="started",
            )

        return await RunLedger(CalibrationSessionService()).launch(
            project_id=PROJECT,
            username=username,
            chip_id=chip_id,
            kind=RunKind.WORKFLOW,
            run_name="nightly",
            request_hash=run_request_hash(RunKind.WORKFLOW, chip_id, request or {"a": 1}),
            calibration_session_id=session,
            idempotency_key=key,
            validate=lambda: None,
            dispatch=dispatch,
            response=lambda _validated, dispatched: dispatched.model_dump(mode="json"),
        )


@pytest.fixture
def launch(init_db: Any) -> _Launcher:
    return _Launcher()


def _manual_session(
    session_id: str = "cs-1",
    *,
    owner: str = "alice",
    chip_id: str = CHIP,
    status: CalibrationSessionStatus = CalibrationSessionStatus.OPEN,
) -> str:
    CalibrationSessionDocument(
        calibration_session_id=session_id,
        project_id=PROJECT,
        chip_id=chip_id,
        objective="Tune q0",
        created_by=owner,
        status=status,
    ).insert()
    return session_id


def _run(run_id: str) -> RunDocument:
    doc = RunDocument.find_one({"run_id": run_id}).run()
    assert doc is not None
    return doc


def _bind(identity: RunIdentity, flow_run_id: str = "fr-1", **overrides: Any) -> RunIdentity:
    fields: dict[str, Any] = {"project_id": PROJECT, "chip_id": CHIP, "username": "alice"}
    return bind_flow_run(identity, flow_run_id=flow_run_id, **{**fields, **overrides})


class TestGroupingOff:
    @pytest.mark.asyncio
    async def test_a_run_naming_no_session_joins_none_and_keeps_every_guarantee(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("explicit")
        first = await launch()
        assert first.calibration_session_id is None and not first.replayed
        run = _run(first.run_id)
        assert run.calibration_session_id is None
        assert run.association == RunAssociation.NONE
        assert run.admission == RunAdmission.ADMITTED
        assert run.idempotency_scope == key_scope("alice", "k-1")
        assert CalibrationSessionDocument.find_all().count() == 0

        # The flow run QDash created binds the run with the token it was handed.
        [identity] = launch.dispatched
        assert identity.calibration_session_id is None
        assert _bind(identity) == identity
        # A retry is the recorded answer, not a second launch.
        again = await launch()
        assert again.replayed and again.run_id == first.run_id
        assert len(launch.dispatched) == 1

    @pytest.mark.asyncio
    async def test_an_unknown_outcome_without_a_session_is_never_launched_again(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("explicit")
        launch.fail_with = HTTPException(status_code=500, detail="Prefect timed out")
        with pytest.raises(HTTPException) as failed:
            await launch()
        assert "unknown outcome" in str(failed.value.detail)
        launch.fail_with = None
        with pytest.raises(HTTPException) as retried:
            await launch()
        assert retried.value.status_code == 409 and "unknown" in str(retried.value.detail)
        assert launch.dispatched == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("prepare", "status_code"),
        [
            (lambda: None, 404),
            (lambda: _manual_session(owner="bob"), 403),
            (lambda: _manual_session(chip_id="other"), 422),
            (lambda: _manual_session(status=CalibrationSessionStatus.CLOSED), 409),
        ],
        ids=["missing", "another-owner", "another-chip", "closed"],
    )
    async def test_a_named_session_that_cannot_take_the_run_refuses_it_before_launch(
        self, launch: _Launcher, grouping: Any, prepare: Any, status_code: int
    ) -> None:
        for mode in ("explicit", "automatic"):
            grouping(mode)
            RunDocument.get_motor_collection().delete_many({})
            CalibrationSessionDocument.get_motor_collection().delete_many({})
            prepare()
            with pytest.raises(HTTPException) as refused:
                await launch(session="cs-1")
            assert refused.value.status_code == status_code
            assert launch.dispatched == []
            # Never turned into a run without the session.
            assert RunDocument.find({"calibration_session_id": None}).count() == 0

    @pytest.mark.asyncio
    async def test_a_named_session_still_groups_its_runs(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("explicit")
        _manual_session()
        first = await launch(session="cs-1", key="k-1")
        second = await launch(session="cs-1", key="k-2")
        assert {first.calibration_session_id, second.calibration_session_id} == {"cs-1"}
        assert _run(first.run_id).association == RunAssociation.EXPLICIT
        session = CalibrationSessionDocument.find_one({"calibration_session_id": "cs-1"}).run()
        assert session is not None and session.child_count == 2
        assert session.pending_children == []

    def test_the_worker_records_an_unlaunched_flow_run_without_a_session(
        self, init_db: Any, grouping: Any
    ) -> None:
        grouping("explicit")
        identity = record_worker_run(
            project_id=PROJECT,
            chip_id=CHIP,
            username="alice",
            flow_run_id="fr-9",
            flow_name="nightly",
            run_name="nightly",
            auto_scheduled=True,
        )
        assert identity.calibration_session_id is None
        assert CalibrationSessionDocument.find_all().count() == 0
        # Turning grouping back on does not move a run already recorded for the flow run.
        grouping("automatic")
        again = record_worker_run(
            project_id=PROJECT,
            chip_id=CHIP,
            username="alice",
            flow_run_id="fr-9",
            flow_name="nightly",
            run_name="nightly",
            auto_scheduled=True,
        )
        assert again == identity
        assert CalibrationSessionDocument.find_all().count() == 0


class TestGroupingChangesBetweenAttempts:
    @pytest.mark.asyncio
    async def test_a_retry_after_grouping_was_turned_off_replays_the_grouped_run(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("automatic")
        first = await launch()
        assert first.calibration_session_id == automatic_session_id_for_key(PROJECT, "alice", "k-1")
        grouping("explicit")
        again = await launch()
        assert again.replayed
        assert (again.run_id, again.calibration_session_id) == (
            first.run_id,
            first.calibration_session_id,
        )
        assert len(launch.dispatched) == 1

    @pytest.mark.asyncio
    async def test_a_retry_after_grouping_was_turned_on_replays_the_ungrouped_run(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("explicit")
        first = await launch()
        grouping("automatic")
        again = await launch()
        assert again.replayed and again.run_id == first.run_id
        assert again.calibration_session_id is None
        # No automatic session was created for a run that already exists.
        assert CalibrationSessionDocument.find_all().count() == 0

    @pytest.mark.asyncio
    async def test_the_same_key_with_another_session_is_a_different_request(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("automatic")
        _manual_session()
        await launch(session="cs-1")
        with pytest.raises(HTTPException) as other:
            await launch()
        assert other.value.status_code == 409 and "different request" in other.value.detail
        assert len(launch.dispatched) == 1


class TestScope:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["automatic", "explicit"])
    async def test_two_users_with_the_same_key_get_two_runs(
        self, launch: _Launcher, grouping: Any, mode: str
    ) -> None:
        grouping(mode)
        alice = await launch(username="alice")
        bob = await launch(username="bob")
        assert alice.run_id != bob.run_id and not bob.replayed
        assert _run(bob.run_id).requested_by == "bob"
        assert len(launch.dispatched) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["automatic", "explicit"])
    async def test_the_same_key_on_another_chip_is_refused_not_launched(
        self, launch: _Launcher, grouping: Any, mode: str
    ) -> None:
        grouping(mode)
        await launch(chip_id=CHIP)
        with pytest.raises(HTTPException) as refused:
            await launch(chip_id="other")
        assert refused.value.status_code == 409
        assert len(launch.dispatched) == 1

    def test_scopes_of_keys_flow_runs_and_actions_never_collide(self) -> None:
        assert key_scope("alice", "k") != key_scope("bob", "k")
        # A client key shaped like a worker's scope stays in the client namespace.
        assert key_scope("alice", "flow-run:fr-1") != "flow-run:fr-1"
        assert key_scope("alice", "agent-action:a-1").startswith("key:")


class TestAdmissionLivesOnTheRun:
    @pytest.mark.asyncio
    async def test_a_run_admitted_to_a_session_binds_after_the_session_is_closed(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("automatic")
        _manual_session()
        launch.dispatched.clear()
        await launch(session="cs-1")
        [identity] = launch.dispatched
        assert _run(identity.run_id).admission == RunAdmission.ADMITTED
        CalibrationSessionDocument.get_motor_collection().update_one(
            {"calibration_session_id": "cs-1"},
            {"$set": {"status": CalibrationSessionStatus.CLOSED.value}},
        )
        assert _bind(identity) == identity

    @pytest.mark.asyncio
    async def test_a_run_binds_even_if_its_session_record_is_gone(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("automatic")
        await launch()
        [identity] = launch.dispatched
        CalibrationSessionDocument.get_motor_collection().delete_many({})
        assert _bind(identity) == identity

    def test_a_pending_attempt_is_never_carried_out(self, init_db: Any) -> None:
        _manual_session()
        RunDocument(
            run_id="cpr-1",
            project_id=PROJECT,
            calibration_session_id="cs-1",
            association=RunAssociation.EXPLICIT,
            chip_id=CHIP,
            idempotency_key="k",
            idempotency_scope=key_scope("alice", "k"),
            request_hash="h",
            requested_by="alice",
            dispatch_token="t-1",
            reservation_id="res-1",
            admission=RunAdmission.PENDING,
        ).insert()
        identity = RunIdentity(calibration_session_id="cs-1", run_id="cpr-1", dispatch_token="t-1")
        with pytest.raises(RunMismatch, match="not admitted"):
            _bind(identity)
        assert _run("cpr-1").flow_run_id is None

    def test_an_identity_naming_a_session_the_run_lacks_is_refused(self, init_db: Any) -> None:
        RunDocument(
            run_id="cpr-1",
            project_id=PROJECT,
            association=RunAssociation.NONE,
            chip_id=CHIP,
            idempotency_key="k",
            idempotency_scope=key_scope("alice", "k"),
            request_hash="h",
            requested_by="alice",
            dispatch_token="t-1",
            admission=RunAdmission.ADMITTED,
        ).insert()
        claimed = RunIdentity(calibration_session_id="cs-1", run_id="cpr-1", dispatch_token="t-1")
        with pytest.raises(RunMismatch):
            _bind(claimed)
        with pytest.raises(RunMismatch, match="another user"):
            _bind(claimed.model_copy(update={"calibration_session_id": None}), username="bob")

    @pytest.mark.asyncio
    async def test_a_lost_admission_write_launches_nothing_and_the_key_may_retry(
        self, launch: _Launcher, grouping: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        grouping("automatic")
        _manual_session()
        original = RunLedger._admit

        def fail(claim: RunDocument) -> None:
            raise_once.append(claim.run_id)
            monkeypatch.setattr(RunLedger, "_admit", original)
            # As if the update never reached the run: settle it the way _admit does.
            RunLedger.settle(claim, RunDispatchStatus.REJECTED, error="admission not recorded")
            raise HTTPException(status_code=503, detail="admission not recorded")

        raise_once: list[str] = []
        monkeypatch.setattr(RunLedger, "_admit", staticmethod(fail))
        with pytest.raises(HTTPException):
            await launch(session="cs-1")
        assert launch.dispatched == []
        retried = await launch(session="cs-1")
        assert retried.run_id == raise_once[0] and not retried.replayed
        assert _run(retried.run_id).attempts == 2


class TestUpgradedRecords:
    """Records written before runs had a scope or an admission."""

    @staticmethod
    def _legacy(
        *,
        session_id: str,
        key: str = "k-1",
        status: str = "dispatched",
        request: dict[str, Any] | None = None,
    ) -> RunDocument:
        doc = RunDocument(
            run_id="cpr-old",
            project_id=PROJECT,
            calibration_session_id=session_id,
            chip_id=CHIP,
            run_kind=RunKind.WORKFLOW,
            idempotency_key=key,
            request_hash=run_request_hash(RunKind.WORKFLOW, CHIP, request or {"a": 1}),
            requested_by="alice",
            status=status,
            dispatch_token="old-token",
            reservation_id="res-old",
            flow_run_id="fr-old" if status == "dispatched" else None,
            response=(
                {
                    "execution_id": "fr-old",
                    "flow_run_id": "fr-old",
                    "flow_run_url": "",
                    "qdash_ui_url": "",
                    "message": "started",
                }
                if status == "dispatched"
                else None
            ),
        )
        doc.insert()
        # Stored as the earlier release wrote it: without the fields it did not have.
        RunDocument.get_motor_collection().update_one(
            {"run_id": "cpr-old"},
            {"$unset": {"idempotency_scope": "", "admission": "", "association": ""}},
        )
        return doc

    @pytest.mark.asyncio
    async def test_a_key_of_a_named_session_still_replays_its_run(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("explicit")
        _manual_session()
        self._legacy(session_id="cs-1")
        again = await launch(session="cs-1")
        assert again.replayed and again.run_id == "cpr-old"
        assert launch.dispatched == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["automatic", "explicit"])
    async def test_a_key_of_an_automatic_session_still_replays_its_run(
        self, launch: _Launcher, grouping: Any, mode: str
    ) -> None:
        grouping(mode)
        self._legacy(session_id=automatic_session_id_for_key(PROJECT, "alice", "k-1"))
        again = await launch()
        assert again.replayed and again.run_id == "cpr-old"
        assert launch.dispatched == []

    @pytest.mark.asyncio
    async def test_a_refused_old_run_is_launched_again_in_place_with_its_admission(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("automatic")
        _manual_session()
        self._legacy(session_id="cs-1", status="rejected")
        again = await launch(session="cs-1")
        assert again.run_id == "cpr-old" and not again.replayed
        run = _run("cpr-old")
        assert (run.attempts, run.admission) == (2, RunAdmission.ADMITTED)
        # It keeps the scope it was recorded with: found again by its session and key.
        assert run.idempotency_scope is None
        assert RunDocument.find_all().count() == 1

    def test_an_old_pending_reservation_is_read_from_its_session_and_fails_closed(
        self, init_db: Any
    ) -> None:
        self._legacy(session_id="cs-1", status="dispatching")
        identity = RunIdentity(
            calibration_session_id="cs-1", run_id="cpr-old", dispatch_token="old-token"
        )
        # Its session cannot be read: the reservation's outcome is unknown, so it is refused.
        with pytest.raises(RunMismatch, match="not admitted"):
            _bind(identity, flow_run_id="fr-new")
        _manual_session()
        assert _bind(identity, flow_run_id="fr-new") == identity


class TestEarlierUniqueIndex:
    @pytest.mark.asyncio
    async def test_it_refuses_runs_without_a_session_until_the_migration_drops_it(
        self, launch: _Launcher, grouping: Any, init_db: Any
    ) -> None:
        collection = init_db[RUN_COLLECTION]
        collection.create_index(
            [
                ("project_id", ASCENDING),
                ("calibration_session_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            unique=True,
            name=LEGACY_SESSION_KEY_INDEX,
        )
        grouping("explicit")
        await launch(username="alice")
        with pytest.raises(HTTPException) as refused:
            await launch(username="bob")
        assert refused.value.status_code == 503
        assert "prepare-run-scope" in refused.value.detail
        assert len(launch.dispatched) == 1

        assert migrate_prepare_run_scope(init_db, dry_run=True)["dropped"] is False
        stats = migrate_prepare_run_scope(init_db, dry_run=False, writers_quiesced=True)
        assert stats["dropped"] is True and stats["legacy_index_present"] is True
        bob = await launch(username="bob")
        assert not bob.replayed and len(launch.dispatched) == 2
        rerun = migrate_prepare_run_scope(init_db, dry_run=False, writers_quiesced=True)
        assert rerun["dropped"] is False and rerun["already_dropped"] is True


class TestStaleReservation:
    @pytest.mark.asyncio
    async def test_a_run_whose_request_stopped_before_launch_may_launch_again(
        self, launch: _Launcher, grouping: Any
    ) -> None:
        grouping("automatic")
        _manual_session()

        # Record an attempt whose request stopped after reserving it, before admission.
        ledger = RunLedger(CalibrationSessionService())
        sessions = CalibrationSessionService()
        reservation = sessions.reserve_child(
            project_id=PROJECT,
            calibration_session_id="cs-1",
            chip_id=CHIP,
            username="alice",
            kind=CalibrationChildKind.PIPELINE_RUN,
            child_id="cpr-stalled",
        )
        ledger._claim(
            existing=None,
            run_id="cpr-stalled",
            reservation_id=reservation.reservation_id,
            project_id=PROJECT,
            calibration_session_id="cs-1",
            association=RunAssociation.EXPLICIT,
            idempotency_key="k-1",
            request_hash=scoped_request_hash(
                run_request_hash(RunKind.WORKFLOW, CHIP, {"a": 1}), "cs-1"
            ),
            chip_id=CHIP,
            username="alice",
            kind=RunKind.WORKFLOW,
            run_name="nightly",
        )
        CalibrationSessionDocument.get_motor_collection().update_one(
            {"calibration_session_id": "cs-1"},
            {"$set": {"pending_children.0.reserved_at": now() - timedelta(hours=1)}},
        )
        again = await launch(session="cs-1")
        assert again.run_id == "cpr-stalled" and not again.replayed
        assert _run("cpr-stalled").attempts == 2
