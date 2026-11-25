"""QDash.device_topology: the topology request, its JSON snapshot and the PNG plot."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from test_sdk_session import Server

from qdash.sdk import (
    DeviceTopology,
    DeviceTopologyPlot,
    QDash,
    QDashApiError,
    QDashAuthError,
    QDashConfigDeprecationWarning,
    QDashTransportError,
    QDashValidationError,
)
from qdash.sdk.types import Condition, Device, FidelityCondition

if TYPE_CHECKING:
    from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

# The device gateway's config/example/device_topology_request.json.
GATEWAY_REQUEST: dict[str, Any] = {
    "name": "anemone",
    "device_id": "anemone",
    "qubits": ["0", "2", "3"],
    "exclude_couplings": ["0-1", "3-1"],
    "condition": {
        "coupling_fidelity": {
            "min": 0.0,
            "max": 1.0,
            "is_within_24h": True,
            "metric": "zx90_gate_fidelity",
        },
        "qubit_fidelity": {
            "min": 0.0,
            "max": 1.0,
            "is_within_24h": True,
            "metric": "x90_gate_fidelity",
        },
        "readout_fidelity": {"min": 0.0, "max": 1.0, "is_within_24h": True},
        "only_maximum_connected": True,
    },
}


def device_body(**extra: Any) -> dict[str, Any]:
    return {
        "name": "anemone",
        "device_id": "anemone",
        "qubits": [
            {
                "id": 0,
                "physical_id": 2,
                "position": {"x": 1.0, "y": 2.0},
                "fidelity": 0.99,
                "meas_error": {
                    "prob_meas1_prep0": 0.01,
                    "prob_meas0_prep1": 0.02,
                    "readout_assignment_error": 0.015,
                },
                "qubit_lifetime": {"t1": 50.0, "t2": 30.0},
                "gate_duration": {"rz": 0, "sx": 20, "x": 40},
            }
        ],
        "couplings": [
            {"control": 0, "target": 1, "fidelity": 0.95, "gate_duration": {"rzx90": 200}}
        ],
        "calibrated_at": "2026-11-24T00:00:00Z",
        **extra,
    }


def topology_server(*plot: httpx.Response) -> Server:
    return Server(
        {
            ("POST", "/device-topology"): [httpx.Response(200, json=device_body(new="kept"))],
            ("POST", "/device-topology/plot"): list(plot)
            or [httpx.Response(200, content=PNG, headers={"content-type": "image/png"})],
        }
    )


def test_create_posts_the_gateway_request_unchanged_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    server = topology_server()
    with server.session(project_id="project-b") as qdash:
        topology = qdash.device_topology.create(**json.loads(json.dumps(GATEWAY_REQUEST)))

    assert isinstance(topology, DeviceTopology)
    assert server.paths() == [("POST", "/device-topology")]
    request = server.requests[0]
    assert json.loads(request.content) == GATEWAY_REQUEST
    assert request.headers["X-Project-Id"] == "project-b"
    assert request.headers["Authorization"] == "Bearer api-token"
    assert list(tmp_path.iterdir()) == []
    assert (topology.name, topology.device_id) == ("anemone", "anemone")
    assert topology.qubits[0].physical_id == 2
    assert topology.couplings[0].target == 1
    assert topology.calibrated_at is not None
    assert isinstance(topology.detail, Device)


def test_create_sends_only_the_fields_given() -> None:
    server = topology_server()
    with server.session() as qdash:
        qdash.device_topology.create(name="n", device_id="label", qubits=["0", "1"])

    assert json.loads(server.requests[0].content) == {
        "name": "n",
        "device_id": "label",
        "qubits": ["0", "1"],
    }


def test_create_accepts_a_generated_condition() -> None:
    condition = Condition(
        coupling_fidelity=FidelityCondition(min=0.5, max=1.0, is_within24h=False),
        qubit_fidelity=FidelityCondition.model_validate({"min": 0.0, "max": 1.0}),
        readout_fidelity=FidelityCondition.model_validate({"min": 0.0, "max": 1.0, "metric": "m"}),
        cr_direction="forward",
    )
    server = topology_server()
    with server.session() as qdash:
        qdash.device_topology.create(name="n", device_id="d", qubits=["0"], condition=condition)

    assert json.loads(server.requests[0].content)["condition"] == {
        "coupling_fidelity": {"min": 0.5, "max": 1.0, "is_within_24h": False},
        "qubit_fidelity": {"min": 0.0, "max": 1.0},
        "readout_fidelity": {"min": 0.0, "max": 1.0, "metric": "m"},
        "cr_direction": "forward",
    }


@pytest.mark.parametrize(
    ("condition", "match"),
    [
        ({**GATEWAY_REQUEST["condition"], "only_max": True}, "unknown fields"),
        (
            {
                **GATEWAY_REQUEST["condition"],
                "qubit_fidelity": {"min": 0, "max": 1, "metrc": "x90"},
            },
            r"condition\.qubit_fidelity has unknown fields \['metrc'\]",
        ),
        (
            Condition.model_validate({**GATEWAY_REQUEST["condition"], "extra": 1}),
            "unknown fields",
        ),
        ({"qubit_fidelity": {"min": 0, "max": 1}}, "invalid condition"),
        ({**GATEWAY_REQUEST["condition"], "readout_fidelity": {"min": "low"}}, "invalid"),
    ],
)
def test_an_unknown_or_invalid_condition_is_rejected_before_sending(
    condition: Any, match: str
) -> None:
    server = topology_server()
    with server.session() as qdash, pytest.raises(ValueError, match=match):
        qdash.device_topology.create(name="n", device_id="d", qubits=["0"], condition=condition)
    assert server.requests == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"qubits": "0,1"},
        {"qubits": [0, 1]},
        {"exclude_couplings": "0-1"},
        {"condition": ["not", "a", "mapping"]},
    ],
)
def test_wrongly_typed_arguments_are_rejected_before_sending(arguments: dict[str, Any]) -> None:
    server = topology_server()
    request = {"name": "n", "device_id": "d", "qubits": ["0"], **arguments}
    with server.session() as qdash, pytest.raises(TypeError):
        qdash.device_topology.create(**request)
    assert server.requests == []


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(503, json={"detail": "busy"}), QDashApiError),
        (httpx.Response(500, json={"detail": "No master calibration note"}), QDashApiError),
        (httpx.Response(401, json={"detail": "no"}), QDashAuthError),
        (httpx.Response(422, json={"detail": [{"msg": "extra"}]}), QDashValidationError),
    ],
)
def test_a_failed_create_is_sent_once(response: httpx.Response, error: type[Exception]) -> None:
    server = Server({("POST", "/device-topology"): [response]})
    with server.session() as qdash, pytest.raises(error):
        qdash.device_topology.create(name="n", device_id="d", qubits=["0"])
    assert server.paths() == [("POST", "/device-topology")]
    assert server.sleeps == []


def test_save_writes_json_with_the_api_field_names(tmp_path: Path) -> None:
    server = topology_server()
    with server.session() as qdash:
        topology = qdash.device_topology.create(name="n", device_id="d", qubits=["0"])

    path = topology.save(tmp_path / "device_topology.json")
    assert path == tmp_path / "device_topology.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == device_body(new="kept")
    assert saved == topology.to_dict()
    assert "prob_meas1_prep0" in saved["qubits"][0]["meas_error"]
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert len(server.requests) == 1


def test_save_refuses_an_existing_file_unless_overwrite(tmp_path: Path) -> None:
    server = topology_server()
    target = tmp_path / "device_topology.json"
    target.write_text("old")
    with server.session() as qdash:
        topology = qdash.device_topology.create(name="n", device_id="d", qubits=["0"])

    with pytest.raises(FileExistsError):
        topology.save(target)
    assert target.read_text() == "old"
    with pytest.raises(IsADirectoryError):
        topology.save(tmp_path)
    with pytest.raises(FileNotFoundError):
        topology.save(tmp_path / "missing" / "device_topology.json")
    topology.save(target, overwrite=True)
    assert json.loads(target.read_text())["device_id"] == "anemone"


def test_plot_posts_the_topology_and_saves_the_png(tmp_path: Path) -> None:
    server = topology_server()
    with server.session(project_id="project-b") as qdash:
        topology = qdash.device_topology.create(name="n", device_id="d", qubits=["0"])
        plot = topology.plot()

    assert isinstance(plot, DeviceTopologyPlot)
    assert server.paths() == [("POST", "/device-topology"), ("POST", "/device-topology/plot")]
    request = server.requests[1]
    assert request.headers["Accept"] == "image/png"
    assert request.headers["X-Project-Id"] == "project-b"
    body = device_body()
    assert json.loads(request.content) == body
    assert plot.read() == PNG
    assert plot._repr_png_() == PNG
    path = plot.save(tmp_path / "device_topology.png")
    assert path.read_bytes() == PNG
    with pytest.raises(FileExistsError):
        plot.save(path)
    assert len(server.requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>sign in</html>", headers={"content-type": "text/html"}),
        httpx.Response(200, content=b"not a png", headers={"content-type": "image/png"}),
    ],
)
def test_plot_that_is_not_a_png_raises(response: httpx.Response) -> None:
    server = topology_server(response)
    with server.session() as qdash:
        topology = qdash.device_topology.create(name="n", device_id="d", qubits=["0"])
        with pytest.raises(QDashTransportError):
            topology.plot()


def test_a_failed_plot_is_sent_once() -> None:
    server = topology_server(httpx.Response(503, json={"detail": "busy"}))
    with server.session() as qdash:
        topology = qdash.device_topology.create(name="n", device_id="d", qubits=["0"])
        with pytest.raises(QDashApiError):
            topology.plot()
    assert [path for _, path in server.paths()].count("/device-topology/plot") == 1


# Profile names as default labels.

PROFILES_TOML = """\
default_profile = "anemone"

[anemone]
base_url = "http://qdash.local"
api_token = "api-token"

[other]
base_url = "http://qdash.local"
api_token = "api-token"
"""


@pytest.fixture
def profile_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Server:
    """A fake server behind every owned session, with a config.toml in $XDG_CONFIG_HOME."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    directory = tmp_path / "xdg" / "qdash"
    directory.mkdir(parents=True)
    (directory / "config.toml").write_text(PROFILES_TOML, encoding="utf-8")
    server = topology_server()
    monkeypatch.setattr("qdash.sdk._session.owned_http_client", lambda config: server.http_client())
    return server


def sent_labels(server: Server) -> list[tuple[str, str]]:
    return [
        (body["name"], body["device_id"])
        for body in (json.loads(request.content) for request in server.requests)
    ]


def test_labels_default_to_the_default_profile_name(profile_server: Server) -> None:
    with QDash() as qdash:
        qdash.device_topology.create(qubits=["0"])
    with QDash.from_profile() as qdash:
        qdash.device_topology.create(qubits=["0"])

    assert sent_labels(profile_server) == [("anemone", "anemone")] * 2


def test_labels_default_to_an_explicit_profile_name(profile_server: Server) -> None:
    with QDash.from_profile("other") as qdash:
        qdash.device_topology.create(qubits=["0"])
        # A session for another project keeps the profile name.
        qdash.with_project("p").device_topology.create(qubits=["0"])

    assert sent_labels(profile_server) == [("other", "other")] * 2


def test_labels_fall_back_to_the_profile_named_default(
    profile_server: Server, tmp_path: Path
) -> None:
    config_toml = tmp_path / "xdg" / "qdash" / "config.toml"
    config_toml.write_text(
        PROFILES_TOML.replace('default_profile = "anemone"', "").replace("[other]", "[default]"),
        encoding="utf-8",
    )
    with QDash() as qdash:
        qdash.device_topology.create(qubits=["0"])

    assert sent_labels(profile_server) == [("default", "default")]


def test_labels_default_to_the_legacy_ini_profile_name(
    profile_server: Server, tmp_path: Path
) -> None:
    directory = tmp_path / "xdg" / "qdash"
    (directory / "config.toml").unlink()
    (directory / "config.ini").write_text(
        "[default]\nbase_url = http://qdash.local\napi_token = api-token\n\n"
        "[lab]\nbase_url = http://qdash.local\napi_token = api-token\n",
        encoding="utf-8",
    )
    with pytest.warns(QDashConfigDeprecationWarning), QDash() as qdash:
        qdash.device_topology.create(qubits=["0"])
    with pytest.warns(QDashConfigDeprecationWarning), QDash.from_profile("lab") as qdash:
        qdash.device_topology.create(qubits=["0"])

    assert sent_labels(profile_server) == [("default", "default"), ("lab", "lab")]


def test_an_explicit_label_overrides_the_profile_name(profile_server: Server) -> None:
    with QDash.from_profile("anemone") as qdash:
        qdash.device_topology.create(name="gateway", qubits=["0"])
        qdash.device_topology.create(device_id="anemone-2", qubits=["0"])
        qdash.device_topology.create(name="n", device_id="d", qubits=["0"])

    assert sent_labels(profile_server) == [
        ("gateway", "anemone"),
        ("anemone", "anemone-2"),
        ("n", "d"),
    ]


@pytest.mark.parametrize("labels", [{"name": ""}, {"device_id": ""}])
def test_an_explicit_empty_label_is_rejected_with_a_profile(
    profile_server: Server, labels: dict[str, Any]
) -> None:
    with QDash.from_profile("anemone") as qdash, pytest.raises(ValueError, match="non-empty"):
        qdash.device_topology.create(qubits=["0"], **labels)
    assert profile_server.requests == []


@pytest.mark.parametrize(
    ("labels", "missing"),
    [({}, "name"), ({"name": "n"}, "device_id"), ({"device_id": "d"}, "name")],
)
def test_a_session_without_a_profile_needs_both_labels(
    labels: dict[str, Any], missing: str
) -> None:
    server = topology_server()
    with server.session() as qdash, pytest.raises(TypeError, match=missing) as raised:
        qdash.device_topology.create(qubits=["0"], **labels)
    assert "not opened from a config profile" in str(raised.value)
    assert f"pass {missing}=" in str(raised.value)
    assert server.requests == []


def test_an_environment_session_needs_both_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("QDASH_BASE_URL", "http://qdash.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "api-token")
    server = topology_server()
    monkeypatch.setattr("qdash.sdk._session.owned_http_client", lambda config: server.http_client())
    with QDash.from_env() as qdash:
        with pytest.raises(TypeError, match="name"):
            qdash.device_topology.create(qubits=["0"])
        assert server.requests == []
        qdash.device_topology.create(name="n", device_id="d", qubits=["0"])

    assert sent_labels(server) == [("n", "d")]
