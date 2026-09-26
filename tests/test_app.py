"""Application lifecycle, dependency isolation and startup recovery contracts."""

import asyncio
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from aigc import api
from aigc.agent.sessions import Conversation
from aigc.store import Store
from aigc.worker import Worker


class OfflineComfy:
    closed = False

    async def close(self):
        self.closed = True

    async def queue(self):
        raise AssertionError("an empty app must not contact ComfyUI")


def test_import_and_openapi_do_not_open_runtime_resources(tmp_path):
    root = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from aigc.api import app; app.openapi(); "
            "assert app.state.store is None; assert app.state.comfy is None; assert app.state.agent is None",
        ],
        env={**os.environ, "AIGC_DATA_DIR": str(root)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not root.exists()


def test_apps_keep_records_and_saved_connections_in_their_own_data_roots(tmp_path):
    first = api.create_app(store=Store(tmp_path / "first"))
    second = api.create_app(store=Store(tmp_path / "second"))
    with TestClient(first) as left, TestClient(second) as right:
        assert (
            left.post(
                "/characters", json={"id": "hero", "name": "Hero", "fixed_tags": []}
            ).status_code
            == 201
        )
        saved = left.put(
            "/agent/settings",
            json={
                "base_url": "https://example.invalid/v1",
                "model": "offline",
                "api_key": "sk-isolated-test",
                "remember": True,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["has_api_key"] is True
        assert right.get("/characters").json() == []
        assert right.get("/agent/settings").json()["has_api_key"] is False


def test_lifespan_recovers_runs_and_closes_background_resources(tmp_path):
    store = Store(tmp_path)
    conversations = Conversation(store)
    conversation = conversations.create(None)
    conversations.start_run(conversation["id"], "message", run_id="interrupted-run")
    comfy = OfflineComfy()
    app = api.create_app(store=store, comfy=comfy)
    with TestClient(app) as client:
        assert client.get("/health").json()["worker_alive"] is True
        assert conversations.get_run("interrupted-run")["status"] == "interrupted"
        tasks = [app.state.worker, app.state.template_sync_task]
    assert all(task.done() for task in tasks)
    assert comfy.closed is True
    assert app.state.comfy is None
    assert app.state.template_sync is None
    Worker(store, OfflineComfy()).close()  # the lock can be reacquired immediately


@pytest.mark.parametrize("during_startup", [False, True])
def test_exceptional_lifespan_releases_the_client_and_worker_lock(
    tmp_path, monkeypatch, during_startup
):
    store = Store(tmp_path)
    comfy = OfflineComfy()
    app = api.create_app(store=store, comfy=comfy)

    def broken_writer(_config):
        raise RuntimeError("startup interrupted")

    if during_startup:
        monkeypatch.setattr(api, "build_writer", broken_writer)

    async def scenario():
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)
            raise RuntimeError("lifespan interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        asyncio.run(scenario())
    assert comfy.closed
    Worker(store, OfflineComfy()).close()
