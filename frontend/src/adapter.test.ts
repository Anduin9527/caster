import test from "node:test";
import assert from "node:assert/strict";
import { demoRepository, STORAGE_KEY } from "./adapter";
import { initialState, enqueue, tick, reviewAsset } from "./model";
test("browser persistence retains queue, settings, selection and reset is demo-only", () => {
  const items = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => items.get(key) || null,
      setItem: (key: string, value: string) => items.set(key, value),
      removeItem: (key: string) => items.delete(key),
    },
  });
  let s = tick(enqueue(initialState(), { role: "identity" }));
  s = {
    ...s,
    offline: true,
    step: 1,
    selections: { "demo-b/casual": { poses: [2, 6], moods: ["angry"] } },
  };
  demoRepository.save(s);
  assert.deepEqual(demoRepository.load(), JSON.parse(JSON.stringify(s)));
  items.set("unrelated-user-data", "keep");
  demoRepository.reset();
  assert.equal(items.has(STORAGE_KEY), false);
  assert.equal(items.get("unrelated-user-data"), "keep");
  items.set(STORAGE_KEY, "broken JSON");
  assert.equal(demoRepository.load().version, 1);
});

test("reload preserves a single chosen path and never selects legacy approvals implicitly", () => {
  const items = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => items.get(key) || null,
      setItem: (key: string, value: string) => items.set(key, value),
      removeItem: (key: string) => items.delete(key),
    },
  });
  let s = initialState();
  for (const role of ["identity", "outfit", "pose"] as const) {
    s = enqueue(s, { role, count: 2, poses: [1, 2] });
    for (let i = 0; i < 120; i++) s = tick(s);
    s = reviewAsset(s, s.assets.at(-1)!.id, "approved");
  }
  s.step = 4;
  demoRepository.save(s);
  assert.deepEqual(demoRepository.load(), JSON.parse(JSON.stringify(s)));
  const legacy = {
    ...s,
    characters: s.characters.map((c) => ({
      ...c,
      selectedOutfitAssetId: undefined,
      selectedPoseId: undefined,
    })),
  };
  demoRepository.save(legacy);
  const loaded = demoRepository.load();
  assert.equal(loaded.step, 2);
  assert.equal(loaded.characters[0].selectedOutfitAssetId, undefined);
  assert.deepEqual(loaded.assets, JSON.parse(JSON.stringify(s.assets)));
  assert.deepEqual(loaded.jobs, JSON.parse(JSON.stringify(s.jobs)));
});
