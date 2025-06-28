from pathlib import Path
from typing import Any, ClassVar

import yaml
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckSkew(BaseTask):
    """Task to check skew the boxies."""

    name: str = "CheckSkew"
    backend: str = "qubex"
    task_type: str = "system"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "box_ids": InputParameterModel(
            unit="a.u.",
            value_type="list",
            value=[
                "R21B",
                "U15A",
                "Q2A",
                "S159A",
                "U10B",
                "R20A",
                "R26A",
                "R31A",
                "R28A",
                "R19A",
                "Q73A",
                "U13B",
                "R23A",
            ],
            description="List of muxes to check skew",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        result = run_result.raw_result
        figures: list = [result.get("fig")]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def load(self, filename: str) -> Any:
        with (Path.cwd() / Path(filename)).open() as file:
            return yaml.safe_load(file)

    def run(self, session: QubexSession, qid: str) -> RunResult:  # noqa: ARG002
        exp = session.get_session()
        result = exp.tool.check_skew(
            box_ids=self.input_parameters["box_ids"].get_value(),
        )
        result = {
            "fig": result.get("fig"),
        }
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
