"""Calibration run identity: automatic sessions and runs the worker records."""

from __future__ import annotations

from typing import Any

import pytest

from qdash.datamodel.calibration_session import (
    CalibrationPipelineRunStatus,
    CalibrationRunIdentity,
)
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.repository.calibration_run import (
    CalibrationRunMismatch,
    adopt_recorded_run,
    automatic_session_id_for_key,
    insert_or_load_automatic_session,
    read_identity,
    record_worker_run,
    run_kind_of_flow,
)


def _session(**overrides: Any) -> CalibrationSessionDocument:
    fields: dict[str, Any] = {
        "calibration_session_id": "cs-auto-1",
        "project_id": "p",
        "chip_id": "c",
        "username": "alice",
        "objective": "Workflow nightly",
    }
    return insert_or_load_automatic_session(**{**fields, **overrides})


def test_a_retry_loads_the_session_an_earlier_attempt_inserted(init_db: Any) -> None:
    first = _session()
    second = _session(objective="ignored on retry")
    assert second.calibration_session_id == first.calibration_session_id
    assert second.objective == "Workflow nightly"
    assert CalibrationSessionDocument.find_all().count() == 1


@pytest.mark.parametrize("overrides", [{"project_id": "q"}, {"chip_id": "d"}, {"username": "bob"}])
def test_an_id_held_by_another_project_chip_or_user_is_refused(
    init_db: Any, overrides: dict[str, Any]
) -> None:
    _session()
    with pytest.raises(CalibrationRunMismatch):
        _session(**overrides)


def test_a_manual_session_is_never_reused_as_automatic(init_db: Any) -> None:
    CalibrationSessionDocument(
        calibration_session_id="cs-auto-1",
        project_id="p",
        chip_id="c",
        objective="A person's objective",
        created_by="alice",
    ).insert()
    with pytest.raises(CalibrationRunMismatch):
        _session()


def test_the_key_derived_id_is_scoped_to_project_and_user() -> None:
    key = automatic_session_id_for_key("p", "alice", "k")
    assert key == automatic_session_id_for_key("p", "alice", "k")
    assert key != automatic_session_id_for_key("p", "bob", "k")
    assert key != automatic_session_id_for_key("q", "alice", "k")


def test_system_flows_name_their_kind_and_others_are_workflows() -> None:
    assert run_kind_of_flow("calibration-pipeline") == "pipeline"
    assert run_kind_of_flow("single-task-executor") == "task"
    assert run_kind_of_flow("nightly") == "workflow"
    assert run_kind_of_flow(None) == "workflow"


def test_the_worker_records_an_unrecorded_flow_run_once(init_db: Any) -> None:
    kwargs: dict[str, Any] = {
        "project_id": "p",
        "chip_id": "c",
        "username": "alice",
        "flow_run_id": "fr-1",
        "flow_name": "nightly",
        "run_name": "nightly",
        "auto_scheduled": False,
    }
    first = record_worker_run(**kwargs)
    again = record_worker_run(**kwargs)
    assert first == again
    [run] = CalibrationPipelineRunDocument.find_all().to_list()
    # Not started by the cron scheduler: a one-time schedule or a run started in Prefect.
    assert run.trigger == "worker"
    assert run.run_kind == "workflow"
    [session] = CalibrationSessionDocument.find_all().to_list()
    assert session.child_count == 1


# The dispatch token the API generated for the launch attempt (a fixed test value).
LAUNCH_ATTEMPT = "launch-attempt-1"


def _api_run(
    *,
    status: str = "dispatching",
    flow_run_id: str | None = None,
    reservation_pending: bool = False,
) -> CalibrationRunIdentity:
    """A run the API recorded in a manual session, and the identity it hands its flow run."""
    from qdash.common.utils.datetime import now
    from qdash.datamodel.calibration_session import (
        CalibrationChildKind,
        CalibrationChildReservation,
    )

    pending = (
        [
            CalibrationChildReservation(
                reservation_id="res-1",
                kind=CalibrationChildKind.PIPELINE_RUN,
                child_id="cpr-1",
                reserved_by="alice",
                reserved_at=now(),
            )
        ]
        if reservation_pending
        else []
    )
    CalibrationSessionDocument(
        calibration_session_id="cs-1",
        project_id="p",
        chip_id="c",
        objective="Tune q0",
        created_by="alice",
        pending_children=pending,
    ).insert()
    CalibrationPipelineRunDocument(
        run_id="cpr-1",
        reservation_id="res-1",
        project_id="p",
        calibration_session_id="cs-1",
        chip_id="c",
        idempotency_key="k",
        request_hash="h",
        requested_by="alice",
        status=status,
        dispatch_token=LAUNCH_ATTEMPT,
        flow_run_id=flow_run_id,
    ).insert()
    return CalibrationRunIdentity(
        calibration_session_id="cs-1", run_id="cpr-1", dispatch_token=LAUNCH_ATTEMPT
    )


def _adopt(identity: CalibrationRunIdentity, **overrides: Any) -> CalibrationRunIdentity:
    fields: dict[str, Any] = {
        "project_id": "p",
        "chip_id": "c",
        "username": "alice",
        "flow_run_id": "fr-1",
    }
    return adopt_recorded_run(identity, **{**fields, **overrides})


def _bound() -> str | None:
    run = CalibrationPipelineRunDocument.find_one({"run_id": "cpr-1"}).run()
    assert run is not None
    return run.flow_run_id


class TestAdoptRecordedRun:
    @pytest.mark.parametrize("status", ["dispatching", "dispatched", "unknown"])
    def test_the_dispatched_flow_run_binds_its_run_before_the_api_settles(
        self, init_db: Any, status: str
    ) -> None:
        # The worker may start before the API learns the launch's outcome, or the API may
        # never learn it (``unknown``): the token proves the flow run is the one launched.
        identity = _api_run(status=status)
        assert _adopt(identity) == identity
        assert _bound() == "fr-1"
        # A later step or a Prefect retry of the same flow run adopts it again.
        assert _adopt(identity) == identity
        run = CalibrationPipelineRunDocument.find_one({"run_id": "cpr-1"}).run()
        assert run is not None and run.status == status

    def test_a_flow_run_naming_the_same_ids_with_another_token_is_refused(
        self, init_db: Any
    ) -> None:
        identity = _api_run()
        forged = identity.model_copy(update={"dispatch_token": "guessed"})
        with pytest.raises(CalibrationRunMismatch, match="does not hold") as raised:
            _adopt(forged, flow_run_id="fr-evil")
        assert LAUNCH_ATTEMPT not in str(raised.value)
        assert _bound() is None

    def test_a_run_bound_to_another_flow_run_is_refused_even_with_its_token(
        self, init_db: Any
    ) -> None:
        identity = _api_run(status="dispatched", flow_run_id="fr-1")
        with pytest.raises(CalibrationRunMismatch, match="carried out by flow run fr-1"):
            _adopt(identity, flow_run_id="fr-2")
        assert _bound() == "fr-1"

    def test_of_simultaneous_claims_on_an_unbound_run_only_one_binds(
        self, init_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        identity = _api_run()
        unbound = CalibrationPipelineRunDocument.find_one({"run_id": "cpr-1"}).run()
        _adopt(identity, flow_run_id="fr-1")
        # The second flow run read the run before the first bound it: only the conditional
        # update decides, and it refuses the second.
        original = CalibrationPipelineRunDocument.find_one
        reads = iter([unbound])

        def stale_first_read(*args: Any, **kwargs: Any) -> Any:
            snapshot = next(reads, None)
            if snapshot is None:
                return original(*args, **kwargs)
            return type("Query", (), {"run": staticmethod(lambda: snapshot)})()

        monkeypatch.setattr(CalibrationPipelineRunDocument, "find_one", stale_first_read)
        with pytest.raises(CalibrationRunMismatch, match="claimed by another flow run"):
            _adopt(identity, flow_run_id="fr-2")
        monkeypatch.undo()
        assert _bound() == "fr-1"

    def test_without_a_token_only_a_run_already_bound_to_this_flow_run_is_adopted(
        self, init_db: Any
    ) -> None:
        # An identity without a token (none is released; fail closed for any other producer)
        # proves nothing, so it is adopted only where the API already recorded this flow run.
        identity = _api_run().model_copy(update={"dispatch_token": None})
        with pytest.raises(CalibrationRunMismatch, match="without its dispatch token"):
            _adopt(identity)
        assert _bound() is None
        CalibrationPipelineRunDocument.get_motor_collection().update_one(
            {"run_id": "cpr-1"}, {"$set": {"flow_run_id": "fr-1", "status": "dispatched"}}
        )
        assert _adopt(identity) == identity
        with pytest.raises(CalibrationRunMismatch):
            _adopt(identity, flow_run_id="fr-2")

    def test_a_run_refused_before_launch_is_never_carried_out(self, init_db: Any) -> None:
        identity = _api_run(status="rejected")
        with pytest.raises(CalibrationRunMismatch, match="refused the launch"):
            _adopt(identity)
        assert _bound() is None

    def test_a_run_whose_reservation_was_never_admitted_is_refused(self, init_db: Any) -> None:
        identity = _api_run(reservation_pending=True)
        with pytest.raises(CalibrationRunMismatch, match="not admitted"):
            _adopt(identity)
        assert _bound() is None

    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            ({"chip_id": "other"}, "on chip"),
            ({"project_id": "q"}, "not recorded"),
            ({"username": "bob"}, "another user"),
        ],
    )
    def test_another_project_chip_or_user_is_refused(
        self, init_db: Any, overrides: dict[str, Any], match: str
    ) -> None:
        identity = _api_run()
        with pytest.raises(CalibrationRunMismatch, match=match):
            _adopt(identity, **overrides)
        assert _bound() is None

    def test_another_session_is_refused(self, init_db: Any) -> None:
        identity = _api_run().model_copy(update={"calibration_session_id": "cs-other"})
        with pytest.raises(CalibrationRunMismatch, match="belongs to session"):
            _adopt(identity)

    def test_a_worker_recorded_run_is_bound_to_its_flow_run_from_the_start(
        self, init_db: Any
    ) -> None:
        identity = record_worker_run(
            project_id="p",
            chip_id="c",
            username="alice",
            flow_run_id="fr-1",
            flow_name="nightly",
            run_name="nightly",
            auto_scheduled=True,
        )
        assert identity.dispatch_token is None
        assert _adopt(identity, flow_run_id="fr-1") == identity
        # Its predictable IDs give another flow run no claim on it.
        with pytest.raises(CalibrationRunMismatch):
            _adopt(
                identity.model_copy(update={"dispatch_token": "worker:fr-1"}),
                flow_run_id="fr-2",
            )


class TestLateSettlement:
    @staticmethod
    def _claim() -> CalibrationPipelineRunDocument:
        run = CalibrationPipelineRunDocument.find_one({"run_id": "cpr-1"}).run()
        assert run is not None
        return run

    def test_the_api_settles_a_run_the_worker_already_bound_to_the_same_flow_run(
        self, init_db: Any
    ) -> None:
        from qdash.api.services.calibration_session_service import CalibrationSessionService

        identity = _api_run()
        claim = self._claim()
        _adopt(identity, flow_run_id="fr-1")
        CalibrationSessionService._settle(
            claim, CalibrationPipelineRunStatus.DISPATCHED, flow_run_id="fr-1"
        )
        run = self._claim()
        assert (run.status, run.flow_run_id) == ("dispatched", "fr-1")

    def test_a_launch_reporting_another_flow_run_never_replaces_the_binding(
        self, init_db: Any
    ) -> None:
        from qdash.api.services.calibration_session_service import CalibrationSessionService

        identity = _api_run()
        claim = self._claim()
        _adopt(identity, flow_run_id="fr-1")
        CalibrationSessionService._settle(
            claim, CalibrationPipelineRunStatus.DISPATCHED, flow_run_id="fr-2"
        )
        run = self._claim()
        assert (run.status, run.flow_run_id) == ("unknown", "fr-1")
        assert "fr-2" in run.error


def test_the_ungrouped_marker_and_no_context_name_no_run() -> None:
    assert read_identity(None) is None
    assert read_identity({"ungrouped": True}) is None
    assert read_identity({"calibration_session_id": "cs", "run_id": "r"}) == (
        CalibrationRunIdentity(calibration_session_id="cs", run_id="r")
    )


@pytest.mark.parametrize("ungrouped", [False, True])
def test_cached_flow_identity_rejects_owner_changes_between_steps(
    init_db: Any, monkeypatch: pytest.MonkeyPatch, ungrouped: bool
) -> None:
    from types import SimpleNamespace

    from qdash.datamodel.calibration_session import CALIBRATION_RUN_CONTEXT_KEY
    from qdash.repository.calibration_run import UNGROUPED_MARKER
    from qdash.workflow.service._internal import run_identity

    monkeypatch.setattr(run_identity, "_resolved", {})
    context = {CALIBRATION_RUN_CONTEXT_KEY: {UNGROUPED_MARKER: True}} if ungrouped else {}
    flow_run = SimpleNamespace(id="cached-owner-flow", name="nightly", context=context)
    monkeypatch.setattr(
        run_identity, "_flow_run_context", lambda: (flow_run, SimpleNamespace(name="nightly"))
    )
    first = run_identity.calibration_note(
        project_id="p", chip_id="c", username="alice", run_name="first step"
    )
    assert (
        run_identity.calibration_note(
            project_id="p", chip_id="c", username="alice", run_name="second step"
        )
        == first
    )
    with pytest.raises(CalibrationRunMismatch, match="owner"):
        run_identity.calibration_note(
            project_id="p", chip_id="c", username="bob", run_name="third step"
        )
