import { randomUUID } from "node:crypto";

// Ephemeral demo exports only; never reads files or contacts the inference API.
export function demoDownloads() {
  const pending = new Map();
  function middleware(req, res, next) {
    const path = (req.url || "").split("?")[0];
    if (!path.startsWith("/demo-downloads/")) return next();
    for (const [key, item] of pending)
      if (item.expires < Date.now()) pending.delete(key);
    if (req.method === "POST" && path === "/demo-downloads/create") {
      const chunks = [];
      let size = 0;
      let overflow = false;
      req.on("data", (chunk) => {
        size += chunk.length;
        if (size > 16 * 1024 * 1024) overflow = true;
        else chunks.push(chunk);
      });
      req.on("end", () => {
        if (overflow) {
          res.writeHead(413).end("Export too large");
          return;
        }
        try {
          const { data, name } = JSON.parse(Buffer.concat(chunks).toString());
          if (
            typeof name !== "string" ||
            !/^[a-zA-Z0-9_-]+\.json$/.test(name) ||
            data === undefined
          )
            throw Error("Invalid export");
          if (pending.size >= 20) pending.delete(pending.keys().next().value);
          const id = randomUUID();
          pending.set(id, {
            data: JSON.stringify(data, null, 2),
            name,
            expires: Date.now() + 600000,
          });
          res.writeHead(201, {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
          });
          res.end(JSON.stringify({ url: `/demo-downloads/${id}` }));
        } catch {
          res.writeHead(400).end("Invalid export JSON");
        }
      });
      return;
    }
    const item = pending.get(path.slice("/demo-downloads/".length));
    if (req.method !== "GET" || !item) {
      res.writeHead(404).end("Export expired");
      return;
    }
    res.writeHead(200, {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${item.name}"`,
      "Cache-Control": "no-store",
    });
    res.end(item.data);
  }
  return {
    name: "caster-demo-downloads",
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}
