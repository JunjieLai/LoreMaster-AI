"""
LoreMaster-AI - Query Processor

Processes user queries:
1. Extracts entity mentions from query
2. Resolves aliases to canonical names (via DynamoDB)
3. Classifies query type (factual, relationship, multi-hop) - with semantic classification
4. Generates query embedding for vector search (with caching)
5. Query expansion for better retrieval
"""

import hashlib
import json
import logging
import os
import re
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import anthropic
import boto3
from openai import OpenAI

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import (
    DYNAMODB_ALIAS_TABLE, DYNAMODB_ENTITY_TABLE, AWS_REGION,
    OPENAI_API_KEY, ANTHROPIC_API_KEY,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class LRUCache:
    """Simple LRU cache for embeddings."""

    def __init__(self, maxsize: int = 1000):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str) -> Optional[list]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: list):
        if self.maxsize <= 0:
            return  # Cache disabled
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.maxsize:
                self.cache.popitem(last=False)
            self.cache[key] = value


class QueryProcessor:
    """Processes and enriches user queries for retrieval."""

    def __init__(self, use_semantic_classification: bool = True, use_query_expansion: bool = True):
        """Initialize QueryProcessor with DynamoDB, OpenAI, and Anthropic clients."""
        self.dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        self.alias_table = self.dynamodb.Table(DYNAMODB_ALIAS_TABLE)
        self.entity_table = self.dynamodb.Table(DYNAMODB_ENTITY_TABLE)
        self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
        self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Feature flags
        self.use_semantic_classification = use_semantic_classification
        self.use_query_expansion = use_query_expansion

        # Cache for entity names (loaded on first use)
        self._entity_names: Optional[Set[str]] = None
        self._alias_map: Optional[Dict[str, str]] = None

        # #2: Embedding cache
        self._embedding_cache = LRUCache(maxsize=1000)
        self._cache_hits = 0
        self._cache_misses = 0

    def _load_entity_names(self):
        """Load all entity names from DynamoDB for matching."""
        if self._entity_names is not None:
            return

        self._entity_names = set()
        response = self.entity_table.scan(ProjectionExpression="entity_name")

        for item in response.get("Items", []):
            name = item.get("entity_name", "")
            if name:
                self._entity_names.add(name)
                self._entity_names.add(name.lower())

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = self.entity_table.scan(
                ProjectionExpression="entity_name",
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            for item in response.get("Items", []):
                name = item.get("entity_name", "")
                if name:
                    self._entity_names.add(name)
                    self._entity_names.add(name.lower())

        logger.info("QueryProcessor: Loaded %d entity names", len(self._entity_names) // 2)

    def _load_alias_map(self):
        """Load alias -> canonical mapping from DynamoDB."""
        if self._alias_map is not None:
            return

        self._alias_map = {}
        response = self.alias_table.scan()

        for item in response.get("Items", []):
            alias = item.get("alias", "")
            canonical = item.get("canonical_name", "")
            if alias and canonical:
                self._alias_map[alias.lower()] = canonical

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = self.alias_table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            for item in response.get("Items", []):
                alias = item.get("alias", "")
                canonical = item.get("canonical_name", "")
                if alias and canonical:
                    self._alias_map[alias.lower()] = canonical

        logger.info("QueryProcessor: Loaded %d alias mappings", len(self._alias_map))

    def extract_entities(self, query: str) -> List[str]:
        """Extract entity mentions from query text."""
        self._load_entity_names()

        entities = []
        query_lower = query.lower()

        # Sort by length (longer matches first) to avoid partial matches
        sorted_names = sorted(self._entity_names, key=len, reverse=True)

        matched_spans = []

        for name in sorted_names:
            name_lower = name.lower()
            start = 0
            while True:
                idx = query_lower.find(name_lower, start)
                if idx == -1:
                    break

                end = idx + len(name_lower)

                before_ok = idx == 0 or not query_lower[idx - 1].isalnum()
                after_ok = end >= len(query_lower) or not query_lower[end].isalnum()

                if before_ok and after_ok:
                    overlaps = any(
                        not (end <= s or idx >= e)
                        for s, e in matched_spans
                    )

                    if not overlaps:
                        original_name = name if name in self._entity_names else name
                        if original_name not in entities:
                            entities.append(original_name)
                        matched_spans.append((idx, end))

                start = end

        return entities

    def resolve_aliases(self, entities: List[str]) -> Dict[str, str]:
        """Resolve entity names/aliases to canonical names."""
        self._load_alias_map()

        resolved = {}
        for entity in entities:
            entity_lower = entity.lower()
            if entity_lower in self._alias_map:
                resolved[entity] = self._alias_map[entity_lower]
            else:
                resolved[entity] = entity

        return resolved

    def _classify_query_regex(self, query: str) -> str:
        """Classify query using regex patterns (fallback)."""
        query_lower = query.lower()

        # Relationship patterns
        relationship_patterns = [
            r"relationship between", r"connection between", r"related to",
            r"和.*什么关系", r"与.*有什么联系", r"之间.*关系", r"怎么认识",
        ]
        for pattern in relationship_patterns:
            if re.search(pattern, query_lower):
                return "RELATIONSHIP"

        # Multi-hop patterns
        multihop_patterns = [r"^why\b", r"^how did\b", r"^为什么", r"的原因"]
        for pattern in multihop_patterns:
            if re.search(pattern, query_lower):
                return "MULTI_HOP"

        # List patterns
        list_patterns = [r"^list\b", r"^what are all\b", r"列出", r"有哪些"]
        for pattern in list_patterns:
            if re.search(pattern, query_lower):
                return "LIST"

        # Comparison patterns
        comparison_patterns = [r"difference between", r"compared to", r"vs\.?", r"区别", r"不同"]
        for pattern in comparison_patterns:
            if re.search(pattern, query_lower):
                return "COMPARISON"

        return "FACTUAL"

    def classify_query_type(self, query: str) -> str:
        """
        #8: Classify query using semantic understanding (Haiku) with regex fallback.
        """
        if not self.use_semantic_classification:
            return self._classify_query_regex(query)

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=20,
                messages=[{
                    "role": "user",
                    "content": f"""Classify this Genshin Impact query into exactly ONE category:
- FACTUAL: Questions about what/who something is
- RELATIONSHIP: Questions about connections between entities
- MULTI_HOP: Why/how questions requiring reasoning
- LIST: Requests to list multiple items
- COMPARISON: Questions comparing entities

Query: "{query}"

Answer with ONE word only (FACTUAL, RELATIONSHIP, MULTI_HOP, LIST, or COMPARISON):"""
                }]
            )
            result = response.content[0].text.strip().upper()
            if result in {"FACTUAL", "RELATIONSHIP", "MULTI_HOP", "LIST", "COMPARISON"}:
                return result
        except Exception as e:
            logger.warning("Semantic classification failed, using regex: %s", e)

        return self._classify_query_regex(query)

    def embed_query(self, query: str) -> List[float]:
        """
        #2: Generate embedding with LRU caching.
        """
        # Create cache key from query
        cache_key = hashlib.md5(query.encode()).hexdigest()

        # Check cache
        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        # Generate new embedding
        self._cache_misses += 1
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        embedding = response.data[0].embedding

        # Store in cache
        self._embedding_cache.set(cache_key, embedding)

        return embedding

    def expand_query(self, query: str, entities: List[str]) -> List[str]:
        """
        #5: Use Haiku to generate related search terms for better retrieval.

        Returns list of expansion terms (2-3 terms).
        Cost: ~$0.0001 per call
        """
        if not self.use_query_expansion or not entities:
            return []

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"""Given this Genshin Impact query and detected entities, generate 2-3 related search terms that would help find relevant information.

Query: "{query}"
Entities: {entities}

Return ONLY a JSON array of strings, no explanation. Example: ["term1", "term2"]"""
                }]
            )

            text = response.content[0].text.strip()
            # Parse JSON array
            if text.startswith("["):
                expansions = json.loads(text)
                if isinstance(expansions, list):
                    return [str(e) for e in expansions[:3]]
        except Exception as e:
            logger.debug("Query expansion failed: %s", e)

        return []

    def get_cache_stats(self) -> dict:
        """Get embedding cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 3),
            "cache_size": len(self._embedding_cache.cache),
        }

    def process(self, query: str) -> dict:
        """
        Full query processing pipeline.
        Runs classify/embed/expand concurrently via ThreadPoolExecutor (~750ms → ~300ms).
        """
        # Extract entities (pure memory operation, very fast)
        entities = self.extract_entities(query)
        resolved = self.resolve_aliases(entities)
        canonical_entities = list(set(resolved.values()))

        # Run 3 independent API calls concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            classify_future = executor.submit(self.classify_query_type, query)
            embed_future = executor.submit(self.embed_query, query)
            expand_future = executor.submit(self.expand_query, query, canonical_entities)
            query_type = classify_future.result()
            embedding = embed_future.result()
            expansions = expand_future.result()

        return {
            "original_query": query,
            "entities": entities,
            "resolved_entities": resolved,
            "canonical_entities": canonical_entities,
            "query_type": query_type,
            "embedding": embedding,
            "expansions": expansions,
        }


# Singleton instance
_query_processor: Optional[QueryProcessor] = None


def get_query_processor() -> QueryProcessor:
    """Get or create singleton QueryProcessor instance."""
    global _query_processor
    if _query_processor is None:
        _query_processor = QueryProcessor()
    return _query_processor


if __name__ == "__main__":
    processor = QueryProcessor()

    test_queries = [
        "Who is Nahida?",
        "What is the relationship between Scaramouche and Raiden Shogun?",
        "Why did the Wanderer erase himself from Irminsul?",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        result = processor.process(query)
        print(f"  Entities: {result['entities']}")
        print(f"  Canonical: {result['canonical_entities']}")
        print(f"  Type: {result['query_type']}")
        print(f"  Expansions: {result['expansions']}")

    # Test cache
    print(f"\n--- Cache Stats ---")
    print(f"First call: {processor.get_cache_stats()}")

    # Call same query again
    processor.process("Who is Nahida?")
    print(f"After repeat: {processor.get_cache_stats()}")
