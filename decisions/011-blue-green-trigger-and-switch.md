# 011: Blue-green deployment trigger and traffic switch

Stage: S3 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

App deployments are automated in the CD workflow (`app-deploy.yaml`): the pipeline identifies the currently idle color (`blue` or `green`), boots the new container version, runs automated smoke tests against both `/version` (verifying Git SHA) and `/predict` (via the `X-Lab-Color` header), and upon passing, atomically switches 100% of live traffic to the newly deployed color via Traefik. The previous color remains running in Docker to allow instantaneous, zero-deployment rollback.

## Rejected alternative

Manual gate requiring human operator approval to flip traffic after deploying to the idle color.

## Why

Automating the switch behind robust smoke tests accelerates iteration and reduces human toil for routine app updates. Because Traefik dynamically re-routes traffic via an atomic file rename in the shared Docker volume (`deploy/web.sh switch <color>`) and the previous container remains running warm, a rollback can be executed in seconds via a single CLI command or workflow dispatch without requiring a container rebuild or redeploy.

## What would show this was wrong

If subtle behavioral or performance regressions pass the synthetic smoke test (`/version` and sample `/predict`) but cause live production failures, high error rates, or degraded user experiences that require manual emergency intervention.
