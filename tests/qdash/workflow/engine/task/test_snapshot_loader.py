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

    def test_init_defaults(self) -> None:
        loader = SnapshotParameterLoader(
            source_execution_id="exec-001",
            project_id="proj-1",
        )
        assert loader._source_execution_id == "exec-001"
        assert loader._project_id == "proj-1"
        assert loader._parameter_overrides is None
        assert loader._limit == DEFAULT_SNAPSHOT_LIMIT
        assert loader._cache is None

    def test_init_with_overrides(self) -> None:
        overrides: dict[str, dict[str, Any]] = {
            "run": {"shots": 2048},
            "input": {"freq": 5.0},
        }
        loader = SnapshotParameterLoader(
            source_execution_id="exec-001",
            project_id="proj-1",
            parameter_overrides=overrides,
        )
        assert loader._parameter_overrides == overrides

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

    def _make_loader_with_cache(
        self,
        cache: _CacheType,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> SnapshotParameterLoader:
        loader = SnapshotParameterLoader("exec-001", "proj-1", parameter_overrides=overrides)
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

    def test_get_snapshot_without_overrides_returns_raw(self) -> None:
        """Test that without overrides, raw snapshot data is returned."""
        snap_input: dict[str, Any] = {"freq": {"value": 5.0, "unit": "GHz"}}
        snap_run: dict[str, Any] = {"shots": {"value": 1024}}
        cache: _CacheType = {("TaskA", "0"): (snap_input, snap_run)}
        loader = self._make_loader_with_cache(cache, overrides=None)

        result = loader.get_snapshot("TaskA", "0")

        assert result == (snap_input, snap_run)

    def test_get_snapshot_with_input_overrides(self) -> None:
        """Test that input overrides are merged on top of snapshot."""
        snap_input: dict[str, Any] = {"freq": {"value": 5.0, "unit": "GHz"}, "amp": {"value": 0.1}}
        snap_run: dict[str, Any] = {"shots": {"value": 1024}}
        cache: _CacheType = {("TaskA", "0"): (snap_input, snap_run)}
        overrides: dict[str, dict[str, Any]] = {"input": {"freq": 6.0}}
        loader = self._make_loader_with_cache(cache, overrides=overrides)

        result = loader.get_snapshot("TaskA", "0")

        assert result is not None
        merged_input, merged_run = result
        # freq should have its value replaced but unit preserved
        assert merged_input["freq"] == {"value": 6.0, "unit": "GHz"}
        # amp should be untouched
        assert merged_input["amp"] == {"value": 0.1}
        # run_params should be unchanged
        assert merged_run == snap_run

    def test_get_snapshot_with_run_overrides(self) -> None:
        """Test that run overrides are merged on top of snapshot."""
        snap_input: dict[str, Any] = {"freq": {"value": 5.0}}
        snap_run: dict[str, Any] = {
            "shots": {"value": 1024, "unit": "count"},
            "interval": {"value": 150},
        }
        cache: _CacheType = {("TaskA", "0"): (snap_input, snap_run)}
        overrides: dict[str, dict[str, Any]] = {"run": {"shots": 2048}}
        loader = self._make_loader_with_cache(cache, overrides=overrides)

        result = loader.get_snapshot("TaskA", "0")

        assert result is not None
        merged_input, merged_run = result
        assert merged_input == snap_input
        assert merged_run["shots"] == {"value": 2048, "unit": "count"}
        assert merged_run["interval"] == {"value": 150}

    def test_get_snapshot_with_both_overrides(self) -> None:
        """Test that both input and run overrides are applied."""
        snap_input: dict[str, Any] = {"freq": {"value": 5.0}}
        snap_run: dict[str, Any] = {"shots": {"value": 1024}}
        cache: _CacheType = {("TaskA", "0"): (snap_input, snap_run)}
        overrides: dict[str, dict[str, Any]] = {"input": {"freq": 6.0}, "run": {"shots": 2048}}
        loader = self._make_loader_with_cache(cache, overrides=overrides)

        result = loader.get_snapshot("TaskA", "0")

        assert result is not None
        merged_input, merged_run = result
        # Both have "value" key, so only the value field is replaced
        assert merged_input["freq"] == {"value": 6.0}
        assert merged_run["shots"] == {"value": 2048}

    def test_get_snapshot_with_empty_overrides(self) -> None:
        """Test that empty overrides dict doesn't modify data."""
        snap_input: dict[str, Any] = {"freq": {"value": 5.0}}
        snap_run: dict[str, Any] = {"shots": {"value": 1024}}
        cache: _CacheType = {("TaskA", "0"): (snap_input, snap_run)}
        overrides: dict[str, dict[str, Any]] = {}
        loader = self._make_loader_with_cache(cache, overrides=overrides)

        result = loader.get_snapshot("TaskA", "0")

        assert result == (snap_input, snap_run)


class TestMergeOverrides:
    """Test SnapshotParameterLoader._merge_overrides static method."""

    def test_empty_overrides_returns_snapshot(self) -> None:
        snapshot: dict[str, Any] = {"a": 1, "b": 2}
        result = SnapshotParameterLoader._merge_overrides(snapshot, {})
        assert result == snapshot

    def test_override_replaces_simple_value(self) -> None:
        snapshot: dict[str, Any] = {"a": 1, "b": 2}
        result = SnapshotParameterLoader._merge_overrides(snapshot, {"a": 10})
        assert result == {"a": 10, "b": 2}

    def test_override_replaces_value_key_in_dict(self) -> None:
        """When snapshot has {"value": ...}, override replaces only the value."""
        snapshot: dict[str, Any] = {
            "freq": {"value": 5.0, "unit": "GHz", "description": "Frequency"},
        }
        result = SnapshotParameterLoader._merge_overrides(snapshot, {"freq": 6.0})
        assert result["freq"] == {"value": 6.0, "unit": "GHz", "description": "Frequency"}

    def test_override_replaces_entire_entry_without_value_key(self) -> None:
        """When snapshot dict lacks 'value' key, override replaces entirely."""
        snapshot: dict[str, Any] = {"config": {"mode": "fast", "retries": 3}}
        result = SnapshotParameterLoader._merge_overrides(snapshot, {"config": "simple"})
        assert result["config"] == "simple"

    def test_override_adds_new_key(self) -> None:
        snapshot: dict[str, Any] = {"a": 1}
        result = SnapshotParameterLoader._merge_overrides(snapshot, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_does_not_mutate_original(self) -> None:
        snapshot: dict[str, Any] = {"a": {"value": 1, "unit": "V"}}
        original_snapshot: dict[str, Any] = {"a": {"value": 1, "unit": "V"}}
        SnapshotParameterLoader._merge_overrides(snapshot, {"a": 2})
        assert snapshot == original_snapshot
