# 014: Prometheus metrics series budget and relabeling rules

Stage: S5 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

Implement strict Prometheus metric and label relabeling in `observability/alloy/budget.alloy` to keep total active series across all lab hosts under 1,000 series (well below Grafana Cloud free tier's 10,000 limit): keep only metrics explicitly queried by dashboards and SLO rules, drop virtual network devices (`veth.*`, `br-.*`, `docker0`), drop non-root filesystems, and strip dynamic container IDs (`id`), image hashes, and container labels from cAdvisor.

## Rejected alternative

Permissive metric ingestion sending all raw cAdvisor container and host node_exporter series (~4,000–5,000 series).

## Why

Every container recreation during blue-green deployments (`app-blue`, `app-green`) or model promotions assigns a new Docker container ID and ephemeral virtual ethernet interface. Unfiltered cAdvisor metrics retain those old series in the Prometheus write-ahead log for up to two hours, causing series counts to spike dramatically after several successive deployments and quickly exhausting the 10,000 free-tier series ceiling. Stripping the `id` label and retaining only the stable container `name` (e.g., `lab-app-app-blue-1`) ensures that new deployments reuse existing series keys, guaranteeing zero series churn on deployment and reserving >8,000 series headroom for S6's LLM host and Langfuse telemetry.

## What would show this was wrong

If deep post-mortem debugging during an infrastructure incident requires dropped low-level metrics (e.g., container blkio throttling or virtual network packet drops) that cannot be retrieved directly from host system logs or SSM.
