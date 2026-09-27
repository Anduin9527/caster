import type { AgentSettings } from "./agent";

export type SavedConnection = {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
};
const KEY = "caster-browser-model-connection-v1";
export const connectionURL = (value: string) =>
  value.trim().replace(/\/+$/, "");

export function readConnection(): SavedConnection | null {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "null");
    return value &&
      ["provider", "base_url", "model", "api_key"].every(
        (key) => typeof value[key] === "string",
      )
      ? value
      : null;
  } catch {
    return null;
  }
}

export function rememberConnection(value: SavedConnection | null): void {
  // Unlike optional preferences, storage failures must be visible to the user.
  if (value) localStorage.setItem(KEY, JSON.stringify(value));
  else localStorage.removeItem(KEY);
}

export function connectionForm(settings: AgentSettings): SavedConnection {
  const saved = readConnection();
  if (!settings.configured && saved) return saved;
  return {
    provider: settings.provider || "custom",
    base_url: settings.base_url || "",
    model: settings.model || "",
    api_key: "",
  };
}

export function connectionToRemember(form: SavedConnection): SavedConnection {
  const previous = readConnection();
  return {
    ...form,
    base_url: connectionURL(form.base_url),
    api_key:
      form.api_key ||
      (previous &&
      connectionURL(previous.base_url) === connectionURL(form.base_url)
        ? previous.api_key
        : ""),
  };
}
