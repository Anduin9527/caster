import sqlite3

from scripts.map_template_names import map_names


def test_names_map_exact_category_without_mutating_input():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE tags(name TEXT PRIMARY KEY, category INTEGER, cn_name TEXT)")
    db.executemany(
        "INSERT INTO tags VALUES(?,?,?)",
        [
            ("hero_name", 4, "角色译名"),
            ("some_work", 3, "作品译名"),
            ("wrong_category", 0, "通用标签"),
            ("base_name", 4, "不能模糊匹配"),
        ],
    )
    bundle = {
        "characters": [
            {"id": "a", "original_name": "hero name", "work_ids": ["w"], "translated_name": ""},
            {"id": "b", "original_name": "wrong category", "work_ids": [], "translated_name": ""},
            {
                "id": "c",
                "original_name": "base name (costume)",
                "work_ids": [],
                "translated_name": "",
            },
        ],
        "works": [{"id": "w", "original_name": "some work", "translated_name": ""}],
    }
    translated, missing, counts = map_names(bundle, db)
    assert translated["characters"][0]["translated_name"] == "角色译名"
    assert translated["works"][0]["translated_name"] == "作品译名"
    assert [r["id"] for r in missing["characters"]] == ["b", "c"]
    assert counts["characters"] == {"total": 3, "matched": 1, "unmatched": 2}
    assert bundle["characters"][0]["translated_name"] == ""
    for group in ("characters", "works"):
        for original, mapped in zip(bundle[group], translated[group]):
            assert {k: v for k, v in mapped.items() if k != "translated_name"} == {
                k: v for k, v in original.items() if k != "translated_name"
            }


def test_bilingual_display_search_keeps_prompt_fields(tmp_path):
    import asyncio

    import httpx
    from fastapi import FastAPI

    from aigc.store import Store
    from aigc.template_api import template_router

    store = Store(tmp_path)
    path = tmp_path / "translation/ffdkj/tag.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tags(name TEXT PRIMARY KEY, category INTEGER, cn_name TEXT)")
        db.executemany(
            "INSERT INTO tags VALUES(?,?,?)",
            [
                ("hero_name", 4, "角色译名"),
                ("some_work", 3, "作品译名"),
                ("blue_eyes", 0, "蓝眼睛"),
            ],
        )
    original = {
        "kind": "character",
        "name": "hero name",
        "trigger": "hero name, some work",
        "tags": ["blue eyes", "unknown tag"],
        "categories": ["some work"],
        "source": "upstream",
    }
    store.put("prompt_template", original, "hero")
    app = FastAPI()
    app.include_router(template_router(lambda: store))

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            for query in (
                "角色译名",
                "hero name",
                "作品译名",
                "some_work",
                "蓝眼睛",
                "blue eyes",
                "角色译名 blue_eyes",
            ):
                r = (
                    await c.get("/prompt-templates", params={"kind": "character", "q": query})
                ).json()
                assert r["total"] == 1
                item = r["items"][0]
                assert item["name"] == "hero name" and item["tags"] == ["blue eyes", "unknown tag"]
                assert item["display"]["name"] == "角色译名"
                assert item["display"]["tags"] == {"blue eyes": "蓝眼睛", "unknown tag": ""}
                assert r["category_labels"]["some work"] == "作品译名"
            exported = (await c.get("/prompt-templates/export")).json()["templates"][0]
            assert "display" not in exported

    asyncio.run(check())
    assert {k: v for k, v in store.get("prompt_template", "hero").items() if k != "id"} == original
