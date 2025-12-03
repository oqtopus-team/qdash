"""Tests for FlowSession factory module."""

from qdash.workflow.flow.config import FlowSessionConfig
from qdash.workflow.flow.factory import create_flow_session


class TestCreateFlowSession:
    """Test create_flow_session factory function."""

    def test_create_flow_session_returns_correct_type(self, mocker):
        """Test that create_flow_session returns a FlowSession instance."""
        # Mock FlowSession to avoid database dependencies
        mock_flow_session = mocker.patch("qdash.workflow.flow.session.FlowSession")

        config = FlowSessionConfig.create(
            username="test_user",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            execution_id="20240101-001",
            backend_name="fake",
            name="Test Calibration",
            tags=["tag1", "tag2"],
            use_lock=False,
            note={"key": "value"},
            muxes=[0, 1],
        )

        create_flow_session(config)

        # Verify FlowSession was called with correct parameters
        mock_flow_session.assert_called_once_with(
            username="test_user",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            execution_id="20240101-001",
            backend_name="fake",
            name="Test Calibration",
            tags=["tag1", "tag2"],
            use_lock=False,
            note={"key": "value"},
            enable_github_pull=False,
            github_push_config=None,
            muxes=[0, 1],
        )


class TestFlowSessionConfigIntegration:
    """Test FlowSessionConfig integration with factory."""

    def test_config_to_dict_for_session_creation(self):
        """Test that config.to_dict() produces valid kwargs."""
        config = FlowSessionConfig.create(
            username="test_user",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            execution_id="20240101-001",
            backend_name="fake",
            name="Test Calibration",
            tags=["tag1", "tag2"],
            use_lock=False,
            note={"key": "value"},
            muxes=[0, 1],
        )

        result = config.to_dict()

        # Verify all keys are present
        assert "username" in result
        assert "chip_id" in result
        assert "qids" in result
        assert "execution_id" in result
        assert "backend_name" in result
        assert "name" in result
        assert "tags" in result
        assert "use_lock" in result
        assert "note" in result
        assert "enable_github_pull" in result
        assert "github_push_config" in result
        assert "muxes" in result

        # Verify values are correct types for FlowSession.__init__
        assert isinstance(result["qids"], list)
        assert isinstance(result["tags"], list)
        assert isinstance(result["muxes"], list)
