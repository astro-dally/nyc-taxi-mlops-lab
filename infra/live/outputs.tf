# Outputs listed in contracts/runtime.yaml → terraform_outputs.
# scripts/register-runner.sh, scripts/catch-up.sh and the grader read them by these exact names.

output "app_public_ip" {
  value       = module.app.public_ip
  description = "Elastic IP of the app host (Traefik, port 80)."
}

output "app_instance_id" {
  value       = module.app.instance_id
  description = "Instance ID for SSM shell and port forwarding."
}

output "platform_instance_id" {
  value       = module.platform.instance_id
  description = "Instance ID for SSM shell and port forwarding."
}

output "llm_instance_id" {
  value       = module.llm.instance_id
  description = "Instance ID for SSM shell and port forwarding."
}

output "rds_endpoint" {
  value       = module.rds.endpoint
  description = "RDS Postgres host (without port)."
}

output "artifact_bucket" {
  value       = module.artifact_bucket.name
  description = "S3 bucket for MLflow artifacts and training data."
}

# Not in runtime.yaml terraform_outputs, but useful for wiring env vars.
output "platform_private_ip" {
  value       = module.platform.private_ip
  description = "Private IP of the platform host (for MLFLOW_TRACKING_URI in later stages)."
}

output "llm_private_ip" {
  value       = module.llm.private_ip
  description = "Private IP of the LLM host (for LLM_HOST in later stages)."
}
