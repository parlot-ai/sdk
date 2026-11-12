# Parlot SDK docs

Public [Fumadocs](https://fumadocs.dev) site for the Parlot SDK. Canonical URL:
**https://parlot.ai/docs**.

Built with Fumadocs UI + React Router. Typography and colors follow the Obsidian
Flux system used on the marketing site so `/docs` feels continuous with
`parlot.ai`.

```bash
cd docs
bun install
bun run dev          # local docs site
bun run build
bun run check:leak   # after build — private-content leak guard
```

`prebuild` / `predev` run:

- `scripts/sync-changelog.sh` — package CHANGELOGs → docs content
- `scripts/build-pdoc.sh` — Python API reference
- `scripts/build-typedoc.sh` — TypeScript API reference (`@parlot/core`)

Regenerate TypeScript reference alone with `bun run build:ts`.

Staging publishes automatically: on push to `main` under `docs/**`, the Docs
workflow dispatches `sdk-docs-updated` to `parlot-ai/platform`, which runs
**Deploy website** (`environment=staging`) to `stg.parlot.ai` (embeds this site
under `/docs/`). Production: platform **Deploy website** with
`environment=production`. Requires repo secret `PARLOT_CROSS_REPO_TOKEN`
(fine-grained PAT on platform with Contents: Read and write). Manual fallback:
Actions → Deploy website → Run workflow.

CI: `.github/workflows/docs.yml` builds and runs the leak check. Local Compose
serves this site at http://127.0.0.1:3000/docs/ (see platform `docker-compose.yml`).
