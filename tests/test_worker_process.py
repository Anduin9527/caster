"""Actual API + worker processes, real RabbitMQ, simulated ComfyUI HTTP service.

Opt-in: AIGC_TEST_AMQP_URL and optionally AIGC_TEST_RABBITMQ_CONTAINER.
Only the explicitly named disposable test broker is stopped/restarted.
"""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

AMQP_URL = os.environ.get("AIGC_TEST_AMQP_URL")
BROKER_CONTAINER = os.environ.get("AIGC_TEST_RABBITMQ_CONTAINER")
pytestmark = pytest.mark.skipif(not AMQP_URL, reason="isolated RabbitMQ not configured")
ROOT = Path(__file__).resolve().parents[1]


def eventually(check, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (httpx.TransportError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for process state")


def test_process_restart_uncertainty_and_broker_outage(tmp_path):
    processes = []
    logs = []
    queue_name = "caster.process." + uuid.uuid4().hex
    env = {
        **os.environ,
        "AIGC_CONFIG_FILE": str(tmp_path / "absent.env"),
        "AIGC_DATA_DIR": str(tmp_path / "data"),
        "AIGC_EXECUTION_MODE": "rabbitmq",
        "AIGC_RABBITMQ_URL": AMQP_URL,
        "AIGC_RABBITMQ_QUEUE": queue_name,
        "AIGC_GPU_LOCK": str(tmp_path / "gpu.lock"),
    }

    def spawn(args):
        log = (tmp_path / ("process-" + str(len(logs)) + ".log")).open("w+")
        logs.append(log)
        process = subprocess.Popen(
            [sys.executable, *args], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        processes.append(process)
        return process

    def serve(app, app_dir):
        # Reserve a loopback port while constructing the subprocess command.
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        spawn(
            ["-m", "uvicorn", app, "--app-dir", app_dir, "--host", "127.0.0.1", "--port", str(port)]
        )
        return "http://127.0.0.1:" + str(port)

    broker_stopped = False
    try:
        mock = serve("mock_comfy_app:app", "tests")
        env["AIGC_COMFY_URL"] = mock
        api = serve("aigc.api:app", ".")
        with httpx.Client(timeout=5) as client:
            eventually(lambda: client.get(mock + "/mock/status").status_code == 200)
            eventually(lambda: client.get(api + "/api/v1/health").status_code == 200)
            assert not client.get(api + "/api/v1/health").json()["worker_alive"]
            worker = spawn(["-m", "aigc.worker_main"])

            def create(key):
                spec = client.post(
                    api + "/api/v1/scene-specs", json={"manual": {"asset_type": "background"}}
                )
                assert spec.status_code == 201, spec.text
                response = client.post(
                    api + "/api/v1/jobs",
                    json={"scene_spec_id": spec.json()["id"], "idempotency_key": key},
                )
                assert response.status_code == 201, response.text
                job_id = response.json()["id"]
                assert read(job_id)["delivery"]["request_id"] == response.headers["x-request-id"]
                return job_id

            def read(job_id):
                response = client.get(api + "/api/v1/jobs/" + job_id)
                assert response.status_code == 200, response.text
                return response.json()

            def wait_state(job_id, state):
                return eventually(lambda: read(job_id)["state"] == state)

            first = create("normal")
            wait_state(first, "running")
            with client.stream("GET", api + "/api/v1/jobs/events") as stream:
                assert stream.status_code == 200
                assert stream.headers["content-type"].startswith("text/event-stream")
                cursor = next(line[4:] for line in stream.iter_lines() if line.startswith("id: "))
            with client.stream(
                "GET", api + "/api/v1/jobs/events", headers={"Last-Event-ID": cursor}
            ) as stream:
                resumed = next(line[4:] for line in stream.iter_lines() if line.startswith("id: "))
                assert int(resumed.split(":")[1]) > int(cursor.split(":")[1])
            # Kill after durable ACK while ComfyUI is still running.
            assert read(first)["delivery"]["received"]
            if BROKER_CONTAINER:
                # The GPU is still busy, but no AMQP message is held unacked.
                observed = subprocess.run(
                    [
                        "docker",
                        "exec",
                        BROKER_CONTAINER,
                        "rabbitmqctl",
                        "list_queues",
                        "-q",
                        "--formatter",
                        "json",
                        "name",
                        "messages_unacknowledged",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                queue_state = next(
                    q for q in json.loads(observed.stdout) if q["name"] == queue_name
                )
                assert queue_state["messages_unacknowledged"] == 0
            worker.kill()
            worker.wait(timeout=10)
            second = create("queued-during-restart")
            worker = spawn(["-m", "aigc.worker_main"])
            time.sleep(3)
            assert read(first)["state"] == "running"
            assert read(second)["state"] == "queued"
            assert len(client.get(mock + "/mock/status").json()["prompts"]) == 1
            client.post(mock + "/mock/control", json={"complete": ["mock-1"]}).raise_for_status()
            wait_state(first, "succeeded")
            wait_state(second, "running")
            client.post(mock + "/mock/control", json={"complete": ["mock-2"]}).raise_for_status()
            wait_state(second, "succeeded")

            client.post(mock + "/mock/control", json={"fault": "uncertain"}).raise_for_status()
            uncertain = create("uncertain")
            wait_state(uncertain, "submission_uncertain")
            blocked = create("behind-uncertain")
            time.sleep(3)
            assert read(blocked)["state"] == "queued"
            assert (
                client.post(
                    api + "/api/v1/jobs/" + uncertain + "/retry", json={"generation": 0}
                ).status_code
                == 409
            )
            client.post(mock + "/mock/control", json={"fault": ""}).raise_for_status()
            wait_state(uncertain, "running")
            client.post(mock + "/mock/control", json={"complete": ["mock-3"]}).raise_for_status()
            wait_state(uncertain, "succeeded")
            wait_state(blocked, "running")
            client.post(mock + "/mock/control", json={"complete": ["mock-4"]}).raise_for_status()
            wait_state(blocked, "succeeded")
            assert client.get(mock + "/mock/status").json()["maximum_running"] == 1

            if BROKER_CONTAINER:
                assert BROKER_CONTAINER.startswith("caster-queue-")
                subprocess.run(
                    ["docker", "stop", "--time", "10", BROKER_CONTAINER],
                    check=True,
                    capture_output=True,
                )
                broker_stopped = True
                eventually(
                    lambda: not client.get(api + "/api/v1/health").json()["broker_connected"]
                )
                offline = create("broker-offline")
                time.sleep(2)
                assert read(offline)["state"] == "queued"
                assert not read(offline)["delivery"]["received"]
                assert client.get(api + "/api/v1/health").json()["outbox_pending"] >= 1
                subprocess.run(
                    ["docker", "start", BROKER_CONTAINER], check=True, capture_output=True
                )
                broker_stopped = False
                wait_state(offline, "running")
                client.post(
                    mock + "/mock/control", json={"complete": ["mock-5"]}
                ).raise_for_status()
                wait_state(offline, "succeeded")
    finally:
        if broker_stopped:
            subprocess.run(["docker", "start", BROKER_CONTAINER], check=True, capture_output=True)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()
