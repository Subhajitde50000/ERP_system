import path from "node:path";

import { defineConfig } from "vitest/config";

/**
 * Unit tests for the mobile app's pure logic layer (API wiring).
 *
 * Node environment — no native modules are loaded; anything from the Expo
 * runtime (e.g. expo-secure-store) is mocked in the test itself. The `@/*`
 * alias mirrors tsconfig paths.
 */
export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
