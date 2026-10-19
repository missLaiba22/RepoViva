# Build from the repo root: docker build -f frontend/Dockerfile .
# Caddy serves the built app and proxies /v1 like the Vite dev server (decision 063).
FROM node:22.12.0-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM caddy:2.10.2-alpine
COPY --from=build /app/dist /srv
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
