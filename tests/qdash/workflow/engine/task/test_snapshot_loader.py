"""Tests for SnapshotParameterLoader."""

from typing import Any
from unittest.mock import MagicMock, patch

from qdash.workflow.engine.task.snapshot_loader import (
    DEFAULT_SNAPSHOT_LIMIT,
    SnapshotParameterLoader,
)

_CacheType = dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]


class TestSnapshotParameterLoaderInit:
    """Test SnapshotParameterLoader initialization."""

    def test_exempt_catalog_task_never_restores_history(self) -> None:
        loader = SnapshotParameterLoader(
            source_execution_id=None,
            source_task_id="source-result",
            project_id="proj-1",
            snapshot_exempt_tasks={"CheckRabi"},
        )
        with patch.object(loader, "_load") as load:
            assert loader.get_snapshot("CheckRabi", "0") is None
            load.assert_not_called()
        assert loader.requires_snapshot("CheckRabi") is False

    def test_init_defaults(self) -> None:
        loader = SnapshotParameterLoader(
            source_execution_id="exec-001",
            project_id="proj-1",
        )
        assert loader._source_execution_id == "exec-001"
        assert loader._source_task_id is None
        assert loader._project_id == "proj-1"
        assert loader._limit == DEFAULT_SNAPSHOT_LIMIT
        assert loader._cache is None
        assert loader.has_snapshot_source is True

    def test_loader_without_source_has_no_snapshot_source(self) -> None:
        loader = SnapshotParameterLoader(source_execution_id=None, project_id="proj-1")

        assert loader.has_snapshot_source is False

    def test_init_with_custom_limit(self) -> None:
        loader = SnapshotParameterLoader(
            source_execution_id="exec-001",
            project_id="proj-1",
            limit=500,
        )
        assert loader._limit == 500


class TestSnapshotParameterLoaderLoad:
    """Test SnapshotParameterLoader._load method."""

    def _make_doc(
        self,
        name: str,
        qid: str,
        input_params: dict[str, Any],
        run_params: dict[str, Any],
    ) -> MagicMock:
        doc = MagicMock()
        doc.name = name
        doc.qid = qid
        doc.input_parameters = input_params
        doc.run_parameters = run_params
        return doc

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_source_task_id_loads_exact_task(self, mock_doc_cls: MagicMock) -> None:
        """Single-task re-execution uses its stable task result ID."""
        doc = self._make_doc("CheckRabi", "0", {"freq": {"value": 5.0}}, {"shots": {"value": 1024}})
        mock_doc_cls.find_one.return_value.run.return_value = doc

        loader = SnapshotParameterLoader(
            source_execution_id="exec-001",
            project_id="proj-1",
            source_task_id="task-001",
        )

        assert loader.get_snapshot("CheckRabi", "0") == (
            {"freq": {"value": 5.0}},
            {"shots": {"value": 1024}},
        )
        mock_doc_cls.find_one.assert_called_once_with(
            {"project_id": "proj-1", "task_id": "task-001"}
        )
        mock_doc_cls.find.assert_not_called()

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_no_source_snapshot_skips_database_load(self, mock_doc_cls: MagicMock) -> None:
        """A loader without a source execution or task does not query history."""
        loader = SnapshotParameterLoader(source_execution_id=None, project_id="proj-1")

        assert loader.get_snapshot("CheckRabi", "0") is None
        assert loader._cache == {}
        mock_doc_cls.find.assert_not_called()

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_load_populates_cache(self, mock_doc_cls: MagicMock) -> None:
        """Test that _load fetches documents and populates the cache."""
        docs = [
            self._make_doc("CheckRabi", "0", {"freq": {"value": 5.0}}, {"shots": {"value": 1024}}),
            self._make_doc("CheckT1", "1", {"amp": {"value": 0.5}}, {}),
        ]
        mock_query = MagicMock()
        mock_query.sort.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.run.return_value = docs
        mock_doc_cls.find.return_value = mock_query

        loader = SnapshotParameterLoader("exec-001", "proj-1")
        loader._load()

        assert loader._cache is not None
        assert len(loader._cache) == 2
        assert ("CheckRabi", "0") in loader._cache
        assert ("CheckT1", "1") in loader._cache

        # Verify query parameters
        mock_doc_cls.find.assert_called_once_with(
            {"project_id": "proj-1", "execution_id": "exec-001"}
        )
        mock_query.limit.assert_called_once_with(DEFAULT_SNAPSHOT_LIMIT)

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_load_uses_custom_limit(self, mock_doc_cls: MagicMock) -> None:
        """Test that _load uses the configured limit."""
        mock_query = MagicMock()
        mock_query.sort.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.run.return_value = []
        mock_doc_cls.find.return_value = mock_query

        loader = SnapshotParameterLoader("exec-001", "proj-1", limit=42)
        loader._load()

        mock_query.limit.assert_called_once_with(42)

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_load_is_lazy_and_cached(self, mock_doc_cls: MagicMock) -> None:
        """Test that _load only queries the database once."""
        mock_query = MagicMock()
        mock_query.sort.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.run.return_value = []
        mock_doc_cls.find.return_value = mock_query

        loader = SnapshotParameterLoader("exec-001", "proj-1")
        loader._load()
        loader._load()  # second call should be a no-op

        mock_doc_cls.find.assert_called_once()

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_load_handles_db_exception(self, mock_doc_cls: MagicMock) -> None:
        """Test that _load sets empty cache on database failure."""
        mock_doc_cls.find.side_effect = RuntimeError("DB connection failed")

        loader = SnapshotParameterLoader("exec-001", "proj-1")
        loader._load()

        assert loader._cache == {}

    @patch("qdash.workflow.engine.task.snapshot_loader.TaskResultHistoryDocument")
    def test_load_handles_none_parameters(self, mock_doc_cls: MagicMock) -> None:
        """Test that _load defaults None parameters to empty dict."""
        doc = MagicMock()
        doc.name = "TaskA"
        doc.qid = "0"
        doc.input_parameters = None
        doc.run_parameters = None

        mock_query = MagicMock()
        mock_query.sort.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.run.return_value = [doc]
        mock_doc_cls.find.return_value = mock_query

        loader = SnapshotParameterLoader("exec-001", "proj-1")
        loader._load()

        assert loader._cache is not None
        assert loader._cache[("TaskA", "0")] == ({}, {})


class TestSnapshotParameterLoaderGetSnapshot:
    """Test SnapshotParameterLoader.get_snapshot method."""

    def _make_loader_with_cache(self, cache: _CacheType) -> SnapshotParameterLoader:
        loader = SnapshotParameterLoader("exec-001", "proj-1")
        loader._cache = cache
        return loader

    def test_get_snapshot_returns_cached_data(self) -> None:
        cache: _CacheType = {
            ("CheckRabi", "0"): (
                {"freq": {"value": 5.0, "unit": "GHz"}},
                {"shots": {"value": 1024}},
            )
        }
        loader = self._make_loader_with_cache(cache)

        result = loader.get_snapshot("CheckRabi", "0")

        assert result is not None
        input_params, run_params = result
        assert input_params == {"freq": {"value": 5.0, "unit": "GHz"}}
        assert run_params == {"shots": {"value": 1024}}

    def test_get_snapshot_returns_none_for_missing_key(self) -> None:
        loader = self._make_loader_with_cache({})
        assert loader.get_snapshot("NonExistent", "0") is None

    def test_get_snapshot_triggers_lazy_load(self) -> None:
        """Test that get_snapshot calls _load when cache is None."""
        loader = SnapshotParameterLoader("exec-001", "proj-1")
        assert loader._cache is None

        with patch.object(loader, "_load") as mock_load:

            def set_cache() -> None:
                loader._cache = {}

            mock_load.side_effect = set_cache
            result = loader.get_snapshot("TaskA", "0")

        mock_load.assert_called_once()
        assert result is None
