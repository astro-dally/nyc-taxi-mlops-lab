# S2: wire infra/modules/notebook (the SageMaker notebook) into this root module, let it reach MLflow
# on the platform host (port 5000, runtime.yaml), and output its name as notebook_name.
# Set github_repo in terraform.tfvars: the notebook clones your public repo.

module "notebook" {
  count     = var.github_repo != null ? 1 : 0
  source    = "../modules/notebook"
  name      = "lab"
  subnet_id = data.aws_subnets.all.ids[0]
  repo_url  = "https://github.com/${var.github_repo}.git"
  env = {
    MLFLOW_TRACKING_URI = "http://${module.platform.private_ip}:5000"
    REDSHIFT_CLUSTER_ID = module.redshift.cluster_id
    REDSHIFT_DATABASE   = module.redshift.database
    REDSHIFT_DB_USER    = "labadmin"
    LAB_DATA_BUCKET     = "nst-mlops-2026"
    LAB_ARTIFACT_BUCKET = module.artifact_bucket.name
  }
}

output "notebook_name" {
  value       = try(module.notebook[0].name, null)
  description = "SageMaker notebook instance name."
}
