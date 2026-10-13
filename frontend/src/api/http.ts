/** The single transport seam for JSON, SSE, thumbnails and downloads. */
export function normalizeAPIBaseURL(value: string): string {
  const base = value.trim().replace(/\/+$/, "");
  if (base.startsWith("/") && !base.startsWith("//")) {
    if (/[?#\\]/.test(base) || base.split("/").includes(".."))
      throw new Error("VITE_API_BASE_URL 必须是 API 根路径或 HTTP 地址。");
    return base;
  }
  const url = new URL(base);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error("VITE_API_BASE_URL 必须是无凭据的 HTTP 地址。");
  return base;
}

export const API_BASE_URL = normalizeAPIBaseURL(
  import.meta.env?.VITE_API_BASE_URL || "/api/v1",
);

export function apiURL(path: string, baseURL = API_BASE_URL): string {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\"))
    throw new Error("API paths must start with a single slash");
  return normalizeAPIBaseURL(baseURL) + path;
}

export class APIError extends Error {
  constructor(
    message: string,
    public status?: number,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "APIError";
  }
}

function errorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== "object" || typeof item.msg !== "string")
          return "";
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part: unknown) => part !== "body").join(".")
          : "";
        return [location, item.msg].filter(Boolean).join(": ");
      })
      .filter(Boolean)
      .join("；");
  }
  return "";
}

export function createHTTPClient(
  fetcher: typeof fetch = fetch,
  baseURL = API_BASE_URL,
) {
  return {
    url: (path: string) => apiURL(path, baseURL),
    async request<T>(
      path: string,
      init: RequestInit = {},
      timeout = 20000,
    ): Promise<T> {
      const headers = new Headers(init.headers);
      headers.set("Accept", "application/json");
      if (typeof init.body === "string" && !headers.has("Content-Type"))
        headers.set("Content-Type", "application/json");
      const response = await fetcher(apiURL(path, baseURL), {
        ...init,
        headers,
        signal: init.signal
          ? AbortSignal.any([init.signal, AbortSignal.timeout(timeout)])
          : AbortSignal.timeout(timeout),
        cache: init.cache ?? (init.method ? undefined : "no-store"),
      });
      if (!response.ok) {
        let detail: unknown;
        try {
          detail = (await response.json()).detail;
        } catch {
          /* Non-JSON gateway error. */
        }
        throw new APIError(
          `后端请求失败（${response.status}）${errorDetail(detail) ? `：${errorDetail(detail)}` : ""}`,
          response.status,
          detail,
        );
      }
      if (response.status === 204) return undefined as T;
      try {
        return (await response.json()) as T;
      } catch {
        // An unreadable successful response is uncertain, not a rejection.
        // The caller must retain its persisted mutation intent for recovery.
        throw new APIError("后端未返回有效 JSON，请检查 API 地址与代理配置。");
      }
    },
  };
}
