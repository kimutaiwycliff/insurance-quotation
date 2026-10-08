# syntax=docker/dockerfile:1.7
# Web app (Next.js, standalone output). Targets: runtime (default), e2e (Playwright runner).
ARG NODE_IMAGE=node:24-bookworm-slim

FROM ${NODE_IMAGE} AS base
ENV PNPM_HOME=/pnpm PATH="/pnpm:${PATH}" NEXT_TELEMETRY_DISABLED=1 CI=true
RUN corepack enable
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

FROM deps AS build
COPY . .
RUN pnpm run build

FROM ${NODE_IMAGE} AS runtime
# Security updates from Debian, and no package managers in production: npm, corepack and yarn are build tools
# whose bundled dependencies (tar, undici...) only add CVEs to an image that runs `node` alone.
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn-* \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]

# Browsers matching @playwright/test 1.63.0
FROM mcr.microsoft.com/playwright:v1.63.0-noble AS e2e
ENV CI=true PNPM_HOME=/pnpm PATH="/pnpm:${PATH}"
RUN corepack enable
WORKDIR /e2e
# Only Playwright and axe: the runner never needs the app's dependencies.
COPY e2e/package.json e2e/pnpm-lock.yaml e2e/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile
COPY e2e/playwright.config.ts ./
COPY e2e/tests ./tests
CMD ["pnpm", "exec", "playwright", "test"]
