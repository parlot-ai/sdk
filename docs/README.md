# Parlot SDK docs

Public Docusaurus site for the Parlot SDK. Canonical URL: **https://parlot.ai/docs**.

Layout follows an ElevenLabs/Fern-inspired three-column docs shell (section tabs, cards, local search) with Parlot branding via `@parlot/docs-theme`.

```bash
cd docs
bun install
bun start          # http://127.0.0.1:3000/docs/
bun run build
bun run check:leak # after build — private-content leak guard
```

Production publishes automatically: on push to `main` under `docs/**`, the Docs
workflow dispatches `sdk-docs-updated` to `parlot-ai/platform`, which runs
**Deploy website** (builds this site into Worker assets at `/docs/`). Requires
repo secret `PLATFORM_DISPATCH_TOKEN` (fine-grained PAT on platform with
Contents: Read and write). Manual fallback: Actions → Deploy website → Run workflow.

Theme is vendored under `vendor/docs-theme` (copy of platform `@parlot/docs-theme`).
Standalone clones use the vendored copy as-is. When developing next to a
`platform` checkout, refresh with:

```bash
bun run sync-theme   # also refreshes node_modules copy
```

CI: `.github/workflows/docs.yml` builds and runs the leak check. Local Compose serves this site at http://127.0.0.1:3000/docs/ (see platform `docker-compose.yml`).
