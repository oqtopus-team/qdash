"""QDash.tasks.load_parameters: current task parameters to inspect, edit and run."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from test_sdk_session import CHIP, Server
from test_sdk_tasks import EXECUTE, execute_response

from qdash.sdk import QDashApiError, QDashNotFoundError, TaskParameters
from qdash.sdk.calibration import TaskCall, sweep

CATALOG = ("GET", "/task-files/tasks")
QUBIT_0 = ("GET", f"/chips/{CHIP}/qubits/0")
QUBIT_1 = ("GET", f"/chips/{CHIP}/qubits/1")
COUPLING = ("GET", f"/chips/{CHIP}/couplings/0-1")


def t1_info(**inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "CheckT1",
        "class_name": "CheckT1",
        "task_type": "qubit",
        "file_path": "qubex/one_qubit/t1.py",
        "enabled": True,
        "input_parameters": inputs
        or {
            "qubit_frequency": {
                "resolution": "database_required",
                "user_override": "allowed",
                "default_value": None,
                "value_type": "float",
                "unit": "GHz",
            },
            "readout_amplitude": {
                "resolution": "database_or_default",
                "user_override": "forbidden",
                "default_value": 0.1,
                "value_type": "float",
            },
        },
        "run_parameters": {
            "time_range": {"value_type": "np.logspace", "value": [2, 5, 51]},
            "shots": {"value_type": "int", "value": 1024},
            "interval": {"value_type": "float"},
        },
        "output_parameters": ["t1"],
    }


def catalog(*tasks: dict[str, Any]) -> list[httpx.Response]:
    return [httpx.Response(200, json={"tasks": list(tasks)})]


def qubit(qid: str, data: dict[str, Any] | None) -> list[httpx.Response]:
    return [httpx.Response(200, json={"qid": qid, "chip_id": CHIP, "data": data})]


def coupling(data: dict[str, Any] | None) -> list[httpx.Response]:
    return [httpx.Response(200, json={"qid": "0-1", "chip_id": CHIP, "data": data})]


def load(server: Server, task: str = "CheckT1", qid: str = "0") -> TaskParameters:
    with server.session() as qdash:
        params: TaskParameters = qdash.tasks.load_parameters(
            task, chip_id=CHIP, qid=qid, backend_name="qubex"
        )
    return params


def test_load_reads_current_values_and_run_defaults_without_writing() -> None:
    server = Server(
        {
            CATALOG: catalog(t1_info()),
            QUBIT_0: qubit("0", {"qubit_frequency": {"value": 5.2, "unit": "GHz"}}),
        }
    )
    params = load(server)

    assert params.input == {"qubit_frequency": 5.2, "readout_amplitude": 0.1}
    assert params.run == {
        "time_range": {"value": [2, 5, 51], "value_type": "np.logspace"},
        "shots": 1024,
    }
    assert params.missing == [] and params.unresolved == []
    assert params.forbidden == ["readout_amplitude"]
    assert (params.name, params.chip_id, params.qid, params.backend_name) == (
        "CheckT1",
        CHIP,
        "0",
        "qubex",
    )
    assert params.definition.name == "CheckT1"
    assert server.paths() == [CATALOG, QUBIT_0]
    assert all(request.method == "GET" for request in server.requests)
    assert all(request.headers["X-Project-Id"] == "project-a" for request in server.requests)


def test_load_without_backend_reads_the_configured_default() -> None:
    server = Server(
        {
            ("GET", "/task-files/settings"): [
                httpx.Response(200, json={"default_backend": "fake"})
            ],
            CATALOG: catalog(t1_info()),
            QUBIT_0: qubit("0", {"qubit_frequency": 5.0}),
        }
    )
    with server.session() as qdash:
        params = qdash.tasks.load_parameters("CheckT1", chip_id=CHIP, qid="0")
    assert params.backend_name == "fake"
    assert server.requests[1].url.params["backend"] == "fake"
    assert len(server.requests) == 3


def test_values_keep_their_python_form() -> None:
    inputs = {
        name: {"resolution": "database_optional", "user_override": "allowed"}
        for name in ("zero", "flag", "points", "bare", "null", "absent", "no_value")
    }
    server = Server(
        {
            CATALOG: catalog(t1_info(**inputs)),
            QUBIT_0: qubit(
                "0",
                {
                    "zero": {"value": 0},
                    "flag": {"value": False},
                    "points": {"value": [1.0, 2.0]},
                    "bare": 3.5,
                    "null": {"value": None},
                    "no_value": {"unit": "GHz"},
                },
            ),
        }
    )
    params = load(server)
    assert params.input == {
        "zero": 0,
        "flag": False,
        "points": [1.0, 2.0],
        "bare": 3.5,
        "null": None,
        "absent": None,
        "no_value": None,
    }
    # database_optional inputs may stay None; they are not sent.
    assert params.missing == []
    assert params.to_call().input == {"zero": 0, "flag": False, "points": [1.0, 2.0], "bare": 3.5}


def test_resolution_and_lookup_names_follow_the_worker() -> None:
    inputs: dict[str, dict[str, Any]] = {
        "renamed": {"resolution": "database_required", "parameter_name": "f01"},
        "aliased": {
            "resolution": "database_required",
            "parameter_name": "new_name",
            "parameter_aliases": ["old_name"],
            "fallback_parameter_names": ["fallback"],
        },
        "fallback_only": {
            "resolution": "database_required",
            "fallback_parameter_names": ["fallback"],
        },
        "with_default": {"resolution": "database_or_default", "default_value": 7},
        "default_used": {"resolution": "database_or_default", "default_value": 0},
        "defaults_only": {"resolution": "default_only", "default_value": 2},
        "required_missing": {"resolution": "database_required"},
        "legacy": {},
        "legacy_value": {"value": 4.0},
        "strange": {"resolution": "runtime_magic"},
    }
    server = Server(
        {
            CATALOG: catalog(t1_info(**inputs)),
            QUBIT_0: qubit(
                "0",
                {
                    "f01": {"value": 5.1},
                    "old_name": {"value": 1},
                    "fallback": {"value": 9},
                    "with_default": {"value": 8},
                    "defaults_only": {"value": 99},
                    "legacy": {"value": 6},
                    "strange": {"value": 1},
                },
            ),
        }
    )
    params = load(server)
    assert params.input == {
        "renamed": 5.1,
        "aliased": 1,
        "fallback_only": 9,
        "with_default": 8,
        "default_used": 0,
        "defaults_only": 2,
        "required_missing": None,
        "legacy": 6,
        "legacy_value": 4.0,
        "strange": None,
    }
    assert params.missing == ["required_missing"]
    assert params.unresolved == ["strange"]


def test_coupling_roles_read_their_qubit_then_the_coupling() -> None:
    inputs: dict[str, dict[str, Any]] = {
        "control_frequency": {
            "resolution": "database_required",
            "parameter_name": "qubit_frequency",
            "qid_role": "control",
        },
        "target_frequency": {
            "resolution": "database_required",
            "parameter_name": "qubit_frequency",
            "qid_role": "target",
        },
        "target_shared": {
            "resolution": "database_required",
            "parameter_name": "shared",
            "qid_role": "target",
        },
        "cr_amplitude": {"resolution": "database_required", "qid_role": "coupling"},
        "self_value": {"resolution": "database_required", "parameter_name": "cr_amplitude"},
        "strange_role": {"resolution": "database_required", "qid_role": "spectator"},
    }
    info = t1_info(**inputs) | {"name": "CheckCR", "task_type": "coupling"}
    server = Server(
        {
            CATALOG: catalog(info),
            QUBIT_0: qubit("0", {"qubit_frequency": {"value": 5.0}}),
            QUBIT_1: qubit("1", {"qubit_frequency": {"value": 5.5}}),
            COUPLING: coupling({"cr_amplitude": {"value": 0.3}, "shared": {"value": 1}}),
        }
    )
    params = load(server, "CheckCR", "0-1")
    assert params.input == {
        "control_frequency": 5.0,
        "target_frequency": 5.5,
        "target_shared": 1,
        "cr_amplitude": 0.3,
        "self_value": 0.3,
        "strange_role": None,
    }
    assert params.unresolved == ["strange_role"]
    assert sorted(server.paths()) == sorted([CATALOG, QUBIT_0, QUBIT_1, COUPLING])


@pytest.mark.parametrize("qid", ["0-", "-1", "0-1-2"])
def test_malformed_coupling_qid_is_rejected_before_requests(qid: str) -> None:
    server = Server()
    with server.session() as qdash, pytest.raises(ValueError, match="control-target"):
        qdash.tasks.load_parameters("CheckCR", chip_id=CHIP, qid=qid, backend_name="qubex")
    assert server.requests == []


def test_coupling_task_on_a_qubit_qid_is_rejected_before_chip_reads() -> None:
    info = t1_info() | {"name": "CheckCR", "task_type": "coupling"}
    server = Server({CATALOG: catalog(info)})
    with pytest.raises(ValueError, match="control-target"):
        load(server, "CheckCR", "0")
    assert server.paths() == [CATALOG]


def test_read_failures_are_translated() -> None:
    server = Server(
        {
            CATALOG: catalog(t1_info()),
            QUBIT_0: [httpx.Response(404, json={"detail": "qubit not found"})],
        }
    )
    with pytest.raises(QDashNotFoundError, match="qubit not found"):
        load(server)
    with pytest.raises(QDashNotFoundError, match="Missing"):
        load(Server({CATALOG: catalog(t1_info())}), "Missing")
    with pytest.raises(QDashApiError, match="500"):
        load(Server({CATALOG: catalog(t1_info())}))  # the fake answers 500 for the qubit


def test_snapshots_are_independent_of_the_response_and_each_other() -> None:
    server = Server(
        {
            CATALOG: catalog(t1_info(points={"resolution": "database_optional"})),
            QUBIT_0: qubit("0", {"points": {"value": [1, 2]}}),
        }
    )
    with server.session() as qdash:
        definition = qdash.tasks.get("CheckT1", backend_name="qubex")
        first = qdash.tasks.load_parameters("CheckT1", chip_id=CHIP, qid="0", backend_name="qubex")
        second = qdash.tasks.load_parameters("CheckT1", chip_id=CHIP, qid="0", backend_name="qubex")
    first.input["points"].append(3)
    first.run["time_range"]["value"][2] = 11
    first.run["shots"] = 1
    assert second.input == {"points": [1, 2]}
    assert second.run["time_range"] == {"value": [2, 5, 51], "value_type": "np.logspace"}
    assert second.run["shots"] == 1024
    assert first.definition.run_parameters == definition.run_parameters
    assert first.definition.run_parameters["time_range"]["value"] == [2, 5, 51]
    assert first.definition is not first.definition


def loaded(data: dict[str, Any] | None = None) -> TaskParameters:
    server = Server(
        {
            CATALOG: catalog(t1_info()),
            QUBIT_0: qubit("0", data if data is not None else {"qubit_frequency": 5.2}),
        }
    )
    return load(server)


def test_to_call_omits_forbidden_inputs_and_keeps_run_forms() -> None:
    params = loaded()
    params.run["shots"] = 2048
    params.run["time_range"] = sweep.linspace(0, 100, 11)
    call = params.to_call()
    assert call == TaskCall(
        name="CheckT1",
        input={"qubit_frequency": 5.2},
        run={"time_range": {"value": [0, 100, 11], "value_type": "np.linspace"}, "shots": 2048},
        update_calibration_parameters=False,
    )
    # The forbidden input stays for inspection, and building a call changes nothing.
    assert params.input == {"qubit_frequency": 5.2, "readout_amplitude": 0.1}
    call.input["qubit_frequency"] = 1.0  # type: ignore[index]
    assert params.input["qubit_frequency"] == 5.2
    assert params.to_call(update_calibration_parameters=None).update_calibration_parameters is None
    assert params.to_call(update_calibration_parameters=True).update_calibration_parameters


def test_none_values_are_left_for_the_server() -> None:
    params = loaded()
    params.input["qubit_frequency"] = None
    with pytest.raises(ValueError, match="without a value: qubit_frequency; set them"):
        params.to_call()
    params.input["qubit_frequency"] = 5.3
    params.run["shots"] = None
    assert params.to_call().run == {
        "time_range": {"value": [2, 5, 51], "value_type": "np.logspace"}
    }


def test_missing_inputs_must_be_set_before_a_call() -> None:
    params = loaded({})
    assert params.missing == ["qubit_frequency"]
    with pytest.raises(ValueError, match="qubit_frequency"):
        params.to_call()
    params.input["qubit_frequency"] = 5.25
    assert params.missing == []
    assert params.to_call().input == {"qubit_frequency": 5.25}


def test_missing_forbidden_input_cannot_be_fixed_by_an_edit() -> None:
    inputs = {"locked": {"resolution": "database_required", "user_override": "forbidden"}}
    params = load(Server({CATALOG: catalog(t1_info(**inputs)), QUBIT_0: qubit("0", {})}))
    assert params.missing == ["locked"]
    with pytest.raises(ValueError, match="cannot be overridden: locked; calibrate"):
        params.to_call()


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda p: p.input.__setitem__("readout_amplitude", 0.2), "were changed: readout_amp"),
        (lambda p: p.input.__setitem__("readout_amplitude", None), "were changed: readout_amp"),
        (lambda p: p.input.__setitem__("typo", 1.0), "unknown input parameters: typo"),
        (lambda p: p.run.__setitem__("shot", 1), "unknown run parameters: shot"),
    ],
)
def test_forbidden_edits_and_unknown_names_are_rejected(edit: Any, message: str) -> None:
    params = loaded()
    edit(params)
    with pytest.raises(ValueError, match=message):
        params.to_call()


def test_removing_an_input_or_a_forbidden_one_leaves_it_to_the_server() -> None:
    params = loaded()
    del params.input["readout_amplitude"]
    params.input["qubit_frequency"] = 5.2
    assert params.to_call().input == {"qubit_frequency": 5.2}


def test_load_edit_run_sends_the_call_once() -> None:
    server = Server(
        {
            CATALOG: catalog(t1_info()),
            QUBIT_0: qubit("0", {"qubit_frequency": {"value": 5.2}}),
            EXECUTE: [httpx.Response(200, json=execute_response())],
        }
    )
    with server.session() as qdash:
        params = qdash.tasks.load_parameters("CheckT1", chip_id=CHIP, qid="0", backend_name="qubex")
        params.run["shots"] = 512
        call = params.to_call()
        assert [r.method for r in server.requests] == ["GET", "GET"]
        run = qdash.tasks.run(call, chip_id=CHIP, qid="0", backend_name="qubex")
    request = server.requests[-1]
    assert (request.method, request.url.path) == EXECUTE
    assert json.loads(request.content) == {
        "chip_id": CHIP,
        "qid": "0",
        "backend_name": "qubex",
        "input_parameter_overrides": {"qubit_frequency": 5.2},
        "run_parameter_overrides": {
            "time_range": {"value": [2, 5, 51], "value_type": "np.logspace"},
            "shots": 512,
        },
        "reconfigure": False,
        "update_calibration_parameters": False,
        "update_params": False,
    }
    assert run.call == call


@pytest.mark.parametrize("resolution", ["database_required", "database_or_default"])
@pytest.mark.parametrize("override", ["allowed", "forbidden"])
def test_explicit_stored_null_does_not_use_a_default(resolution: str, override: str) -> None:
    definition = t1_info(
        value={
            "resolution": resolution,
            "user_override": override,
            "default_value": 7,
            "parameter_aliases": ["alias"],
        }
    )
    server = Server(
        {
            CATALOG: catalog(definition),
            QUBIT_0: qubit("0", {"value": {"value": None}, "alias": {"value": 9}}),
        }
    )
    params = load(server)
    assert params.input["value"] is None
    assert params.missing == ["value"]
    with pytest.raises(ValueError, match="value"):
        params.to_call()


@pytest.mark.parametrize("stored", [None, {}, {"unit": "GHz"}])
def test_entry_without_a_stored_value_uses_default(stored: Any) -> None:
    server = Server(
        {
            CATALOG: catalog(
                t1_info(value={"resolution": "database_or_default", "default_value": 7})
            ),
            QUBIT_0: qubit("0", {"value": stored}),
        }
    )
    params = load(server)
    assert params.input["value"] == 7
    assert params.to_call().input == {"value": 7}
