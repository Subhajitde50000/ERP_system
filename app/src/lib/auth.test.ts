/// <reference types="vitest/globals" />
/**
 * B7 regression tests — release builds can never ship pointing at localhost.
 */
import { expect, test, vi } from "vitest";

// The auth module reads tokens through Expo's secure store — mock it so the
// native runtime is not required in unit tests.
vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn().mockResolvedValue(null),
  setItemAsync: vi.fn().mockResolvedValue(undefined),
  deleteItemAsync: vi.fn().mockResolvedValue(undefined),
}));

import { resolveApiBaseUrl } from "./auth";

test("dev builds keep the localhost default (correct for emulators)", () => {
  expect(resolveApiBaseUrl({ NODE_ENV: "development" })).toBe("http://localhost:8000");
  expect(resolveApiBaseUrl({})).toBe("http://localhost:8000");
});

test("dev builds accept an explicit LAN/HTTPS URL and strip trailing slashes", () => {
  expect(resolveApiBaseUrl({ NODE_ENV: "development", EXPO_PUBLIC_API_URL: "http://192.168.1.20:8000/" }))
    .toBe("http://192.168.1.20:8000");
});

test("release builds without an API URL fail fast with instructions", () => {
  expect(() => resolveApiBaseUrl({ NODE_ENV: "production" })).toThrow(/EXPO_PUBLIC_API_URL/);
});

test("release builds refuse localhost-style URLs (the phone itself)", () => {
  for (const url of ["http://localhost:8000", "http://127.0.0.1:8000", "http://10.0.2.2:8000"]) {
    expect(() => resolveApiBaseUrl({ NODE_ENV: "production", EXPO_PUBLIC_API_URL: url })).toThrow(
      /Release builds must use the HTTPS API URL/,
    );
  }
});

test("release builds accept the production HTTPS API", () => {
  expect(resolveApiBaseUrl({ NODE_ENV: "production", EXPO_PUBLIC_API_URL: "https://api.example.com" }))
    .toBe("https://api.example.com");
});
