"""Pydantic models for Copilot tool-call boundaries."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GetQubitParamsArgs(BaseModel):
    chip_id: str
    qid: str


class GetLatestTaskResultArgs(BaseModel):
    task_name: str
    chip_id: str
    qid: str


class GetTaskHistoryArgs(BaseModel):
    task_name: str
    chip_id: str
    qid: str
    last_n: int = 5


class GetParameterTimeseriesArgs(BaseModel):
    parameter_name: str
    chip_id: str
    qid: str
    last_n: int = 10


class CompareQubitsArgs(BaseModel):
    chip_id: str
    qids: list[str]
    param_names: list[str] | None = None


class GetCouplingParamsArgs(BaseModel):
    chip_id: str
    coupling_id: str | None = None
    qubit_id: str | None = None
    param_names: list[str] | None = None


class GetChipSummaryArgs(BaseModel):
    chip_id: str
    param_names: list[str] | None = None


class GetChipTopologyArgs(BaseModel):
    chip_id: str


class GenerateChipHeatmapArgs(BaseModel):
    chip_id: str
    metric_name: str
    selection_mode: str = "latest"
    within_hours: int | None = None


class ListAvailableParametersArgs(BaseModel):
    chip_id: str
    qid: str | None = None


class GetChipParameterTimeseriesArgs(BaseModel):
    parameter_name: str
    chip_id: str
    last_n: int = 10
    qids: list[str] | None = None


class GetExecutionHistoryArgs(BaseModel):
    chip_id: str
    status: str | None = None
    tags: list[str] | None = None
    last_n: int = 10


class SearchTaskResultsArgs(BaseModel):
    chip_id: str
    task_name: str | None = None
    qid: str | None = None
    status: str | None = None
    execution_id: str | None = None
    last_n: int = 10


class GetCalibrationNotesArgs(BaseModel):
    chip_id: str
    execution_id: str | None = None
    task_id: str | None = None
    last_n: int = 10


class GetParameterLineageArgs(BaseModel):
    parameter_name: str
    qid: str
    chip_id: str
    last_n: int = 10


class GetProvenanceLineageGraphArgs(BaseModel):
    entity_id: str
    chip_id: str
    max_depth: int = 5


class ExecutePythonAnalysisArgs(BaseModel):
    code: str = Field(min_length=1)
