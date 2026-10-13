"""Failure contracts across approval, delivery, execution and restart."""

import asyncio
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from aigc.broker import publish_pending, receive
from aigc.delivery import Delivery, enqueue
from aigc.schema import SceneSpec
from aigc.store import Store
from aigc.worker import Worker
from aigc.workflows import digest, read_template


class FakeComfy:
    def __init__(self):
        self.submissions = []
        self.complete = False
        self.uncertain = False
        self.offline = False

    async def info(self):
        if self.offline:
            raise httpx.ConnectError("mock unavailable")
        return {n["class_type"]: {"input": {}} for n in read_template("background").values()}

    async def submit(self, graph, job_id):
        self.submissions.append((job_id, graph))
        if self.uncertain:
            raise json.JSONDecodeError("malformed success", "", 0)
        return "prompt-1"

    async def queue(self):
        return {
            "queue_running": []
            if self.complete or not self.submissions
            else [[0, "prompt-1", {}, {"aigc_job_id": self.submissions[0][0]}]],
            "queue_pending": [],
        }

    async def locate(self, job_id):
        return "prompt-1" if self.submissions and self.submissions[0][0] == job_id else None

    async def history(self, prompt_id):
        if not self.complete:
            return {}
        return {
            prompt_id: {
                "status": {"completed": True},
                "outputs": {"9": {"images": [{"filename": "mock.png", "type": "output"}]}},
            }
        }

    async def download(self, entry):
        blob = BytesIO()
        Image.new("RGB", (16, 16), "blue").save(blob, format="PNG")
        return blob.getvalue()


class Message:
    def __init__(self, job_id, generation=0):
        self.body = json.dumps({"job_id": job_id, "generation": generation}).encode()
        self.correlation_id = "mock-request"
        self.message_id = "mock-message"
        self.acked = False
        self.rejected = False

    async def ack(self):
        self.acked = True

    async def reject(self, requeue):
        assert requeue is False
        self.rejected = True


def job(store, key="one"):
    spec = store.put("scene_spec", {"spec": SceneSpec(asset_type="background").model_dump()})
    return store.create_job({"scene_spec_id": spec["id"], "idempotency_key": key, "seed": 1})


def test_job_and_outbox_roll_back_together(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO jobs(id,idempotency_key,body,state,created,updated) VALUES('rollback','rollback','{}','queued',0,0)"
            )
            enqueue(db, "rollback")
            raise RuntimeError("approval transaction aborted")
    assert store.jobs() == []
    assert Delivery(store).pending() == []


def test_publish_failure_and_lost_confirm_preserve_intent(tmp_path):
    store = Store(tmp_path)
    queued = job(store)
    ledger = Delivery(store)
    sent = []

    async def lose_confirm(entry):
        sent.append(entry["id"])
        raise ConnectionError("confirm lost after publish")

    with pytest.raises(ConnectionError):
        asyncio.run(publish_pending(ledger, lose_confirm))
    assert store.job(queued["id"])["state"] == "queued"
    with store.connect() as db:
        row = db.execute("SELECT * FROM job_outbox").fetchone()
        assert row["published"] is None and row["attempts"] == 1
        db.execute("UPDATE job_outbox SET available=0")

    async def confirm(entry):
        sent.append(entry["id"])

    asyncio.run(publish_pending(ledger, confirm))
    assert sent[0] == sent[1]
    assert not ledger.pending()


def test_duplicate_delivery_normal_completion_and_restart(tmp_path):
    store = Store(tmp_path)
    queued = job(store)
    other = job(store, "two")
    ledger = Delivery(store)
    comfy = FakeComfy()
    worker = Worker(store, comfy, mode="rabbitmq")

    async def scenario():
        for _ in range(2):
            message = Message(queued["id"])
            await receive(ledger, message)
            assert message.acked
            await worker.execute(store.job(queued["id"]))
        assert len(comfy.submissions) == 1
        # ACK happened before the long GPU task finished; receipt survives restart.
        assert store.job(queued["id"])["state"] == "running"
        worker.close()
        restarted = Worker(Store(tmp_path), comfy, mode="rabbitmq")
        try:
            await restarted.reconcile(store.job(queued["id"]))
            ledger.accept(other["id"], 0)
            await restarted.execute(other)
            assert len(comfy.submissions) == 1  # active GPU job blocks the next one
            comfy.complete = True
            await restarted.reconcile(store.job(queued["id"]))
            assert store.job(queued["id"])["state"] == "succeeded"
            assert len(store.job(queued["id"])["outputs"]) == 1
        finally:
            restarted.close()

    asyncio.run(scenario())


def test_uncertain_submit_is_not_retryable_and_reconciles(tmp_path):
    store = Store(tmp_path)
    queued = job(store)
    comfy = FakeComfy()
    comfy.uncertain = True
    worker = Worker(store, comfy)
    try:
        asyncio.run(worker.execute(queued))
        assert store.job(queued["id"])["state"] == "submission_uncertain"
        with pytest.raises(ValueError):
            Delivery(store).retry(queued["id"], 0)
        asyncio.run(worker.execute(queued))
        assert len(comfy.submissions) == 1
        asyncio.run(worker.reconcile(store.job(queued["id"])))
        assert store.job(queued["id"])["state"] == "running"
        assert len(comfy.submissions) == 1
    finally:
        worker.close()


def test_finite_safe_retry_dead_letter_and_stale_delivery(tmp_path):
    store = Store(tmp_path)
    queued = job(store)
    comfy = FakeComfy()
    comfy.offline = True
    ledger = Delivery(store)
    worker = Worker(store, comfy, mode="rabbitmq")
    ledger.accept(queued["id"], 0)
    try:
        for _ in range(3):
            with store.connect() as db:
                db.execute("UPDATE job_delivery SET available=0")
            asyncio.run(worker.execute(store.job(queued["id"])))
        assert store.job(queued["id"])["state"] == "failed"
        assert ledger.info(queued["id"])["retryable"] is True
        assert [e["kind"] for e in ledger.pending()] == ["dispatch", "dead"]
        ledger.retry(queued["id"], 0)
        ledger.retry(queued["id"], 0)  # double-click is idempotent
        ledger.accept(queued["id"], 0)  # old delivery cannot authorize a new attempt
        assert not ledger.eligible(queued["id"], "rabbitmq")
        ledger.accept(queued["id"], 1)
        comfy.offline = False
        asyncio.run(worker.execute(store.job(queued["id"])))
        assert len(comfy.submissions) == 1
    finally:
        worker.close()


def test_modes_and_gpu_lock_exclude_competing_workers(tmp_path):
    store = Store(tmp_path / "first")
    lock = tmp_path / "gpu.lock"
    worker = Worker(store, FakeComfy(), mode="rabbitmq", gpu_lock=lock)
    try:
        with pytest.raises(BlockingIOError):
            Worker(Store(tmp_path / "second"), FakeComfy(), gpu_lock=lock)
        with pytest.raises(ValueError, match="mode"):
            Delivery(store).bind_mode("local")
    finally:
        worker.close()
    Worker(Store(tmp_path / "second"), FakeComfy(), gpu_lock=lock).close()


def test_job_events_are_transactional_and_resume_by_cursor(tmp_path):
    store = Store(tmp_path)
    queued = job(store)
    ledger = Delivery(store)
    first = ledger.events_since("jobs")
    store.update_job(queued["id"], state="running")
    later = ledger.events_since("jobs", first[-1].event_id)
    assert [e.state for e in first] == ["queued"]
    assert [e.state for e in later] == ["running"]
    with pytest.raises(LookupError):
        ledger.events_since("jobs", "other:1")


def test_confirmed_workbench_snapshot_survives_template_changes(tmp_path, monkeypatch):
    store = Store(tmp_path)
    queued = job(store)
    snapshot = store.get("job_snapshot", queued["id"])
    store.put(
        "prompt_settings",
        {
            "artist_style": "changed-after-confirmation",
            "fixed_positive": "changed-after-confirmation",
            "fixed_negative": "",
        },
        "anima",
        replace=True,
    )

    def changed_template(_kind):
        raise AssertionError("Worker must use the confirmed snapshot")

    monkeypatch.setattr("aigc.workflows.read_template", changed_template)
    comfy = FakeComfy()
    worker = Worker(store, comfy)
    try:
        asyncio.run(worker.execute(queued))
        assert store.job(queued["id"])["state"] == "running"
        execution = store.get("execution", queued["id"])
        assert "changed-after-confirmation" not in execution["prompt"]["positive"]
        assert execution["template_sha256"] == digest(snapshot["graph"])
    finally:
        worker.close()


def test_retry_http_contract_and_idempotent_generation(tmp_path):
    from fastapi.testclient import TestClient

    from aigc.api import create_app

    store = Store(tmp_path)
    queued = job(store)
    ledger = Delivery(store)
    ledger.fail_before_submit(queued["id"], "offline", transient=True, max_attempts=1)
    client = TestClient(create_app(config={}, store=store))
    path = "/api/v1/jobs/" + queued["id"] + "/retry"
    first = client.post(path, json={"generation": 0})
    assert first.status_code == 200
    assert first.json()["delivery"]["generation"] == 1
    assert client.post(path, json={"generation": 0}).status_code == 200
    assert client.post(path, json={"generation": 1}).status_code == 409
    assert client.post(path, json={"generation": -1}).status_code == 422
    assert [e["kind"] for e in ledger.pending()].count("dispatch") == 2


def test_prompt_id_write_failure_keeps_submission_intent(tmp_path, monkeypatch):
    store = Store(tmp_path)
    queued = job(store)
    comfy = FakeComfy()
    worker = Worker(store, comfy)
    update = store.update_job
    failed_once = False

    def interrupted(job_id, **changes):
        nonlocal failed_once
        if changes.get("state") == "running" and not failed_once:
            failed_once = True
            raise OSError("database write interrupted after POST")
        return update(job_id, **changes)

    monkeypatch.setattr(store, "update_job", interrupted)
    try:
        asyncio.run(worker.execute(queued))
        assert store.job(queued["id"])["state"] == "submission_uncertain"
        asyncio.run(worker.reconcile(store.job(queued["id"])))
        assert store.job(queued["id"])["prompt_id"] == "prompt-1"
        assert len(comfy.submissions) == 1
    finally:
        worker.close()
