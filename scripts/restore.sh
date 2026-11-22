#!/usr/bin/env bash
# Bring the lab back after a session end or overnight shutdown (S4).
#
#   scripts/restore.sh
#
# Starts stopped EC2 instances, starts RDS if stopped, resumes Redshift if paused,
# waits for databases to become available, and verifies lab health.
set -euo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
# Ensure standard system curl is used if third-party arch-mismatched curl exists in PATH
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

root="$(cd "$(dirname "$0")/.." && pwd)"

echo "== [1/5] Checking AWS credentials..."
if ! who=$(aws sts get-caller-identity --query Arn --output text 2>&1); then
  echo "ERROR: AWS credentials expired or invalid." >&2
  echo "Please start the lab in AWS Academy Learner Lab and export fresh session credentials." >&2
  echo "Details: $who" >&2
  exit 1
fi
echo "Authenticated as: ${who##*/}"

echo "== [2/5] Checking EC2 instances..."
stopped_instances=$(aws ec2 describe-instances \
  --filters Name=tag:project,Values=mlops-lab Name=instance-state-name,Values=stopped \
  --query 'Reservations[].Instances[].InstanceId' --output text)

if [[ -n "$stopped_instances" ]]; then
  echo "Starting stopped EC2 instances: $stopped_instances"
  aws ec2 start-instances --instance-ids $stopped_instances >/dev/null
else
  echo "All tagged EC2 instances are already running or starting."
fi

echo "== [3/5] Checking RDS Postgres database..."
rds_status=$(aws rds describe-db-instances --db-instance-identifier lab \
  --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "absent")

if [[ "$rds_status" == "stopped" ]]; then
  echo "Starting RDS instance 'lab'..."
  aws rds start-db-instance --db-instance-identifier lab >/dev/null
elif [[ "$rds_status" == "available" ]]; then
  echo "RDS instance 'lab' is already available."
else
  echo "RDS instance 'lab' status: $rds_status"
fi

echo "== [4/5] Checking Redshift cluster..."
rs_status=$(aws redshift describe-clusters --cluster-identifier lab \
  --query 'Clusters[0].ClusterStatus' --output text 2>/dev/null || echo "absent")

if [[ "$rs_status" == "paused" ]]; then
  echo "Resuming Redshift cluster 'lab'..."
  aws redshift resume-cluster --cluster-identifier lab >/dev/null
elif [[ "$rs_status" == "available" ]]; then
  echo "Redshift cluster 'lab' is already available."
else
  echo "Redshift cluster 'lab' status: $rs_status"
fi

echo "== [5/5] Waiting for RDS and Redshift to become available..."
max_attempts=45
attempt=1
while [[ $attempt -le $max_attempts ]]; do
  current_rds=$(aws rds describe-db-instances --db-instance-identifier lab \
    --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "unknown")
  current_rs=$(aws redshift describe-clusters --cluster-identifier lab \
    --query 'Clusters[0].ClusterStatus' --output text 2>/dev/null || echo "unknown")

  if [[ "$current_rds" == "available" && "$current_rs" == "available" ]]; then
    echo "RDS and Redshift are both available!"
    break
  fi

  echo "Attempt $attempt/$max_attempts: RDS is '$current_rds', Redshift is '$current_rs'. Waiting 15s..."
  sleep 15
  attempt=$((attempt + 1))
done

if [[ "$current_rds" != "available" || "$current_rs" != "available" ]]; then
  echo "WARNING: Databases did not reach 'available' within timeout (RDS: $current_rds, Redshift: $current_rs)." >&2
fi

echo
echo "== Running lab health check..."
"$root/scripts/health.sh"
