"""
LoreMaster-AI - P2 Optimization: Build Alias Mapping

Auto-discovers entity aliases from multiple sources:
1. Entity descriptions (regex patterns: "also known as", "formerly", etc.)
2. Neo4j TRANSFORMED_INTO relationships
3. Wiki document first sentences

Writes results to DynamoDB alias-mapping table.
Cost: $0 (pure regex, no LLM)
"""

import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Optional, Set, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import boto3
from neo4j import GraphDatabase

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    DYNAMODB_ALIAS_TABLE, AWS_REGION,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Regex patterns for alias extraction
ALIAS_PATTERNS = [
    # "also known as X"
    (r'also known as ["\']?([^"\',.]+)["\']?', 1),
    # "also called X"
    (r'also called ["\']?([^"\',.]+)["\']?', 1),
    # "known as X"
    (r'(?:is |was )?known as ["\']?([^"\',.]+)["\']?', 1),
    # "by the name X"
    (r'by (?:the |her |his )?name ["\']?([^"\',.]+)["\']?', 1),
    # "formerly known as X" or "formerly X"
    (r'formerly (?:known as |called )?["\']?([^"\',.]+)["\']?', 1),
    # "nicknamed X"
    (r'nicknamed ["\']?([^"\',.]+)["\']?', 1),
    # "alias X" or "her/his alias X"
    (r'(?:her |his )?alias ["\']?([^"\',.]+)["\']?', 1),
    # "real name is X"
    (r'(?:real |true |actual )name (?:is |was )?["\']?([^"\',.]+)["\']?', 1),
    # "whose name is X"
    (r'whose name (?:is |was )["\']?([^"\',.]+)["\']?', 1),
    # "originally named X"
    (r'originally (?:named |called )["\']?([^"\',.]+)["\']?', 1),
    # "titled X" or "with the title X"
    (r'(?:titled |with the title )["\']?([^"\',.]+)["\']?', 1),
    # Genshin-specific: "The X" as title
    (r'(?:is |was )?(?:the |an? )?([A-Z][a-z]+ (?:Archon|Harbinger|Sage|Matra))', 1),
]

# Common words to filter out (not real aliases)
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "been", "being",
    "he", "she", "it", "they", "him", "her", "them",
    "his", "her", "its", "their",
    "this", "that", "these", "those",
    "who", "which", "what", "where", "when",
    "character", "person", "entity", "npc", "playable",
}


def clean_alias(alias: str) -> Optional[str]:
    """Clean and validate an alias string."""
    if not alias:
        return None

    # Strip whitespace and quotes
    alias = alias.strip().strip('"\'')

    # Skip if too short or too long
    if len(alias) < 2 or len(alias) > 50:
        return None

    # Skip if it's just a stopword
    if alias.lower() in STOPWORDS:
        return None

    # Skip if it's mostly non-alphabetic
    alpha_ratio = sum(c.isalpha() or c.isspace() for c in alias) / len(alias)
    if alpha_ratio < 0.7:
        return None

    return alias


def extract_from_descriptions(entities_path: str) -> Dict[str, Set[str]]:
    """Extract aliases from entity descriptions using regex patterns."""
    logger.info("Extracting aliases from entity descriptions...")

    alias_map = defaultdict(set)  # canonical_name -> set of aliases

    with open(entities_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            entity = json.loads(line)
            canonical = entity.get("name", "")
            description = entity.get("description", "")

            if not canonical or not description:
                continue

            # Apply each pattern
            for pattern, group_idx in ALIAS_PATTERNS:
                matches = re.finditer(pattern, description, re.IGNORECASE)
                for match in matches:
                    alias = clean_alias(match.group(group_idx))
                    if alias and alias.lower() != canonical.lower():
                        alias_map[canonical].add(alias)

    total_aliases = sum(len(v) for v in alias_map.values())
    logger.info("  Found %d aliases for %d entities from descriptions",
                total_aliases, len(alias_map))

    return alias_map


def extract_from_transformed_relations(driver) -> Dict[str, Set[str]]:
    """Extract aliases from TRANSFORMED_INTO relationships in Neo4j."""
    logger.info("Extracting aliases from TRANSFORMED_INTO relationships...")

    alias_map = defaultdict(set)

    with driver.session() as session:
        # Get all TRANSFORMED_INTO relationships
        result = session.run("""
            MATCH (a:Entity)-[:TRANSFORMED_INTO]->(b:Entity)
            RETURN a.name AS from_name, b.name AS to_name
        """)

        for record in result:
            from_name = record["from_name"]
            to_name = record["to_name"]

            if from_name and to_name and from_name != to_name:
                # Both names are aliases of each other
                # We'll use the "to" name as canonical (the transformed result)
                alias_map[to_name].add(from_name)
                alias_map[from_name].add(to_name)

    total_aliases = sum(len(v) for v in alias_map.values())
    logger.info("  Found %d aliases for %d entities from TRANSFORMED_INTO",
                total_aliases, len(alias_map))

    return alias_map


def extract_from_wiki_documents(docs_path: str) -> Dict[str, Set[str]]:
    """Extract aliases from wiki document first sentences."""
    logger.info("Extracting aliases from wiki documents...")

    alias_map = defaultdict(set)

    if not os.path.exists(docs_path):
        logger.warning("  Wiki documents not found: %s", docs_path)
        return alias_map

    with open(docs_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            doc = json.loads(line)
            canonical = doc.get("canonical_name", "") or doc.get("title", "")

            # Check for explicit aliases field
            if "aliases" in doc:
                for alias in doc.get("aliases", []):
                    alias = clean_alias(alias)
                    if alias and alias.lower() != canonical.lower():
                        alias_map[canonical].add(alias)

            # Extract from first sentence of content
            content = doc.get("content", "")
            if content:
                first_sentence = content.split(".")[0] if "." in content else content[:200]

                for pattern, group_idx in ALIAS_PATTERNS:
                    matches = re.finditer(pattern, first_sentence, re.IGNORECASE)
                    for match in matches:
                        alias = clean_alias(match.group(group_idx))
                        if alias and alias.lower() != canonical.lower():
                            alias_map[canonical].add(alias)

    total_aliases = sum(len(v) for v in alias_map.values())
    logger.info("  Found %d aliases for %d entities from wiki docs",
                total_aliases, len(alias_map))

    return alias_map


def merge_alias_maps(*maps) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    """Merge multiple alias maps and resolve transitive aliases."""
    logger.info("Merging and deduplicating alias maps...")

    merged = defaultdict(set)

    # Combine all maps
    for alias_map in maps:
        for canonical, aliases in alias_map.items():
            merged[canonical].update(aliases)

    # Build reverse mapping (alias -> canonical candidates)
    reverse_map = defaultdict(set)
    for canonical, aliases in merged.items():
        for alias in aliases:
            reverse_map[alias].add(canonical)

    # Resolve conflicts: if an alias points to multiple canonicals,
    # and one of them is more "primary" (has more aliases), use that
    final_map = defaultdict(set)

    for canonical, aliases in merged.items():
        for alias in aliases:
            # Check if this alias itself is a canonical name
            if alias in merged and len(merged[alias]) > len(aliases):
                # The alias is a better canonical, reverse the relationship
                final_map[alias].add(canonical)
            else:
                final_map[canonical].add(alias)

    # Add reverse mappings (alias -> canonical)
    reverse_final = {}
    for canonical, aliases in final_map.items():
        for alias in aliases:
            reverse_final[alias] = canonical

    total_aliases = sum(len(v) for v in final_map.values())
    logger.info("  Final: %d canonical names with %d total aliases",
                len(final_map), total_aliases)

    return final_map, reverse_final


def load_to_dynamodb(alias_map: Dict[str, Set[str]], entity_types: Dict[str, str]):
    """Write alias mappings to DynamoDB."""
    logger.info("Loading aliases to DynamoDB table: %s", DYNAMODB_ALIAS_TABLE)

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(DYNAMODB_ALIAS_TABLE)

    now_iso = datetime.now(timezone.utc).isoformat()

    # Build unique alias items (alias is the PK, so we need to dedupe)
    # If same alias points to multiple canonicals, pick the one with most aliases
    alias_items = {}  # alias -> (canonical, entity_type, num_aliases)

    for canonical, aliases in alias_map.items():
        entity_type = entity_types.get(canonical, "Unknown")
        num_aliases = len(aliases)

        for alias in aliases:
            # Keep the mapping with the most aliases (more authoritative canonical)
            if alias not in alias_items or num_aliases > alias_items[alias][2]:
                alias_items[alias] = (canonical, entity_type, num_aliases)

    logger.info("  Unique alias mappings after dedup: %d", len(alias_items))

    loaded = 0
    with table.batch_writer() as batch:
        for alias, (canonical, entity_type, _) in alias_items.items():
            item = {
                "alias": alias,
                "canonical_name": canonical,
                "entity_type": entity_type,
                "source": "auto_discovery",
                "updated_at": now_iso,
            }
            batch.put_item(Item=item)
            loaded += 1

            if loaded % 100 == 0:
                logger.info("  Loaded %d alias mappings...", loaded)

    logger.info("  Total aliases loaded: %d", loaded)
    return loaded


def get_entity_types(entities_path: str) -> Dict[str, str]:
    """Build a mapping of entity name to type."""
    entity_types = {}

    with open(entities_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entity = json.loads(line)
            name = entity.get("name", "")
            etype = entity.get("type", "Unknown")
            if name:
                entity_types[name] = etype

    return entity_types


def main():
    logger.info("=" * 60)
    logger.info("P2: Build Alias Mapping")
    logger.info("=" * 60)

    start_time = time.time()

    # Paths
    entities_path = os.path.join(PROJECT_ROOT, "data/processed/triples/entities.jsonl")
    docs_path = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_clean.jsonl")

    # Connect to Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    logger.info("Connected to Neo4j")

    # Extract aliases from multiple sources
    desc_aliases = extract_from_descriptions(entities_path)
    transform_aliases = extract_from_transformed_relations(driver)
    wiki_aliases = extract_from_wiki_documents(docs_path)

    driver.close()

    # Merge all alias maps
    final_map, reverse_map = merge_alias_maps(desc_aliases, transform_aliases, wiki_aliases)

    # Get entity types for metadata
    entity_types = get_entity_types(entities_path)

    # Load to DynamoDB
    loaded = load_to_dynamodb(final_map, entity_types)

    elapsed = time.time() - start_time

    # Show some examples
    logger.info("")
    logger.info("Sample aliases discovered:")
    count = 0
    for canonical, aliases in sorted(final_map.items(), key=lambda x: -len(x[1])):
        if aliases and count < 10:
            logger.info("  %s -> %s", canonical, list(aliases)[:5])
            count += 1

    logger.info("")
    logger.info("=" * 60)
    logger.info("Alias mapping complete!")
    logger.info("  Canonical entities with aliases: %d", len(final_map))
    logger.info("  Total aliases loaded: %d", loaded)
    logger.info("  Cost: $0.00 (regex only)")
    logger.info("  Elapsed: %.1fs", elapsed)
    logger.info("=" * 60)

    return {
        "canonical_count": len(final_map),
        "alias_count": loaded,
        "cost": 0.0,
        "elapsed": round(elapsed, 1),
    }


if __name__ == "__main__":
    main()
