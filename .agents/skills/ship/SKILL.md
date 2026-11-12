---
name: ship
description: >-
  Required before committing, pushing, or opening a pull request in this repo.
  Use when the user asks to commit, push, land changes, or open a PR. Covers
  Conventional Commits for Release Please, never pushing main, and which
  prefixes bump vs not.
---

# Ship (commit / push / PR)

## Done looks like

- Conventional commit message on a non-`main` branch in this repository
- Pushed when the user asked to push
- PR opened only when the user asked (title must be Conventional Commits — the human’s squash-merge makes the **PR title** the commit on `main`)
- **Never merge the PR** and **never deploy / promote** as part of shipping — stop after the PR URL

Style: `fix: …`, `feat: …`, optional scope.

## Scope

Operate only inside this SDK repository. Do not assume sibling private checkouts or cloud deploy steps.

## Release Please

Squash-merge uses the **PR title** as the commit on `main`. That commit drives version bumps and changelogs.

- Bump: `feat`, `fix`, `perf` (use only when a bump is intended)
- Usually no bump: `chore`, `docs`, `ci`, `test`, `refactor`, `build`, `style`, `security`, `deps`
- Breaking: `feat!:` / `fix!:` or footer `BREAKING CHANGE:`

Allowed types match `.github/workflows/validate-pr-title.yml`. Do not invent types.

Source of truth for the prefix table and release flow: [CONTRIBUTING.md](../../../CONTRIBUTING.md).

## Guardrails

- If HEAD is `main`, create a branch first. Never push or `--force` to `main` / `master`.
- Do not commit secrets or `.env` files with credentials.
- Wait for an explicit commit / push / open-PR ask; do not ship unprompted.
- **Never merge a PR** — no `gh pr merge`, merge API, auto-merge enablement, or merging Release Please / dependabot PRs. “Ship,” “land,” “finish the todos,” green CI, or even an explicit “merge it” does **not** authorize the agent to merge; tell the user to merge in the GitHub UI.
- Prefer the goal and these constraints over a fixed sequence of git commands — inspect status, diff, and log, then act.
- If the PR changes `packages/core` or `packages/instrumentation-*`, call out in the PR body that a **follow-up meta floor bump** in `packages/meta/pyproject.toml` is required after the Release Please wheel hits PyPI (see `AGENTS.md`). Do not bump floors to unpublished versions in the feature PR.
