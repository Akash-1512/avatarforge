import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies the API so the SPA can call /api/v1/* same-origin against
// the FastAPI backend on :8000. In production the built assets are static and
// VITE_API_BASE can point at the deployed API.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
