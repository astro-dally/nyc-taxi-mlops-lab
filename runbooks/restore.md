# Runbook: Morning restore after Learner Lab session boundary

Owner: dally · Last run: 2026-11-22 · Time to restore last run: 12 min

## When to use it

Start of every working day, or after a Learner Lab 4-hour session expiry:
- `scripts/health.sh` reports FAIL for session, EC2 hosts, RDS, or Redshift.
- Riders receive static fallback quotes (`"alias": "static"` or 12.25 min) instead of champion quotes (`"alias": "champion"`).
- Port-forwarding to Dagster (3000) or MLflow (5000) fails with connection refused.

## Before you start

1. Log into AWS Academy Learner Lab web console.
2. Click **Start Lab** and wait for the circle to turn green.
3. Open **AWS Details** > **AWS CLI**, copy the temporary session credentials (`[default]` section: `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`), and export them in your local terminal.
4. Verify AWS identity: `aws sts get-caller-identity`.

## Steps

| # | Check (command) | Healthy looks like | If not: fix (command) | Took | Automated? |
|---|---|---|---|---|---|
| 1 | `aws sts get-caller-identity` | JSON with `LabRole` ARN | Export fresh AWS credentials from AWS Academy console | 1 min | No (SSO/MFA requires human) |
| 2 | `curl -s https://checkip.amazonaws.com` vs `grep ingress_cidrs infra/live/terraform.tfvars` | Laptop IP is listed in `ingress_cidrs` | Update `ingress_cidrs` in `infra/live/terraform.tfvars` and run `terraform apply` (or update SG ingress via AWS CLI) | 1 min | Partially (can be scripted) |
| 3 | `aws ec2 describe-instances --filters Name=tag:project,Values=mlops-lab --query 'Reservations[].Instances[].[Tags[?Key==\`role\`]|[0].Value,State.Name]' --output text` | `app running`, `platform running`, `llm running` | `aws ec2 start-instances --instance-ids $(aws ec2 describe-instances --filters Name=tag:project,Values=mlops-lab Name=instance-state-name,Values=stopped --query 'Reservations[].Instances[].InstanceId' --output text)` | 2 min | Yes (`scripts/restore.sh`) |
| 4 | `aws rds describe-db-instances --db-instance-identifier lab --query 'DBInstances[0].DBInstanceStatus' --output text` | `available` | `aws rds start-db-instance --db-instance-identifier lab` (wait until `available`) | 7 min | Yes (`scripts/restore.sh`) |
| 5 | `aws redshift describe-clusters --cluster-identifier lab --query 'Clusters[0].ClusterStatus' --output text` | `available` | `aws redshift resume-cluster --cluster-identifier lab` (wait until `available`) | 3 min | Yes (`scripts/restore.sh`) |
| 6 | `aws sagemaker describe-notebook-instance --notebook-instance-name lab --query NotebookInstanceStatus --output text` | `Stopped` (cost-saving) or `InService` | `aws sagemaker start-notebook-instance --notebook-instance-name lab` (only if interactive EDA notebook needed) | 5 min | No (kept manual to avoid credit burn) |
| 7 | `gh api repos/astro-dally/nyc-taxi-mlops-lab/actions/runners --jq '.runners[] \| "\(.name)=\(.status)"'` | `lab-app=online`, `lab-platform=online` | Runners auto-start via systemd; if stuck, SSM into host: `sudo systemctl restart actions.runner.*` | 30s | Yes (systemd auto-starts on boot) |
| 8 | `curl -fsS http://100.63.24.83/predict -H 'Content-Type: application/json' -d '{"pickup_zone_id": 132, "dropoff_zone_id": 230, "pickup_datetime": "2024-03-08T17:05:00"}'` | JSON response with `"model":{"alias":"champion","version":"2"}` | If champion container lost model during MLflow restart: `deploy/web.sh reload champion` on app host | 15s | Yes (containers retry with restart: unless-stopped) |
| 9 | `gh workflow run status.yaml --repo astro-dally/nyc-taxi-mlops-lab` | Status run completes green, artifact shows RDS and Redshift available | Check status workflow logs and verify Dagster code location | 2 min | Yes (scheduled cron & dispatch) |

## Done when

1. `scripts/health.sh` exits 0 with all checks `OK`.
2. `curl -X POST http://<app_public_ip>/predict` returns `"alias": "champion"` and the promoted champion version.
3. The `status` GitHub Action run is green and uploads the `lab-status` artifact reporting RDS and Redshift `available`.

## What we automated, and what we left as a step

- See decision record [012-what-to-automate.md](../decisions/012-what-to-automate.md).
- **Automated in `scripts/restore.sh`**: Starting stopped EC2 instances, waking stopped RDS instances, resuming paused Redshift clusters, waiting for service convergence, and running health checks.
- **Left as manual steps**:
  1. *AWS Credentials export*: AWS Academy console enforces human SSO login and periodic session expiration; automation cannot generate session tokens without defeating credential access controls.
  2. *SageMaker Notebook startup*: Stopped notebooks cost storage only ($0.05/mo vs $0.05/hr compute). Starting it automatically would unnecessarily consume Learner Lab budget on days when work is focused on CI/CD, pipelines, or serving rather than exploratory notebooks.
