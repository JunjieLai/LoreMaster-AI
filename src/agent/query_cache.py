"""
LoreMaster-AI - Semantic Answer Cache

Caches pipeline answers indexed by query embedding.
On cache hit (cosine similarity >= threshold), returns stored result in <100ms with zero API cost.

Improvements from reading Claude Code toolResultStorage.ts:
- Atomic file writes via tmp + os.replace (already had this)
- Concurrent write guard: _writing set prevents two threads racing to store
  the same query simultaneously (toolResultStorage uses 'wx' exclusive flag)
- Idempotent: lookup before store in store() — no duplicate entries
"""

import json
import logging
import math
import os
import threading
import time
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
    "data", "answer_cache.json"
)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticAnswerCache:
    """
    Caches pipeline results keyed by query embedding.
    "Who is Nahida?" and "Tell me about Nahida" both hit the same cached answer.
    """

    def __init__(self, threshold: float = 0.95, max_size: int = 500):
        self.threshold = threshold
        self.max_size = max_size
        self._entries: List[dict] = []
        self._hits = 0
        self._misses = 0
        # Improvement: concurrent write guard (inspired by toolResultStorage 'wx' flag)
        # Tracks question strings currently being stored; prevents double-write races.
        self._writing: Set[str] = set()
        self._write_lock = threading.Lock()
        self._load()

    def lookup(self, embedding: List[float]) -> Optional[dict]:
        """Return cached result if a similar-enough query exists, else None."""
        best_sim = 0.0
        best_result = None
        for entry in self._entries:
            sim = _cosine_similarity(embedding, entry["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_result = entry["result"]
        if best_sim >= self.threshold:
            self._hits += 1
            logger.info("Cache HIT (similarity=%.4f)", best_sim)
            return best_result
        self._misses += 1
        return None

    def store(self, embedding: List[float], question: str, result: dict):
        """
        Store a result. Skips if:
        - an identical entry already exists (idempotent replay safety)
        - another thread is already storing the same question (concurrent write guard)
        """
        with self._write_lock:
            # Improvement: skip if already being written (like 'wx' exclusive flag)
            if question in self._writing:
                logger.debug("Cache: skipping duplicate store for '%s'", question[:50])
                return
            # Also skip if a very similar entry already exists
            existing = self.lookup(embedding)
            if existing is not None:
                return
            self._writing.add(question)

        try:
            self._entries.append({
                "embedding": embedding,
                "question": question,
                "result": result,
                "ts": time.time(),
            })
            if len(self._entries) > self.max_size:
                self._entries = self._entries[-self.max_size:]
            self._save()
        finally:
            with self._write_lock:
                self._writing.discard(question)

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            "size": len(self._entries),
        }

    def _load(self):
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r") as f:
                    self._entries = json.load(f)
                logger.info("SemanticAnswerCache: loaded %d entries", len(self._entries))
        except Exception as e:
            logger.warning("SemanticAnswerCache: failed to load cache: %s", e)
            self._entries = []

    def _save(self):
        """Atomic write: write to .tmp then rename (never leaves partial file on disk)."""
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._entries, f)
            os.replace(tmp, CACHE_FILE)
        except Exception as e:
            logger.warning("SemanticAnswerCache: failed to save cache: %s", e)


# Singleton
_cache: Optional[SemanticAnswerCache] = None


def get_answer_cache() -> SemanticAnswerCache:
    global _cache
    if _cache is None:
        _cache = SemanticAnswerCache()
    return _cache
