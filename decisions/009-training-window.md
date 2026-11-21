# 009: Training window and holdout month

Stage: S2 · Date: 2026-11-21 · Author: dally · Drafted by agent: yes

## Choice

Train on a 3-month window from January through March 2024 (`2024-01..2024-03`, ~9.5 million trips) and evaluate holdout performance on April 2024 (`2024-04`, ~3.5 million trips).

## Rejected alternative

A 2-month training window (`2024-02..2024-03`) or a random cross-validation split across all four months.

## Why

Taxi trip durations exhibit seasonal and temporal trends (weather, holidays, changing city construction). Evaluating on the subsequent calendar month simulates real-world production conditions where models predict future, unseen traffic dynamics. Using three months for training (~9.5M trips) provides sufficient statistical coverage across rare zone-pair trajectories and transitions from winter to early spring, while April 2024 provides an authentic out-of-time test set.

## What would show this was wrong

If training on three months exceeds the memory or execution time budget of the Graviton platform host, or if temporal drift between Q1 and April is so extreme that a rolling 30-day window outperforms the 90-day seasonal window.
