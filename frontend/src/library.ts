import { parseBundle, uid, type Character, type Template } from "./model";

import { createHTTPClient } from "./api/http";
import type { components } from "./api/schema";
export type ServerCharacter = components["schemas"]["CharacterRecord"];

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
  const http = createHTTPClient(fetcher);
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const data = await http.request<T>(path, { cache: "default", ...init }, 60000);
    if (init?.method && init.method !== "GET") {
      revision += 1;
      pages.clear();
    }
    return data;
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
      const data = await request<{
        total: number;
        categories: string[];
        category_labels?: Record<string, string>;
        items: Template[];
      }>(`/prompt-templates?${params}`, { signal });
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
      const rows = await request<ServerCharacter[]>("/characters", { signal });
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
      return request<Template>(
        `/prompt-templates/${encodeURIComponent(t.id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify((({ display, ...original }) => original)(t)),
        },
      );
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
