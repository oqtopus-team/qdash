"""The public ``qdash.sdk.version()`` and the default User-Agent built from it."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

import pytest

import qdash.sdk
from qdash.sdk import QDashConfig, _http, _version


def test_version_is_a_public_callable() -> None:
    from qdash.sdk import version

    assert "version" in qdash.sdk.__all__
    assert callable(version)
    resolved = version()
    assert isinstance(resolved, str)
    assert resolved


def test_dunder_version_is_an_alias_of_version() -> None:
    from qdash.sdk import __version__

    assert "__version__" in qdash.sdk.__all__
    assert __version__ == qdash.sdk.version()


def test_version_matches_the_installed_distribution_metadata() -> None:
    try:
        installed = distribution_version("qdash-sdk")
    except PackageNotFoundError:
        pytest.skip("qdash-sdk is not installed; running from a source tree")
    assert qdash.sdk.version() == installed
    assert qdash.sdk.__version__ == installed


def test_version_falls_back_to_unknown_without_distribution_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(_version, "_distribution_version", missing)
    assert _version._installed_version() == "unknown"


def test_default_user_agent_reuses_the_package_version() -> None:
    config = QDashConfig(base_url="http://qdash.local", api_token="t")
    assert _http.user_agent(config) == f"qdash-sdk/{qdash.sdk.version()}"


def test_configured_user_agent_overrides_the_default() -> None:
    config = QDashConfig(base_url="http://qdash.local", api_token="t", user_agent="notebook/1.0")
    assert _http.user_agent(config) == "notebook/1.0"
