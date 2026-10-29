from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from qdash.workflow.calibtasks.qubex.box_setup import configuration_lock


class FakeMissingContextError(Exception):
    pass


class FakeObjectAlreadyExists(Exception):
    pass


class FakeObjectNotFound(Exception):
    pass


def test_configuration_push_lock_is_skipped_outside_prefect_context(monkeypatch) -> None:
    ensure_limits = MagicMock()
    monkeypatch.setattr(configuration_lock, "_ensure_limits", ensure_limits)
    monkeypatch.setattr(configuration_lock, "MissingContextError", FakeMissingContextError)
    monkeypatch.setattr(
        configuration_lock,
        "get_run_context",
        MagicMock(side_effect=FakeMissingContextError()),
    )

    with configuration_lock.configuration_push_lock(["box-1"]):
        pass

    ensure_limits.assert_not_called()


def test_configuration_push_lock_acquires_all_distinct_box_limits(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    @contextmanager
    def fake_concurrency(names, **kwargs):
        events.append(("acquire", (names, kwargs)))
        yield
        events.append(("release", names))

    monkeypatch.setattr(configuration_lock, "get_run_context", MagicMock(return_value=object()))
    monkeypatch.setattr(
        configuration_lock,
        "_ensure_limits",
        lambda names: events.append(("ensure", names)),
    )
    monkeypatch.setattr(configuration_lock, "concurrency", fake_concurrency)

    with configuration_lock.configuration_push_lock(["box-2", "box-1", "box-2"]):
        events.append(("body", None))

    box_1_name = configuration_lock._lock_name("box-1")
    box_2_name = configuration_lock._lock_name("box-2")
    names = (box_1_name, box_2_name)
    assert events == [
        ("ensure", names),
        (
            "acquire",
            (
                list(names),
                {
                    "occupy": 1,
                    "strict": True,
                    "lease_duration": 600,
                    "raise_on_lease_renewal_failure": True,
                },
            ),
        ),
        ("body", None),
        ("release", list(names)),
    ]


def test_ensure_limits_creates_missing_limit(monkeypatch) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    client.read_global_concurrency_limit_by_name.side_effect = FakeObjectNotFound()
    monkeypatch.setattr(configuration_lock, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(configuration_lock, "ObjectNotFound", FakeObjectNotFound)
    monkeypatch.setattr(
        configuration_lock,
        "GlobalConcurrencyLimitCreate",
        SimpleNamespace,
    )

    configuration_lock._ensure_limits(("limit-1",))

    created = client.create_global_concurrency_limit.call_args.args[0]
    assert created.name == "limit-1"
    assert created.limit == 1
    assert created.active is True
    assert created.slot_decay_per_second == 0.0
    client.update_global_concurrency_limit.assert_not_called()


def test_ensure_limits_handles_concurrent_creation(monkeypatch) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    existing = SimpleNamespace(limit=1, active=True, slot_decay_per_second=0.0)
    client.read_global_concurrency_limit_by_name.side_effect = [
        FakeObjectNotFound(),
        existing,
    ]
    client.create_global_concurrency_limit.side_effect = FakeObjectAlreadyExists()
    monkeypatch.setattr(configuration_lock, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(configuration_lock, "ObjectNotFound", FakeObjectNotFound)
    monkeypatch.setattr(configuration_lock, "ObjectAlreadyExists", FakeObjectAlreadyExists)
    monkeypatch.setattr(
        configuration_lock,
        "GlobalConcurrencyLimitCreate",
        SimpleNamespace,
    )

    configuration_lock._ensure_limits(("limit-1",))

    assert client.read_global_concurrency_limit_by_name.call_count == 2
    client.update_global_concurrency_limit.assert_not_called()


def test_ensure_limits_repairs_non_mutex_limit(monkeypatch) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    client.read_global_concurrency_limit_by_name.return_value = SimpleNamespace(
        limit=4,
        active=False,
        slot_decay_per_second=2.0,
    )
    monkeypatch.setattr(configuration_lock, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(
        configuration_lock,
        "GlobalConcurrencyLimitUpdate",
        SimpleNamespace,
    )

    configuration_lock._ensure_limits(("limit-1",))

    name, update = client.update_global_concurrency_limit.call_args.args
    assert name == "limit-1"
    assert update.limit == 1
    assert update.active is True
    assert update.slot_decay_per_second == 0.0


def test_ensure_limits_disables_slot_decay(monkeypatch) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    client.read_global_concurrency_limit_by_name.return_value = SimpleNamespace(
        limit=1,
        active=True,
        slot_decay_per_second=2.0,
    )
    monkeypatch.setattr(configuration_lock, "get_client", lambda **kwargs: client)
    monkeypatch.setattr(
        configuration_lock,
        "GlobalConcurrencyLimitUpdate",
        SimpleNamespace,
    )

    configuration_lock._ensure_limits(("limit-1",))

    _, update = client.update_global_concurrency_limit.call_args.args
    assert update.slot_decay_per_second == 0.0
