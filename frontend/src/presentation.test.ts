import test from "node:test";
import assert from "node:assert/strict";
import {
  expressionPresets,
  expressionLabel,
  assetTypeLabel,
  jobErrorLabel,
} from "./presentation";
test("expression menu keeps original three prompts and offers fifteen unique choices", () => {
  assert.equal(expressionPresets.length, 15);
  assert.equal(new Set(expressionPresets.map((m) => m.prompt)).size, 15);
  assert.deepEqual(
    expressionPresets.slice(0, 3).map((m) => m.prompt),
    ["a gentle happy smile", "a surprised expression", "an angry expression"],
  );
  assert.equal(expressionLabel("neutral expression"), "自然表情");
  assert.equal(expressionLabel("a gentle happy smile"), "开心");
  assert.equal(
    expressionLabel("custom", [{ name: "自定名称", prompt: "custom" }]),
    "自定名称",
  );
  assert.equal(expressionLabel("unrecognized English"), "自定义表情");
});
test("task copy translates internal kinds and errors", () => {
  for (const type of ["outfit", "sprite", "pose", "expression", "matte"])
    assert.match(assetTypeLabel(type), /[\u4e00-\u9fff]/);
  assert.equal(assetTypeLabel("future_type"), "图片");
  assert.match(jobErrorLabel("CUDA out of memory"), /资源不足/);
  assert.match(jobErrorLabel("no face detected"), /定位脸部/);
});
