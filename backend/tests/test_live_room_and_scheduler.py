"""B4/B5 regression tests: live-room cross-worker fan-out and scheduler leadership.

The production bug (B5): ``LiveRoomManager._redis`` was always ``None`` and the
APScheduler started its jobs in every worker, so with 8–60 workers a teacher and
student connected to different workers could never see each other's chat and
every scheduled class auto-started N times. These tests pin the fixes:

* two managers sharing one Redis (fakeredis backed by a shared server — the
  same wire semantics as a real Redis for pub/sub + keys) see each other's
  broadcasts, direct sends and presence;
* the scheduler leader lease elects exactly one owner and hands over cleanly.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import fakeredis
import pytest
import pytest_asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.services import scheduler_service
from app.services.online_class_service import LiveRoomManager


class FakeWebSocket:
    """Minimal async stand-in for a FastAPI WebSocket (records sent frames)."""

    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


@pytest_asyncio.fixture
async def redis_pair():
    """Two clients backed by one shared Redis server (= two workers)."""
    server = fakeredis.FakeServer()
    client_a = fakeredis.FakeAsyncRedis(server=server)
    client_b = fakeredis.FakeAsyncRedis(server=server)
    return client_a, client_b


@pytest_asyncio.fixture
async def manager_pair(redis_pair):
    client_a, client_b = redis_pair
    manager_a = LiveRoomManager(redis_factory=lambda: client_a)
    manager_b = LiveRoomManager(redis_factory=lambda: client_b)
    await manager_a.start()
    await manager_b.start()
    try:
        yield manager_a, manager_b
    finally:
        await manager_a.stop()
        await manager_b.stop()


# ── Cross-worker fan-out (B5) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_reaches_sockets_on_other_workers(manager_pair):
    manager_a, manager_b = manager_pair
    class_id, teacher = uuid.uuid4(), uuid.uuid4()
    local_ws, remote_ws = FakeWebSocket(), FakeWebSocket()

    await manager_a.register(class_id, teacher, local_ws, "Teacher", "teacher")
    remote_student = uuid.uuid4()
    await manager_b.register(class_id, remote_student, remote_ws, "Student", "student")

    await manager_a.broadcast(class_id, {"type": "chat", "body": "hello across workers"})

    await asyncio.sleep(0.05)  # pub/sub delivery is asynchronous by design
    assert {"type": "chat", "body": "hello across workers"} in local_ws.frames
    assert {"type": "chat", "body": "hello across workers"} in remote_ws.frames


@pytest.mark.asyncio
async def test_send_to_routes_to_peer_on_other_worker(manager_pair):
    manager_a, manager_b = manager_pair
    class_id = uuid.uuid4()
    teacher = uuid.uuid4()
    ws_teacher = FakeWebSocket()
    await manager_a.register(class_id, teacher, ws_teacher, "Teacher", "teacher")

    # Signalling originates on worker B for a peer owned by worker A.
    await manager_b.send_to(class_id, teacher, {"type": "signal", "data": {"sdp": "offer"}})

    await asyncio.sleep(0.05)
    assert {"type": "signal", "data": {"sdp": "offer"}} in ws_teacher.frames


@pytest.mark.asyncio
async def test_broadcast_exclude_honoured_across_workers(manager_pair):
    manager_a, manager_b = manager_pair
    class_id = uuid.uuid4()
    teacher, student = uuid.uuid4(), uuid.uuid4()
    ws_teacher, ws_student = FakeWebSocket(), FakeWebSocket()
    await manager_a.register(class_id, teacher, ws_teacher, "Teacher", "teacher")
    await manager_b.register(class_id, student, ws_student, "Student", "student")

    # Exclude the sender (on worker A) from a broadcast issued there.
    await manager_a.broadcast(class_id, {"type": "stroke"}, exclude=teacher)

    await asyncio.sleep(0.05)
    assert ws_teacher.frames == []
    assert {"type": "stroke"} in ws_student.frames


# ── Cluster-wide presence (B5) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_online_peers_and_active_count_are_cluster_wide(manager_pair):
    manager_a, manager_b = manager_pair
    class_id = uuid.uuid4()
    teacher, student = uuid.uuid4(), uuid.uuid4()
    await manager_a.register(class_id, teacher, FakeWebSocket(), "Teacher", "teacher")
    await manager_b.register(class_id, student, FakeWebSocket(), "Student", "student")

    peers_on_b = await manager_b.online_peers(class_id)
    assert {p["name"] for p in peers_on_b} == {"Teacher", "Student"}

    # Self-exclusion still works with the cluster roster.
    peers_without_student = await manager_b.online_peers(class_id, exclude=student)
    assert {p["name"] for p in peers_without_student} == {"Teacher"}

    assert await manager_a.active_count(class_id) == 2


@pytest.mark.asyncio
async def test_unregister_removes_presence_and_roster(manager_pair):
    manager_a, manager_b = manager_pair
    class_id = uuid.uuid4()
    teacher, student = uuid.uuid4(), uuid.uuid4()
    await manager_a.register(class_id, teacher, FakeWebSocket(), "Teacher", "teacher")
    await manager_b.register(class_id, student, FakeWebSocket(), "Student", "student")

    await manager_b.unregister(class_id, student)
    await asyncio.sleep(0.05)

    peers = await manager_a.online_peers(class_id)
    assert [p["name"] for p in peers] == ["Teacher"]
    assert await manager_a.active_count(class_id) == 1


@pytest.mark.asyncio
async def test_presence_of_dead_worker_is_swept(manager_pair, redis_pair):
    _, client_b = redis_pair
    manager_a, manager_b = manager_pair
    class_id = uuid.uuid4()
    student = uuid.uuid4()
    await manager_b.register(class_id, student, FakeWebSocket(), "Student", "student")

    # Simulate worker B crashing: its heartbeat key expires without renewal.
    worker_id = manager_b._worker_id
    await client_b.delete(f"live:worker:{worker_id}")

    peers = await manager_a.online_peers(class_id)
    assert peers == []
    assert await manager_a.active_count(class_id) == 0


@pytest.mark.asyncio
async def test_reconnect_on_other_worker_keeps_presence(manager_pair):
    """A peer that moved to another worker is not wiped by the old one."""
    manager_a, manager_b = manager_pair
    class_id, student = uuid.uuid4(), uuid.uuid4()
    await manager_a.register(class_id, student, FakeWebSocket(), "Student", "student")
    # Re-register on worker B (new socket), then the OLD worker A unregisters.
    await manager_b.register(class_id, student, FakeWebSocket(), "Student", "student")
    await manager_a.unregister(class_id, student)
    await asyncio.sleep(0.05)

    peers = await manager_b.online_peers(class_id)
    assert [p["name"] for p in peers] == ["Student"]


@pytest.mark.asyncio
async def test_oversized_envelope_is_dropped_not_published(manager_pair):
    manager_a, manager_b = manager_pair
    class_id = uuid.uuid4()
    teacher, student = uuid.uuid4(), uuid.uuid4()
    ws_teacher, ws_student = FakeWebSocket(), FakeWebSocket()
    await manager_a.register(class_id, teacher, ws_teacher, "Teacher", "teacher")
    await manager_b.register(class_id, student, ws_student, "Student", "student")

    await manager_a.broadcast(class_id, {"type": "blob", "data": "x" * (LiveRoomManager._MAX_ENVELOPE_BYTES + 1)})

    await asyncio.sleep(0.05)
    # Local delivery of an oversized frame is allowed, but it must not be
    # relayed: the signalling channel stays usable for everyone else.
    assert ws_student.frames == []


# ── Degraded mode (Redis down) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_outage_degrades_to_single_worker_mode():
    def broken_factory():
        raise ConnectionError("redis is down")

    manager = LiveRoomManager(redis_factory=broken_factory)
    await manager.start()  # must not raise — falls back to local-only mode

    class_id, teacher, student = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ws_teacher, ws_student = FakeWebSocket(), FakeWebSocket()
    await manager.register(class_id, teacher, ws_teacher, "Teacher", "teacher")
    await manager.register(class_id, student, ws_student, "Student", "student")

    await manager.broadcast(class_id, {"type": "chat", "body": "still works locally"})
    assert {"type": "chat", "body": "still works locally"} in ws_teacher.frames
    assert {"type": "chat", "body": "still works locally"} in ws_student.frames

    # Roster falls back to the local view instead of erroring.
    assert len(await manager.online_peers(class_id)) == 2
    await manager.stop()


@pytest.mark.asyncio
async def test_local_only_manager_without_factory_never_touches_redis():
    manager = LiveRoomManager()  # e.g. constructed in tests / local-only mode
    await manager.start()
    await manager.stop()


# ── Scheduler leader election (B5) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_leader_lock_elects_single_owner_and_hands_over(redis_pair):
    from app.services.scheduler_service import _LeaderLock

    client_a, client_b = redis_pair
    lock_a, lock_b = _LeaderLock(client_a), _LeaderLock(client_b)

    assert await lock_a.acquire_or_renew() is True  # first worker wins
    assert await lock_b.acquire_or_renew() is False  # second worker defers
    assert await lock_a.acquire_or_renew() is True  # incumbent renews

    await lock_a.release()  # graceful shutdown → instant failover
    assert await lock_b.acquire_or_renew() is True

    await lock_b.release()


@pytest.mark.asyncio
async def test_leader_heartbeat_toggles_jobs_with_leadership(monkeypatch):
    server = fakeredis.FakeServer()
    client = fakeredis.FakeAsyncRedis(server=server)
    rival = fakeredis.FakeAsyncRedis(server=server)
    lock = scheduler_service._LeaderLock(client)
    monkeypatch.setattr(scheduler_service, "_leader_lock", lock)
    # Use a THROWAWAY scheduler bound to this test's event loop — touching
    # the module-global one would poison later tests on fresh loops.
    local_scheduler = AsyncIOScheduler()
    monkeypatch.setattr(scheduler_service, "scheduler", local_scheduler)
    monkeypatch.setattr(scheduler_service, "_job_ids", set())
    local_scheduler.start()
    try:
        await scheduler_service._leader_heartbeat()
        assert scheduler_service._job_ids == {
            "online_class_auto_start",
            "online_class_reminders",
            "push_deliveries",
        }
        for job_id in scheduler_service._job_ids:
            assert local_scheduler.get_job(job_id) is not None

        # Leadership loss = the lease expired and a rival now owns the key
        # (a rival could never steal it with NX while we hold it — that is
        # the lock doing its job).
        await rival.set(scheduler_service._LEADER_KEY, "someone-else")
        await scheduler_service._leader_heartbeat()
        assert scheduler_service._job_ids == set()
        for job_id in ("online_class_auto_start", "online_class_reminders", "push_deliveries"):
            assert local_scheduler.get_job(job_id) is None
    finally:
        local_scheduler.shutdown(wait=False)
        await lock.release()


@pytest.mark.asyncio
async def test_start_scheduler_disabled_adds_no_jobs(monkeypatch):
    local_scheduler = AsyncIOScheduler()
    monkeypatch.setattr(scheduler_service, "scheduler", local_scheduler)
    monkeypatch.setattr(scheduler_service, "_leader_lock", None)
    monkeypatch.setattr(scheduler_service, "_job_ids", set())
    settings = get_settings()
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    await scheduler_service.start_scheduler()
    assert not local_scheduler.running
    assert scheduler_service._job_ids == set()
