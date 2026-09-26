import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { readRuntimeConfig } from "../scripts/runtime-config.mjs";

function workspace(t) {
  const root = mkdtempSync(join(tmpdir(), "caster-config-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

test("frontend runs with defaults in a checkout without Python or config.env", (t) => {
  const config = readRuntimeConfig(workspace(t), {});
  assert.deepEqual(config, {
    AIGC_API_URL: "http://127.0.0.1:8189",
    AIGC_UI_URL: "http://127.0.0.1:4173",
  });
});

test("public URLs use environment > selected config file > defaults", (t) => {
  const root = workspace(t);
  const selected = join(root, "selected.env");
  writeFileSync(
    join(root, "config.env"),
    "AIGC_API_URL=http://wrong.invalid\n",
  );
  writeFileSync(
    selected,
    'export AIGC_API_URL="http://127.0.0.1:9100" # local\n' +
      'AIGC_UI_URL=http://127.0.0.1:4200\nAIGC_AGENT_API_KEY="$(private command)"\n',
  );
  assert.deepEqual(
    readRuntimeConfig(root, {
      AIGC_CONFIG_FILE: selected,
      AIGC_API_URL: "http://127.0.0.1:9200",
    }),
    {
      AIGC_API_URL: "http://127.0.0.1:9200",
      AIGC_UI_URL: "http://127.0.0.1:4200",
    },
  );
});

test("invalid URLs fail clearly instead of producing a broken proxy", (t) => {
  assert.throws(
    () =>
      readRuntimeConfig(workspace(t), {
        AIGC_API_URL: "file:///private",
      }),
    /AIGC_API_URL must use http or https/,
  );
});
