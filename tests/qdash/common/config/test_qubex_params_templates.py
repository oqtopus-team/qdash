"""The QDash params templates classify files and render System directories."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from qdash.common.config import qubex_params_templates as templates

if TYPE_CHECKING:
    from pathlib import Path


def test_physics_files_are_common_and_hardware_files_are_backend_specific() -> None:
    common = {item.name for item in templates.common_templates()}
    quel1 = {item.name for item in templates.backend_templates("quel1")}
    quel3 = {item.name for item in templates.backend_templates("quel3")}

    assert {"qubit_frequency.yaml", "t1.yaml", "zx90_gate_fidelity.yaml"} <= common
    assert quel1 == {
        "capture_delay.yaml",
        "capture_delay_word.yaml",
        "control_fsc.yaml",
        "control_vatt.yaml",
        "readout_fsc.yaml",
        "readout_vatt.yaml",
    }
    assert quel3 == {"capture_delay.yaml"}
    assert templates.is_common_file("t1.yaml")
    assert not templates.is_common_file("capture_delay.yaml")


def test_capture_delay_unit_follows_the_backend() -> None:
    quel1 = next(t for t in templates.templates_for("quel1") if t.name == "capture_delay.yaml")
    quel3 = next(t for t in templates.templates_for("quel3") if t.name == "capture_delay.yaml")

    assert (quel1.unit, quel1.scope) == ("ndelay", "mux")
    assert (quel3.unit, quel3.scope) == ("ns", "mux")
    assert "capture_delay_word.yaml" not in {t.name for t in templates.templates_for("quel3")}


def test_render_fills_labels_from_values_then_defaults_and_strips_scope() -> None:
    t1 = next(t for t in templates.common_templates() if t.name == "t1.yaml")
    labels = templates.labels_for("qubit", n_qubits=4, mux_ids=[0], couplings=[])

    rendered = yaml.safe_load(templates.render(t1, labels=labels, values={"Q01": 12.5}))

    assert labels == ["Q00", "Q01", "Q02", "Q03"]
    assert rendered["meta"] == {
        "description": "T1 coherence time of the qubit",
        "unit": "µs",
        "default": None,
    }
    assert rendered["data"] == {"Q01": 12.5}


def test_render_uses_the_default_for_mux_and_coupling_scopes() -> None:
    capture = next(
        t for t in templates.backend_templates("quel3") if t.name == "capture_delay.yaml"
    )
    zx90 = next(t for t in templates.common_templates() if t.name == "zx90_gate_fidelity.yaml")

    capture_data = yaml.safe_load(templates.render(capture, labels=[3, 1]))["data"]
    zx_labels = templates.labels_for("coupling", n_qubits=16, mux_ids=[], couplings=["0-1"])
    zx_data = yaml.safe_load(templates.render(zx90, labels=zx_labels, values={"Q00-Q01": 99.0}))

    assert capture_data == {1: 700, 3: 700}
    assert zx_data["data"] == {"Q00-Q01": 99.0}


def test_verbatim_template_is_copied_unchanged() -> None:
    defaults = next(
        t for t in templates.common_templates() if t.name == "measurement_defaults.yaml"
    )

    assert defaults.scope is None
    assert templates.render(defaults, labels=()) == defaults.path.read_text(encoding="utf-8")


def test_value_for_template_requires_matching_units() -> None:
    t1 = next(t for t in templates.common_templates() if t.name == "t1.yaml")

    assert templates.value_for_template(t1, {"value": 20.0, "unit": "µs"}) == 20.0
    assert templates.value_for_template(t1, {"value": 20.0}) == 20.0
    assert templates.value_for_template(t1, {"value": 20.0, "unit": "ns"}) is None
    assert templates.value_for_template(t1, {"value": None}) is None
    assert templates.value_for_template(t1, None) is None


def test_every_template_parses_and_names_a_scope(tmp_path: Path) -> None:
    for backend in ("quel1", "quel3"):
        for template in templates.templates_for(backend):
            assert template.scope in {None, "qubit", "mux", "coupling"}
            if template.scope is not None:
                assert "scope" not in yaml.safe_load(templates.render(template, labels=()))["meta"]


def test_every_mapped_params_file_has_a_template() -> None:
    """A new output parameter needs a template, or new chips never get its file.

    ``workflow.params_updater.parameter_file_map`` names the params file each task
    output is written to; chip provisioning creates the files it has templates for.
    """
    from qdash.common.config.params_updater import _load_param_file_map

    mapped = set(_load_param_file_map().values())
    templated = {template.name for template in templates.common_templates()}
    for backend in templates.available_backends():
        templated.update(template.name for template in templates.backend_templates(backend))
    assert mapped <= templated, sorted(mapped - templated)
