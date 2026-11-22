"""S6: the wiki RAG branch, in the `rag` database on RDS (pgvector), on a daily schedule.

- wiki_pages: the published pages from the ops wiki (resource `wiki`: labpipes/wiki.py). Store each
  page's ETag and send it next time: an unchanged page then costs a 304 and no body.
- wiki_chunks: split changed pages with labpipes.chunking.chunk_markdown (chunk size and overlap are
  decision 015) and store the chunks; use Chunk.content_hash as the id so unchanged text keeps it.
- wiki_embeddings: embed only the chunks that have no vector yet (resource `embed`: nomic-embed-text,
  768 dimensions) and store them as pgvector `vector(768)`, with an index (HNSW or IVFFlat: decision 016).
- A blocking check that every chunk has a vector, and a schedule (and a job you can run by hand with
  scripts/dagster-run.sh) for the three.
The RDS admin connection comes from the `rag` resource (RagStore.connect); `create extension vector`
works there. Copy asset and check shapes from pipelines/reference/patterns.py.
"""

import dagster as dg
from dagster import AssetExecutionContext

from labpipes.chunking import chunk_markdown
from labpipes.resources import LlmEmbed, RagStore, WikiApi

# Decision 015: Chunk size and overlap
CHUNK_MAX_TOKENS = 150
CHUNK_OVERLAP_TOKENS = 30


def _vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


@dg.asset(group_name="rag")
def wiki_pages(context: AssetExecutionContext, wiki: WikiApi, rag: RagStore) -> dg.MaterializeResult:
    """Fetch published wiki pages conditionally with ETags."""
    client = wiki.client()
    pages_list = client.pages()
    total_pages = len(pages_list)

    with rag.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    etag TEXT NOT NULL,
                    body TEXT NOT NULL,
                    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            cur.execute("SELECT id, etag FROM pages;")
            existing_etags = dict(cur.fetchall())

            fetched = 0
            unchanged = 0

            for pref in pages_list:
                etag = existing_etags.get(pref.id)
                page = client.page(pref.id, etag=etag)
                if page is None:
                    unchanged += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO pages (id, title, updated_at, etag, body, fetched_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            updated_at = EXCLUDED.updated_at,
                            etag = EXCLUDED.etag,
                            body = EXCLUDED.body,
                            fetched_at = NOW();
                        """,
                        (page.id, page.title, page.updated_at, page.etag, page.body),
                    )
                    fetched += 1
            conn.commit()

    context.log.info(f"Wiki pages: {fetched} fetched, {unchanged} unchanged (304), {total_pages} total")
    return dg.MaterializeResult(
        metadata={
            "fetched": dg.MetadataValue.int(fetched),
            "unchanged": dg.MetadataValue.int(unchanged),
            "total": dg.MetadataValue.int(total_pages),
        }
    )


@dg.asset(deps=[wiki_pages], group_name="rag")
def wiki_chunks(context: AssetExecutionContext, rag: RagStore) -> dg.MaterializeResult:
    """Split wiki pages into content-hashed chunks."""
    with rag.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    chunk_index INT NOT NULL,
                    heading TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tokens INT NOT NULL,
                    embedding vector(768)
                );
            """)
            cur.execute("SELECT id, title, body FROM pages;")
            pages = cur.fetchall()

            total_chunks = 0
            new_chunks = 0

            for page_id, title, body in pages:
                chunks = chunk_markdown(title, body, max_tokens=CHUNK_MAX_TOKENS, overlap_tokens=CHUNK_OVERLAP_TOKENS)
                valid_chunk_ids = []
                for c in chunks:
                    c_id = c.content_hash(page_id)
                    valid_chunk_ids.append(c_id)
                    total_chunks += 1
                    cur.execute(
                        """
                        INSERT INTO chunks (id, page_id, chunk_index, heading, content, tokens)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                        """,
                        (c_id, page_id, c.index, c.heading, c.text, c.tokens),
                    )
                    if cur.rowcount > 0:
                        new_chunks += 1

                # Clean up any removed chunks for this page
                if valid_chunk_ids:
                    cur.execute("DELETE FROM chunks WHERE page_id = %s AND id NOT IN %s;", (page_id, tuple(valid_chunk_ids)))
                else:
                    cur.execute("DELETE FROM chunks WHERE page_id = %s;", (page_id,))

            conn.commit()

    context.log.info(f"Wiki chunks: {total_chunks} total, {new_chunks} new chunks created")
    return dg.MaterializeResult(
        metadata={
            "chunks": dg.MetadataValue.int(total_chunks),
            "new_chunks": dg.MetadataValue.int(new_chunks),
        }
    )


@dg.asset(deps=[wiki_chunks], group_name="rag")
def wiki_embeddings(context: AssetExecutionContext, rag: RagStore, embed: LlmEmbed) -> dg.MaterializeResult:
    """Embed chunks missing embeddings and maintain vector index."""
    with rag.connect() as conn:
        with conn.cursor() as cur:
            # Ensure pgvector extension exists
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("SELECT id, content FROM chunks WHERE embedding IS NULL ORDER BY page_id, chunk_index;")
            unembedded = cur.fetchall()

            embedded_count = 0
            if unembedded:
                chunk_ids = [row[0] for row in unembedded]
                texts = [row[1] for row in unembedded]
                context.log.info(f"Embedding {len(texts)} chunks via nomic-embed-text...")
                vectors = embed.embed_documents(texts)
                for c_id, vec in zip(chunk_ids, vectors, strict=True):
                    cur.execute(
                        "UPDATE chunks SET embedding = %s::vector WHERE id = %s;",
                        (_vector_literal(vec), c_id),
                    )
                    embedded_count += 1

            # Decision 016: HNSW index on cosine distance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
                ON chunks USING hnsw (embedding vector_cosine_ops);
            """)

            cur.execute("SELECT count(*) FROM chunks WHERE embedding IS NOT NULL;")
            total_embedded = cur.fetchone()[0]
            conn.commit()

    context.log.info(f"Wiki embeddings: {embedded_count} newly embedded, {total_embedded} total embeddings")
    return dg.MaterializeResult(
        metadata={
            "embedded": dg.MetadataValue.int(embedded_count),
            "total_embedded": dg.MetadataValue.int(total_embedded),
        }
    )


@dg.asset_check(asset=wiki_embeddings, blocking=True, description="Every wiki chunk has an embedding vector.")
def wiki_embeddings_complete(rag: RagStore) -> dg.AssetCheckResult:
    with rag.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks WHERE embedding IS NULL;")
            missing = cur.fetchone()[0]

    return dg.AssetCheckResult(
        passed=missing == 0,
        severity=dg.AssetCheckSeverity.ERROR,
        description=f"{missing} chunk(s) missing embedding vector" if missing > 0 else "All chunks embedded",
        metadata={"missing_embeddings": dg.MetadataValue.int(missing)},
    )


ingest_wiki = dg.define_asset_job(
    "ingest_wiki",
    selection=dg.AssetSelection.groups("rag"),
    description="Daily ingestion of ops wiki pages, chunks, and embeddings.",
)

daily_wiki_schedule = dg.ScheduleDefinition(
    name="daily_wiki_schedule",
    job=ingest_wiki,
    cron_schedule="0 6 * * *",
)
