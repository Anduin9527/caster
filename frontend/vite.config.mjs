import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { demoDownloads } from "./scripts/downloads.mjs";
import { readRuntimeConfig } from "./scripts/runtime-config.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const frontendRoot = fileURLToPath(new URL("./", import.meta.url));

export default defineConfig(({ mode }) => {
  const config = readRuntimeConfig(root, {
    ...loadEnv(mode, frontendRoot, "AIGC_"),
    ...process.env,
  });
  const ui = new URL(config.AIGC_UI_URL);
  return {
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
        "/api/v1": {
          target: config.AIGC_API_URL,
          changeOrigin: false,
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
  };
});
