import test from "node:test";
import assert from "node:assert/strict";
import { parseWorkbenchOptions } from "./workbenchPreferences";
import { expressionPresets } from "./presentation";

test("malformed or absent character preferences restore independent defaults", () => {
  for (const raw of [null, "{", "null", "42", '"old version"']) {
    const options = parseWorkbenchOptions(raw);
    assert.equal(options.step, 0);
    assert.deepEqual(options.outfitIds, []);
    assert.deepEqual(options.poseIds, []);
    assert.deepEqual(options.expressions, expressionPresets);
    assert.equal(options.chosenMoods.length, 3);
  }
});

test("saved preferences retain valid custom expressions while rejecting invalid control values", () => {
  const value = parseWorkbenchOptions(
    JSON.stringify({
      step: 20,
      outfitIds: [null, "outfit"],
      poseIds: [102, "preset:102", "legacy"],
      expressions: [
        null,
        { name: "自定义", prompt: "custom" },
        { prompt: "missing-name" },
      ],
      chosenMoods: [null, "custom", "missing"],
    }),
  );
  assert.equal(value.step, 0);
  assert.deepEqual(value.outfitIds, ["outfit"]);
  assert.deepEqual(value.poseIds, ["preset:102"]);
  assert.deepEqual(value.chosenMoods, ["custom"]);
  assert.equal(value.expressions.at(-1)?.name, "自定义");
});
