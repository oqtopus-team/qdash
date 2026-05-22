"""Cache helpers for API dependency providers."""

from collections.abc import Callable
from functools import lru_cache
from typing import ParamSpec, Protocol, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class CachedDependencyProvider(Protocol[P, R]):
    """Callable dependency provider with an attached cache clear hook."""

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...

    def cache_clear(self) -> None: ...


_cached_dependency_providers: list[CachedDependencyProvider[..., object]] = []


def cached_dependency_provider(func: Callable[P, R]) -> CachedDependencyProvider[P, R]:
    """Cache and register a dependency provider for centralized reset."""
    cached = lru_cache(maxsize=1)(func)
    _cached_dependency_providers.append(cached)
    return cached


def clear_dependency_caches() -> None:
    """Clear all registered dependency provider caches."""
    for provider in _cached_dependency_providers:
        provider.cache_clear()
