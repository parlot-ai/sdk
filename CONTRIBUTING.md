# Contributing

## Pull requests only

Never push directly to `main`. Open a branch, create a PR, get review, then **squash-merge**.

Squash-merge uses the **PR title** as the commit on `main`. That commit feeds [Release Please](https://github.com/googleapis/release-please), so titles must follow Conventional Commits.

## PR title check

A required GitHub Action (`Validate PR title`) rejects non-conventional titles.

| Prefix | Typical release effect |
| --- | --- |
| `feat:` | version bump |
| `fix:` / `perf:` | patch bump |
| `feat!:` / `fix!:` | major / breaking |
| `chore:`, `docs:`, `ci:`, `test:`, `refactor:`, `build:`, `style:`, `security:`, `deps:` | usually no bump |

Examples: `feat: capture AMD latency`, `fix: flush spans on shutdown`, `docs: update install snippet`.

## Releases (SDK)

Merging the Release Please PR cuts the package tag(s) and changelog. SDK releases **do not** deploy Parlot Cloud staging/production.

Public docs: on push to `main`, the Docs workflow dispatches **Deploy website** on platform (`environment=staging`). Production docs ship via platform **Deploy website** with `environment=production`.
