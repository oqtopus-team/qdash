"""Tests for automatic AI triage scheduling."""

from unittest.mock import MagicMock, patch

from qdash.common.copilot.settings import AnalysisConfig, CopilotConfig, ModelConfig
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import QubitTaskModel, TaskStatusModel
from qdash.workflow.engine.task.ai_triage import (
    _ai_triage_config,
    _forced_ai_triage_markdown,
    enqueue_ai_triage_note,
)


def _execution_model() -> ExecutionModel:
    return ExecutionModel(
        username="test",
        name="test-execution",
        execution_id="test-exec-001",
        chip_id="test-chip",
        calib_data_path="/tmp/calib",
        tags=[],
        note={},
        status=ExecutionStatusModel.RUNNING,
        start_at=None,
        end_at=None,
        elapsed_time=None,
        message="",
        system_info=SystemInfoModel(),
    )


def _task(
    name: str,
    qid: str,
    status: TaskStatusModel = TaskStatusModel.COMPLETED,
) -> QubitTaskModel:
    return QubitTaskModel(
        name=name,
        qid=qid,
        status=status,
    )


def _config() -> MagicMock:
    config = MagicMock()
    config.enabled = True
    config.analysis.enabled = True
    config.analysis.ai_triage_tasks = ["CheckQubitSpectroscopy", "CheckResonatorSpectroscopy"]
    return config


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.settings.load_copilot_config")
def test_enqueue_skips_non_representative_resonator_spectroscopy(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Only the representative MUX resonator result should receive AI triage."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(_task("CheckResonatorSpectroscopy", "17"), _execution_model())

    mock_executor.submit.assert_not_called()


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.settings.load_copilot_config")
def test_enqueue_accepts_representative_resonator_spectroscopy(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Representative MUX resonator result is scheduled asynchronously."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(_task("CheckResonatorSpectroscopy", "16"), _execution_model())

    mock_executor.submit.assert_called_once()


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.settings.load_copilot_config")
def test_enqueue_accepts_failed_ai_triage_task(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Configured AI triage tasks are scheduled even when the result failed."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(
        _task("CheckQubitSpectroscopy", "4", status=TaskStatusModel.FAILED),
        _execution_model(),
    )

    mock_executor.submit.assert_called_once()


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.settings.load_copilot_config")
def test_enqueue_skips_running_ai_triage_task(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Automatic AI triage waits for a terminal task result."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(
        _task("CheckQubitSpectroscopy", "4", status=TaskStatusModel.RUNNING),
        _execution_model(),
    )

    mock_executor.submit.assert_not_called()


def test_ai_triage_config_applies_local_vlm_defaults_only_to_triage() -> None:
    config = CopilotConfig(
        model=ModelConfig(provider="openai", name="gpt-4.1", max_output_tokens=4096),
        analysis_models=[ModelConfig(provider="ollama", name="gemma4:26b", max_output_tokens=4096)],
        analysis=AnalysisConfig(
            max_expected_images=2,
            ai_triage_max_expected_images=0,
            ai_triage_max_output_tokens=1024,
        ),
    )

    triage_config = _ai_triage_config(config)

    assert config.analysis.max_expected_images == 2
    assert config.analysis_models[0].max_output_tokens == 4096
    assert triage_config.analysis.max_expected_images == 0
    assert triage_config.analysis_model is not None
    assert triage_config.analysis_model.max_output_tokens == 1024


def test_forced_ai_triage_markdown_marks_missing_f01_as_no_signal() -> None:
    markdown = _forced_ai_triage_markdown("CheckQubitSpectroscopy", {})

    assert markdown is not None
    assert "- Decision: `FAIL`" in markdown
    assert "- Human label suggestion: `NO_SIGNAL`" in markdown


def test_forced_ai_triage_markdown_allows_present_f01() -> None:
    markdown = _forced_ai_triage_markdown(
        "CheckQubitSpectroscopy",
        {"coarse_qubit_frequency": {"value": 4.21}},
    )

    assert markdown is None
