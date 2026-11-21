# 006: Distribution and sort keys for trip tables

Stage: S1 · Date: 2026-11-21 · Author: (you) · Drafted by agent: yes

## Choice

- **Sort Key**: `tpep_pickup_datetime` on `ingest.raw_trips` and `pickup_at` on `staging.stg_trips`.
- **Distribution Style**: `DISTSTYLE EVEN` (or `AUTO`) on `raw_trips` and `stg_trips`; `DISTSTYLE ALL` on `ingest.taxi_zones`.

## Rejected alternative

Use `DISTKEY (pulocationid)` on the trip tables to colocate with `ingest.taxi_zones`.

## Why

1. **Zone Pruning (Sort Key)**: Nearly all analytics, partitioning, and feature engineering queries filter or group by timestamp/month/hour (`WHERE pickup_at BETWEEN ...` or `DATE_TRUNC`). A sort key on pickup timestamp allows Redshift 1MB block zone maps to prune >90% of disk blocks during scans.
2. **Data Skew Avoidance (Dist Key)**: NYC taxi rides are heavily concentrated in Midtown and Lower Manhattan. Distributing by `pulocationid` creates severe data skew across cluster slices, leaving most slices idle while one slice handles disproportionate compute.
3. **Broadcast Joins for Small Tables**: `ingest.taxi_zones` is a tiny lookup table of only 265 rows. Setting `DISTSTYLE ALL` replicates it to all compute nodes, enabling 100% local joins with `stg_trips` without requiring network hash joins or trip table distribution skew.

## What would show this was wrong

If a multi-node Redshift cluster shows network broadcast bottlenecks during joins on non-zone columns, or if query patterns shift to predominantly zone-to-zone pair aggregations independent of time windows.
