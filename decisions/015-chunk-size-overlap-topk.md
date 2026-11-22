# 015: Chunk size, overlap and top-k retrieval

Stage: S6 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

Chunk wiki pages with `max_tokens=150` and `overlap_tokens=30`, and retrieve `top_k=3` chunks for query answering.

## Rejected alternative

Larger chunks (`max_tokens=500`, `overlap_tokens=100`) with `top_k=5`.

## Why

The ops wiki pages are brief and modular (16 pages totaling ~1,100 words, averaging ~70 words per page). With `max_tokens=150`, 15 out of 16 pages naturally fit into a single cohesive chunk, and the largest page (`eta-quoting`) splits cleanly into two chunks with 30-token overlap to maintain semantic continuity across section boundaries.

On our CPU-based LLM host (Graviton `m8g.large`), prompt processing processes tokens at approximately 13 tokens/sec (~11 seconds per chunk). Retrieving `top_k=3` yields ~300–450 prompt tokens, providing sufficient domain coverage for policy questions while keeping prompt processing latency within ~25–35 seconds. Setting `top_k=5` or 500-token chunks would inflate prompt latency beyond 60 seconds without adding relevant context given the small page sizes.

## What would show this was wrong

If retrieval evaluation shows queries failing to retrieve the relevant policy paragraph (recall@3 < 90%), or if the wiki evolves to contain long multi-page manuals where 150-token chunks fracture semantic topics across multiple chunks.
