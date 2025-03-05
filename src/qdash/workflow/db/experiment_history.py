from datetime import datetime
from typing import Any

from qdash.dbmodel.experiment_history import ExperimentHistoryModel


def insert_experiment_history(
    label: str,
    exp_name: str,
    input_params: dict[str, Any],
    output_params: dict[str, Any],
    fig_path: str,
    timestamp: datetime,
    execution_id: str,
) -> None:
    execution = ExperimentHistoryModel(
        experiment_name=exp_name,
        timestamp=timestamp,
        label=label,
        status="running",
        input_parameter=input_params,
        output_parameter={},
        fig_path=f"{fig_path}/{label}_{exp_name}.png",
        execution_id=execution_id,
    )
    execution.insert()


def update_experiment_history(
    label: str,
    exp_name: str,
    status: str,
    output_params: dict[str, Any],
    timestamp: datetime,
) -> None:
    execution = ExperimentHistoryModel.find_one(
        {
            "experiment_name": exp_name,
            "label": label,
            "timestamp": timestamp,
        }
    ).run()
    execution.status = status
    execution.output_parameter = output_params
    execution.save()
