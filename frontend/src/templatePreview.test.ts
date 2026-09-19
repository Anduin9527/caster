import test from "node:test";
import assert from "node:assert/strict";
import { templatePreview, templateSource } from "./templatePreview";
import type { Template } from "./model";
const base: Template = {
  id: "a",
  kind: "character",
  name: "yamazaki sousuke",
  tags: [],
  source: "https://github.com/j955229/Comfyui-Anima-Tools-HUB",
  source_revision: "a0c351e81a24ebdbc7f47c524139a8dfe1226705",
  source_key: "yamazaki sousuke||free!",
};
test("preview mapping follows upstream source key, not editable display name", () => {
  assert.equal(
    templateSource(base),
    "https://blobs.animadex.net/Outputs/thumbs/yamazaki%20sousuke%2C%20free!.webp",
  );
  assert.equal(
    templateSource({ ...base, name: "自定义名称" }),
    templateSource(base),
  );
  assert.equal(
    templateSource({ ...base, kind: "outfit", source_key: "1741118591102" }),
    "https://cdn.jsdelivr.net/gh/nregret/Dressing-doll@main/images/1741118591102.webp",
  );
  assert.equal(templateSource({ ...base, source: "user" }), undefined);
  assert.equal(
    templateSource({ ...base, kind: "outfit", source_key: "../other" }),
    undefined,
  );
});

test("template images use only the same-origin backend cache", () => {
  const url = templatePreview(base)!;
  assert.ok(url.startsWith('/api/prompt-templates/a/image?v='));
  assert.ok(!url.includes('https://'));
  assert.notEqual(url, templatePreview({...base,source_key:'another||series'}));
});
