"""
LoreMaster-AI ETL - Step 5: Chunk

Splits cleaned documents into retrieval-ready text blocks.
Uses section-aware chunking: each section becomes one or more chunks,
with metadata preserved for downstream embedding and graph construction.
"""

import hashlib
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import CHUNK_SIZE, CHUNK_OVERLAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_clean.jsonl")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/chunks/wiki_chunks.jsonl")

# Approximate chars per token (for rough token estimation)
CHARS_PER_TOKEN = 4
MAX_CHUNK_CHARS = CHUNK_SIZE * CHARS_PER_TOKEN  # ~2048 chars
OVERLAP_CHARS = CHUNK_OVERLAP * CHARS_PER_TOKEN  # ~200 chars


def split_text(text, max_chars, overlap_chars):
    """Split text into overlapping chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        # If single paragraph exceeds max, split by sentences
        if len(para) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            sentences = para.replace(". ", ".\n").split("\n")
            for sent in sentences:
                if len(current) + len(sent) + 1 > max_chars:
                    if current:
                        chunks.append(current.strip())
                    # Overlap: keep tail of previous chunk
                    if overlap_chars > 0 and current:
                        current = current[-overlap_chars:].lstrip() + " " + sent
                    else:
                        current = sent
                else:
                    current = current + " " + sent if current else sent
        elif len(current) + len(para) + 2 > max_chars:
            chunks.append(current.strip())
            # Overlap: keep tail of previous chunk
            if overlap_chars > 0:
                current = current[-overlap_chars:].lstrip() + "\n\n" + para
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_document(doc):
    """Split a document into chunks with metadata."""
    doc_id = doc["doc_id"]
    title = doc.get("canonical_name", doc.get("title", ""))
    entity_type = doc["entity_type"]
    regions = doc["regions"]
    categories = doc["categories"]
    source_url = doc["source_url"]

    chunks = []
    chunk_idx = 0

    # Strategy: chunk by section, then split large sections
    sections = doc.get("sections", [])

    if not sections:
        # Fallback: chunk the full content
        text_chunks = split_text(doc["content"], MAX_CHUNK_CHARS, OVERLAP_CHARS)
        for text in text_chunks:
            chunk_id = f"{doc_id}_c{chunk_idx:03d}"
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "title": title,
                "section_title": "",
                "chunk_index": chunk_idx,
                "text": text,
                "text_length": len(text),
                "entity_type": entity_type,
                "regions": regions,
                "categories": categories,
                "source_url": source_url,
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
            chunk_idx += 1
        return chunks

    # Group adjacent small sections to avoid tiny chunks
    buffer_title = ""
    buffer_text = ""

    for sec in sections:
        sec_title = sec.get("title", "")
        sec_content = sec.get("content", "")

        # If adding this section would exceed limit, flush buffer
        if buffer_text and len(buffer_text) + len(sec_content) + 2 > MAX_CHUNK_CHARS:
            text_chunks = split_text(buffer_text, MAX_CHUNK_CHARS, OVERLAP_CHARS)
            for text in text_chunks:
                chunk_id = f"{doc_id}_c{chunk_idx:03d}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "title": title,
                    "section_title": buffer_title,
                    "chunk_index": chunk_idx,
                    "text": text,
                    "text_length": len(text),
                    "entity_type": entity_type,
                    "regions": regions,
                    "categories": categories,
                    "source_url": source_url,
                    "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                })
                chunk_idx += 1
            buffer_title = sec_title
            buffer_text = sec_content
        else:
            if not buffer_title:
                buffer_title = sec_title
            buffer_text = buffer_text + "\n\n" + sec_content if buffer_text else sec_content

    # Flush remaining buffer
    if buffer_text:
        text_chunks = split_text(buffer_text, MAX_CHUNK_CHARS, OVERLAP_CHARS)
        for text in text_chunks:
            chunk_id = f"{doc_id}_c{chunk_idx:03d}"
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "title": title,
                "section_title": buffer_title,
                "chunk_index": chunk_idx,
                "text": text,
                "text_length": len(text),
                "entity_type": entity_type,
                "regions": regions,
                "categories": categories,
                "source_url": source_url,
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
            chunk_idx += 1

    return chunks


def main():
    logger.info("Chunking %s ...", INPUT_PATH)
    logger.info("Config: CHUNK_SIZE=%d tokens (~%d chars), OVERLAP=%d tokens (~%d chars)",
                CHUNK_SIZE, MAX_CHUNK_CHARS, CHUNK_OVERLAP, OVERLAP_CHARS)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    doc_count = 0
    chunk_count = 0
    total_text_length = 0
    type_chunk_counts = {}

    with open(INPUT_PATH, encoding="utf-8") as fin, \
         open(OUTPUT_PATH, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            doc_count += 1

            chunks = chunk_document(doc)
            for chunk in chunks:
                fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                chunk_count += 1
                total_text_length += chunk["text_length"]

                et = chunk["entity_type"]
                type_chunk_counts[et] = type_chunk_counts.get(et, 0) + 1

    avg_chunk_len = total_text_length / chunk_count if chunk_count else 0
    avg_chunks_per_doc = chunk_count / doc_count if doc_count else 0

    logger.info("Chunking complete:")
    logger.info("  Documents: %d", doc_count)
    logger.info("  Chunks: %d", chunk_count)
    logger.info("  Avg chunks/doc: %.1f", avg_chunks_per_doc)
    logger.info("  Avg chunk length: %.0f chars (~%d tokens)", avg_chunk_len, avg_chunk_len / CHARS_PER_TOKEN)
    logger.info("  Total text: %.1f MB", total_text_length / 1e6)
    logger.info("Output: %s", OUTPUT_PATH)

    logger.info("Chunks by entity type:")
    for t, c in sorted(type_chunk_counts.items(), key=lambda x: -x[1]):
        logger.info("  %5d  %s", c, t)

    return chunk_count, doc_count, avg_chunk_len


if __name__ == "__main__":
    main()
