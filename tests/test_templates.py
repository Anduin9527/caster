import asyncio

import httpx
import pytest

from aigc.store import Store
from aigc.templates import (
    PromptTemplate,
    TemplateBundle,
    TemplateConflict,
    TemplateSelection,
    hub_bundle,
    import_bundle,
    materialize,
    parse_clothing_js,
)
from aigc.workflows import build


def bundle():
    return TemplateBundle(
        templates=[
            PromptTemplate(
                id="novel-hero",
                kind="character",
                name="小说主角",
                trigger="hero",
                tags=["silver hair"],
                description="A quiet traveler.",
            ),
            PromptTemplate(id="navy", kind="outfit", name="深蓝外套", tags=["navy coat"]),
        ]
    )


def test_atomic_import_and_persistence(tmp_path):
    store = Store(tmp_path)
    assert import_bundle(store, bundle()) == {"created": 2, "skipped": 0}
    assert import_bundle(Store(tmp_path), bundle()) == {"created": 0, "skipped": 2}
    changed = bundle()
    changed.templates[0].id = "new"
    changed.templates[1].tags = ["different"]
    with pytest.raises(TemplateConflict):
        import_bundle(store, changed)
    assert store.get("prompt_template", "new") is None


def test_actual_hub_shapes_and_no_js_execution():
    result = hub_bundle(
        {"hero||novel": {"trigger": "hero, novel", "tags": ["blue eyes"]}},
        parse_clothing_js(
            'const clothingData = [{"id":"1","name":"Coat","tags":"coat, boots,","categories":["Outerwear"]}]; window.clothingData = clothingData;'
        ),
    )
    assert [x.kind for x in result.templates] == ["character", "outfit"]
    assert result.templates[1].tags == ["coat", "boots"]
    assert result.templates[0].categories == ["novel"]
    with pytest.raises(ValueError):
        parse_clothing_js("const clothingData = []; window.clothingData = clothingData; evil();")
    with pytest.raises(ValueError):
        TemplateBundle(templates=[result.templates[0], result.templates[0]])


def test_template_snapshot_reaches_anima_graph(tmp_path):
    store = Store(tmp_path)
    import_bundle(store, bundle())
    selection = TemplateSelection(
        character_template_id="novel-hero", outfit_template_ids=["navy"], character_id="test-hero"
    )
    result = materialize(store, selection)
    store.put("character", result["character"], "test-hero")
    graph, _, _ = build("sprite", result["previews"][0]["prompt"], 9527, "test")
    assert "silver hair" in graph["4"]["inputs"]["text"]
    assert "navy coat" in graph["4"]["inputs"]["text"]
    assert graph["1"]["inputs"]["unet_name"] == "AnimaYume_v15_base.safetensors"
    changed = bundle().templates[0]
    changed.tags = ["black hair"]
    store.put("prompt_template", changed.model_dump(), changed.id, replace=True)
    assert store.get("character", "test-hero")["fixed_tags"] == ["hero", "silver hair"]
    selection.include_character_tags = False
    assert materialize(store, selection)["character"]["fixed_tags"] == ["hero"]
    assert store.jobs() == [] and store.list("approval") == []


def test_http_upload_search_edit_and_instantiate(tmp_path, monkeypatch):
    monkeypatch.setenv("AIGC_DATA_DIR", str(tmp_path))
    from aigc import api

    app = api.create_app(store=Store(tmp_path))

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            files = {"file": ("templates.json", bundle().model_dump_json(), "application/json")}
            assert (await client.post("/prompt-templates/import", files=files)).json()[
                "created"
            ] == 2
            assert (await client.post("/prompt-templates/import", files=files)).json()[
                "skipped"
            ] == 2
            assert (
                await client.get("/prompt-templates", params={"kind": "outfit", "q": "深蓝"})
            ).json()["total"] == 1
            assert (await client.get("/prompt-templates", params={"limit": 0})).status_code == 422
            selection = {
                "character_template_id": "novel-hero",
                "outfit_template_ids": ["navy"],
                "character_id": "new-hero",
            }
            assert (
                await client.post("/prompt-templates/preview", json=selection)
            ).status_code == 200
            assert app.state.store.list("character") == []
            assert (
                await client.post("/prompt-templates/instantiate", json=selection)
            ).status_code == 201
            assert (
                await client.post("/prompt-templates/instantiate", json=selection)
            ).status_code == 409
            selection["character_template_id"] = "navy"
            assert (
                await client.post("/prompt-templates/preview", json=selection)
            ).status_code == 422
            selection["character_template_id"] = "missing"
            assert (
                await client.post("/prompt-templates/preview", json=selection)
            ).status_code == 404
            edited = bundle().templates[0].model_dump()
            edited["tags"] = ["black hair"]
            assert (
                await client.put("/prompt-templates/novel-hero", json=edited)
            ).status_code == 200
            assert app.state.store.get("character", "new-hero")["fixed_tags"] == [
                "hero",
                "silver hair",
            ]
            assert (await client.post("/prompt-templates/import", files=files)).status_code == 409
            bad = {"file": ("bad.json", '{"schema_version":1,"templates":[{}]}')}
            assert (await client.post("/prompt-templates/import", files=bad)).status_code == 422
            exported = (await client.get("/prompt-templates/export")).json()
            assert len(TemplateBundle.model_validate(exported).templates) == 2
            assert app.state.store.jobs() == [] and app.state.store.list("approval") == []

    asyncio.run(run())
