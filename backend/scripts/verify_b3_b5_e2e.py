"""E2E verification for the B3/B4/B5 fix round, against REAL running workers.

Spins up TWO uvicorn workers of the actual app plus an embedded Redis
(redislite), then proves the three defect fixes end to end:

* B3 — the student result endpoint returns the typed lifecycle
  (NOT_ATTEMPTED → IN_PROGRESS → UNDER_EVALUATION → AVAILABLE) with no
  score/answer leak before availability, and honours
  show_score_immediately quiz mode.
* B4 — the live-room WebSocket `welcome` frame carries the deployment's
  ICE servers, including the authenticated TURN relay configured via env.
* B5 — a teacher on worker A and a student on worker B (different
  processes!) see each other's presence, chat, hand-raise and signalling
  frames through Redis pub/sub, and exactly ONE scheduler leader exists.

Run:
  DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST/DBNAME" \
  JWT_SECRET_KEY=dev-secret PYTHONPATH=backend \
  .venv/bin/python scripts/verify_b3_b5_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("EMAIL_PROVIDER", "console")

import httpx  # noqa: E402
import websockets  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, BACKEND_DIR)

from verify_b1_b2_e2e import seed  # noqa: E402  (reuses tenant/teacher/student seeding)

from app.database import AsyncSessionLocal  # noqa: E402

API = "/api/v1"
REDIS_PORT = 6399
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/0"
PORT_A, PORT_B = 8101, 8102
TURN_URL_ENV = "turn:turn.e2e.test:3478"
RESULTS: dict[str, bool] = {}

WORKERS: list[subprocess.Popen] = []
REDIS = None


def hr(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS[name] = ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))


async def wait_healthy(client: httpx.AsyncClient, port: int, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = await client.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    return False


def assert_ports_free() -> None:
    """Fail fast instead of silently talking to a stale worker from an
    earlier aborted run (which would poison every cross-worker check)."""
    import socket
    for port in (PORT_A, PORT_B):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(
                    f"port {port} is already in use — kill the stale worker "
                    f"(ps aux | grep uvicorn) and rerun"
                )


def start_workers() -> None:
    env = os.environ.copy()
    env.update({
        "REDIS_URL": REDIS_URL,
        "TURN_URL": TURN_URL_ENV,
        "TURN_USERNAME": "e2e-turn-user",
        "TURN_CREDENTIAL": "e2e-turn-secret",
    })
    for port in (PORT_A, PORT_B):
        log = open(f"/tmp/e2e-worker-{port}.log", "w")
        WORKERS.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
        ))


async def ws_collect(ws, want_type: str, timeout: float = 8.0) -> dict | None:
    """Read frames until one matches want_type; None on timeout."""
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("type") == want_type:
                return msg
    except (asyncio.TimeoutError, TimeoutError):
        return None


async def verify_b3(client: httpx.AsyncClient, ids, teacher, student) -> str | None:
    hr("B3 — typed result lifecycle over HTTP (worker A)")
    now = datetime.now(timezone.utc)
    created = await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations", headers=teacher, json={
        "title": "B3 E2E Gated Exam", "subject_id": str(ids.subject_id), "class_id": str(ids.class_id),
        "exam_type": "MIXED", "mode": "ONLINE", "total_marks": 5, "passing_marks": 2,
        "duration_minutes": 30, "scheduled_at": (now - timedelta(minutes=2)).isoformat(),
        "window_end_at": (now + timedelta(minutes=60)).isoformat(),
        "allow_review": True, "show_score_immediately": False,
    })
    assert created.status_code == 201, created.text
    exam_id = created.json()["data"]["id"]

    q = await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations/{exam_id}/questions", headers=teacher, json={
        "text": "1 + 2 = ?", "question_type": "MCQ", "marks": 5.0,
        "options": [
            {"text": "3", "is_correct": True, "sort_order": 1},
            {"text": "4", "is_correct": False, "sort_order": 2},
        ],
    })
    assert q.status_code == 201, q.text
    correct_id = next(o["id"] for o in q.json()["data"]["options"] if o["is_correct"])
    await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations/{exam_id}/publish", headers=teacher)
    base = f"http://127.0.0.1:{PORT_A}{API}/student/examinations/{exam_id}"

    r = await client.get(f"{base}/result", headers=student)
    d = r.json()["data"]
    check("NOT_ATTEMPTED → 200 + typed state", r.status_code == 200 and d["result_state"] == "NOT_ATTEMPTED" and d["total_score"] is None, r.text[:200])

    await client.post(f"{base}/attempt", headers=student)
    r = await client.get(f"{base}/result", headers=student)
    d = r.json()["data"]
    check("IN_PROGRESS → typed state, no scores", d["result_state"] == "IN_PROGRESS" and d["answers"] == [], r.text[:200])

    await client.put(f"{base}/attempt/answers", headers=student,
                     json={"question_id": q.json()["data"]["id"], "selected_option_id": correct_id})
    await client.post(f"{base}/attempt/submit", headers=student)
    r = await client.get(f"{base}/result", headers=student)
    d = r.json()["data"]
    check("UNDER_EVALUATION → header only (allow_review must NOT bypass release)",
          r.status_code == 200 and d["result_state"] == "UNDER_EVALUATION"
          and d["total_score"] is None and d["answers"] == [] and d["submitted_at"],
          r.text[:300])

    rel = await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations/{exam_id}/release", headers=teacher)
    assert rel.status_code == 200, rel.text
    r = await client.get(f"{base}/result", headers=student)
    d = r.json()["data"]
    check("AVAILABLE → score + marks breakdown",
          d["result_state"] == "AVAILABLE" and d["total_score"] == 5.0 and len(d["answers"]) == 1
          and d["answers"][0]["correct_option_text"] == "3", r.text[:300])

    # Quiz mode: teacher opted into show_score_immediately → score right after submit.
    quiz = await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations", headers=teacher, json={
        "title": "B3 E2E Instant Quiz", "subject_id": str(ids.subject_id), "class_id": str(ids.class_id),
        "exam_type": "QUIZ", "mode": "ONLINE", "total_marks": 5, "passing_marks": 2,
        "duration_minutes": 10, "scheduled_at": (now - timedelta(minutes=1)).isoformat(),
        "window_end_at": (now + timedelta(minutes=30)).isoformat(),
        "show_score_immediately": True,
    })
    assert quiz.status_code == 201, quiz.text
    quiz_id = quiz.json()["data"]["id"]
    qq = await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations/{quiz_id}/questions", headers=teacher, json={
        "text": "2 + 2 = ?", "question_type": "MCQ", "marks": 5.0,
        "options": [{"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}],
    })
    await client.post(f"http://127.0.0.1:{PORT_A}{API}/teacher/examinations/{quiz_id}/publish", headers=teacher)
    qbase = f"http://127.0.0.1:{PORT_A}{API}/student/examinations/{quiz_id}"
    await client.post(f"{qbase}/attempt", headers=student)
    correct_quiz = next(o["id"] for o in qq.json()["data"]["options"] if o["is_correct"])
    await client.put(f"{qbase}/attempt/answers", headers=student,
                     json={"question_id": qq.json()["data"]["id"], "selected_option_id": correct_quiz})
    await client.post(f"{qbase}/attempt/submit", headers=student)
    r = await client.get(f"{qbase}/result", headers=student)
    d = r.json()["data"]
    check("show_score_immediately → AVAILABLE with score before release",
          d["result_state"] == "AVAILABLE" and d["total_score"] == 5.0, r.text[:300])
    return exam_id


async def verify_b4_b5(client: httpx.AsyncClient, ids, teacher, student) -> None:
    hr("B4 — TURN/ICE delivered on the WS welcome frame")
    now = datetime.now(timezone.utc)
    instant = await client.post(f"http://127.0.0.1:{PORT_A}{API}/online-classes/instant", headers=teacher, json={
        "class_id": str(ids.class_id), "subject_id": str(ids.subject_id),
        "topic": "B4/B5 cross-worker live room", "duration_minutes": 30,
    })
    assert instant.status_code == 201, instant.text
    class_id = instant.json()["data"]["id"]
    # Instant classes are LIVE from creation; "start" only applies to
    # scheduled ones, so a 409 here is the expected "already live".
    started = await client.post(f"http://127.0.0.1:{PORT_A}{API}/online-classes/{class_id}/start", headers=teacher)
    assert started.status_code in (200, 409), started.text
    # Students must join before the live socket accepts them (attendance gate).
    joined = await client.post(f"http://127.0.0.1:{PORT_B}{API}/online-classes/{class_id}/join", headers=student)
    assert joined.status_code == 200, joined.text
    # Waiting-room flow: the teacher (on worker A) admits the student; the
    # admit path also DMs an "admitted" frame through Redis — a bonus
    # cross-worker direct-send check before the student is even connected.
    from sqlalchemy import text as sql_text
    async with AsyncSessionLocal() as db:
        student_id = str((await db.execute(sql_text(
            "SELECT id FROM users WHERE email = :email"), {"email": ids.student_email})).scalar_one())
    admitted = await client.post(
        f"http://127.0.0.1:{PORT_A}{API}/online-classes/{class_id}/participants/{student_id}/admit",
        headers=teacher)
    assert admitted.status_code == 200, admitted.text

    teacher_token = teacher["Authorization"].split(" ", 1)[1]
    async with websockets.connect(
        f"ws://127.0.0.1:{PORT_A}{API}/online-classes/{class_id}/live?token={teacher_token}"
    ) as ws_teacher:
        welcome = json.loads(await ws_teacher.recv())
        ice = welcome.get("ice_servers") or []
        urls = [entry.get("urls") for entry in ice]
        check("welcome carries STUN fallback", "stun:stun.l.google.com:19302" in urls, str(ice))
        turn = next((e for e in ice if str(e.get("urls", "")).startswith("turn")), None)
        check("welcome carries authenticated TURN from env",
              turn is not None and turn.get("username") == "e2e-turn-user"
              and turn.get("credential") == "e2e-turn-secret", str(ice))

        hr("B5 — teacher on worker A ↔ student on worker B (real Redis pub/sub)")
        async with websockets.connect(
            f"ws://127.0.0.1:{PORT_B}{API}/online-classes/{class_id}/live?token={student['Authorization'].split(' ', 1)[1]}"
        ) as ws_student:
            swelcome = json.loads(await ws_student.recv())
            peers = {p["name"] for p in swelcome.get("peers", [])}
            check("cluster presence: student on B sees teacher on A",
                  "Ms. Feynman" in peers, str(swelcome.get("peers")))

            pj = await ws_collect(ws_teacher, "peer-joined")
            check("teacher on A sees peer-joined from B", pj is not None and pj["peer"]["name"] == "Ada L")

            await ws_teacher.send(json.dumps({"type": "chat", "body": "hello across workers"}))
            got = await ws_collect(ws_student, "chat")
            check("chat broadcast crosses processes",
                  got is not None and got["message"]["body"] == "hello across workers")

            await ws_student.send(json.dumps({"type": "hand", "raised": True}))
            got = await ws_collect(ws_teacher, "hand")
            check("hand-raise broadcast crosses processes",
                  got is not None and got["raised"] is True)

            teacher_id = welcome["you"]["id"]
            await ws_student.send(json.dumps({
                "type": "signal", "to": teacher_id, "data": {"sdp": {"type": "offer"}},
            }))
            got = await ws_collect(ws_teacher, "signal")
            check("WebRTC signalling DM routes to the peer's worker",
                  got is not None and got["data"]["sdp"]["type"] == "offer")

    hr("B5 — scheduler leader election across the two workers")
    import redis.asyncio as aioredis
    r = aioredis.from_url(REDIS_URL)
    leader = await r.get("erp:scheduler:leader")
    ttl = await r.ttl("erp:scheduler:leader")
    check("exactly one leader lease exists", leader is not None, "no erp:scheduler:leader key")
    check("leader lease has a TTL (failover works if the leader dies)", leader is not None and 0 < ttl <= 90, f"ttl={ttl}")
    await r.aclose()


async def _main_inner() -> int:
    global REDIS
    hr("Phase 0 — infrastructure (embedded Redis + two real app workers)")
    import redis.asyncio as aioredis
    try:
        probe = aioredis.from_url(REDIS_URL)
        await probe.ping()
        await probe.aclose()
        REDIS = None  # an earlier run left a server up — reuse it
        print(f"  reusing redis already listening on :{REDIS_PORT}")
    except Exception:
        import redislite
        REDIS = redislite.Redis(serverconfig={"port": str(REDIS_PORT)})
        print(f"  embedded redis started on :{REDIS_PORT}")

    async with AsyncSessionLocal() as db:
        ids = await seed(db)
        await db.commit()
    print(f"  seeded tenant {ids.slug}")

    assert_ports_free()
    start_workers()
    async with httpx.AsyncClient(timeout=15.0) as client:
        ok_a = await wait_healthy(client, PORT_A)
        ok_b = await wait_healthy(client, PORT_B)
        check("worker A healthy", ok_a, open("/tmp/e2e-worker-8101.log").read()[-500:] if not ok_a else "")
        check("worker B healthy", ok_b, open("/tmp/e2e-worker-8102.log").read()[-500:] if not ok_b else "")
        if not (ok_a and ok_b):
            return finish(1)

        teacher = await login(client, PORT_A, ids.teacher_email, ids.teacher_pw, ids.slug)
        student = await login(client, PORT_B, ids.student_email, ids.student_pw, ids.slug)
        await verify_b3(client, ids, teacher, student)
        await verify_b4_b5(client, ids, teacher, student)
    return 0 if all(RESULTS.values()) else 1


async def main() -> int:
    """Always run finish() — even a failed check must not leak worker processes."""
    code = 1
    try:
        code = await _main_inner()
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    finally:
        sys.exit(finish(code))


async def login(client: httpx.AsyncClient, port: int, identifier: str, password: str, slug: str) -> dict:
    r = await client.post(f"http://127.0.0.1:{port}{API}/tenant/auth/login",
                          json={"slug": slug, "identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


def finish(code: int) -> int:
    hr("Summary")
    for name, ok in RESULTS.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for w in WORKERS:
        if w.poll() is None:
            w.send_signal(signal.SIGTERM)
    for w in WORKERS:
        try:
            w.wait(timeout=10)
        except subprocess.TimeoutExpired:
            w.kill()
    if REDIS is not None:
        REDIS.shutdown()
    print(f"\n{'ALL CHECKS PASSED' if code == 0 else 'FAILURES PRESENT'}")
    return code


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    finally:
        pass
