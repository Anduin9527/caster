import test from "node:test";
import assert from "node:assert/strict";
import {
  initialState,
  current,
  enqueue,
  tick,
  reviewAsset,
  identityReady,
  outfitReady,
  selectedOutfit,
  poseReady,
  canStep,
  cancelJob,
  retryJob,
  parseBundle,
  importTemplates,
  type State,
} from "./model";
function finish(s: State) {
  for (
    let i = 0;
    i < 250 && s.jobs.some((j) => ["queued", "running"].includes(j.state));
    i++
  )
    s = tick(s);
  return s;
}
function withIdentity() {
  let s = finish(enqueue(initialState(), { role: "identity", count: 2 }));
  return reviewAsset(s, s.assets[0].id, "approved");
}
function withOutfit() {
  let s = finish(enqueue(withIdentity(), { role: "outfit", count: 3 }));
  return reviewAsset(s, s.assets.at(-1)!.id, "approved");
}
test("full flow: explicit approvals, two outfits, poses, expressions, exportable parent history", () => {
  let s = initialState();
  assert.equal(canStep(s, 2), false);
  assert.throws(() => enqueue(s, { role: "pose", poses: [1] }));
  s = finish(enqueue(s, { role: "identity", count: 2 }));
  assert.equal(s.assets.length, 2);
  assert.equal(identityReady(s, current(s).c), false);
  s = reviewAsset(s, s.assets[0].id, "approved");
  assert.equal(canStep(s, 2), true);
  assert.equal(outfitReady(s, current(s).c, current(s).o), false);
  assert.equal(canStep(s, 3), false);
  const originalIdentity = s.characters[0].identityId;
  s = {
    ...s,
    outfitId: "navy",
    characters: s.characters.map((c) => ({
      ...c,
      outfits: [
        ...c.outfits,
        { id: "navy", name: "旅行外套", tags: "navy coat" },
      ],
    })),
  };
  assert.equal(canStep(s, 3), false);
  s = finish(enqueue(s, { role: "outfit", count: 3 }));
  s = reviewAsset(s, s.assets.at(-1)!.id, "approved");
  assert.equal(s.characters[0].identityId, originalIdentity);
  assert.equal(canStep(s, 3), true);
  s = finish(enqueue(s, { role: "pose", poses: [1, 2, 3] }));
  assert.equal(canStep(s, 4), false);
  for (const a of s.assets.filter((a) => a.role === "pose"))
    s = reviewAsset(s, a.id, "approved");
  assert.equal(poseReady(s, current(s).c, current(s).o).length, 1);
  assert.throws(
    () =>
      enqueue(s, { role: "expression", poses: [1, 2, 3], moods: ["happy"] }),
    /只能/,
  );
  s = finish(
    enqueue(s, {
      role: "expression",
      poses: [3],
      moods: ["happy", "surprised", "angry"],
    }),
  );
  assert.equal(s.assets.filter((a) => a.role === "expression").length, 3);
  for (const a of s.assets.filter((a) => a.role === "expression")) {
    assert.equal(a.review, "pending");
    assert.ok(s.assets.some((p) => p.id === a.parentId && p.role === "pose"));
    assert.ok(a.alpha);
  }
  assert.equal(s.assets.length, 11);
  assert.equal(s.characters[0].outfits.length, 2);
});
test("editing upstream invalidates gates; snapshots and historical outputs survive", () => {
  let s = withOutfit();
  s = finish(enqueue(s, { role: "pose", poses: [1] }));
  s = reviewAsset(s, s.assets.at(-1)!.id, "approved");
  const old = s.assets.at(-1)!;
  const oldTags = old.prompt;
  s = {
    ...s,
    characters: s.characters.map((c) => ({
      ...c,
      draft: { ...c.draft, tags: "new tags" },
    })),
  };
  assert.equal(canStep(s, 3), false);
  assert.equal(canStep(s, 4), false);
  assert.equal(s.assets.at(-1)!.prompt, oldTags);
  assert.throws(
    () => reviewAsset(s, old.id, "approved"),
    /设定已改变|基准尚未确认/,
  );
  s = finish(enqueue(s, { role: "identity" }));
  s = reviewAsset(s, s.assets.at(-1)!.id, "approved");
  assert.equal(poseReady(s, current(s).c, current(s).o).length, 0);
  assert.ok(s.assets.some((a) => a.id === old.id));
});
test("queue serializes; offline pauses; cancellation and retry preserve original jobs", () => {
  let s = enqueue(withOutfit(), {
    role: "pose",
    poses: [1, 2, 3],
    scenario: "mixed",
  });
  s = tick(s);
  const running = s.jobs.find((j) => j.state === "running")!;
  assert.throws(() => cancelJob(s, running.id));
  const queued = s.jobs.find((j) => j.state === "queued")!;
  s = cancelJob(s, queued.id);
  assert.equal(s.jobs.find((j) => j.id === queued.id)!.state, "cancelled");
  s = { ...s, offline: true };
  assert.deepEqual(tick(s), s);
  s = { ...s, offline: false };
  s = finish(s);
  const broken = s.jobs.find((j) => j.state === "needs_correction")!;
  assert.ok(broken);
  const before = s.jobs.length;
  s = retryJob(s, broken.id);
  assert.equal(s.jobs.length, before + 1);
  assert.equal(
    s.jobs.find((j) => j.id === broken.id)!.state,
    "needs_correction",
  );
  s = finish(s);
  assert.equal(s.jobs.at(-1)!.state, "succeeded");
  assert.equal(s.jobs.at(-1)!.retryOf, broken.id);
});
test("template bundles validate before atomic import; edited templates do not mutate character", () => {
  const bundle = {
    schema_version: 1,
    templates: [
      { id: "hero", kind: "character", name: "主角", tags: ["silver hair"] },
    ],
  };
  const items = parseBundle(JSON.stringify(bundle));
  let s = importTemplates(initialState(), items);
  const character = JSON.stringify(s.characters);
  assert.equal(importTemplates(s, items).templates.length, 1);
  assert.throws(() => parseBundle("{oops"));
  assert.throws(() =>
    parseBundle(
      JSON.stringify({
        ...bundle,
        templates: [...bundle.templates, ...bundle.templates],
      }),
    ),
  );
  assert.throws(() =>
    parseBundle(
      JSON.stringify({
        schema_version: 1,
        templates: [{ id: "bad", kind: "character", name: "x", tags: [] }],
      }),
    ),
  );
  assert.throws(
    () => importTemplates(s, [{ ...items[0], tags: ["black hair"] }]),
    /已存在/,
  );
  assert.equal(s.templates[0].tags[0], "silver hair");
  assert.equal(JSON.stringify(s.characters), character);
  assert.deepEqual(parseBundle('{"schema_version":1,"templates":[]}'), []);
});


test("multiple clothing trials produce three candidates each; one exact clothing and pose continue", () => {
  let s = withIdentity();
  s = {
    ...s,
    characters: s.characters.map((c) => ({
      ...c,
      outfits: [
        ...c.outfits,
        { id: "navy", name: "蓝外套", tags: "navy coat" },
      ],
    })),
  };
  const before = s.jobs.length;
  s = finish(
    enqueue(s, { role: "outfit", outfitIds: ["casual", "navy"], count: 3 }),
  );
  const trials = s.jobs.slice(before);
  assert.equal(trials.length, 6);
  assert.equal(new Set(trials.map((j) => j.batchId)).size, 1);
  const casual = s.assets.filter(
    (a) => a.role === "outfit" && a.outfitId === "casual",
  );
  const navy = s.assets.filter(
    (a) => a.role === "outfit" && a.outfitId === "navy",
  );
  assert.equal(casual.length, 3);
  assert.equal(navy.length, 3);
  assert.equal(canStep(s, 3), false);
  s = reviewAsset(s, casual[0].id, "approved");
  // Browsing another clothing plan must not switch the next stage's source.
  s = { ...s, outfitId: "navy" };
  s = finish(enqueue(s, { role: "pose", poses: [1, 2] }));
  const poses = s.assets.filter((a) => a.role === "pose");
  assert.ok(poses.every((a) => a.parentId === casual[0].id));
  s = reviewAsset(s, poses[0].id, "approved");
  s = finish(enqueue(s, { role: "expression", moods: ["happy", "angry"] }));
  const oldChildren = s.assets.filter((a) => a.role === "expression");
  assert.equal(oldChildren.length, 2);
  assert.ok(oldChildren.every((a) => a.parentId === poses[0].id));
  s = reviewAsset(s, poses[1].id, "approved");
  assert.deepEqual(
    poseReady(s, current(s).c).map((a) => a.id),
    [poses[1].id],
  );
  assert.throws(() => reviewAsset(s, oldChildren[0].id, "approved"), /父姿态/);
  s = finish(enqueue(s, { role: "expression", moods: ["happy"] }));
  assert.equal(s.assets.at(-1)!.parentId, poses[1].id);
  s = reviewAsset(s, navy[2].id, "approved");
  assert.equal(selectedOutfit(s, current(s).c)!.asset.id, navy[2].id);
  assert.equal(poseReady(s, current(s).c).length, 0);
  assert.equal(canStep(s, 4), false);
  assert.throws(() => enqueue(s, { role: "expression", moods: ["happy"] }));
  assert.ok(
    oldChildren.every((old) =>
      s.assets.some((a) => a.id === old.id && a.image === old.image),
    ),
  );
  // Switching between two candidates from the same outfit also clears pose selection.
  s = reviewAsset(s, casual[1].id, "approved");
  assert.equal(selectedOutfit(s, current(s).c)!.asset.id, casual[1].id);
  assert.equal(poseReady(s, current(s).c).length, 0);
});

test("clothing edits do not change the initial identity recipe; stale queued branches cannot be selected", () => {
  let s = withOutfit();
  s = enqueue(s, { role: "pose", poses: [1] });
  const oldJob = s.jobs.at(-1)!;
  const alternative = s.assets.find(
    (a) => a.role === "outfit" && a.id !== current(s).c.selectedOutfitAssetId,
  )!;
  s = reviewAsset(s, alternative.id, "approved");
  s = finish(s);
  assert.throws(
    () =>
      reviewAsset(
        s,
        s.assets.find(
          (a) => a.id === s.jobs.find((j) => j.id === oldJob.id)!.resultId,
        )!.id,
        "approved",
      ),
    /基准/,
  );
  const identity = s.assets.find((a) => a.id === current(s).c.identityId)!;
  s = {
    ...s,
    characters: s.characters.map((c) => ({
      ...c,
      outfits: c.outfits.map((o) => ({ ...o, tags: "new costume" })),
    })),
  };
  assert.equal(identityReady(s, current(s).c), true);
  s = reviewAsset(s, identity.id, "approved");
  s = enqueue(s, { role: "identity" });
  assert.ok(s.jobs.at(-1)!.payload.prompt.includes("simple neutral clothing"));
  assert.ok(!s.jobs.at(-1)!.payload.prompt.includes("new costume"));
});
