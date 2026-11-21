# 005: Data-quality checks: blocking vs warning

Stage: S1 · Date: 2026-11-21 · Author: (you) · Drafted by agent: yes

## Choice

- **Blocking checks**:
  - `schema_contract` on `trip_files`: blocks before COPY if the Parquet footer columns or data types mismatch `contracts/trips.schema.yaml`.
  - `has_rows` on `stg_trips`: blocks if row count is 0.
  - `plausible_dates` on `stg_trips`: blocks if more than 2% of trips have pickup dates outside the partition month.
- **Warning checks**:
  - `duration_plausible` on `stg_trips`: warns if trips with non-positive duration (`duration_min <= 0`) or extreme duration (`> 180` minutes) exceed 2%.
  - `valid_zones` on `stg_trips`: warns if pickup zone IDs outside the TLC taxi zones (1..263) exceed 2%.

## Rejected alternative

Make all quality checks (including duration > 0 and strict zone bounds) blocking with zero tolerance.

## Why

Real-world TLC Yellow Taxi records contain intrinsic sensor noise: meter cancellations, zero-distance meter resets, and stray trips with meter clock misconfigurations occur in every single historical month (~0.5%–1.2% of rows). 

A zero-tolerance blocking policy on duration would cause every legitimate monthly ingestion to fail, halting all downstream pipeline execution. By designating noise checks as warnings (with downstream filtering in `trip_features` in S2), we protect the mart from total failures while strictly blocking against actual structural corruption (schema mismatch, empty files, completely mismatched months).

## What would show this was wrong

If downstream mart statistics (`zone_hour_stats`) show skewed percentiles caused by negative or extreme duration trips that were only warned about, or if upstream data provider TLC institutes perfect pre-cleaning, making zero tolerance viable.
