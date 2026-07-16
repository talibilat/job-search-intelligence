import type { IncomingMessage } from "node:http";

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const BACKEND_URL = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/auth": BACKEND_URL,
      "/attention": BACKEND_URL,
      "/sync": BACKEND_URL,
      // "/setup" is both a backend API path (POST /setup, GET /setup/status)
      // and the frontend's own client-side page route. Bypass the proxy for
      // a bare GET /setup navigation so Vite serves the SPA instead of
      // forwarding the page load to the backend.
      "/setup": {
        target: BACKEND_URL,
        changeOrigin: true,
        bypass(req: IncomingMessage) {
          if (req.method === "GET" && req.url === "/setup") {
            return req.url;
          }
        },
      },
      "/config": BACKEND_URL,
      "/health": BACKEND_URL,
      "/local-data": BACKEND_URL,
      "/metrics": BACKEND_URL,
      "/pipeline": BACKEND_URL,
      "/classification": BACKEND_URL,
      "/processing": BACKEND_URL,
      // "/insights" is both a backend API path and a frontend page route.
      // Serve SPA page navigations (browser HTML requests) from Vite and
      // forward JSON API requests to the backend.
      "/insights": {
        target: BACKEND_URL,
        changeOrigin: true,
        bypass(req: IncomingMessage) {
          if (
            req.method === "GET" &&
            (req.headers.accept ?? "").includes("text/html")
          ) {
            return req.url;
          }
        },
      },
      // "/applications/{id}" is both a backend API path and a frontend page
      // route. Serve SPA page navigations (browser HTML requests) from Vite
      // and forward JSON API requests to the backend.
      "/applications": {
        target: BACKEND_URL,
        changeOrigin: true,
        bypass(req: IncomingMessage) {
          if (
            req.method === "GET" &&
            (req.headers.accept ?? "").includes("text/html")
          ) {
            return req.url;
          }
        },
      },
    },
  },
  test: {
    css: true,
    environment: "jsdom",
  },
});
