import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { demoDownloads } from "./scripts/downloads.mjs";

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: process.env.CASTER_API_TARGET || "http://127.0.0.1:8189",
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
