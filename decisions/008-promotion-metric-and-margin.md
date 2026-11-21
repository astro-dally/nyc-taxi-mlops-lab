# 008: Promotion metric and margin

Stage: S2 · Date: 2026-11-21 · Author: dally · Drafted by agent: yes

## Choice

A candidate model qualifies for the `challenger` alias in MLflow if its holdout Mean Absolute Error is at least 0.05 minutes (~3 seconds) better than the baseline/champion (`mae_min < champion_mae_min - 0.05`) while keeping single-row p95 prediction latency strictly under 20 ms (`p95_latency_ms <= 20`).

## Rejected alternative

A strict beat policy (`mae_min < champion_mae_min`) without any margin requirement.

## Why

Training on large datasets with non-deterministic multi-threading or differing random seeds can produce minute metric fluctuations (e.g., 0.001 minutes) that represent statistical noise rather than genuine algorithmic improvement. Requiring an explicit 0.05-minute improvement ensures that promotions reflect meaningful predictive gains while preventing unnecessary downstream redeployments and model churn. The latency SLA ensures that complex tree depths do not compromise sub-20ms real-time serving performance.

## What would show this was wrong

If a model with major qualitative improvements on critical operational slices (e.g., airport trips or night-time trips) fails the promotion gate because its overall holdout MAE improvement was only 0.04 minutes, or if serving latency in production degrades significantly despite passing the in-process 20 ms benchmark.
