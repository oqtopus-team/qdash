"""Per-run target overrides preserve code defaults unless explicitly requested."""

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from qdash.datamodel.flow_targets import TARGET_CONTEXT_KEY, FlowTargetOverride
from qdash.workflow.service.calib_service import CalibService
from qdash.workflow.service.flow_targets import override_target, read_target_override
from qdash.workflow.service.targets import MuxTargets, QubitTargets


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"mux_ids": []},
        {"mux_ids": [-1]},
        {"mux_ids": [True]},
        {"qids": ["a"]},
        {"qids": ["1", "1"]},
        {"qids": ["1"], "mux_ids": [0]},
        {"qids": ["1"], "exclude_qids": ["2"]},
    ],
)
def test_invalid_overrides(value):
    with pytest.raises(ValidationError):
        FlowTargetOverride.model_validate(value)


def test_unchanged_targets_preserve_identity():
    target = MuxTargets([1], ["4"])
    assert override_target(target, None) is target


def test_mode_switch_replaces_original_exclusions():
    assert override_target(MuxTargets([1], ["4"]), FlowTargetOverride(qids=["9"])) == QubitTargets(
        ["9"]
    )


def test_no_flow_context_leaves_defaults():
    assert read_target_override() is None


def test_context_applies_to_constructor_and_pipeline():
    override = FlowTargetOverride(qids=["9"])
    context = SimpleNamespace(
        flow_run=SimpleNamespace(context={TARGET_CONTEXT_KEY: override.model_dump()})
    )
    with (
        patch.dict(
            sys.modules,
            {
                "prefect.context": SimpleNamespace(
                    FlowRunContext=SimpleNamespace(get=lambda: context)
                )
            },
        ),
        patch.object(CalibService, "_initialize") as initialize,
    ):
        service = CalibService(
            "user", "chip", qids=["0"], muxes=[0], project_id="project", backend_name="fake"
        )
        assert service.qids == ["9"]
        assert service.muxes is None
        initialize.assert_called_once_with(["9"], None, None)
        with patch.object(service, "_run_pipeline", return_value={}) as run:
            service.run(MuxTargets([0]), [])
            run.assert_called_once_with(QubitTargets(["9"]), [])


def test_isolated_worker_keeps_its_scheduled_subset():
    with (
        patch(
            "qdash.workflow.service.flow_targets.read_target_override",
            return_value=FlowTargetOverride(qids=["1", "2"]),
        ),
        patch.object(CalibService, "_initialize"),
    ):
        worker = CalibService(
            "user",
            "chip",
            qids=["2"],
            project_id="project",
            backend_name="fake",
            use_lock=False,
            skip_execution=True,
        )
        assert worker.qids == ["2"]
        assert worker._target_override is None
