"""Root configuration for tests."""

import pytest

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Set async fixture loop scope
pytest.mark.asyncio_default_fixture_loop_scope = "function"
