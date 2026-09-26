import { parseBundle, uid, type Character, type Template } from "./model";

export type ServerCharacter = {
  id: string;
  name: string;
  fixed_tags: string[];
  description?: string;
  outfits: { id: string; tags: string[]; description?: string }[];
};

// Template catalog access is independent of production task polling.
export function createLibrary(fetcher: typeof fetch = fetch) {
  let revision = 0;
  const pages = new Map<
    string,
    {
      expires: number;
      data: {
        total: number;
        categories: string[];
        items: Template[];
        category_labels?: Record<string, string>;
      };
    }
  >();
  async function request(path: string, init?: RequestInit) {
    const r = await fetcher(`/api${path}`, {
      ...init,
      signal: init?.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(60000)])
        : AbortSignal.timeout(60000),
    });
    if (!r.ok) {
      let detail = "";
      try {
        detail = JSON.stringify((await r.json()).detail || "");
      } catch {
        /* non-JSON gateway error */
      }
      throw Error(
        `后端请求失败（${r.status}）${detail}。请检查 SSH 隧道与服务。`,
      );
    }
    if (init?.method && init.method !== "GET") {
      revision += 1;
      pages.clear();
    }
    return r.json();
  }
  return {
    async page(
      query: {
        kind: string;
        source: string;
        q: string;
        category: string;
        offset: number;
      },
      signal?: AbortSignal,
    ) {
      signal?.throwIfAborted();
      const params = new URLSearchParams({
        ...query,
        offset: String(query.offset),
        limit: "12",
      });
      const key = params.toString();
      const cached = pages.get(key);
      if (cached && cached.expires > Date.now()) return cached.data;
      const started = revision;
      const data = await request(`/prompt-templates?${params}`, { signal });
      const result = {
        total: data.total as number,
        categories: data.categories as string[],
        category_labels: data.category_labels as
          Record<string, string> | undefined,
        items: data.items.length
          ? parseBundle(
              JSON.stringify({ schema_version: 1, templates: data.items }),
            )
          : [],
      };
      if (started === revision && !signal?.aborted) {
        if (pages.size >= 40) pages.delete(pages.keys().next().value!);
        pages.set(key, { expires: Date.now() + 30000, data: result });
      }
      return result;
    },
    async templates(): Promise<Template[]> {
      return parseBundle(
        JSON.stringify(await request("/prompt-templates/export")),
      );
    },
    async characters(signal?: AbortSignal): Promise<ServerCharacter[]> {
      const rows = await request("/characters", { signal });
      if (
        !Array.isArray(rows) ||
        rows.some(
          (c: ServerCharacter) =>
            typeof c.id !== "string" ||
            typeof c.name !== "string" ||
            !Array.isArray(c.fixed_tags) ||
            !Array.isArray(c.outfits),
        )
      )
        throw Error("后端角色格式不兼容，未载入。");
      return rows;
    },
    async import(items: Template[]) {
      const body = new FormData();
      body.append(
        "file",
        new Blob(
          [
            JSON.stringify({
              schema_version: 1,
              templates: items.map(({ display, ...t }) => t),
            }),
          ],
          {
            type: "application/json",
          },
        ),
        "templates.json",
      );
      return request("/prompt-templates/import", { method: "POST", body });
    },
    async edit(t: Template) {
      return request(`/prompt-templates/${encodeURIComponent(t.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify((({ display, ...original }) => original)(t)),
      });
    },
  };
}
export const serverLibrary = createLibrary();
export function characterDraft(source: ServerCharacter): Character {
  return {
    id: `server-draft-${uid()}`,
    sourceId: source.id,
    draft: {
      name: source.name,
      tags: source.fixed_tags.join(", "),
      description: source.description || "",
    },
    outfits: source.outfits.length
      ? source.outfits.map((o) => ({
          id: o.id,
          name: o.id,
          tags: [...o.tags, o.description].filter(Boolean).join(", "),
        }))
      : [{ id: "draft-outfit", name: "待设定服装", tags: "" }],
  };
}
