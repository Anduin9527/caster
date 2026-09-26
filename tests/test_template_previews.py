import asyncio
from io import BytesIO

import httpx
from fastapi import FastAPI
from PIL import Image

from aigc.store import Store
from aigc.template_api import template_router
from aigc.template_previews import cache_path, fetch_preview, source_url
from aigc.templates import HUB_REPO, HUB_REVISION


def test_download_resume_and_local_image_route(tmp_path):
    store = Store(tmp_path)
    t = store.put(
        "prompt_template",
        {
            "kind": "character",
            "source": HUB_REPO,
            "source_revision": HUB_REVISION,
            "source_key": "yamazaki sousuke||free!",
        },
        "hero",
    )
    assert (
        source_url(t)
        == "https://blobs.animadex.net/Outputs/thumbs/yamazaki%20sousuke%2C%20free!.webp"
    )
    assert source_url(dict(t, source="user")) is None
    calls = []
    output = BytesIO()
    Image.new("RGB", (600, 900), "blue").save(output, format="PNG")

    def serve(request):
        calls.append(request.url)
        return httpx.Response(200, content=output.getvalue(), headers={"content-type": "image/png"})

    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        assert fetch_preview(store, t, client)["status"] == "downloaded"
        assert fetch_preview(store, t, client)["status"] == "cached"
    assert len(calls) == 1
    path = cache_path(store, t)
    assert Image.open(path).size == (256, 384)
    app = FastAPI()
    app.include_router(template_router(lambda: store))

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/prompt-templates/hero/image")
            assert r.status_code == 200 and r.content == path.read_bytes()
            assert (
                await client.get(
                    "/prompt-templates/hero/image", headers={"If-None-Match": r.headers["etag"]}
                )
            ).status_code == 304
            assert (await client.get("/prompt-templates/missing/image")).headers[
                "cache-control"
            ] == "no-store"

    asyncio.run(check())
    assert store.list("approval") == [] and store.jobs() == []


def test_invalid_upstream_does_not_poison_cache(tmp_path):
    store = Store(tmp_path)
    t = {
        "id": "a",
        "kind": "character",
        "source": HUB_REPO,
        "source_revision": HUB_REVISION,
        "source_key": "a||b",
    }
    import pytest

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"html", headers={"content-type": "text/html"})
        )
    ) as client:
        with pytest.raises(ValueError, match="non-image"):
            fetch_preview(store, t, client)
    assert not cache_path(store, t).exists()


def test_generated_preview_is_local_revision_bound_and_never_downloaded(tmp_path):
    import hashlib

    store = Store(tmp_path)
    template = store.put(
        "prompt_template",
        {
            "kind": "outfit",
            "source": "caster://curated-outfits-v1",
            "source_revision": "v1",
        },
        "curated",
    )
    assert cache_path(store, template) is None
    blob = BytesIO()
    Image.new("RGB", (32, 48), "gray").save(blob, format="WEBP")
    digest = hashlib.sha256(blob.getvalue()).hexdigest()
    record = {"template_revision": "v1", "sha256": digest}
    store.put("template_preview", record, "curated")
    path = cache_path(store, template)
    path.parent.mkdir(parents=True)
    path.write_bytes(blob.getvalue())
    app = FastAPI()
    app.include_router(template_router(lambda: store))

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/prompt-templates/curated/image")
            assert response.status_code == 200 and response.content == blob.getvalue()
            assert (
                await client.get(
                    "/prompt-templates/curated/image",
                    headers={
                        "If-None-Match": response.headers["etag"],
                    },
                )
            ).status_code == 304
            store.put(
                "prompt_template", dict(template, source_revision="v2"), "curated", replace=True
            )
            assert (await client.get("/prompt-templates/curated/image")).status_code == 404

    asyncio.run(check())
    assert cache_path(store, dict(template, source="user")) is None
    store.put("template_preview", dict(record, sha256="../../elsewhere"), "curated", replace=True)
    assert cache_path(store, template) is None
    store.put("template_preview", record, "curated", replace=True)
    path.unlink()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: (_ for _ in ()).throw(
                AssertionError("Generated previews must not make network requests")
            )
        )
    ) as client:
        assert fetch_preview(store, template, client)["status"] == "unsupported"
