import test from "node:test";
import assert from "node:assert/strict";
import {
  createProductionAPI,
  productionProgress,
  productionAssetURL,
  type ProductionJob,
} from "./production";
test("production reads never write, infer approvals or fall back to demo", async () => {
  const calls: string[] = [];
  const api = createProductionAPI((async (url, init) => {
    calls.push(String(url));
    assert.equal(init?.method, undefined);
    return Response.json({
      schema_version: 1,
      characters: [{ id: "a" }],
      jobs: [{ state: "submission_uncertain" }],
      assets: [],
      approvals: [],
      poses: [],
    });
  }) as typeof fetch);
  const result = await api.snapshot("a");
  assert.equal(result.jobs[0].state, "submission_uncertain");
  assert.equal(result.approvals.length, 0);
  assert.equal(calls[0], "/api/production/snapshot?character_id=a");
  await assert.rejects(() => api.snapshot("b"), /格式不兼容/);
  const offline = createProductionAPI(
    (async () => new Response("", { status: 503 })) as typeof fetch,
  );
  await assert.rejects(() => offline.snapshot("a"), /连接失败/);
});
test("progress uses observed values and never invents percent; download stays on the API origin", () => {
  const job = { state: "running" } as ProductionJob;
  assert.equal(productionProgress(job), undefined);
  assert.equal(
    productionProgress({ ...job, progress: { value: 1, max: 4 } }),
    25,
  );
  assert.equal(
    productionProgress({ ...job, progress: { value: 1, max: 0 } }),
    undefined,
  );
  assert.equal(productionProgress({ ...job, state: "succeeded" }), 100);
  assert.equal(productionAssetURL("a/b"), "/api/assets/a%2Fb/file");
});

test("production writes explicit revisions and preserves the batch key for recovery", async () => {
  const calls: { url: string; body: any; method?: string }[] = [];
  const api = createProductionAPI((async (url, init) => {
    calls.push({
      url: String(url),
      body: JSON.parse(String(init?.body)),
      method: init?.method,
    });
    return Response.json({ id: "batch" });
  }) as typeof fetch);
  const selection = {
    character_id: "a",
    revision: 7,
    identity_asset_id: null,
    outfit_asset_id: null,
    outfit_id: null,
    pose_asset_id: null,
  };
  await api.select("a", selection, "identity", "image", true);
  assert.deepEqual(calls[0].body, {
    expected_revision: 7,
    stage: "identity",
    asset_id: "image",
    approve: true,
  });
  assert.equal(calls[0].method, "PUT");
  const request = {
    idempotency_key: "persisted-key",
    expected_revision: 7,
    role: "identity" as const,
    candidates: [{ seed: 123 }],
  };
  await api.submitBatch("a", request);
  await api.submitBatch("a", request);
  assert.deepEqual(calls[1], calls[2]);
  await assert.rejects(
    () => api.cancelQueued({ id: "j", state: "running" } as ProductionJob),
    /排队/,
  );
  assert.equal(calls.length, 3);
});

test("ComfyUI websocket progress envelope is mapped without invented progress", () => {
  assert.equal(
    productionProgress({
      state: "running",
      progress: { type: "progress", data: { value: 7, max: 28 } },
    } as ProductionJob),
    25,
  );
  assert.equal(
    productionProgress({
      state: "running",
      progress: { type: "executing", data: {} },
    } as ProductionJob),
    undefined,
  );
});

test("native pose requests carry the selected source resolution", async () => {
  let called="";
  const api=createProductionAPI((async (url)=>{called=String(url);return Response.json({id:"native",render_asset_id:"render"});}) as typeof fetch);
  await api.savePreset(105,768,1152);
  assert.equal(called,"/api/production/pose-presets/105?width=768&height=1152");
});

test("prompt preferences use a dedicated read/write settings endpoint", async () => {
  const calls: { url: string; method?: string; body?: unknown }[] = [];
  const value = {
    schema_version: 1 as const,
    artist_style: "@rella",
    fixed_positive: "masterpiece, safe",
    fixed_negative: "worst quality",
    content_hash: "a".repeat(64),
    source: "saved" as const,
  };
  const api = createProductionAPI((async (url, init) => {
    calls.push({
      url: String(url), method: init?.method,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return Response.json(value);
  }) as typeof fetch);

  await api.promptSettings();
  await api.savePromptSettings({
    artist_style: value.artist_style,
    fixed_positive: value.fixed_positive,
    fixed_negative: value.fixed_negative,
  });

  assert.deepEqual(calls, [
    { url: "/api/prompt-settings", method: undefined, body: undefined },
    {
      url: "/api/prompt-settings", method: "PUT",
      body: {
        artist_style: "@rella",
        fixed_positive: "masterpiece, safe",
        fixed_negative: "worst quality",
      },
    },
  ]);
});
