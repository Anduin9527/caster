import test from "node:test";
import assert from "node:assert/strict";
import { PassThrough } from "node:stream";
import { demoDownloads } from "../scripts/downloads.mjs";
function setup() {
  let handler;
  demoDownloads().configureServer({
    middlewares: {
      use(fn) {
        handler = fn;
      },
    },
  });
  return (method, url, body) =>
    new Promise((resolve) => {
      const req = new PassThrough();
      Object.assign(req, { method, url });
      const res = {
        status: 0,
        headers: {},
        writeHead(code, headers = {}) {
          this.status = code;
          this.headers = headers;
          return this;
        },
        end(data) {
          resolve({ status: this.status, headers: this.headers, data });
        },
      };
      handler(req, res, () => resolve({ status: 404 }));
      req.end(body === undefined ? "" : JSON.stringify(body));
    });
}
test("JSON export is a real same-origin attachment with unchanged demo manifest", async () => {
  const send = setup();
  const manifest = { demo: true, assets: [{ id: "kept", review: "pending" }] };
  const created = await send("POST", "/demo-downloads/create", {
    data: manifest,
    name: "caster-demo-manifest.json",
  });
  assert.equal(created.status, 201);
  const file = await send("GET", JSON.parse(created.data).url);
  assert.equal(file.status, 200);
  assert.equal(
    file.headers["Content-Disposition"],
    'attachment; filename="caster-demo-manifest.json"',
  );
  assert.deepEqual(JSON.parse(file.data), manifest);
});
test("download service rejects path/header injection and unknown exports", async () => {
  const send = setup();
  assert.equal(
    (
      await send("POST", "/demo-downloads/create", {
        data: {},
        name: "../secret.json",
      })
    ).status,
    400,
  );
  assert.equal((await send("GET", "/demo-downloads/missing")).status, 404);
});
