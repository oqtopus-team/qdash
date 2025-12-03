"""Tests for session context management."""

import threading
from unittest.mock import MagicMock

from qdash.workflow.flow.context import (
    SessionContext,
    clear_current_session,
    get_current_session,
    set_current_session,
)


class TestSessionContext:
    """Test SessionContext class."""

    def setup_method(self):
        """Clear session before each test."""
        clear_current_session()

    def test_singleton_pattern(self):
        """Test that SessionContext is a singleton."""
        context1 = SessionContext()
        context2 = SessionContext()

        assert context1 is context2

    def test_set_and_get_session(self):
        """Test setting and getting session."""
        context = SessionContext()
        mock_session = MagicMock()

        context.set_session(mock_session)
        result = context.get_session()

        assert result is mock_session

    def test_clear_session(self):
        """Test clearing session."""
        context = SessionContext()
        mock_session = MagicMock()

        context.set_session(mock_session)
        context.clear_session()
        result = context.get_session()

        assert result is None


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def setup_method(self):
        """Clear session before each test."""
        clear_current_session()

    def test_set_and_get_current_session(self):
        """Test set_current_session and get_current_session."""
        mock_session = MagicMock()

        set_current_session(mock_session)
        result = get_current_session()

        assert result is mock_session

    def test_clear_current_session(self):
        """Test clear_current_session."""
        mock_session = MagicMock()

        set_current_session(mock_session)
        clear_current_session()
        result = get_current_session()

        assert result is None


class TestThreadSafety:
    """Test thread safety of SessionContext."""

    def setup_method(self):
        """Clear session before each test."""
        clear_current_session()

    def test_thread_local_isolation(self):
        """Test that sessions are isolated per thread."""
        context = SessionContext()
        results = {}
        barrier = threading.Barrier(2)

        def thread_func(thread_id, session):
            context.set_session(session)
            barrier.wait()  # Sync threads
            results[thread_id] = context.get_session()

        session1 = MagicMock(name="session1")
        session2 = MagicMock(name="session2")

        thread1 = threading.Thread(target=thread_func, args=("t1", session1))
        thread2 = threading.Thread(target=thread_func, args=("t2", session2))

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        # Each thread should see its own session
        assert results["t1"] is session1
        assert results["t2"] is session2
