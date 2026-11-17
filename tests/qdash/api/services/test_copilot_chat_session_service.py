"""Persisted chat sessions: steers and answers across a save and a reload, and branches."""

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi import HTTPException

from qdash.api.schemas.copilot_chat_session import (
    CopilotChatMessageSchema,
    CreateCopilotChatBranchRequest,
    CreateCopilotChatSessionRequest,
    UpdateCopilotChatSessionRequest,
)
from qdash.api.services.copilot_chat_session_service import (
    BranchRefusedError,
    ChatUnavailableError,
    CopilotChatSessionService,
    ForkedBranch,
    ForkSettledError,
    RuntimeTarget,
    StopOutcome,
    _to_doc_message,
    _to_schema_message,
    resolve_runtime_target,
    store_generation,
)
from qdash.common.utils.datetime import now
from qdash.dbmodel.copilot_chat_session import CopilotChatSessionDocument


def test_a_steer_message_round_trips_with_its_placement() -> None:
    sent = CopilotChatMessageSchema.model_validate(
        {
            "role": "user",
            "content": "Use Q5",
            "steer": {"request_id": "r1", "entry_id": "12", "placement": "approximate"},
        }
    )
    loaded = _to_schema_message(_to_doc_message(sent))
    assert loaded.steer is not None
    assert loaded.steer.model_dump() == {
        "request_id": "r1",
        "entry_id": "12",
        "placement": "approximate",
    }
    plain = _to_schema_message(_to_doc_message(CopilotChatMessageSchema(role="user", content="Hi")))
    assert plain.steer is None


# ---------------------------------------------------------------------------
# Branches: the store mapping, branch creation, and store cleanup
# ---------------------------------------------------------------------------


def test_an_answer_keeps_its_runtime_entry_id() -> None:
    sent = CopilotChatMessageSchema(role="assistant", content="{}", entry_id="42")
    assert _to_schema_message(_to_doc_message(sent)).entry_id == "42"
    with pytest.raises(ValueError):
        CopilotChatMessageSchema(role="assistant", content="{}", entry_id="not-an-id")


def _messages() -> list[dict[str, object]]:
    return [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1", "entry_id": "5"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2 (saved before entry IDs)"},
        {"role": "user", "content": "Q3"},
        {"role": "assistant", "content": "A3", "entry_id": "9"},
    ]


def _source(service: CopilotChatSessionService, session_id: str = "s1", username: str = "alice"):
    return service.create_session(
        username=username,
        request=CreateCopilotChatSessionRequest.model_validate(
            {"session_id": session_id, "title": "Calibrate", "messages": _messages()}
        ),
    )


class FakeRuntime:
    """The runtime's fork, idempotent by target as the real one is, and its store removal."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, str, str]] = []
        self.branches: dict[str, str] = {}
        self.refuse: BranchRefusedError | None = None
        # Raised after the fork was made, as a lost answer or a failed save would leave it.
        self.fail_after_fork: Exception | None = None
        self.release_ok = True
        self.release_calls: list[tuple[str, list[tuple[str, RuntimeTarget]]]] = []
        # The generation each removal named, in call order.
        self.release_generations: list[str] = []
        self.released: list[str] = []
        self.stopped: list[tuple[str, RuntimeTarget]] = []
        self.stop_outcome: StopOutcome = "not_running"

    async def fork(
        self, store: str, source: str | None, entry_id: str, target: str
    ) -> ForkedBranch:
        self.calls.append((store, source, entry_id, target))
        if self.refuse is not None:
            raise self.refuse
        created = target not in self.branches
        self.branches.setdefault(target, str(100 + len(self.branches)))
        if self.fail_after_fork is not None:
            raise self.fail_after_fork
        return ForkedBranch(self.branches[target], created)

    async def release(
        self, store: str, generation: str, chats: list[tuple[str, RuntimeTarget]]
    ) -> bool:
        # Every stop a removal makes names the generation it removes.
        assert all(target.generation == generation for _, target in chats)
        self.release_generations.append(generation)
        self.release_calls.append((store, [(s, replace(t, generation=None)) for s, t in chats]))
        if self.release_ok:
            self.released.append(store)
        return self.release_ok

    async def stop(self, session_id: str, target: RuntimeTarget) -> StopOutcome:
        assert target.generation == store_generation("alice", target.store_session_id)
        self.stopped.append((session_id, replace(target, generation=None)))
        return self.stop_outcome


def _target_of(username: str, session_id: str) -> RuntimeTarget:
    """Where the chat lives, without its store's generation, which every chat's target names."""
    target = resolve_runtime_target(username, session_id)
    assert target.generation == store_generation(username, target.store_session_id)
    return replace(target, generation=None)


def _branch(service, runtime, entry_id="5", target="b1", source="s1", username="alice"):
    return asyncio.run(_branch_async(service, runtime, entry_id, target, source, username))


async def _branch_async(service, runtime, entry_id="5", target="b1", source="s1", username="alice"):
    return await service.branch_session(
        username=username,
        source_session_id=source,
        request=CreateCopilotChatBranchRequest(entry_id=entry_id, target_session_id=target),
        project_id="p1",
        fork=runtime.fork,
        release_store=runtime.release,
    )


def _delete(
    service: CopilotChatSessionService,
    runtime: FakeRuntime,
    session_id: str,
    username: str = "alice",
) -> bool:
    return asyncio.run(
        service.delete_session(
            username=username,
            session_id=session_id,
            stop_chat=runtime.stop,
            release_store=runtime.release,
        )
    )


def _reclaim(service, runtime, username: str = "alice") -> None:
    asyncio.run(
        service.reclaim(username=username, release_store=runtime.release, stop_chat=runtime.stop)
    )


def _expire_lease(session_id: str) -> None:
    doc = _stored(session_id)
    assert doc.branch is not None
    doc.branch.lease_expires_at = now() - timedelta(seconds=1)
    doc.save()


def _visible_ids(service, username: str = "alice") -> set[str]:
    return {s.session_id for s in service.list_sessions(username=username).sessions}


def _stored(session_id: str) -> CopilotChatSessionDocument:
    doc = CopilotChatSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc


def _status(call) -> int:
    with pytest.raises(HTTPException) as raised:
        call()
    return raised.value.status_code


def test_a_branch_copies_the_chat_through_the_answer_and_maps_to_the_source_store(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    branch = _branch(service, runtime)
    assert runtime.calls == [("s1", None, "5", "b1")]
    assert [m.content for m in branch.messages] == ["Q1", "A1"]
    assert branch.messages[-1].entry_id == "5"
    assert branch.branch is not None
    assert branch.branch.model_dump() == {"source_session_id": "s1", "source_entry_id": "5"}
    doc = _stored("b1")
    assert doc.branch is not None
    assert doc.store_session_id == "s1"
    assert doc.conversation_id == "100"
    assert doc.branch.project_id == "p1"
    assert doc.branch.status == "ready"
    # The runtime opens the branch's conversation in the source's store.
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")
    assert _target_of("alice", "s1") == RuntimeTarget("s1")
    # A branch of the branch names the branch's conversation as its source.
    _branch(service, runtime, source="b1", target="b2")
    assert runtime.calls[-1] == ("s1", "100", "5", "b2")
    # The same request again returns the same session without forking again.
    calls = len(runtime.calls)
    again = _branch(service, runtime)
    assert again.session_id == "b1"
    assert len(runtime.calls) == calls
    assert {s.session_id for s in service.list_sessions(username="alice").sessions} == {
        "s1",
        "b1",
        "b2",
    }


def test_a_branch_is_refused_for_an_answer_without_an_entry_another_owner_or_a_reused_id(
    init_db,
) -> None:
    service = CopilotChatSessionService()
    _source(service)
    _source(service, "other")
    runtime = FakeRuntime()
    # Never inferred from the message position: an answer saved without its entry ID is not offered.
    assert _status(lambda: _branch(service, runtime, entry_id="7")) == 404
    # Another user's chat is not found.
    assert _status(lambda: _branch(service, runtime, username="mallory")) == 404
    # An existing chat's ID, or the chat itself, is not a new branch.
    assert _status(lambda: _branch(service, runtime, target="other")) == 409
    assert _status(lambda: _branch(service, runtime, target="s1")) == 409
    assert runtime.calls == []
    # The same target from another answer conflicts with the branch that exists.
    _branch(service, runtime)
    assert _status(lambda: _branch(service, runtime, entry_id="9")) == 409
    assert len(runtime.calls) == 1


def test_a_branch_finishes_on_retry_after_the_runtime_forked_and_saving_failed(
    init_db, monkeypatch
) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    original = CopilotChatSessionService._finish_branch

    def fail(self, target, forked, operation_id):
        raise RuntimeError("mongo is down")

    monkeypatch.setattr(CopilotChatSessionService, "_finish_branch", fail)
    with pytest.raises(RuntimeError):
        _branch(service, runtime)
    # The runtime forked; the session waits, hidden, and keeps the store in use.
    pending = _stored("b1")
    assert pending.branch is not None
    assert pending.branch.status == "pending"
    assert [s.session_id for s in service.list_sessions(username="alice").sessions] == ["s1"]
    assert _status(lambda: service.get_session(username="alice", session_id="b1")) == 404
    with pytest.raises(ChatUnavailableError) as unavailable:
        resolve_runtime_target("alice", "b1")
    assert unavailable.value.status_code == 409
    monkeypatch.setattr(CopilotChatSessionService, "_finish_branch", original)
    finished = _branch(service, runtime)
    assert finished.session_id == "b1"
    assert runtime.calls == [("s1", None, "5", "b1")] * 2
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")


def test_a_refused_branch_leaves_nothing_behind(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    runtime.refuse = BranchRefusedError(409, "the conversation is still answering", "busy")
    assert _status(lambda: _branch(service, runtime)) == 409
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None
    # The source still uses its store, so it is kept.
    assert runtime.released == []


def test_a_source_deleted_while_branching_takes_the_pending_branch_and_the_store(
    init_db, monkeypatch
) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    begin = CopilotChatSessionService._begin_branch

    def begin_then_delete(self, **kwargs):
        target = begin(self, **kwargs)
        # The source is deleted by another request; the pending branch kept its store.
        assert asyncio.run(
            self.delete_session(
                username="alice",
                session_id="s1",
                stop_chat=runtime.stop,
                release_store=runtime.release,
            )
        )
        assert runtime.released == []
        return target

    monkeypatch.setattr(CopilotChatSessionService, "_begin_branch", begin_then_delete)
    assert _status(lambda: _branch(service, runtime)) == 404
    assert runtime.calls == []
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None
    assert runtime.released == ["s1"]


def test_the_store_goes_with_the_last_session_that_uses_it(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    # Deleting the source keeps the store: its branch uses it.
    assert _delete(service, runtime, "s1")
    assert runtime.released == []
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")
    # The deleted chat is not reopened, or recreated, under its old ID.
    with pytest.raises(ChatUnavailableError) as unavailable:
        resolve_runtime_target("alice", "s1")
    assert unavailable.value.status_code == 404
    assert (
        _status(
            lambda: service.create_session(
                username="alice",
                request=CreateCopilotChatSessionRequest(session_id="s1"),
            )
        )
        == 409
    )
    # Deleting the last one releases it.
    assert _delete(service, runtime, "b1")
    assert runtime.released == ["s1"]
    # A chat never branched is its own store, released with it.
    _source(service, "solo")
    assert _delete(service, runtime, "solo")
    assert runtime.released[-1] == "solo"
    # Another user's session never counts as a user of this one's store.
    _source(service, "s2")
    _source(service, "s2", username="bob")
    assert _delete(service, runtime, "s2")
    assert runtime.released[-1] == "s2"
    assert CopilotChatSessionDocument.find({"username": "alice"}).to_list() == []


# ---------------------------------------------------------------------------
# Failure and deletion lifecycle: leases, take-over, cleanup, and tombstones
# ---------------------------------------------------------------------------


def test_an_ambiguous_failure_keeps_the_branch_until_its_lease_ends_then_cleanup_removes_it(
    init_db,
) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    # The fork call timed out: the runtime may still be forking.
    runtime.fail_after_fork = TimeoutError("read timed out")
    with pytest.raises(TimeoutError):
        _branch(service, runtime)
    pending = _stored("b1").branch
    assert pending is not None
    assert pending.status == "pending"
    # The same request again, during the lease, is refused without reaching the runtime.
    runtime.fail_after_fork = None
    assert _status(lambda: _branch(service, runtime)) == 409
    assert len(runtime.calls) == 1
    # The cleanup leaves a branch whose request may still run.
    _reclaim(service, runtime)
    pending = _stored("b1").branch
    assert pending is not None
    assert pending.status == "pending"
    # After a reload the client branches again under a new target; the store is shared.
    again = _branch(service, runtime, target="b2")
    assert again.session_id == "b2"
    assert _visible_ids(service) == {"s1", "b2"}
    # Once the lease is over, the cleanup takes the lost branch over and removes it. The
    # runtime's fork of it stays in the store, which the source still uses.
    _expire_lease("b1")
    _reclaim(service, runtime)
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None
    assert runtime.released == []
    assert _target_of("alice", "b2") == RuntimeTarget("s1", "101")


def test_a_failure_the_runtime_answered_can_be_retried_at_once(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    # The runtime answered with an error (a storage fault, HTTP 500) or was not reached.
    runtime.fail_after_fork = ForkSettledError("Agent runtime returned HTTP 500")
    with pytest.raises(ForkSettledError):
        _branch(service, runtime)
    pending = _stored("b1").branch
    assert pending is not None
    assert pending.status == "pending"
    runtime.fail_after_fork = None
    finished = _branch(service, runtime)
    assert finished.session_id == "b1"
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")


def test_a_pending_branch_of_a_deleted_source_is_removed_with_the_store(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    runtime.fail_after_fork = TimeoutError("read timed out")
    with pytest.raises(TimeoutError):
        _branch(service, runtime)
    runtime.fail_after_fork = None
    # The source is deleted; the pending branch still counts, so the store stays.
    assert _delete(service, runtime, "s1")
    assert runtime.released == []
    assert runtime.stopped == [("s1", RuntimeTarget("s1"))]
    # The retry during the lease is refused and leaves it.
    assert _status(lambda: _branch(service, runtime)) == 409
    pending = _stored("b1").branch
    assert pending is not None
    assert pending.status == "pending"
    # After the lease the retry takes it over: the source is gone, so it removes the
    # branch and, as the store's last user, the store. It does not fork.
    _expire_lease("b1")
    assert _status(lambda: _branch(service, runtime)) == 404
    assert len(runtime.calls) == 1
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None
    assert runtime.released == ["s1"]
    # A pending branch never ends up in the deleted chats whose turns may be stopped.
    assert runtime.release_calls[-1] == ("s1", [])


def test_the_cleanup_removes_a_pending_branch_of_a_deleted_source_after_a_reload(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    runtime.fail_after_fork = TimeoutError("read timed out")
    with pytest.raises(TimeoutError):
        _branch(service, runtime)
    assert _delete(service, runtime, "s1")
    _expire_lease("b1")
    # The client lost the target; listing the chats cleans up.
    _reclaim(service, runtime)
    assert CopilotChatSessionDocument.find({"username": "alice"}).to_list() == []
    assert runtime.released == ["s1"]
    assert service.create_session(
        username="alice", request=CreateCopilotChatSessionRequest(session_id="s1")
    )


def test_a_duplicate_request_cannot_remove_the_branch_another_request_is_creating(
    init_db,
) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    forking = asyncio.Event()
    finish = asyncio.Event()
    fork = runtime.fork

    async def slow_fork(store, source, entry_id, target):
        forking.set()
        await finish.wait()
        return await fork(store, source, entry_id, target)

    async def scenario():
        first = asyncio.create_task(
            service.branch_session(
                username="alice",
                source_session_id="s1",
                request=CreateCopilotChatBranchRequest(entry_id="5", target_session_id="b1"),
                project_id="p1",
                fork=slow_fork,
                release_store=runtime.release,
            )
        )
        await forking.wait()
        # The same payload while the first request forks: refused, and the runtime is not
        # asked, even if it would refuse the fork as busy.
        runtime.refuse = BranchRefusedError(409, "busy", "busy")
        with pytest.raises(HTTPException) as duplicate:
            await _branch_async(service, runtime)
        assert duplicate.value.status_code == 409
        assert runtime.calls == []
        pending = _stored("b1").branch
        assert pending is not None
        assert pending.status == "pending"
        # The source is deleted meanwhile: the pending branch keeps the store, and a
        # duplicate still cannot take it over.
        assert await service.delete_session(
            username="alice", session_id="s1", stop_chat=runtime.stop, release_store=runtime.release
        )
        with pytest.raises(HTTPException) as orphaned:
            await _branch_async(service, runtime)
        assert orphaned.value.status_code == 409
        runtime.refuse = None
        finish.set()
        return await first

    created = asyncio.run(scenario())
    assert created.session_id == "b1"
    assert runtime.released == []
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")


def test_a_request_that_lost_its_branch_does_not_bring_it_back(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    forking = asyncio.Event()
    finish = asyncio.Event()
    fork = runtime.fork

    async def slow_fork(store, source, entry_id, target):
        forking.set()
        await finish.wait()
        return await fork(store, source, entry_id, target)

    async def scenario():
        first = asyncio.create_task(
            service.branch_session(
                username="alice",
                source_session_id="s1",
                request=CreateCopilotChatBranchRequest(entry_id="5", target_session_id="b1"),
                project_id="p1",
                fork=slow_fork,
                release_store=runtime.release,
            )
        )
        await forking.wait()
        # The request outlived its lease; the cleanup took the branch over and removed it.
        await asyncio.to_thread(_expire_lease, "b1")
        await service.reclaim(username="alice", release_store=runtime.release)
        finish.set()
        with pytest.raises(HTTPException) as lost:
            await first
        assert lost.value.status_code == 409

    asyncio.run(scenario())
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None
    # The same request again finds the runtime's fork and finishes a new session.
    assert _branch(service, runtime).session_id == "b1"
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")


def test_a_ready_branch_is_returned_again_whatever_the_source_is_now(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    # The source was edited past the answer, then deleted: the replay still returns the branch.
    service.update_session(
        username="alice",
        session_id="s1",
        request=UpdateCopilotChatSessionRequest.model_validate(
            {"messages": [{"role": "user", "content": "Edited"}]}
        ),
    )
    assert _branch(service, runtime).session_id == "b1"
    assert _delete(service, runtime, "s1")
    assert _branch(service, runtime).session_id == "b1"
    assert len(runtime.calls) == 1
    # Another user's request never returns it.
    assert _status(lambda: _branch(service, runtime, username="mallory")) == 404


def test_concurrent_last_deletions_keep_the_later_tombstone_for_retry(init_db, monkeypatch) -> None:
    from qdash.api.services import copilot_chat_session_service as module

    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    service._tombstone_session("alice", "s1")
    store_live = module._store_live

    def delete_last_after_live_check(username, store):
        live = store_live(username, store)
        assert live
        service._tombstone_session("alice", "b1")
        return live

    with monkeypatch.context() as patch:
        patch.setattr(module, "_store_live", delete_last_after_live_check)
        assert asyncio.run(service._settle_store("alice", "s1", runtime.release))

    assert _stored("b1").deleted_at is not None
    runtime.release_ok = False
    assert not asyncio.run(service._settle_store("alice", "s1", runtime.release))
    assert runtime.release_calls == [("s1", [("b1", RuntimeTarget("s1", "100"))])]
    assert _stored("b1").deleted_at is not None
    runtime.release_ok = True
    _reclaim(service, runtime)
    assert runtime.released == ["s1"]
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None


def test_a_failed_store_removal_keeps_the_deleted_chat_hidden_until_a_retry(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    # The runtime refused: the chat's turn still holds the store.
    runtime.release_ok = False
    assert _delete(service, runtime, "s1") is False
    assert runtime.stopped == [("s1", RuntimeTarget("s1"))]
    assert runtime.release_calls == [("s1", [("s1", RuntimeTarget("s1"))])]
    # Gone for the user, and not reopened or recreated under its ID, but kept for the retry.
    assert _visible_ids(service) == set()
    assert _status(lambda: service.get_session(username="alice", session_id="s1")) == 404
    with pytest.raises(ChatUnavailableError):
        resolve_runtime_target("alice", "s1")
    assert (
        _status(
            lambda: service.create_session(
                username="alice", request=CreateCopilotChatSessionRequest(session_id="s1")
            )
        )
        == 409
    )
    # Deleting it again retries the removal.
    assert _delete(service, runtime, "s1") is False
    runtime.release_ok = True
    assert _delete(service, runtime, "s1") is True
    assert runtime.released == ["s1"]
    assert _status(lambda: _delete(service, runtime, "s1")) == 404


def test_the_cleanup_retries_a_failed_store_removal(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    runtime.release_ok = False
    assert _delete(service, runtime, "s1")
    assert _delete(service, runtime, "b1") is False
    # The deleted branch's turn is the one that may be stopped, by its exact conversation.
    assert runtime.release_calls[-1] == ("s1", [("b1", RuntimeTarget("s1", "100"))])
    runtime.release_ok = True
    _reclaim(service, runtime)
    assert runtime.released == ["s1"]
    assert CopilotChatSessionDocument.find({"username": "alice"}).to_list() == []


def test_deleting_a_branch_stops_only_its_own_turn_and_keeps_its_siblings(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    _branch(service, runtime, target="b2")
    assert _delete(service, runtime, "b1")
    assert runtime.stopped == [("b1", RuntimeTarget("s1", "100"))]
    assert runtime.release_calls == []
    assert _visible_ids(service) == {"s1", "b2"}
    assert _target_of("alice", "b2") == RuntimeTarget("s1", "101")
    assert _target_of("alice", "s1") == RuntimeTarget("s1")
    # A save of a deleted chat does not bring it back.
    assert (
        _status(
            lambda: service.update_session(
                username="alice",
                session_id="b1",
                request=UpdateCopilotChatSessionRequest(title="late save"),
            )
        )
        == 404
    )
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None


def test_a_client_cannot_set_the_store_mapping_or_the_origin(init_db) -> None:
    service = CopilotChatSessionService()
    created = service.create_session(
        username="alice",
        request=CreateCopilotChatSessionRequest.model_validate(
            {
                "session_id": "s1",
                "store_session_id": "victim",
                "conversation_id": "3",
                "branch": {"source_session_id": "x", "source_entry_id": "1"},
            }
        ),
    )
    assert created.branch is None
    service.update_session(
        username="alice",
        session_id="s1",
        request=UpdateCopilotChatSessionRequest.model_validate(
            {"title": "Renamed", "store_session_id": "victim", "conversation_id": "3"}
        ),
    )
    assert _target_of("alice", "s1") == RuntimeTarget("s1")
    assert _target_of("alice", "never-saved") == RuntimeTarget("never-saved")


def test_a_deleted_chat_whose_stop_is_unconfirmed_stays_until_a_retry_confirms_it(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    # The runtime could not be told to stop the root's turn; the branch still uses the store.
    runtime.stop_outcome = "unknown"
    assert _delete(service, runtime, "s1")
    assert runtime.stopped == [("s1", RuntimeTarget("s1"))]
    assert runtime.release_calls == []
    kept = _stored("s1")
    assert kept.deleted_at is not None and kept.stop_pending
    # Hidden, and its ID is not reused, but a later delete or cleanup still finds it.
    assert _visible_ids(service) == {"b1"}
    with pytest.raises(ChatUnavailableError):
        resolve_runtime_target("alice", "s1")
    # Still unknown on the cleanup: kept, and only its own turn was asked to stop.
    _reclaim(service, runtime)
    assert runtime.stopped[-1] == ("s1", RuntimeTarget("s1"))
    assert _stored("s1").stop_pending
    # Deleting it again confirms it: then it goes, and the store stays for the branch.
    runtime.stop_outcome = "stopped"
    assert _delete(service, runtime, "s1")
    assert CopilotChatSessionDocument.find_one({"session_id": "s1"}).run() is None
    assert runtime.release_calls == []
    assert runtime.stopped.count(("b1", RuntimeTarget("s1", "100"))) == 0
    assert _target_of("alice", "b1") == RuntimeTarget("s1", "100")


def test_the_cleanup_confirms_a_stop_left_unknown(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    _branch(service, runtime)
    runtime.stop_outcome = "unknown"
    assert _delete(service, runtime, "b1")
    assert _stored("b1").stop_pending
    runtime.stop_outcome = "not_running"
    _reclaim(service, runtime)
    assert runtime.stopped == [("b1", RuntimeTarget("s1", "100"))] * 2
    assert CopilotChatSessionDocument.find_one({"session_id": "b1"}).run() is None
    assert runtime.release_calls == []


def test_a_stale_teardown_never_removes_a_store_recreated_under_the_same_id(init_db) -> None:
    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    assert _delete(service, runtime, "s1")
    assert runtime.released == ["s1"]
    # The ID is free again: a new chat under it runs its first turn before it is saved.
    assert _target_of("alice", "s1") == RuntimeTarget("s1")
    # A second teardown that read the store as unused before the first finished
    # finds nothing left to remove and never asks the runtime.
    assert asyncio.run(service._settle_store("alice", "s1", runtime.release))
    assert runtime.release_calls == [("s1", [("s1", RuntimeTarget("s1"))])]


def test_a_held_teardown_excludes_another_and_blocks_reusing_the_store_name(init_db) -> None:
    from qdash.api.services import copilot_chat_session_service as module

    service = CopilotChatSessionService()
    _source(service)
    runtime = FakeRuntime()
    runtime.release_ok = False
    assert _delete(service, runtime, "s1") is False
    calls = len(runtime.release_calls)
    assert module._acquire_teardown("alice", "s1", "other-request")
    try:
        # Another request is tearing the store down: this one leaves it to that one.
        runtime.release_ok = True
        assert asyncio.run(service._settle_store("alice", "s1", runtime.release)) is False
        assert len(runtime.release_calls) == calls
    finally:
        module._release_teardown("alice", "s1", "other-request")
    # Once released, the next request settles it.
    _reclaim(service, runtime)
    assert runtime.released == ["s1"]
    assert CopilotChatSessionDocument.find({"username": "alice"}).to_list() == []


def test_a_store_being_torn_down_cannot_be_reused_by_a_new_chat(init_db) -> None:
    from qdash.api.services import copilot_chat_session_service as module

    service = CopilotChatSessionService()
    assert module._acquire_teardown("alice", "s9", "teardown")
    try:
        with pytest.raises(ChatUnavailableError) as raised:
            resolve_runtime_target("alice", "s9")
        assert raised.value.status_code == 409
        assert (
            _status(
                lambda: service.create_session(
                    username="alice", request=CreateCopilotChatSessionRequest(session_id="s9")
                )
            )
            == 409
        )
        # Another owner's store of the same name is another store.
        assert _target_of("bob", "s9") == RuntimeTarget("s9")
    finally:
        module._release_teardown("alice", "s9", "teardown")
    assert _target_of("alice", "s9") == RuntimeTarget("s9")


def test_an_expired_teardown_is_taken_over(init_db) -> None:
    from qdash.api.services import copilot_chat_session_service as module

    assert module._acquire_teardown("alice", "s1", "crashed")
    assert not module._acquire_teardown("alice", "s1", "next")
    module._teardowns().update_one(
        {"_id": module._teardown_key("alice", "s1")},
        {"$set": {"lease_expires_at": now() - timedelta(seconds=1)}},
    )
    assert not module._teardown_held("alice", "s1")
    assert module._acquire_teardown("alice", "s1", "next")
    assert module._holds_teardown("alice", "s1", "next")
    assert not module._holds_teardown("alice", "s1", "crashed")


class GenerationRuntime:
    """The runtime's stores as store-identity.ts keeps them: each with the generation it
    was created with, removed only for that generation, its removed generations retired."""

    def __init__(self) -> None:
        self.stores: dict[str, tuple[str, str]] = {}
        self.retired: dict[str, set[str]] = {}

    def chat(self, store: str, generation: str, data: str) -> None:
        """A turn opens (and creates) the store; a retired or another generation is refused."""
        assert generation not in self.retired.get(store, set())
        current = self.stores.get(store)
        assert current is None or current[0] == generation
        self.stores[store] = (generation, data)

    def remove(self, store: str, generation: str) -> bool:
        current = self.stores.get(store)
        if current is not None and current[0] != generation:
            return True  # A newer incarnation: the one named is gone already.
        self.retired.setdefault(store, set()).add(generation)
        self.stores.pop(store, None)
        return True


def test_a_teardown_that_outlived_its_lease_never_removes_or_forgets_a_recreated_chat(
    init_db,
) -> None:
    from qdash.api.services import copilot_chat_session_service as module

    service = CopilotChatSessionService()
    runtime = FakeRuntime()
    stores = GenerationRuntime()
    _source(service)
    first = resolve_runtime_target("alice", "s1").generation
    assert first is not None
    stores.chat("s1", first, "old")

    async def scenario() -> None:
        entered = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_release(store, generation, chats) -> bool:
            # The first teardown's runtime call is delayed past its lease.
            entered.set()
            await proceed.wait()
            return stores.remove(store, generation)

        async def release(store, generation, chats) -> bool:
            return stores.remove(store, generation)

        slow = asyncio.create_task(
            service.delete_session(
                username="alice",
                session_id="s1",
                stop_chat=runtime.stop,
                release_store=slow_release,
            )
        )
        await entered.wait()
        # Its lease runs out; a retry takes the teardown over and removes the store.
        await asyncio.to_thread(
            module._teardowns().update_one,
            {"_id": module._teardown_key("alice", "s1")},
            {"$set": {"lease_expires_at": now() - timedelta(seconds=1)}},
        )
        assert await service._settle_store("alice", "s1", release)
        assert "s1" not in stores.stores
        # The chat is created again under the same ID, with a new generation, and
        # deleted, its removal failing: its tombstone waits for a retry.
        await asyncio.to_thread(
            service.create_session,
            username="alice",
            request=CreateCopilotChatSessionRequest(session_id="s1"),
        )
        second = (await asyncio.to_thread(resolve_runtime_target, "alice", "s1")).generation
        assert second is not None and second != first
        stores.chat("s1", second, "new")

        async def failing(store, generation, chats) -> bool:
            assert generation == second
            return False

        assert not await service.delete_session(
            username="alice", session_id="s1", stop_chat=runtime.stop, release_store=failing
        )
        # The first teardown's runtime call arrives only now.
        proceed.set()
        assert await slow
        # It removed nothing of the new chat, and forgot neither its tombstone nor its generation.
        assert stores.stores["s1"] == (second, "new")
        assert _stored("s1").deleted_at is not None
        assert store_generation("alice", "s1") == second
        # A retry of the new chat's removal removes the new store.
        assert await service._settle_store("alice", "s1", release)
        assert "s1" not in stores.stores
        assert stores.retired["s1"] == {first, second}

    asyncio.run(scenario())
    assert CopilotChatSessionDocument.find({"username": "alice"}).to_list() == []
