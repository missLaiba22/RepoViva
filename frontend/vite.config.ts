/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // Core API is proxied under /v1, so the browser sees one origin and no
  // CORS setup is needed. 127.0.0.1, not localhost: on Windows localhost
  // tries IPv6 first and adds ~2 s per call. The page itself must be opened
  // on localhost:5173, the same host as the OAuth callback, so the session
  // cookie set there reaches it (cookies are per host, not per port).
  const env = loadEnv(mode, process.cwd());
  const coreApi = env.VITE_CORE_API_URL ?? "http://127.0.0.1:8000";
  // The interview WebSocket goes to Voice Service through the same proxy.
  const voice = env.VITE_VOICE_SERVICE_URL ?? "http://127.0.0.1:8002";

  return {
    plugins: [react()],
    server: {
      host: "localhost",
      port: 5173,
      strictPort: true,
      // Order matters: the more specific /v1/ws must come before /v1.
      proxy: {
        "/v1/ws": { target: voice, ws: true },
        "/v1": coreApi,
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./tests/setup.ts"],
      css: false,
    },
  };
});
