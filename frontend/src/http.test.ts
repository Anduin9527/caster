import assert from "node:assert/strict";
import test from "node:test";
import {
  APIError,
  apiURL,
  createHTTPClient,
  normalizeAPIBaseURL,
} from "./api/http";

test("JSON, media and event URLs preserve independent origins and path prefixes", async () => {
  const base = "https://api.example.test/caster/api/v1/";
  assert.equal(
    apiURL("/assets/a%2Fb/file", base),
    "https://api.example.test/caster/api/v1/assets/a%2Fb/file",
  );
  const calls: string[] = [];
  const http = createHTTPClient(
    (async (url) => {
      calls.push(String(url));
      return Response.json({ ok: true });
    }) as typeof fetch,
    base,
  );
  await http.request("/health");
  assert.equal(calls[0], http.url("/health"));
  assert.equal(apiURL("/health"), "/api/v1/health");
  for (const bad of [
    "//outside.test/api",
    "https://user:key@api.test",
    "https://api.test?secret=key",
    "file:///api",
    "/api/../other",
  ])
    assert.throws(() => normalizeAPIBaseURL(bad));
});

test("HTTP errors retain status and explain FastAPI field validation without leaking HTML", async () => {
  const validation = createHTTPClient((async () =>
    Response.json(
      { detail: [{ loc: ["body", "name"], msg: "Field required" }] },
      { status: 422 },
    )) as typeof fetch);
  await assert.rejects(
    validation.request("/characters"),
    (error: unknown) =>
      error instanceof APIError &&
      error.status === 422 &&
      error.message.includes("name: Field required"),
  );
  const gateway = createHTTPClient(
    (async () =>
      new Response("<html>private gateway</html>", {
        status: 502,
      })) as typeof fetch,
  );
  await assert.rejects(
    gateway.request("/health"),
    (error: unknown) =>
      error instanceof APIError &&
      error.status === 502 &&
      !error.message.includes("private"),
  );
});

test("transport forwards cancellation, preserves multipart headers and never retries writes", async () => {
  let calls = 0;
  const controller = new AbortController();
  const body = new FormData();
  body.append("file", new Blob(["{}"]), "templates.json");
  const http = createHTTPClient((async (_url, init) => {
    calls++;
    assert.equal(new Headers(init?.headers).has("Content-Type"), false);
    assert.equal(init?.body, body);
    controller.abort();
    assert.equal(init?.signal?.aborted, true);
    throw new TypeError("Failed to fetch");
  }) as typeof fetch);
  await assert.rejects(
    http.request("/prompt-templates/import", {
      method: "POST",
      body,
      signal: controller.signal,
    }),
    /Failed to fetch/,
  );
  assert.equal(calls, 1);
});

test("an unreadable successful write response is uncertain rather than a rejection", async () => {
  const http = createHTTPClient(
    (async () =>
      new Response("<html>proxy</html>", { status: 200 })) as typeof fetch,
  );
  await assert.rejects(
    http.request("/production/characters/a/batches", {
      method: "POST",
      body: "{}",
    }),
    (error: unknown) =>
      error instanceof APIError &&
      error.status === undefined &&
      error.message.includes("JSON"),
  );
});
