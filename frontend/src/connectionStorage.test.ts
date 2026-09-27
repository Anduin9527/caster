import test from "node:test";
import assert from "node:assert/strict";
import {
  connectionForm,
  connectionToRemember,
  readConnection,
  rememberConnection,
} from "./connectionStorage";
import { appearanceTags } from "./appearanceTags";
import type { AgentSettings } from "./agent";

test("browser connection survives reads, never lends a key to another endpoint, and can be forgotten", () => {
  const rows = new Map<string, string>();
  const prior = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => rows.get(key) ?? null,
      setItem: (key: string, value: string) => rows.set(key, value),
      removeItem: (key: string) => rows.delete(key),
    },
  });
  try {
    const connection = {
      provider: "custom",
      base_url: "https://example.invalid/v1",
      model: "offline",
      api_key: "test-only-key",
    };
    rememberConnection(connection);
    assert.deepEqual(readConnection(), connection);
    assert.equal(
      connectionToRemember({
        ...connection,
        api_key: "",
        base_url: connection.base_url + "/",
      }).api_key,
      connection.api_key,
    );
    assert.equal(
      connectionToRemember({
        ...connection,
        api_key: "",
        base_url: "https://another.invalid/v1",
      }).api_key,
      "",
    );
    assert.deepEqual(
      connectionForm({ configured: false } as AgentSettings),
      connection,
    );
    assert.equal(
      connectionForm({
        configured: true,
        ...connection,
      } as unknown as AgentSettings).api_key,
      "",
    );
    rememberConnection(null);
    assert.equal(readConnection(), null);
  } finally {
    if (prior) Object.defineProperty(globalThis, "localStorage", prior);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});

test("blocked browser storage reports failed persistence without breaking reads", () => {
  const prior = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw Error("blocked");
    },
  });
  try {
    assert.equal(readConnection(), null);
    assert.throws(() => rememberConnection(null), /blocked/);
  } finally {
    if (prior) Object.defineProperty(globalThis, "localStorage", prior);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});

test("appearance tags normalize only on save and keep multi-word tags together", () => {
  assert.deepEqual(
    appearanceTags([
      "pancham,    pokemon, no humans, blue eyes,\npokemon (creature), ",
    ]),
    ["pancham", "pokemon", "no humans", "blue eyes", "pokemon (creature)"],
  );
  assert.deepEqual(appearanceTags(["蓝眼睛，短发\n白衬衫", " "]), [
    "蓝眼睛",
    "短发",
    "白衬衫",
  ]);
});
