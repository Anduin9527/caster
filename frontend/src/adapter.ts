import {
  initialState,
  canStep,
  identityReady,
  selectedOutfit,
  tick,
  parseBundle,
  type State,
  type Template,
} from "./model";
export const STORAGE_KEY = "caster-sketchbook-demo-v1";
export interface DemoRepository {
  load(): State;
  save(s: State): void;
  catalog(): Promise<Template[]>;
  advance(s: State): State;
  reset(): State;
}
export const demoRepository: DemoRepository = {
  load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return initialState();
      const s = JSON.parse(raw) as State;
      if (
        s.version !== 1 ||
        !Array.isArray(s.characters) ||
        !s.characters.some((c) => c.id === s.activeId) ||
        !Array.isArray(s.assets) ||
        !Array.isArray(s.jobs) ||
        !Array.isArray(s.templates) ||
        !Array.isArray(s.moods)
      )
        throw Error("bad state");
      if (!canStep(s, s.step)) {
        const character = s.characters.find((c) => c.id === s.activeId)!;
        s.step = !identityReady(s, character)
          ? 1
          : selectedOutfit(s, character)
            ? 3
            : 2;
      }
      return s;
    } catch {
      return initialState();
    }
  },
  save(s) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  },
  async catalog() {
    const r = await fetch("/demo-assets/catalog.json");
    if (!r.ok) throw Error("本地模板目录不可用，可继续使用个人模板。");
    return parseBundle(await r.text());
  },
  advance: tick,
  reset() {
    localStorage.removeItem(STORAGE_KEY);
    return initialState();
  },
};
export async function downloadJSON(data: unknown, name: string) {
  const response = await fetch("/demo-downloads/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data, name }),
  });
  if (!response.ok)
    throw Error("清单下载服务不可用，请使用本地开发或预览服务。");
  const { url } = await response.json();
  return downloadImage(url, name);
}
export async function downloadImage(url: string, name: string) {
  // Same-origin asset URL preserves the click gesture, including WebKit downloads.
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
