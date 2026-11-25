"""Runs are durable on their own: launch, replay, admission, and binding with or without a session.

The ledger is driven directly with the real ``CalibrationSessionService`` and an in-memory
MongoDB; ``validate`` and ``dispatch`` are stubs that record what they were given, so a test
can tell whether anything was launched. A request that names no session gets an automatic
one; runs recorded without a session (history, or actions of an agent session that has none) are
inserted directly, so the run's guarantees are shown not to depend on a session.
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
from qdash.repository.calibration_run import (
    automatic_session_id_for_flow_run,
    automatic_session_id_for_key,
)
from qdash.repository.run_ledger import (
    RunMismatch,
    bind_flow_run,
    key_scope,
    record_worker_run,
    run_id_for_flow_run,
)

PROJECT = "p"
CHIP = "c"


class _Launcher:
    """Calls the ledger as a router does, recording every dispatch."""

    def __init__(self) -> None:
        self.dispatched: list[RunIdentity] = []
        self.fail_with: BaseException | None = None
        # The preflight check: refuses with 409 while ``busy``; counts its calls.
        self.busy = False
        self.checked = 0
        self.invalid = False

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

        def validate() -> None:
            if self.invalid:
                raise HTTPException(status_code=422, detail="invalid request")

        def preflight(_: Any) -> None:
            self.checked += 1
            if self.busy:
                raise HTTPException(status_code=409, detail="hardware busy")

        return await RunLedger(CalibrationSessionService()).launch(
            project_id=PROJECT,
            username=username,
            chip_id=chip_id,
            kind=RunKind.WORKFLOW,
            run_name="nightly",
            request_hash=run_request_hash(RunKind.WORKFLOW, chip_id, request or {"a": 1}),
            calibration_session_id=session,
            idempotency_key=key,
            validate=validate,
            dispatch=dispatch,
            response=lambda _validated, dispatched: dispatched.model_dump(mode="json"),
            preflight=preflight,
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


def _sessionless_run(
    run_id: str = "cpr-alone",
    *,
    key: str = "k-1",
    status: RunDispatchStatus = RunDispatchStatus.DISPATCHED,
    flow_run_id: str | None = "fr-alone",
) -> RunDocument:
    """A run recorded without a calibration session, as history or an agent action has one."""
    doc = RunDocument(
        run_id=run_id,
        project_id=PROJECT,
        association=RunAssociation.NONE,
        chip_id=CHIP,
        run_kind=RunKind.WORKFLOW,
        idempotency_key=key,
        idempotency_scope=key_scope("alice", key),
        request_hash=scoped_request_hash(run_request_hash(RunKind.WORKFLOW, CHIP, {"a": 1}), None),
        requested_by="alice",
        status=status,
        dispatch_token="t-alone",
        admission=RunAdmission.ADMITTED,
        flow_run_id=flow_run_id,
        response=(
            {
                "execution_id": flow_run_id,
                "flow_run_id": flow_run_id,
                "flow_run_url": "",
                "qdash_ui_url": "",
                "message": "started",
            }
            if status == RunDispatchStatus.DISPATCHED
            else None
        ),
    )
    doc.insert()
    return doc


class TestAutomaticSession:
    @pytest.mark.asyncio
    async def test_a_run_naming_no_session_gets_an_automatic_one_and_keeps_every_guarantee(
        self, launch: _Launcher
    ) -> None:
        first = await launch()
        automatic = automatic_session_id_for_key(PROJECT, "alice", "k-1")
        assert first.calibration_session_id == automatic and not first.replayed
        run = _run(first.run_id)
        assert run.calibration_session_id == automatic
        assert run.association == RunAssociation.AUTOMATIC
        assert run.admission == RunAdmission.ADMITTED
        assert run.idempotency_scope == key_scope("alice", "k-1")
        assert CalibrationSessionDocument.find_all().count() == 1

        # The flow run QDash created binds the run with the token it was handed.
        [identity] = launch.dispatched
        assert identity.calibration_session_id == automatic
        assert _bind(identity) == identity
        # A retry is the recorded answer, not a second launch or a second session.
        again = await launch()
        assert again.replayed and again.run_id == first.run_id
        assert len(launch.dispatched) == 1
        assert CalibrationSessionDocument.find_all().count() == 1

    @pytest.mark.asyncio
    async def test_an_unknown_outcome_is_never_launched_again(self, launch: _Launcher) -> None:
        launch.fail_with = HTTPException(status_code=500, detail="Prefect timed out")
        with pytest.raises(HTTPException) as failed:
            await launch()
        assert "unknown outcome" in str(failed.value.detail)
        launch.fail_with = None
        with pytest.raises(HTTPException) as retried:
            await launch()
        assert retried.value.status_code == 409 and "unknown" in str(retried.value.detail)
        assert launch.dispatched == []

    def test_the_worker_records_an_unlaunched_flow_run_in_an_automatic_session(
        self, init_db: Any
    ) -> None:
        fields: dict[str, Any] = {
            "project_id": PROJECT,
            "chip_id": CHIP,
            "username": "alice",
            "flow_run_id": "fr-9",
            "flow_name": "nightly",
            "run_name": "nightly",
            "auto_scheduled": True,
        }
        identity = record_worker_run(**fields)
        assert identity.calibration_session_id == automatic_session_id_for_flow_run("fr-9")
        assert _run(identity.run_id).association == RunAssociation.AUTOMATIC
        # A retry of the same flow run finds the same records.
        assert record_worker_run(**fields) == identity
        assert CalibrationSessionDocument.find_all().count() == 1


class TestExplicitSession:
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
        self, launch: _Launcher, prepare: Any, status_code: int
    ) -> None:
        prepare()
        with pytest.raises(HTTPException) as refused:
            await launch(session="cs-1")
        assert refused.value.status_code == status_code
        assert launch.dispatched == []
        # Never turned into a run without the session, or into an automatic session.
        assert RunDocument.find_all().count() == 0
        assert CalibrationSessionDocument.find({"origin": "automatic"}).count() == 0

    @pytest.mark.asyncio
    async def test_a_named_session_groups_its_runs(self, launch: _Launcher) -> None:
        _manual_session()
        first = await launch(session="cs-1", key="k-1")
        second = await launch(session="cs-1", key="k-2")
        assert {first.calibration_session_id, second.calibration_session_id} == {"cs-1"}
        assert _run(first.run_id).association == RunAssociation.EXPLICIT
        session = CalibrationSessionDocument.find_one({"calibration_session_id": "cs-1"}).run()
        assert session is not None and session.child_count == 2
        assert session.pending_children == []
        assert CalibrationSessionDocument.find_all().count() == 1

    @pytest.mark.asyncio
    async def test_the_same_key_with_another_session_is_a_different_request(
        self, launch: _Launcher
    ) -> None:
        _manual_session()
        await launch(session="cs-1")
        with pytest.raises(HTTPException) as other:
            await launch()
        assert other.value.status_code == 409 and "different request" in other.value.detail
        assert len(launch.dispatched) == 1


class TestPreflight:
    """A request its preflight refuses (busy hardware) leaves no run, session, or reservation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["k-1", None])
    async def test_a_refused_request_creates_no_automatic_session_or_run(
        self, launch: _Launcher, key: str | None
    ) -> None:
        launch.busy = True
        with pytest.raises(HTTPException) as refused:
            await launch(key=key)
        assert refused.value.status_code == 409
        assert launch.checked == 1
        assert launch.dispatched == []
        assert RunDocument.find_all().count() == 0
        assert CalibrationSessionDocument.find_all().count() == 0

    @pytest.mark.asyncio
    async def test_a_refused_request_leaves_a_named_session_untouched(
        self, launch: _Launcher
    ) -> None:
        _manual_session()
        launch.busy = True
        with pytest.raises(HTTPException) as refused:
            await launch(session="cs-1")
        assert refused.value.status_code == 409
        assert launch.dispatched == []
        assert RunDocument.find_all().count() == 0
        session = CalibrationSessionDocument.find_one({"calibration_session_id": "cs-1"}).run()
        assert session is not None
        assert session.child_count == 0
        assert session.pending_children == []
        assert session.status == CalibrationSessionStatus.OPEN

    @pytest.mark.asyncio
    async def test_an_invalid_request_is_refused_before_the_preflight(
        self, launch: _Launcher
    ) -> None:
        launch.invalid = launch.busy = True
        with pytest.raises(HTTPException) as refused:
            await launch()
        assert refused.value.status_code == 422
        assert launch.checked == 0

    @pytest.mark.asyncio
    async def test_a_retry_of_a_launched_run_replays_without_the_preflight(
        self, launch: _Launcher
    ) -> None:
        first = await launch()
        # The run's own execution now holds the hardware.
        launch.busy = True
        again = await launch()
        assert again.replayed is True
        assert again.run_id == first.run_id
        assert again.response == first.response
        assert launch.checked == 1
        assert len(launch.dispatched) == 1

    @pytest.mark.asyncio
    async def test_a_late_refusal_stays_rejected_until_its_retry_passes_the_preflight(
        self, launch: _Launcher
    ) -> None:
        # The preflight passed, but the claim at dispatch found the hardware taken.
        launch.fail_with = HTTPException(status_code=409, detail="claimed meanwhile")
        with pytest.raises(HTTPException):
            await launch()
        [run] = RunDocument.find_all().to_list()
        assert run.status == RunDispatchStatus.REJECTED and run.attempts == 1
        session = CalibrationSessionDocument.find_one(
            {"calibration_session_id": run.calibration_session_id}
        ).run()
        assert session is not None
        count = session.child_count

        launch.fail_with = None
        launch.busy = True
        with pytest.raises(HTTPException) as refused:
            await launch()
        assert refused.value.status_code == 409
        # No new attempt and no reservation in its session.
        assert _run(run.run_id).attempts == 1
        assert _run(run.run_id).status == RunDispatchStatus.REJECTED
        session = CalibrationSessionDocument.find_one(
            {"calibration_session_id": run.calibration_session_id}
        ).run()
        assert session is not None
        assert session.child_count == count and session.pending_children == []

        launch.busy = False
        retried = await launch()
        assert retried.run_id == run.run_id and retried.replayed is False
        assert _run(run.run_id).attempts == 2
        assert len(launch.dispatched) == 1


class TestRunsWithoutASession:
    """A run recorded without a session keeps every guarantee and is never regrouped."""

    @pytest.mark.asyncio
    async def test_a_retry_replays_it_without_creating_a_session(self, launch: _Launcher) -> None:
        _sessionless_run()
        again = await launch()
        assert again.replayed and again.run_id == "cpr-alone"
        assert again.calibration_session_id is None
        assert launch.dispatched == []
        assert CalibrationSessionDocument.find_all().count() == 0

    def test_its_flow_run_binds_with_its_token(self, init_db: Any) -> None:
        _sessionless_run(status=RunDispatchStatus.DISPATCHING, flow_run_id=None)
        identity = RunIdentity(run_id="cpr-alone", dispatch_token="t-alone")
        assert _bind(identity) == identity
        assert _run("cpr-alone").flow_run_id == "fr-1"
        assert CalibrationSessionDocument.find_all().count() == 0

    def test_a_worker_run_recorded_without_one_stays_without_one(self, init_db: Any) -> None:
        RunDocument(
            run_id=run_id_for_flow_run("fr-9"),
            project_id=PROJECT,
            association=RunAssociation.NONE,
            chip_id=CHIP,
            idempotency_key="flow-run:fr-9",
            idempotency_scope="flow-run:fr-9",
            request_hash="",
            requested_by="alice",
            status=RunDispatchStatus.DISPATCHED,
            dispatch_token="worker:fr-9",
            admission=RunAdmission.ADMITTED,
            flow_run_id="fr-9",
        ).insert()
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


class TestScope:
    @pytest.mark.asyncio
    async def test_two_users_with_the_same_key_get_two_runs(self, launch: _Launcher) -> None:
        alice = await launch(username="alice")
        bob = await launch(username="bob")
        assert alice.run_id != bob.run_id and not bob.replayed
        assert _run(bob.run_id).requested_by == "bob"
        assert len(launch.dispatched) == 2

    @pytest.mark.asyncio
    async def test_the_same_key_on_another_chip_is_refused_not_launched(
        self, launch: _Launcher
    ) -> None:
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
        self, launch: _Launcher
    ) -> None:
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
    async def test_a_run_binds_even_if_its_session_record_is_gone(self, launch: _Launcher) -> None:
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
        self, launch: _Launcher, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
    async def test_a_key_of_a_named_session_still_replays_its_run(self, launch: _Launcher) -> None:
        _manual_session()
        self._legacy(session_id="cs-1")
        again = await launch(session="cs-1")
        assert again.replayed and again.run_id == "cpr-old"
        assert launch.dispatched == []

    @pytest.mark.asyncio
    async def test_a_key_of_an_automatic_session_still_replays_its_run(
        self, launch: _Launcher
    ) -> None:
        self._legacy(session_id=automatic_session_id_for_key(PROJECT, "alice", "k-1"))
        again = await launch()
        assert again.replayed and again.run_id == "cpr-old"
        assert launch.dispatched == []

    @pytest.mark.asyncio
    async def test_a_refused_old_run_is_launched_again_in_place_with_its_admission(
        self, launch: _Launcher
    ) -> None:
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
    async def test_it_refuses_no_run_qdash_records_and_may_be_dropped_optionally(
        self, launch: _Launcher, init_db: Any
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
        # Two users with the same key: each run joins its own automatic session.
        alice = await launch(username="alice")
        bob = await launch(username="bob")
        assert alice.run_id != bob.run_id and len(launch.dispatched) == 2
        # Actions of agent sessions without a calibration session are keyed by the action.
        for action_id in ("a-1", "a-2"):
            run, _ = RunLedger.begin_agent_action_run(
                project_id=PROJECT,
                calibration_session_id=None,
                chip_id=CHIP,
                agent_session_id="as-old",
                action_id=action_id,
                requested_by="alice",
                run_name="CheckRabi",
            )
            assert run.calibration_session_id is None
            RunLedger.settle_agent_action_run(
                run,
                dispatched=ExecuteFlowResponse(
                    execution_id=f"fr-{action_id}",
                    flow_run_id=f"fr-{action_id}",
                    flow_run_url="",
                    qdash_ui_url="",
                    message="started",
                ),
            )

        assert migrate_prepare_run_scope(init_db, dry_run=True)["dropped"] is False
        stats = migrate_prepare_run_scope(init_db, dry_run=False, writers_quiesced=True)
        assert stats["dropped"] is True and stats["legacy_index_present"] is True
        rerun = migrate_prepare_run_scope(init_db, dry_run=False, writers_quiesced=True)
        assert rerun["dropped"] is False and rerun["already_dropped"] is True


class TestStaleReservation:
    @pytest.mark.asyncio
    async def test_a_run_whose_request_stopped_before_launch_may_launch_again(
        self, launch: _Launcher
    ) -> None:
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
