import test from "node:test";
import assert from "node:assert/strict";
import { createLibrary, characterDraft, type ServerCharacter } from "./library";
const template = {
  id: "example",
  kind: "character",
  name: "旅人",
  tags: ["brown hair"],
  source: "user",
} as const;
const character: ServerCharacter = {
  id: "demo-b",
  name: "角色 B",
  fixed_tags: ["brown hair"],
  outfits: [{ id: "casual", tags: ["jacket"] }],
};
test("live library reads through same-origin API; server identity creates isolated unapproved draft", async () => {
  const calls: string[] = [];
  const api = createLibrary((async (url: string, init?: RequestInit) => {
    calls.push(url);
    assert.equal(init?.method, undefined);
    return Response.json(
      url.endsWith("characters")
        ? [character]
        : { schema_version: 1, templates: [template] },
    );
  }) as typeof fetch);
  assert.equal((await api.templates()).length, 1);
  assert.equal((await api.characters())[0].id, "demo-b");
  assert.deepEqual(calls, ["/api/prompt-templates/export", "/api/characters"]);
  const draft = characterDraft(character);
  assert.notEqual(draft.id, character.id);
  assert.equal(draft.sourceId, character.id);
  assert.equal(draft.identityId, undefined);
  assert.equal(draft.outfits[0].baselineId, undefined);
  draft.outfits[0].tags = "changed";
  assert.deepEqual(character.outfits[0].tags, ["jacket"]);
});
test("template writes use backend endpoints and propagate conflicts, never simulate success", async () => {
  const api = createLibrary((async (url: string, init: RequestInit) => {
    assert.ok(url.startsWith("/api/prompt-templates"));
    assert.ok(["POST", "PUT"].includes(init.method!));
    return Response.json({ detail: "Template exists" }, { status: 409 });
  }) as typeof fetch);
  await assert.rejects(
    api.import([{ ...template, tags: [...template.tags] }]),
    /409/,
  );
  await assert.rejects(
    api.edit({ ...template, tags: [...template.tags] }),
    /409/,
  );
});


test("template pages reuse cache and invalidate it after a successful write", async () => {
  const calls: string[] = [];
  const api = createLibrary((async (url: string, init?: RequestInit) => {
    calls.push(url);
    return Response.json(
      init?.method ? {} : { total: 1, categories: [], items: [template] },
    );
  }) as typeof fetch);
  const query = {
    kind: "character",
    source: "user",
    q: "旅人",
    category: "",
    offset: 0,
  };
  assert.equal((await api.page(query)).items[0].name, "旅人");
  await api.page(query);
  assert.equal(calls.length, 1);
  assert.ok(calls[0].includes("limit=12"));
  assert.ok(!calls[0].includes("export"));
  await api.edit({ ...template, tags: [...template.tags] });
  await api.page(query);
  assert.equal(calls.length, 3);
});

test("display translations are excluded from template writes", async () => {
  const api = createLibrary((async (_url, init) => {
    const body = JSON.parse(String(init?.body));
    assert.equal(body.display, undefined);
    assert.deepEqual(body.tags, ["brown hair"]);
    return Response.json(body);
  }) as typeof fetch);
  await api.edit({
    ...template,
    tags: [...template.tags],
    display: { name: "旅人", categories: [], tags: { "brown hair": "棕发" } },
  });
});
