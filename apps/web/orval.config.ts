import { defineConfig } from "orval";

// Generated from the committed API contract (apps/api/openapi.json). Run `pnpm client` after `make openapi`.
export default defineConfig({
  api: {
    input: "../api/openapi.json",
    output: {
      mode: "tags-split",
      target: "src/lib/api/generated/endpoints.ts",
      schemas: "src/lib/api/generated/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: { path: "src/lib/api/fetcher.ts", name: "apiFetch" },
        query: { signal: true },
        // The fetcher throws ApiError on non-2xx, so hooks return the success body directly.
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
});
