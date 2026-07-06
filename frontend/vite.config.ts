import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const BACKEND_URL = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/auth": BACKEND_URL,
      "/sync": BACKEND_URL,
      // "/setup" is both a backend API path (POST /setup, GET /setup/status)
      // and the frontend's own client-side page route. Bypass the proxy for
      // a bare GET /setup navigation so Vite serves the SPA instead of
      // forwarding the page load to the backend.
      "/setup": {
        target: BACKEND_URL,
        changeOrigin: true,
        bypass(req) {
          if (req.method === "GET" && req.url === "/setup") {
            return req.url;
          }
        },
      },
      "/config": BACKEND_URL,
      "/health": BACKEND_URL,
      "/local-data": BACKEND_URL,
    },
  },
  test: {
    css: true,
    environment: "jsdom",
  },
});
