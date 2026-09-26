import asyncio

import httpx
from fastapi import FastAPI

from aigc.production import production_router
from aigc.store import Store


def test_snapshot_is_read_only_scoped_and_keeps_actual_states(tmp_path):
    store = Store(tmp_path)
    for cid in ("a", "b"):
        store.put("character", {"name": cid, "fixed_tags": [], "outfits": []}, cid)
        store.put("scene_spec", {"spec": {"asset_type": "pose", "character_id": cid}}, cid)
        store.put(
            "asset",
            {
                "role": "original",
                "scene_spec_id": cid,
                "path": "private.png",
                "generation": {"graph": "large"},
                "mode": "RGB",
            },
            cid,
        )
        store.put("approval", {"character_id": cid, "asset_id": cid, "kind": "pose"})
    job = store.create_job(
        {"scene_spec_id": "a", "reference_asset_id": "a", "idempotency_key": "one"}
    )
    store.update_job(
        job["id"],
        state="submission_uncertain",
        error="unknown receipt",
        outputs=["a"],
        progress={"value": 2, "max": 4},
    )
    before = store.jobs(), store.list("approval"), store.list("asset")
    app = FastAPI()
    app.include_router(production_router(lambda: store))

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            result = await client.get("/production/snapshot", params={"character_id": "a"})
            assert result.status_code == 200
            data = result.json()
            assert [c["id"] for c in data["characters"]] == ["a"]
            assert [a["id"] for a in data["assets"]] == ["a"]
            assert data["jobs"][0]["state"] == "submission_uncertain"
            assert data["jobs"][0]["progress"] == {"value": 2, "max": 4}
            assert data["approvals"][0]["kind"] == "pose"
            assert "generation" not in data["assets"][0] and "path" not in data["assets"][0]
            assert data["assets"][0]["download_url"] == "/assets/a/file"
            assert (
                await client.get("/production/snapshot?character_id=missing")
            ).status_code == 404
            assert len((await client.get("/production/snapshot")).json()["characters"]) == 2
            manifest = await client.get("/production/characters/a/manifest")
            assert (
                manifest.headers["content-disposition"]
                == 'attachment; filename="caster-assets.json"'
            )
            assert manifest.json() == data
            capabilities = (await client.get("/production/capabilities")).json()
            assert capabilities["generation_online"] is False

    asyncio.run(check())
    assert (store.jobs(), store.list("approval"), store.list("asset")) == before


def test_outfit_versions_append_without_changing_old_character_or_specs(tmp_path):
    store = Store(tmp_path)
    original = {
        "name": "A",
        "fixed_tags": ["blue eyes"],
        "outfits": [{"id": "original", "tags": ["coat"], "description": ""}],
    }
    store.put("character", original, "a")
    store.put("scene_spec", {"spec": {"character_id": "a", "outfit_id": "original"}}, "old-spec")
    version = {"id": "v2", "tags": ["dress"], "description": "red"}
    saved = store.append_outfit("a", version, "Red dress", "original")
    assert store.append_outfit("a", version, "Red dress", "original") == saved
    assert store.get("character", "a")["outfits"] == original["outfits"] + [version]
    assert store.get("character", "a")["fixed_tags"] == original["fixed_tags"]
    assert store.get("scene_spec", "old-spec")["spec"]["outfit_id"] == "original"
    import pytest

    with pytest.raises(ValueError):
        store.append_outfit("a", dict(version, tags=["changed"]), "Red dress", "original")
    with pytest.raises(LookupError):
        store.append_outfit("a", dict(version, id="v3"), "Bad parent", "missing")
    assert len(store.get("character", "a")["outfits"]) == 2


def test_outfit_workflow_uses_identity_image_and_has_no_pose_lora():
    from aigc.schema import SceneSpec
    from aigc.workflows import build

    assert SceneSpec(asset_type="outfit", character_id="a", outfit_id="v2").asset_type == "outfit"
    graph, outputs, _ = build(
        "outfit",
        {"positive": "red dress", "negative": ""},
        12,
        "job",
        {"reference": "approved.png"},
    )
    assert graph["13"]["inputs"]["image"] == "approved.png"
    assert graph["6"]["inputs"]["pixels"] == ["13", 0]
    assert graph["4"]["inputs"]["text"].endswith("red dress")
    assert not any("pose" in str(n["inputs"].get("lora_name", "")).lower() for n in graph.values())
    assert outputs == {"9": "original"}


def test_http_outfit_generation_requires_identity_and_pose_requires_matching_outfit(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AIGC_DATA_DIR", str(tmp_path))
    from aigc import api

    store = Store(tmp_path)
    app = api.create_app(store=store)
    store.put(
        "character", {"name": "A", "fixed_tags": [], "outfits": [{"id": "old", "tags": []}]}, "a"
    )
    store.put("asset", {"role": "original", "mode": "RGB"}, "identity")
    store.put("pose", {"render_asset_id": "render", "state": {}}, "pose")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            version = {"id": "v2", "name": "Dress", "tags": ["red dress"], "parent_id": "old"}
            assert (
                await client.post("/production/characters/a/outfits", json=version)
            ).status_code == 201
            assert (
                await client.post(
                    "/production/characters/a/outfits", json=dict(version, tags=["blue"])
                )
            ).status_code == 409

            async def spec(kind, outfit):
                r = await client.post(
                    "/scene-specs",
                    json={"manual": {"asset_type": kind, "character_id": "a", "outfit_id": outfit}},
                )
                assert r.status_code == 201
                return r.json()["id"]

            sid = await spec("outfit", "v2")
            request = {
                "scene_spec_id": sid,
                "reference_asset_id": "identity",
                "idempotency_key": "outfit-1",
            }
            assert (await client.post("/jobs", json=request)).status_code == 422
            assert (
                await client.post(
                    "/assets/identity/approve",
                    json={"kind": "character", "character_id": "a", "outfit_id": "old"},
                )
            ).status_code == 200
            result = await client.post("/jobs", json=request)
            assert result.status_code == 201
            assert (await client.post("/jobs", json=request)).json()["id"] == result.json()["id"]
            store.put(
                "asset",
                {
                    "role": "original",
                    "mode": "RGB",
                    "scene_spec_id": sid,
                    "parent_asset_id": "identity",
                },
                "clothed",
            )
            assert (
                await client.post(
                    "/assets/clothed/approve",
                    json={"kind": "character", "character_id": "a", "outfit_id": "v2"},
                )
            ).status_code == 422
            assert (
                await client.post(
                    "/assets/clothed/approve",
                    json={"kind": "outfit", "character_id": "a", "outfit_id": "v2"},
                )
            ).status_code == 200
            pose = {
                "scene_spec_id": await spec("pose", "v2"),
                "reference_asset_id": "clothed",
                "pose_asset_id": "pose",
                "idempotency_key": "pose-new",
            }
            assert (await client.post("/jobs", json=pose)).status_code == 201
            pose["scene_spec_id"] = await spec("pose", "old")
            pose["idempotency_key"] = "wrong-outfit"
            assert (await client.post("/jobs", json=pose)).status_code == 422
            assert len(store.jobs()) == 2

    asyncio.run(check())
