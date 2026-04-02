"""
LoreMaster-AI - Text Loader (P3 Implementation)

Loads full text for chunks that were truncated in Pinecone metadata.
Provides chunk_id -> full_text mapping for retrieval enrichment.
"""

import json
import logging
import os
import sys
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHUNKS_PATH = os.path.join(PROJECT_ROOT, "data/processed/chunks/wiki_chunks.jsonl")


class TextLoader:
    """Loads and provides full text for chunks."""

    def __init__(self, chunks_path: str = CHUNKS_PATH):
        """
        Initialize TextLoader by building chunk_id -> full_text index.

        Args:
            chunks_path: Path to the chunks JSONL file
        """
        self.chunks_path = chunks_path
        self.chunk_index: Dict[str, dict] = {}
        self._load_chunks()

    def _load_chunks(self):
        """Load all chunks into memory index."""
        if not os.path.exists(self.chunks_path):
            logger.warning("Chunks file not found: %s", self.chunks_path)
            return

        with open(self.chunks_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                chunk = json.loads(line)
                chunk_id = chunk.get("chunk_id", "")
                if chunk_id:
                    self.chunk_index[chunk_id] = {
                        "text": chunk.get("text", ""),
                        "doc_id": chunk.get("doc_id", ""),
                        "title": chunk.get("title", ""),
                        "section_title": chunk.get("section_title", ""),
                        "entity_type": chunk.get("entity_type", ""),
                        "regions": chunk.get("regions", []),
                        "source_url": chunk.get("source_url", ""),
                    }

        logger.info("TextLoader: Loaded %d chunks", len(self.chunk_index))

    def get_full_text(self, chunk_id: str) -> str:
        """
        Get full text for a chunk by its ID.

        Args:
            chunk_id: The chunk identifier

        Returns:
            Full text string, or empty string if not found
        """
        chunk = self.chunk_index.get(chunk_id, {})
        return chunk.get("text", "")

    def get_chunk_metadata(self, chunk_id: str) -> Optional[dict]:
        """
        Get full metadata for a chunk.

        Args:
            chunk_id: The chunk identifier

        Returns:
            Chunk metadata dict or None if not found
        """
        return self.chunk_index.get(chunk_id)

    def enrich_pinecone_results(self, results: List[dict]) -> List[dict]:
        """
        Enrich Pinecone search results with full text.

        Pinecone metadata has text truncated to 1000 chars.
        This method replaces it with the full text from our index.

        Args:
            results: List of Pinecone match results with 'id' and 'metadata'

        Returns:
            Enriched results with 'full_text' field added
        """
        enriched = []
        for result in results:
            chunk_id = result.get("id", "")
            score = result.get("score", 0)
            metadata = result.get("metadata", {})

            # Get full text from our index
            full_text = self.get_full_text(chunk_id)

            # If not found in index, fall back to Pinecone metadata
            if not full_text:
                full_text = metadata.get("text", "")

            enriched.append({
                "chunk_id": chunk_id,
                "score": score,
                "full_text": full_text,
                "title": metadata.get("title", ""),
                "section_title": metadata.get("section_title", ""),
                "entity_type": metadata.get("entity_type", ""),
                "doc_id": metadata.get("doc_id", ""),
                "source_url": metadata.get("source_url", ""),
                "text_length": len(full_text),
            })

        return enriched

    def get_stats(self) -> dict:
        """Get statistics about loaded chunks."""
        if not self.chunk_index:
            return {"total_chunks": 0}

        text_lengths = [len(c["text"]) for c in self.chunk_index.values()]
        return {
            "total_chunks": len(self.chunk_index),
            "avg_text_length": sum(text_lengths) // len(text_lengths),
            "max_text_length": max(text_lengths),
            "min_text_length": min(text_lengths),
        }


# Singleton instance for reuse
_text_loader: Optional[TextLoader] = None


def get_text_loader() -> TextLoader:
    """Get or create singleton TextLoader instance."""
    global _text_loader
    if _text_loader is None:
        _text_loader = TextLoader()
    return _text_loader


if __name__ == "__main__":
    # Test the TextLoader
    loader = TextLoader()
    stats = loader.get_stats()
    print(f"TextLoader Stats: {stats}")

    # Show a sample
    if loader.chunk_index:
        sample_id = list(loader.chunk_index.keys())[0]
        sample = loader.get_chunk_metadata(sample_id)
        print(f"\nSample chunk ({sample_id}):")
        print(f"  Title: {sample['title']}")
        print(f"  Text length: {len(sample['text'])} chars")
        print(f"  Text preview: {sample['text'][:200]}...")
