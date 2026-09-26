"""Compose the CASTER application without opening resources at import time."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .agent.engine import AgentEngine
from .agent.router import agent_router
from .agent.template_sync import TemplateSync
from .comfy import Comfy
from .config import load
from .production import production_router
from .prompt_settings import prompt_settings_router
from .rag import build_writer
from .routes.assets import assets_router
from .routes.jobs import jobs_router
from .routes.scenes import scenes_router
from .store import Store
from .template_api import template_router
from .worker import Worker


def create_app(
    config: dict[str, str] | None = None,
    *,
    store: Store | None = None,
    comfy: Comfy | None = None,
) -> FastAPI:
    """Create an isolated app; its lifespan owns background tasks and clients.

    Imports and OpenAPI generation do not create a database, open an HTTP
    client, acquire a worker lock or load an embedding model. Tests may inject
    a store and ComfyUI adapter and exercise the same routers as production.
    """
    config = dict(load() if config is None else config)
    if store is not None:
        config["AIGC_DATA_DIR"] = str(store.root)

    def get_store() -> Store:
        if app.state.store is None:
            app.state.store = Store(config["AIGC_DATA_DIR"])
        return app.state.store

    def get_comfy() -> Comfy:
        if app.state.comfy is None:
            app.state.comfy = Comfy(config["AIGC_COMFY_URL"])
        return app.state.comfy

    def get_agent() -> AgentEngine:
        if app.state.agent is None:
            app.state.agent = AgentEngine(get_store(), config)
        return app.state.agent

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = get_comfy()
        worker = None
        tasks: list[asyncio.Task] = []
        try:
            storage = get_store()
            worker = Worker(storage, client)
            # Recovery runs once, before requests or background work can race it.
            app.state.recovered_agent_runs = get_agent().recover_interrupted()
            sync = TemplateSync(storage, build_writer(config))
            app.state.template_sync = sync
            app.state.worker = asyncio.create_task(worker.run(), name="caster-worker")
            tasks.append(app.state.worker)
            app.state.template_sync_task = asyncio.create_task(
                sync.run(), name="caster-template-sync"
            )
            tasks.append(app.state.template_sync_task)
            yield
        finally:
            # Also runs on partial startup failure and exceptions during lifespan.
            try:
                if app.state.agent is not None:
                    await app.state.agent.close()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if worker is not None:
                    worker.close()
                try:
                    sync = app.state.template_sync
                    if sync is not None and sync.writer is not None:
                        sync.writer.close()
                finally:
                    await client.close()
                    app.state.comfy = None
                    app.state.agent = None
                    app.state.template_sync = None

    app = FastAPI(
        title="CASTER",
        description="Human-approved agent workflows for character asset production.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.store = store
    app.state.comfy = comfy
    app.state.worker = None
    app.state.agent = None
    app.state.template_sync = None

    @app.get("/health", tags=["System"])
    async def health():
        task = app.state.worker
        return {"status": "ok", "worker_alive": task is not None and not task.done()}

    app.include_router(scenes_router(get_store, config))
    app.include_router(assets_router(get_store))
    app.include_router(jobs_router(get_store, get_comfy))
    app.include_router(template_router(get_store))
    app.include_router(prompt_settings_router(get_store))
    app.include_router(production_router(get_store, get_comfy))
    app.include_router(agent_router(get_agent, config))
    return app


# Preserve the deployed ASGI entry point. Resources remain lazy until startup.
app = create_app()
