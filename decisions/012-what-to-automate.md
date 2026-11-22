# 012: What to automate and what to leave as a documented step in service restoration

Stage: S4 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

Automate infrastructure wake and health convergence in a single script (`scripts/restore.sh`): start stopped project EC2 instances, resume the paused Redshift cluster, start the stopped RDS Postgres database, wait for both to become `available`, and run `scripts/health.sh`. Leave AWS session credential acquisition and SageMaker notebook activation as manual documented runbook steps.

## Rejected alternative

Aggressive full-system automation that boots all services including the SageMaker notebook and automatically triggers pipeline materialization runs on host wake.

## Why

1. **Security and Platform Boundaries**: Learner Lab session tokens expire every 4 hours and require interactive SSO authentication via the AWS Academy console; automation cannot and should not attempt to bypass console authentication or fabricate tokens.
2. **Cost and Resource Preservation**: Running a SageMaker notebook (`ml.t3.medium`) costs active compute charges against a tight $100 Learner Lab credit cap. An idle stopped notebook costs storage pennies only. Since Day 2 work centers on pipelines, serving, blue-green deploys, and observability, the notebook is rarely needed; starting it by default would needlessly burn credits.
3. **Recovery Order and Toil Reduction**: RDS takes ~7 minutes and Redshift ~3 minutes to transition from stopped/paused to `available`. Waiting for each sequentially by hand is repetitive toil. Automating concurrent wake requests and status polling frees the engineer to review overnight commits and prepare daily work while the cloud converges.

## What would show this was wrong

If developers frequently forget to start the notebook when required and lose significant time waiting for it mid-task, or if the automation script masks an underlying AWS provisioning failure by infinitely waiting on an unresponsive RDS state.
