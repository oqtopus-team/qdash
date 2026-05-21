"""Experimental single-execution bring-up with simultaneous qubit spectroscopy."""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import on_flow_cancellation
from qdash.workflow.service.steps import ExperimentalSimultaneousBringUp
from qdash.workflow.service.targets import MuxTargets


@flow(on_cancellation=[on_flow_cancellation])
def experimental_simultaneous_bringup(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run resonator and simultaneous qubit spectroscopy in one execution."""
    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)
    if qids:
        selected_mux_ids = sorted({int(qid) // 4 for qid in qids})
        selected_qids = {str(qid) for qid in qids}
        expanded_qids = {
            str(mux_id * 4 + offset) for mux_id in selected_mux_ids for offset in range(4)
        }
        targets = MuxTargets(
            mux_ids=selected_mux_ids,
            exclude_qids=sorted(set(exclude_qids) | (expanded_qids - selected_qids), key=int),
        )

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        # ExperimentalSimultaneousBringUp owns one combined Execution.
        skip_execution=True,
        default_run_parameters={
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=[ExperimentalSimultaneousBringUp()])
