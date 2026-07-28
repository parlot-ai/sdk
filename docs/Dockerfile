# Public SDK docs (Docusaurus) — static nginx or Bun dev server
#
# Build from parlot.ai repo root (sibling sdk + platform):
#   docker build -f sdk/docs/Dockerfile .
#   docker build -f sdk/docs/Dockerfile --target dev .

FROM oven/bun:1 AS builder
WORKDIR /app

COPY sdk/docs/package.json sdk/docs/bun.lock ./
COPY sdk/docs/vendor ./vendor
COPY sdk/docs/docs ./docs
COPY sdk/docs/src ./src
COPY sdk/docs/static ./static
COPY sdk/docs/docusaurus.config.ts sdk/docs/sidebars.ts sdk/docs/tsconfig.json ./

RUN bun install --frozen-lockfile
RUN bun run build

FROM nginx:1.27-alpine AS runner
COPY sdk/docs/nginx.docker.conf /etc/nginx/conf.d/default.conf
# baseUrl /docs/ — asset URLs are /docs/assets/... so mount build under /docs/
COPY --from=builder /app/build /usr/share/nginx/html/docs
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

FROM oven/bun:1 AS dev
WORKDIR /app

COPY sdk/docs/package.json sdk/docs/bun.lock ./
COPY sdk/docs/vendor ./vendor
COPY sdk/docs/docs ./docs
COPY sdk/docs/src ./src
COPY sdk/docs/static ./static
COPY sdk/docs/docusaurus.config.ts sdk/docs/sidebars.ts sdk/docs/tsconfig.json ./
COPY sdk/docs/scripts ./scripts

RUN bun install --frozen-lockfile

EXPOSE 3000
CMD ["bunx", "docusaurus", "start", "--host", "0.0.0.0", "--port", "3000"]
