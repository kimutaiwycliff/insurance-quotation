import next from "eslint-config-next";

const config = [
  ...next,
  { ignores: ["src/lib/api/generated/**", ".next/**", "playwright-report/**", "test-results/**", "e2e/**"] },
];

export default config;
