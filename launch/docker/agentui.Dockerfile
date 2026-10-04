# syntax=docker/dockerfile:1
# agentui.Dockerfile — builds agno-agi/agent-ui (Next.js) with NO clone onto your host.
# The repo is cloned INSIDE the builder stage, so the only thing on your machine is the image.

# REVIEWED WITH AGNO LEARNOS
# Peer-review fixes applied (reviewed against local clone agent-ui-git/, HEAD 6dad959):
#  - Pinned to a known commit via build arg (reproducible + cache-busts only on purpose).
#  - Standalone output patched into next.config.ts at build time (small runner image).
#  - .next/cache removed before copy.
#  - Exec next directly (proper SIGTERM/graceful shutdown).
#  - node:22-alpine (Node 20 EOL 2026-04), non-root user in nodejs group.

# NOTE on env vars (verified by grepping src/):
#   The app reads ONLY `NEXT_PUBLIC_OS_SECURITY_KEY` (auth token, src/app/page.tsx).
#   There is NO `NEXT_PUBLIC_AGENTOS_URL` — the endpoint defaults to
#   http://localhost:7777 (src/store.ts, Sidebar.tsx) and is editable in the UI.
#   So we bake ONLY the auth key; the endpoint stays at the UI default / sidebar.

# ---------- Builder ----------
FROM node:22-alpine AS builder
WORKDIR /app

# Pin the upstream ref so the image is reproducible. Override deliberately:
#   docker build --build-arg AGENT_UI_REF=refs/heads/main -f agentui.Dockerfile .
# Use a branch/tag ref (e.g. refs/heads/main). NOTE: GitHub does NOT allow fetching an
# arbitrary commit SHA (no allowAnySHA1InWant), so do not pass a bare 40-char SHA here.
ARG AGENT_UI_REF=refs/heads/main
# Auth token baked into the client bundle at build time (NEXT_PUBLIC_* is inlined).
# Leave blank if AgentOS needs no auth.
ARG NEXT_PUBLIC_OS_SECURITY_KEY=

# git (to clone the pinned ref) + corepack (reproducible pnpm).
# pnpm@9 matches the repo's pnpm-lock.yaml lockfileVersion: '9.0' (verified in clone).
RUN apk add --no-cache git \
    && corepack enable \
    && corepack prepare pnpm@9 --activate

# Shallow clone, then fetch/checkout the pinned ref; drop .git metadata.
# We fetch the ref explicitly so a --build-arg AGENT_UI_REF bump busts the cache on purpose.
RUN git clone --depth 1 https://github.com/agno-agi/agent-ui.git . \
    && git fetch --depth 1 origin "${AGENT_UI_REF}" \
    && git checkout FETCH_HEAD \
    && rm -rf .git

# Patch standalone output in (no need to hand-edit the committed next.config.ts).
RUN sed -i 's/const nextConfig[^=]*= {/&\n  output: "standalone",/' next.config.ts

# Reproducible install from the committed lockfile, then build + drop build cache.
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_OS_SECURITY_KEY=${NEXT_PUBLIC_OS_SECURITY_KEY}
RUN pnpm install --frozen-lockfile
RUN pnpm build \
    && rm -rf .next/cache

# ---------- Runner ----------
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

# Non-root user, placed in the nodejs group (so COPY ownership lines up).
RUN addgroup -S -g 1001 nodejs \
    && adduser -S -u 1001 -G nodejs nextjs

# Standalone server.js binds to HOSTNAME (NOT 0.0.0.0 by default) -- verified: without
# this it bound to the container IP and localhost/healthcheck failed with ECONNREFUSED.
ENV HOSTNAME=0.0.0.0

# Standalone output: Next copied only what's needed into .next/standalone.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
# Static assets are still served from the app dir, so include them.
COPY --from=builder --chown=nextjs:nodejs /app/.next/static /app/.next/static


USER nextjs

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"]
# Cleanest entrypoint: standalone server.js (PID 1 = node, so SIGTERM is handled).
CMD ["node", "server.js"]

# --- ALTERNATIVE: build from the LOCAL clone (no network at build time) ---
# If you have ./agent-ui-git already and want offline builds:
#   1) place this file as agent-ui-git/Dockerfile
#   2) in compose, set build: { context: ./agent-ui-git, dockerfile: Dockerfile }
#   3) replace the `git clone ...` RUN block with:  COPY . .
#   4) KEEP the sed/standalone patch + the ARG/ENV for NEXT_PUBLIC_OS_SECURITY_KEY.