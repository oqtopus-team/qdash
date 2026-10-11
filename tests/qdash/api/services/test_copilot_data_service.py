"""Tests for the task context a chat about a task result opens with."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from qdash.copilot.config import CopilotConfig, ModelConfig, TaskChatConfig
from qdash.copilot.runtime import CopilotRuntime


class TestBuildTaskContext:
    """Tests for task context assembly."""

    def _config(self, *, multimodal: bool) -> CopilotConfig:
        return CopilotConfig(
            enabled=True,
            model=ModelConfig(provider="openai", name="gpt-4.1"),
            task_chat=TaskChatConfig(multimodal=multimodal, max_expected_images=2),
        )

    def test_builds_context_with_history_and_coupling_params(self):
        service = CopilotRuntime(data_access=MagicMock())
        knowledge = MagicMock()
        knowledge.to_prompt.return_value = "Prompt body"

        with (
            patch.object(service, "load_qubit_params", return_value={"f01": 5.0}),
            patch.object(
                service,
                "load_task_result",
                return_value={
                    "input_parameters": {"drive_amp": 0.1},
                    "output_parameters": {"t1": {"value": 12.0}},
                    "run_parameters": {"shots": 1024},
                    "figure_path": ["/tmp/figure.png"],
                },
            ),
            patch.object(service, "load_task_history", return_value=[{"task_id": "older"}]),
            patch.object(service, "load_neighbor_qubit_params", return_value={"1": {"t1": 9.0}}),
            patch.object(service, "load_coupling_params", return_value={"0-1": {"g": 0.02}}),
            patch("qdash.datamodel.task_knowledge.get_task_knowledge", return_value=knowledge),
        ):
            result = service.build_task_context(
                task_name="CheckZX90",
                chip_id="chip-1",
                qid="0-1",
                task_id="task-1",
                image_base64=None,
                config=self._config(multimodal=False),
            )

        knowledge.to_prompt.assert_called_once_with(include_examples=True)
        assert result.context.task_knowledge_prompt == "Prompt body"
        assert result.context.qubit_params == {"f01": 5.0}
        assert result.context.input_parameters == {"drive_amp": 0.1}
        assert result.context.output_parameters == {"t1": {"value": 12.0}}
        assert result.context.run_parameters == {"shots": 1024}
        # Every chat gets the task's recent runs; a coupling target also gets its parameters.
        assert result.context.history_results == [{"task_id": "older"}]
        assert result.context.neighbor_qubit_params == {}
        assert result.context.coupling_params == {"0-1": {"g": 0.02}}
        assert result.figure_paths == ["/tmp/figure.png"]
        assert result.image_base64 is None
        assert result.expected_images == []

    def test_multimodal_context_loads_missing_figure_and_expected_images(self):
        service = CopilotRuntime(data_access=MagicMock())
        knowledge = MagicMock()
        knowledge.to_prompt.return_value = "Prompt body"

        with (
            patch.object(service, "load_qubit_params", return_value={}),
            patch.object(
                service,
                "load_task_result",
                return_value={
                    "input_parameters": {},
                    "output_parameters": {},
                    "run_parameters": {},
                    "figure_path": ["/tmp/figure.png"],
                },
            ),
            patch.object(
                service, "load_figure_as_base64", return_value="encoded-image"
            ) as load_fig,
            patch.object(
                service,
                "collect_expected_images",
                return_value=[("img-1", "expected alt")],
            ) as collect_expected,
            patch("qdash.datamodel.task_knowledge.get_task_knowledge", return_value=knowledge),
        ):
            result = service.build_task_context(
                task_name="CheckT1",
                chip_id="chip-1",
                qid="0",
                task_id="task-1",
                image_base64=None,
                config=self._config(multimodal=True),
            )

        load_fig.assert_called_once_with(["/tmp/figure.png"])
        collect_expected.assert_called_once_with(
            knowledge, max_images=2, include_example_images=True
        )
        assert result.image_base64 == "encoded-image"
        assert result.expected_images == [("img-1", "expected alt")]


class TestLoaderWiring:
    """The runtime calls its loaders with the keyword names they declare."""

    def test_history_and_topology_loaders_accept_the_runtime_calls(self):
        service = CopilotRuntime(data_access=MagicMock())
        with (
            patch.object(service._history_loader, "load_task_history", return_value=[]) as hist,
            patch.object(
                service._topology_context_loader, "load_neighbor_qubit_params", return_value={}
            ) as neighbors,
            patch.object(
                service._topology_context_loader, "load_coupling_params", return_value={}
            ) as couplings,
        ):
            service.load_task_history("CheckT1", "chip-1", "0", 3)
            service.load_neighbor_qubit_params("chip-1", "0", ["t1"])
            service.load_coupling_params("chip-1", "0", None)
        hist.assert_called_once_with(task_name="CheckT1", chip_id="chip-1", qid="0", last_n=3)
        neighbors.assert_called_once_with(chip_id="chip-1", qid="0", param_names=["t1"])
        couplings.assert_called_once_with(chip_id="chip-1", qid="0", param_names=[])

    def test_the_real_loaders_declare_those_keywords(self):
        import inspect

        from qdash.copilot.services.history_service import CopilotHistoryLoader
        from qdash.copilot.services.topology_context_service import TopologyContextLoader

        assert {"task_name", "chip_id", "qid", "last_n"} <= set(
            inspect.signature(CopilotHistoryLoader.load_task_history).parameters
        )
        for name in ("load_neighbor_qubit_params", "load_coupling_params"):
            assert {"chip_id", "qid", "param_names"} <= set(
                inspect.signature(getattr(TopologyContextLoader, name)).parameters
            )
