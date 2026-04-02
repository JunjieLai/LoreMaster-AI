"""
LoreMaster-AI ETL - Step 7: Embed

Generates vector embeddings for all text chunks using OpenAI
text-embedding-3-small (1536 dimensions). Processes in batches
with rate limiting and checkpoint/resume support.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from openai import OpenAI

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import EMBEDDING_DIMENSION
from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/chunks/wiki_chunks.jsonl")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/embeddings/wiki_embeddings.jsonl")
CHECKPOINT_PATH = os.path.join(PROJECT_ROOT, "data/processed/embeddings/.embed_checkpoint")

# OpenAI text-embedding-3-small config
MODEL = "text-embedding-3-small"
BATCH_SIZE = 100  # OpenAI supports up to 2048 inputs per request
MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds


def load_checkpoint():
    """Load the last processed chunk index for resume support."""
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            return int(f.read().strip())
    return 0


def save_checkpoint(index):
    """Save progress checkpoint."""
    with open(CHECKPOINT_PATH, "w") as f:
        f.write(str(index))


def embed_batch(client, texts):
    """Embed a batch of texts with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.embeddings.create(
                model=MODEL,
                input=texts,
            )
            return [item.embedding for item in response.data], response.usage.total_tokens
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (2 ** attempt)
                logger.warning("Embed attempt %d failed: %s. Retrying in %ds...", attempt + 1, e, wait)
                time.sleep(wait)
            else:
                raise


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set. Add it to .env file.")
        return

    client = OpenAI(api_key=api_key)

    logger.info("=" * 60)
    logger.info("LoreMaster-AI ETL Step 7: Embed")
    logger.info("=" * 60)
    logger.info("Model: %s", MODEL)
    logger.info("Dimension: %d", EMBEDDING_DIMENSION)
    logger.info("Batch size: %d", BATCH_SIZE)

    # Load all chunks
    logger.info("Loading chunks from %s ...", INPUT_PATH)
    chunks = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    logger.info("Loaded %d chunks", len(chunks))

    # Resume from checkpoint
    start_idx = load_checkpoint()
    if start_idx > 0:
        logger.info("Resuming from checkpoint: chunk %d", start_idx)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # Open output in append mode if resuming, write mode if starting fresh
    mode = "a" if start_idx > 0 else "w"
    total_tokens = 0
    embedded_count = 0
    start_time = time.time()

    with open(OUTPUT_PATH, mode, encoding="utf-8") as fout:
        for batch_start in range(start_idx, len(chunks), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(chunks))
            batch = chunks[batch_start:batch_end]

            # Extract texts for embedding
            texts = [chunk["text"] for chunk in batch]

            # Generate embeddings
            embeddings, tokens_used = embed_batch(client, texts)
            total_tokens += tokens_used

            # Write results
            for chunk, embedding in zip(batch, embeddings):
                record = {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk["doc_id"],
                    "title": chunk["title"],
                    "section_title": chunk.get("section_title", ""),
                    "entity_type": chunk["entity_type"],
                    "regions": chunk["regions"],
                    "source_url": chunk["source_url"],
                    "text": chunk["text"],
                    "text_length": chunk["text_length"],
                    "embedding": embedding,
                }
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                embedded_count += 1

            # Save checkpoint
            save_checkpoint(batch_end)

            # Progress log
            elapsed = time.time() - start_time
            pct = 100 * batch_end / len(chunks)
            rate = embedded_count / elapsed if elapsed > 0 else 0
            logger.info(
                "  [%5.1f%%] %d/%d chunks | %d tokens | %.1f chunks/sec",
                pct, batch_end, len(chunks), total_tokens, rate,
            )

    elapsed = time.time() - start_time

    # Remove checkpoint file on success
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)

    # Cost estimate: text-embedding-3-small = $0.02 per 1M tokens
    cost = total_tokens / 1_000_000 * 0.02

    logger.info("=" * 60)
    logger.info("Embedding complete!")
    logger.info("  Chunks embedded: %d", embedded_count)
    logger.info("  Total tokens: %d", total_tokens)
    logger.info("  Estimated cost: $%.4f", cost)
    logger.info("  Elapsed: %.1f seconds", elapsed)
    logger.info("  Output: %s", OUTPUT_PATH)
    logger.info("  Output size: %.1f MB", os.path.getsize(OUTPUT_PATH) / 1e6)
    logger.info("=" * 60)

    # Write embedding manifest
    manifest = {
        "embedding_time": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "dimension": EMBEDDING_DIMENSION,
        "chunks_embedded": embedded_count,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(cost, 4),
        "elapsed_seconds": round(elapsed, 1),
        "output_file": "data/processed/embeddings/wiki_embeddings.jsonl",
        "output_size_mb": round(os.path.getsize(OUTPUT_PATH) / 1e6, 1),
    }
    manifest_path = os.path.join(PROJECT_ROOT, "data/metadata/embedding_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("Manifest: %s", manifest_path)

    return manifest


if __name__ == "__main__":
    main()
