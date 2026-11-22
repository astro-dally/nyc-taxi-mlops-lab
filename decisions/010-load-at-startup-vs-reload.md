# 010: Model loading: in-memory reload vs cold container restart

Stage: S3 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

Model serving containers load their initial model at boot time from MLflow according to their assigned alias (`champion` or `challenger`) and handle subsequent alias promotions via an internal `POST /reload` HTTP endpoint that fetches the newly aliased artifact and performs an atomic in-memory reference swap.

## Rejected alternative

Cold container restart (`docker compose restart` or recreate) whenever an MLflow alias changes.

## Why

A cold container restart incurs several seconds of downtime during which the container cannot serve traffic (causing 503s or forcing rideapp to fall back to static median duration quotes). In contrast, `POST /reload` fetches the new model and warms it in memory while the previous model continues to serve incoming inference requests. The memory reference is swapped atomically only when the new model is fully loaded and validated, ensuring continuous, zero-downtime inference with no dropped requests or fallback degradation for riders.

## What would show this was wrong

If repeated in-memory model reloads cause significant memory fragmentation or memory leaks in long-running Python processes on memory-constrained EC2 instances (e.g., t4g.medium), or if an unhandled dependency/environment drift between model artifacts requires a clean process restart.
