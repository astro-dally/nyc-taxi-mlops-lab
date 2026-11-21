# Security groups for the lab.
#
# Decision point (decisions/003-ingress-scope.md): who may reach port 80 on the app host?
# var.ingress_cidrs is set in terraform.tfvars (gitignored).
# No SSH / port 22 anywhere: shell access is SSM Session Manager.

# ── App host ────────────────────────────────────────────────────────────────
resource "aws_security_group" "app" {
  name        = "lab-app"
  description = "App host: HTTP from approved CIDRs, all egress."
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "lab-app" }
}

resource "aws_vpc_security_group_ingress_rule" "app_http" {
  for_each          = toset(var.ingress_cidrs)
  security_group_id = aws_security_group.app.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = each.value
  description       = "HTTP from ${each.value}"
}

resource "aws_vpc_security_group_egress_rule" "app_egress" {
  security_group_id = aws_security_group.app.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "All egress"
}

# ── Platform host ────────────────────────────────────────────────────────────
resource "aws_security_group" "platform" {
  name        = "lab-platform"
  description = "Platform host: MLflow from app, all egress."
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "lab-platform" }
}

resource "aws_vpc_security_group_ingress_rule" "platform_mlflow" {
  security_group_id            = aws_security_group.platform.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
  referenced_security_group_id = aws_security_group.app.id
  description                  = "MLflow from app host"
}

resource "aws_vpc_security_group_ingress_rule" "platform_mlflow_notebook" {
  count                        = var.github_repo != null ? 1 : 0
  security_group_id            = aws_security_group.platform.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
  referenced_security_group_id = module.notebook[0].security_group_id
  description                  = "MLflow from SageMaker notebook"
}

resource "aws_vpc_security_group_egress_rule" "platform_egress" {
  security_group_id = aws_security_group.platform.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "All egress"
}

# ── LLM host ────────────────────────────────────────────────────────────────
resource "aws_security_group" "llm" {
  name        = "lab-llm"
  description = "LLM host: chat and embed from app and platform, all egress."
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "lab-llm" }
}

resource "aws_vpc_security_group_ingress_rule" "llm_chat_from_app" {
  security_group_id            = aws_security_group.llm.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8081
  referenced_security_group_id = aws_security_group.app.id
  description                  = "LLM chat+embed from app host"
}

resource "aws_vpc_security_group_ingress_rule" "llm_chat_from_platform" {
  security_group_id            = aws_security_group.llm.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8081
  referenced_security_group_id = aws_security_group.platform.id
  description                  = "LLM chat+embed from platform host"
}

resource "aws_vpc_security_group_egress_rule" "llm_egress" {
  security_group_id = aws_security_group.llm.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "All egress"
}

# ── RDS ─────────────────────────────────────────────────────────────────────
resource "aws_security_group" "rds" {
  name        = "lab-rds"
  description = "RDS Postgres: from app and platform hosts only."
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "lab-rds" }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_app" {
  security_group_id            = aws_security_group.rds.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.app.id
  description                  = "Postgres from app host"
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_platform" {
  security_group_id            = aws_security_group.rds.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.platform.id
  description                  = "Postgres from platform host"
}

resource "aws_vpc_security_group_egress_rule" "rds_egress" {
  security_group_id = aws_security_group.rds.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "All egress"
}
