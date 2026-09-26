import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parseEnv } from "node:util";

const defaults = {
  AIGC_API_URL: "http://127.0.0.1:8189",
  AIGC_UI_URL: "http://127.0.0.1:4173",
};

/** Read public server URLs without a Python runtime or shell evaluation. */
export function readRuntimeConfig(root, env = process.env) {
  let file = {};
  try {
    file = parseEnv(
      readFileSync(env.AIGC_CONFIG_FILE || join(root, "config.env"), "utf8"),
    );
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  return Object.fromEntries(
    Object.entries(defaults).map(([key, fallback]) => {
      const value = env[key] ?? file[key] ?? fallback;
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol)) {
        throw new Error(`${key} must use http or https`);
      }
      return [key, value];
    }),
  );
}
