# 002: Image tag scheme

Stage: S0 · Date: 2026-11-21 · Author: (you) · Drafted by agent: yes

## Choice

Images are tagged `sha-<7-char-git-sha>` (e.g. `sha-a1b2c3d`). The CD workflow sets `IMAGE_TAG` to
the same value and passes it into the container as `IMAGE_TAG` env var, so `/version` echoes both the
tag and the full `GIT_SHA` build arg baked into the image. A rollback points at the previous commit's
tag: `docker compose up` with `IMAGE_TAG=sha-<old-sha>`.

## Rejected alternative

Use a build number or timestamp (e.g. `20240308-1234` or `run-${{ github.run_number }}`). This is the
standard approach in teams that treat CI run numbers as the canonical version, and it makes the tag
sortable chronologically without cloning the repo.

## Why

The commit SHA is the primary key of the deployment: every tool (GitHub UI, `git log`, CloudWatch,
the `/version` endpoint) speaks SHA. A tag like `sha-a1b2c3d` lets you go from "what's deployed?" to
"what changed?" in one step (`git show a1b2c3d`), without mapping through a build number.

A rollback is simply `IMAGE_TAG=sha-<previous>` — no separate "latest" or "stable" pointer to manage.
Run numbers or timestamps require an external mapping (CI logs, a database) to answer "what code is
this?". In a lab with one environment and infrequent deploys, the indirection adds cost without benefit.

The 7-char prefix keeps tags readable. Full SHAs would work too; the choice of length is cosmetic.

## What would show this was wrong

If we ever need to build multiple images from the same commit (e.g. a hotfix cherry-pick on a release
branch where two commits have the same 7-char prefix), we'd get a collision. At that point we'd add
the branch or run number as a disambiguator, e.g. `sha-<7>-<run>`.
