# 016: Vector index type: HNSW vs IVFFlat

Stage: S6 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

Use an HNSW (Hierarchical Navigable Small World) index with cosine distance (`vector_cosine_ops`) in pgvector on RDS Postgres.

## Rejected alternative

IVFFlat (Inverted File Flat) index.

## Why

HNSW constructs a multi-layer graph that supports incremental vector inserts and updates immediately without retraining or prior data clustering. In our daily wiki ingestion pipeline, pages start from zero and update incrementally daily. 

IVFFlat requires pre-clustering data into lists (k-means centroids) and requires an existing corpus before indexing (rule of thumb: thousands of vectors per list). On an empty or small table (our initial wiki has 17 chunks), IVFFlat cannot build a meaningful centroid structure, and recall degrades drastically as the vector distribution shifts. 

While HNSW consumes more memory and build time than IVFFlat at massive scale (e.g., 1M+ chunks), at our scale (dozens to thousands of chunks) the memory overhead is negligible (~a few megabytes), build time is instantaneous, and recall remains near-perfect (>98%) through continuous updates without needing periodic `REINDEX` or retraining.

## What would show this was wrong

If vector count grows past millions of chunks and RDS memory usage causes HNSW index graph pages to spill from cache to disk, slowing down vector searches compared to a memory-compact IVFFlat index.
