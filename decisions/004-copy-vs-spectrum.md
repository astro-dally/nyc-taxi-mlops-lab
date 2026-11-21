# 004: Ingestion strategy: Redshift COPY vs Spectrum

Stage: S1 · Date: 2026-11-21 · Author: (you) · Drafted by agent: yes

## Choice

Load each monthly trip Parquet file into Redshift managed storage using the native `COPY` command into `ingest.raw_trips`. Each month's load is wrapped in an idempotent transaction (`DELETE FROM ingest.raw_trips WHERE source_file = ...` followed by `COPY`).

## Rejected alternative

Use Redshift Spectrum to create an external schema and query the Parquet files directly in S3 without moving data into Redshift tables.

## Why

1. **Downstream Query Performance**: Redshift columnar storage with local block-level zone maps and compression yields sub-second aggregations for the `zone_hour_stats` mart and feature materialization. Spectrum queries incur S3 GET network latency on every query.
2. **Cost Predictability**: Redshift ra3.large compute and managed storage are fixed-cost in our lab environment, whereas Spectrum charges $5.00 per TB scanned. Frequent sensor runs and pipeline retries against external tables accumulate scanning costs.
3. **Transactional Idempotency**: `COPY` allows atomic reload within a single transaction in Redshift. Spectrum relies on file presence in S3 prefixes, making partial loads or schema drifts harder to isolate atomically at the database layer.

## What would show this was wrong

If monthly data volumes grew beyond the Redshift cluster's managed storage capacity (exceeding 100 GB in Learner Lab), or if files arrived in micro-batches (e.g. streaming every 5 minutes) where COPY overhead dominates, Spectrum or Athena querying in place would be more suitable.
