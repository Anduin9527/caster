import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { demoDownloads } from "./scripts/downloads.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const config = JSON.parse(execFileSync(root + ".venv/bin/python", ["-m", "aigc.config"], { cwd: root, encoding: "utf8" }));
const ui = new URL(config.AIGC_UI_URL);

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: ui.hostname,
    port: Number(ui.port || 4173),
    proxy: {
      "/api": {
        target: config.AIGC_API_URL,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ""),
        timeout: 65000,
        proxyTimeout: 65000,
      },
    },
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/main.tsx"],
    },
  },
  plugins: [react(), demoDownloads()],
});
