# 001: Runner credentials

Stage: S0 · Date: 2026-11-21 · Author: (you) · Drafted by agent: yes

## Choice

The app host's self-hosted runner uses the **EC2 instance profile** (LabInstanceProfile / LabRole) for
AWS access. No static session credentials are stored in GitHub secrets for the deploy job.

## Rejected alternative

Store the current Learner Lab session credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_SESSION_TOKEN`) in GitHub repository secrets (via `scripts/gh-secrets.sh`) and inject them into
the deploy job as environment variables, the same way `scripts/gh-secrets.sh` does for the destroy
workflow.

## Why

| Dimension | Instance profile | Static session credentials |
|---|---|---|
| Credential lifetime | Rotate automatically every hour via IMDS | Die when the Learner Lab session ends (~4 h); need re-running `gh-secrets.sh` after every Start Lab |
| Attack surface | Never leave the host; not visible in workflow logs or GitHub UI | Stored in GitHub secrets; every job that reads them is a potential exfiltration point |
| Operational friction | Zero: runner starts, profile is there | Re-run `gh-secrets.sh` after every session restart |
| Scope | Only what LabRole allows; already the least-privilege we can get in this lab | Same scope, but credentials are more portable |

The instance profile wins on every dimension: it rotates automatically, never leaves the host, and
removes a manual step after every session restart. The only reason to reach for static credentials
would be a runner that isn't on EC2 at all — which is not our situation.

## What would show this was wrong

If the IMDS hop limit (currently 2, so containers can reach it) is insufficient for a future service,
or if AWS changes how LabRole permissions are granted and the profile stops giving the runner what it
needs, we'd need to revisit. A workflow failure with a 403 from IMDS or from GHCR would be the signal.
