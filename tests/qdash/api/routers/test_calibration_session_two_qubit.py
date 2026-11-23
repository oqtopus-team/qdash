"""A real two-qubit pipeline carried out for a recorded decision, through the API.

The spec and the decision are the ones the ZX90 search skill ships (parsed from its
SKILL.md, not rewritten here): a ``CustomTwoQubit`` step in manual mode measuring the directed
coupling ``0-1`` with ``CheckCrossResonance`` and ``CreateZX90``. The API validates and records
it; Prefect is patched, so no flow runs and no hardware is touched. The step executions and
task results a worker would write are inserted as records, so measured values here are fixtures:
the tests pin the contract (validation, decision linkage, directed pair, audit projection), not
a hardware outcome.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from qdash.dbmodel.calibration_session import CalibrationPipelineRunDocument
from qdash.dbmodel.task import TaskDocument
from tests.qdash.api.routers.test_calibration_pipeline import good_spec
from tests.qdash.api.routers.test_calibration_session_audit import (
    MODEL,
    _audit,
    _decide,
    _detail,
    _task,
)
from tests.qdash.api.routers.test_calibration_sessions import (
    CHIP,
    _create_session,
    _headers,
    _release_locks,
    _step_execution,
    lab,  # noqa: F401 - the pytest fixture every test here uses
    prefect,
)

SKILL = (
    Path(__file__).resolve().parents[4]
    / "packages/pi-qdash/skills/qdash-zx90-optimization/SKILL.md"
)


def _skill_blocks() -> list[dict[str, Any]]:
    text = SKILL.read_text(encoding="utf-8")
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]


def _skill_spec() -> dict[str, Any]:
    [spec] = [block for block in _skill_blocks() if "spec_version" in block]
    return copy.deepcopy(spec)


def _skill_experiment() -> dict[str, Any]:
    """The skill's decision experiment, in the API's field names."""
    [decision] = [block for block in _skill_blocks() if "experiment" in block]
    experiment = decision["experiment"]
    return {
        "candidate_id": experiment["candidateId"],
        "stage": experiment["stage"],
        "target": experiment["target"],
        "requested_changes": [
            {
                "task_name": change["taskName"],
                "parameter": change["parameter"],
                "value": change["value"],
                "previous": change["previous"],
            }
            for change in experiment["requestedChanges"]
        ],
    }


def _propose(test_client, session_id: str, key: str, experiment: dict[str, Any]) -> str:
    response = _decide(test_client, session_id, key, experiment=experiment, model=MODEL)
    assert response.status_code == 201, response.text
    return str(response.json()["decision_id"])


def _post(test_client, session_id: str, key: str, spec: dict[str, Any], decision_id: str) -> Any:
    with prefect([f"flow-{key}"]):
        response = test_client.post(
            "/calibration-pipelines/execute",
            headers=_headers(),
            json={
                "chip_id": CHIP,
                "spec": spec,
                "calibration_session_id": session_id,
                "idempotency_key": key,
                "decision_id": decision_id,
            },
        )
    _release_locks()
    return response


@pytest.fixture
def coupling_tasks(lab):  # noqa: F811 - the fixture above, extended
    for name in ("CheckCrossResonance", "CreateZX90"):
        TaskDocument(
            project_id="lab-a",
            username="owner",
            name=name,
            backend="qubex",
            description=name,
            task_type="coupling",
        ).insert()


@pytest.mark.usefixtures("coupling_tasks")
class TestTwoQubitDecisionLinkage:
    def test_skill_spec_validates_as_a_directed_manual_pair(self, test_client):
        spec = _skill_spec()
        assert spec["steps"][0]["type"] == "CustomTwoQubit"
        assert spec["steps"][0]["rounds"] == [[["0", "1"]]]
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=_headers(),
            json={"chip_id": CHIP, "spec": spec},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["valid"] is True, body["problems"]
        [step] = body["steps"]
        assert step["type"] == "CustomTwoQubit"
        assert [call["call_id"] for call in step["calls"]] == ["cr_c03", "zx90_c03"]
        assert step["calls"][0]["settings"]["run"] == {"adiabatic_safe_factor": {"value": 0.8}}

    def test_run_carries_out_the_decision_and_the_audit_correlates_it(self, test_client):
        session_id = _create_session(test_client)
        experiment = _skill_experiment()
        assert experiment["target"] == "0-1"
        decision = _propose(test_client, session_id, "d-c03", experiment)

        response = _post(test_client, session_id, "run-c03", _skill_spec(), decision)
        assert response.status_code == 202, response.text
        dispatched = response.json()
        assert dispatched["decision_id"] == decision
        assert dispatched["targets"]["qids"] == ["0", "1"]
        [run] = CalibrationPipelineRunDocument.find({"run_id": dispatched["pipeline_run_id"]}).run()
        assert run.decision_id == decision
        assert run.spec is not None
        assert run.spec["steps"][0]["rounds"] == [[["0", "1"]]]

        # What a worker would record for the pair: fixtures, not a measurement.
        execution_id = dispatched["execution_id"]
        _step_execution(execution_id, "flow-run-c03", 1, "completed")
        _task(
            "t-cr",
            execution_id,
            name="CheckCrossResonance",
            qid="0-1",
            run={"adiabatic_safe_factor": {"value": 0.8}},
            outputs={"cr_amplitude": {"value": 0.42, "unit": ""}},
        )
        _task(
            "t-zx90",
            execution_id,
            name="CreateZX90",
            qid="0-1",
            outputs={
                "zx90_gate_time": {"value": 224.0, "unit": "ns"},
                "cr_duration": {"value": 192.0, "unit": "ns"},
            },
        )
        # A result on the reversed coupling is a different target and is never read.
        _task(
            "t-reverse",
            execution_id,
            name="CreateZX90",
            qid="1-0",
            outputs={"zx90_gate_time": {"value": 999.0, "unit": "ns"}},
        )

        detail = _detail(test_client, session_id)
        [row] = detail["experiments"]
        assert row["target"] == "0-1"
        assert row["candidate_id"] == "c03"
        assert row["pipeline_run_id"] == dispatched["pipeline_run_id"]
        [check] = row["parameter_checks"]
        assert check["task_name"] == "CheckCrossResonance"
        assert check["parameter"] == "adiabatic_safe_factor"
        assert (check["requested"], check["in_spec"], check["executed"]) == (0.8, 0.8, 0.8)
        assert check["consistent"] is True
        assert row["measured"]["gate_time_ns"]["value"] == 224.0
        assert row["measured"]["gate_time_ns"]["task_id"] == "t-zx90"
        assert row["measured"]["cr_duration_ns"]["value"] == 192.0
        assert row["measured"]["cr_amplitude"]["value"] == 0.42

        latest = detail["latest_requested_run"]
        assert latest["decision_id"] == decision and latest["candidate_id"] == "c03"
        assert latest["execution_outcome"] == "completed"
        assert any("hardware" in fact for fact in latest["missing"])

        audit = _audit(test_client, session_id)
        requested = next(e for e in audit["events"] if e["kind"] == "pipeline_requested")
        assert requested["decision_id"] == decision
        calls = {c["call_id"]: c for c in requested["data"]["requested_task_calls"]}
        assert calls["cr_c03"]["run"] == {"adiabatic_safe_factor": 0.8}
        measurements = [e for e in audit["events"] if e["kind"] == "measurement"]
        assert measurements and {e["decision_id"] for e in measurements} == {decision}

    def test_reversed_direction_never_links(self, test_client):
        session_id = _create_session(test_client)
        reversed_experiment = {**_skill_experiment(), "candidate_id": "c03r", "target": "1-0"}
        decision = _propose(test_client, session_id, "d-rev", reversed_experiment)
        response = _post(test_client, session_id, "run-rev", _skill_spec(), decision)
        assert response.status_code == 422, response.text
        assert "directed coupling 1-0" in response.json()["detail"]
        assert "0-1" in response.json()["detail"]
        # Refused before anything was recorded or dispatched.
        assert CalibrationPipelineRunDocument.find({"idempotency_key": "run-rev"}).count() == 0

    def test_a_coupling_decision_never_links_to_a_one_qubit_spec(self, test_client):
        session_id = _create_session(test_client)
        decision = _propose(test_client, session_id, "d-c03", _skill_experiment())
        response = _post(test_client, session_id, "run-1q", good_spec(), decision)
        assert response.status_code == 422, response.text
        assert "no two-qubit step" in response.json()["detail"]
        assert CalibrationPipelineRunDocument.find({"idempotency_key": "run-1q"}).count() == 0

    def test_automatic_pair_selection_only_checks_the_qubits(self, test_client):
        """A step that picks its pairs at run time cannot be checked for direction here."""
        session_id = _create_session(test_client)
        decision = _propose(
            test_client, session_id, "d-auto", {**_skill_experiment(), "target": "1-0"}
        )
        spec = _skill_spec()
        step = spec["steps"][0]
        del step["rounds"]
        step["execution_mode"] = "automatic"
        response = _post(test_client, session_id, "run-auto", spec, decision)
        assert response.status_code == 202, response.text
        assert response.json()["decision_id"] == decision
