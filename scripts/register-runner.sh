#!/usr/bin/env bash
# Register an EC2 host as a self-hosted GitHub Actions runner with the label lab-<role>.
# Uses SSM Session Manager (no SSH, no port 22, per lab rules).
#
# Usage: scripts/register-runner.sh <role>   (role = app | platform | llm)
#
# Requires:
#   - gh CLI authenticated to your repo
#   - AWS credentials with ssm:StartSession and ssm:SendCommand on the instance
#   - terraform outputs applied (reads instance ID from infra/live)
#
# The runner runs as the `runner` user (created by the host module's user-data)
# and uses the EC2 instance profile for AWS access — no static credentials.
set -euo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""

role=${1:?usage: scripts/register-runner.sh <role>  (app | platform | llm)}
root="$(cd "$(dirname "$0")/.." && pwd)"

# Validate role
case "$role" in
  app | platform | llm) ;;
  *) echo "role must be app, platform or llm" >&2; exit 1 ;;
esac

label="lab-${role}"
output_key="${role}_instance_id"

echo "==> Getting ${role} instance ID from Terraform outputs..."
instance_id=$(terraform -chdir="$root/infra/live" output -raw "$output_key")
echo "    Instance: $instance_id"

echo "==> Waiting for cloud-init to finish (/var/lib/lab-setup-done)..."
for i in {1..30}; do
  status=$(aws ssm send-command \
    --instance-ids "$instance_id" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["test -f /var/lib/lab-setup-done && echo READY || echo WAITING"]' \
    --query "Command.CommandId" --output text)
  sleep 3
  res=$(aws ssm get-command-invocation --command-id "$status" --instance-id "$instance_id" --query "StandardOutputContent" --output text 2>/dev/null || echo "")
  if [[ "$res" == *"READY"* ]]; then
    echo "    Host setup ready."
    break
  fi
  echo "    Waiting for host setup ($i/30)..."
  sleep 5
done

echo "==> Getting runner registration token from GitHub..."
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
reg_token=$(gh api -X POST "repos/$repo/actions/runners/registration-token" -q .token)
runner_url="https://github.com/${repo}"
runner_version=$(gh api repos/actions/runner/releases/latest -q .tag_name | sed 's/^v//')
echo "    Runner version: $runner_version"

# Build the script to run on the host as root (which delegates to runner user)
script=$(printf '%s\n' \
  "set -euxo pipefail" \
  "cd /opt/actions-runner" \
  "rm -rf *" \
  "curl -fsSL https://github.com/actions/runner/releases/download/v${runner_version}/actions-runner-linux-arm64-${runner_version}.tar.gz | tar -xz" \
  "chown -R runner:runner /opt/actions-runner" \
  "sudo -u runner ./config.sh --url '${runner_url}' --token '${reg_token}' --labels '${label}' --name '${label}' --unattended --replace" \
  "./svc.sh install runner || true" \
  "./svc.sh start || true" \
  "./svc.sh status || true")

echo "==> Sending runner install+configure+start command via SSM to ${instance_id}..."
command_id=$(aws ssm send-command \
  --instance-ids "$instance_id" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=$(printf '%s' "$script" | jq -Rsc 'split("\n") | map(select(length > 0))')" \
  --comment "Register ${label} runner" \
  --query "Command.CommandId" \
  --output text)

echo "==> Waiting for registration command ${command_id} to complete..."
for i in {1..30}; do
  status=$(aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance_id" --query "Status" --output text 2>/dev/null || echo "Pending")
  if [[ "$status" == "Success" || "$status" == "Failed" ]]; then
    break
  fi
  sleep 5
done

output=$(aws ssm get-command-invocation \
  --command-id "$command_id" \
  --instance-id "$instance_id" \
  --query "StandardOutputContent" \
  --output text)
echo "$output"

stderr=$(aws ssm get-command-invocation \
  --command-id "$command_id" \
  --instance-id "$instance_id" \
  --query "StandardErrorContent" \
  --output text)
if [ -n "$stderr" ]; then
  echo "STDERR: $stderr" >&2
fi

echo ""
echo "==> Runner registered. Verify at: https://github.com/${repo}/settings/actions/runners"
