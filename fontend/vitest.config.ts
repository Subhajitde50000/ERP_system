import path from "node:path";

import { defineConfig } from "vitest/config";

/**
 * Component/unit test setup for the web console.
 *
 * jsdom because the suites render React components (teacher grading panel,
 * assignment reopen flow); the `@/*` alias mirrors tsconfig paths. Vite's
 * esbuild already applies the automatic JSX runtime to .tsx in test mode, so
 * no React plugin is needed here.
 */
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
