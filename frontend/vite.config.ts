/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// HA Ingress serves the UI under a prefixed path (e.g. /api/hassio_ingress/<token>/).
// base: "./" makes all asset URLs relative so they resolve correctly under any prefix.
// Dev server proxies /accounts and /providers to the running modeldeck webui process.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    // Output lands inside the Python package so the wheel ships the UI.
    outDir: path.resolve(__dirname, "../src/modeldeck/webui/static"),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/accounts": { target: "http://127.0.0.1:8099", changeOrigin: false },
      "/providers": { target: "http://127.0.0.1:8099", changeOrigin: false },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    testTimeout: 30_000,
    hookTimeout: 30_000,
    coverage: {
      provider: "v8",
      reportsDirectory: "./coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "**/*.d.ts", "src/main.tsx"],
      reporter: ["text", "json-summary"],
      thresholds: { lines: 70, functions: 65, branches: 60, statements: 70 },
    },
  },
});
