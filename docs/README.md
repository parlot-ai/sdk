# Parlot SDK docs

Public Docusaurus site for the Parlot SDK. Canonical URL: **https://parlot.ai/docs**.

Layout uses an Obsidian Flux–aligned `@parlot/docs-theme` shell (Inter + JetBrains Mono, shared brand hexes, section tabs, cards, local search) so `/docs` feels continuous with the marketing site.

```bash
# From repo root — uv is required (API pages are generated from Python docstrings)
uv sync --group dev

cd docs
bun install
bun start          # http://127.0.0.1:3000/docs/
bun run build
bun run check:leak # after build — private-content leak guard
```

`prestart` / `prebuild` run:

- `scripts/sync-changelog.sh` — package CHANGELOGs → `docs/reference/changelog.md`
- `scripts/sync-api.sh` — Griffe over workspace packages → `docs/api/{configure,livekit,langgraph,core}.md`

Regenerate API docs alone with `bun run sync-api` (or `uv run python docs/scripts/generate-api.py` from the repo root).

Production publishes automatically: on push to `main` under `docs/**` (or package Python / CHANGELOG paths), the Docs
workflow dispatches `sdk-docs-updated` to `parlot-ai/platform`, which runs
**Deploy website** (builds this site into Worker assets at `/docs/`). Requires
repo secret `PARLOT_CROSS_REPO_TOKEN` (fine-grained PAT on platform with
Contents: Read and write). Manual fallback: Actions → Deploy website → Run workflow.

Theme is vendored under `vendor/docs-theme` (copy of platform `@parlot/docs-theme`).
Standalone clones use the vendored copy as-is. When developing next to a
`platform` checkout, refresh with:

```bash
bun run sync-theme   # also refreshes node_modules copy
```

CI: `.github/workflows/docs.yml` syncs the uv workspace, builds, and runs the leak check. Local Compose serves this site at http://127.0.0.1:3000/docs/ (see platform `docker-compose.yml`).
