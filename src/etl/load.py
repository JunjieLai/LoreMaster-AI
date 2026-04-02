"""
LoreMaster-AI ETL - Step 9: Load

Loads processed data into three target databases:
  1. Pinecone  - vector embeddings for semantic search
  2. Neo4j     - knowledge graph (entities + relationships)
  3. DynamoDB  - entity metadata for fast lookups
"""

import json
import logging
import os
import sys
import time
import unicodedata
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import (
    PINECONE_API_KEY, PINECONE_INDEX, PINECONE_HOST, EMBEDDING_DIMENSION,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    DYNAMODB_ENTITY_TABLE, DYNAMODB_ALIAS_TABLE, AWS_REGION,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

EMBEDDINGS_PATH = os.path.join(PROJECT_ROOT, "data/processed/embeddings/wiki_embeddings.jsonl")
ENTITIES_PATH = os.path.join(PROJECT_ROOT, "data/processed/triples/entities.jsonl")
TRIPLES_PATH = os.path.join(PROJECT_ROOT, "data/processed/triples/triples.jsonl")

PINECONE_BATCH_SIZE = 100
DYNAMO_BATCH_SIZE = 25  # DynamoDB batch_write limit


# ============================================================
# 1. Pinecone: Load vector embeddings
# ============================================================

def load_pinecone():
    """Load embeddings into Pinecone index."""
    from pinecone import Pinecone

    logger.info("=" * 60)
    logger.info("Loading embeddings into Pinecone")
    logger.info("=" * 60)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX, host=PINECONE_HOST)

    # Check index stats before
    stats = index.describe_index_stats()
    logger.info("Index '%s' before: %d vectors, dimension=%s",
                PINECONE_INDEX, stats.total_vector_count, stats.dimension)

    # Load embeddings
    records = []
    with open(EMBEDDINGS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    logger.info("Loaded %d embedding records", len(records))

    # Upsert in batches
    upserted = 0
    start_time = time.time()

    for batch_start in range(0, len(records), PINECONE_BATCH_SIZE):
        batch = records[batch_start:batch_start + PINECONE_BATCH_SIZE]
        vectors = []
        for rec in batch:
            # Pinecone requires ASCII-only IDs
            vec_id = unicodedata.normalize("NFKD", rec["chunk_id"]).encode("ascii", "ignore").decode("ascii")
            vectors.append({
                "id": vec_id,
                "values": rec["embedding"],
                "metadata": {
                    "doc_id": rec["doc_id"],
                    "title": rec["title"],
                    "section_title": rec.get("section_title", ""),
                    "entity_type": rec["entity_type"],
                    "regions": rec["regions"],
                    "source_url": rec["source_url"],
                    "text": rec["text"][:1000],  # Pinecone metadata limit
                    "text_length": rec["text_length"],
                },
            })

        index.upsert(vectors=vectors)
        upserted += len(vectors)

        if upserted % 1000 == 0 or batch_start + PINECONE_BATCH_SIZE >= len(records):
            elapsed = time.time() - start_time
            logger.info("  Pinecone: %d/%d vectors upserted (%.1fs)",
                        upserted, len(records), elapsed)

    # Verify
    time.sleep(2)  # Wait for index consistency
    stats = index.describe_index_stats()
    elapsed = time.time() - start_time

    logger.info("Pinecone load complete:")
    logger.info("  Vectors upserted: %d", upserted)
    logger.info("  Index total: %d vectors", stats.total_vector_count)
    logger.info("  Elapsed: %.1fs", elapsed)

    return {"vectors_upserted": upserted, "index_total": stats.total_vector_count, "elapsed": round(elapsed, 1)}


# ============================================================
# 2. Neo4j: Load knowledge graph
# ============================================================

def load_neo4j():
    """Load entities and relationships into Neo4j."""
    from neo4j import GraphDatabase

    logger.info("=" * 60)
    logger.info("Loading knowledge graph into Neo4j")
    logger.info("=" * 60)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    logger.info("Connected to Neo4j: %s", NEO4J_URI)

    # Load entity data
    entities = []
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entities.append(json.loads(line))
    logger.info("Loaded %d entity records", len(entities))

    # Load triple data
    triples = []
    with open(TRIPLES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                triples.append(json.loads(line))
    logger.info("Loaded %d triple records", len(triples))

    # Deduplicate entities by name (keep first occurrence with longest description)
    entity_map = {}
    for ent in entities:
        name = ent["name"]
        if name not in entity_map or len(ent.get("description", "")) > len(entity_map[name].get("description", "")):
            entity_map[name] = ent
    unique_entities = list(entity_map.values())
    logger.info("Unique entities after dedup: %d (from %d raw)", len(unique_entities), len(entities))

    start_time = time.time()

    # Clear existing data
    with driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS count")
        existing = result.single()["count"]
        if existing > 0:
            logger.info("Clearing %d existing nodes...", existing)
            session.run("MATCH (n) DETACH DELETE n")

    # Create constraints and indexes
    with driver.session() as session:
        # Create constraint for entity names (unique)
        try:
            session.run("CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")
        except Exception as e:
            logger.warning("Constraint creation note: %s", e)

        # Create index for entity type
        try:
            session.run("CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)")
        except Exception as e:
            logger.warning("Index creation note: %s", e)

    # Batch create entities
    entity_count = 0
    batch_size = 500
    with driver.session() as session:
        for batch_start in range(0, len(unique_entities), batch_size):
            batch = unique_entities[batch_start:batch_start + batch_size]
            params = []
            for ent in batch:
                params.append({
                    "name": ent["name"],
                    "type": ent.get("type", "Unknown"),
                    "description": ent.get("description", ""),
                    "source_doc_id": ent.get("source_doc_id", ""),
                    "source_title": ent.get("source_title", ""),
                })

            session.run("""
                UNWIND $entities AS e
                MERGE (n:Entity {name: e.name})
                ON CREATE SET
                    n.type = e.type,
                    n.description = e.description,
                    n.source_doc_id = e.source_doc_id,
                    n.source_title = e.source_title
                ON MATCH SET
                    n.description = CASE WHEN size(e.description) > size(coalesce(n.description, ''))
                                        THEN e.description ELSE n.description END
            """, entities=params)

            entity_count += len(batch)
            if entity_count % 1000 == 0 or batch_start + batch_size >= len(unique_entities):
                logger.info("  Neo4j entities: %d/%d created", entity_count, len(unique_entities))

    # Also add type-specific labels (Character, Location, etc.)
    with driver.session() as session:
        for entity_type in ["Character", "Location", "Organization", "Event", "Item", "Concept"]:
            result = session.run("""
                MATCH (n:Entity {type: $type})
                SET n:%s
                RETURN count(n) AS count
            """ % entity_type, type=entity_type)
            count = result.single()["count"]
            if count > 0:
                logger.info("  Added :%s label to %d nodes", entity_type, count)

    # Batch create relationships
    triple_count = 0
    skipped = 0
    with driver.session() as session:
        for batch_start in range(0, len(triples), batch_size):
            batch = triples[batch_start:batch_start + batch_size]
            params = []
            for tri in batch:
                if tri.get("head") and tri.get("tail") and tri.get("relation"):
                    params.append({
                        "head": tri["head"],
                        "tail": tri["tail"],
                        "relation": tri["relation"],
                        "evidence": tri.get("evidence", ""),
                        "source_doc_id": tri.get("source_doc_id", ""),
                    })
                else:
                    skipped += 1

            if params:
                session.run("""
                    UNWIND $triples AS t
                    MATCH (h:Entity {name: t.head})
                    MATCH (tl:Entity {name: t.tail})
                    MERGE (h)-[r:RELATES_TO {relation: t.relation}]->(tl)
                    ON CREATE SET
                        r.evidence = t.evidence,
                        r.source_doc_id = t.source_doc_id
                """, triples=params)

            triple_count += len(params)
            if triple_count % 1000 == 0 or batch_start + batch_size >= len(triples):
                logger.info("  Neo4j triples: %d/%d created (skipped: %d)",
                            triple_count, len(triples), skipped)

    # Verify
    with driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS nodes")
        node_count = result.single()["nodes"]
        result = session.run("MATCH ()-[r]->() RETURN count(r) AS rels")
        rel_count = result.single()["rels"]

    elapsed = time.time() - start_time
    driver.close()

    logger.info("Neo4j load complete:")
    logger.info("  Nodes: %d", node_count)
    logger.info("  Relationships: %d", rel_count)
    logger.info("  Skipped triples: %d", skipped)
    logger.info("  Elapsed: %.1fs", elapsed)

    return {"nodes": node_count, "relationships": rel_count, "skipped": skipped, "elapsed": round(elapsed, 1)}


# ============================================================
# 3. DynamoDB: Load entity metadata
# ============================================================

def load_dynamodb():
    """Load entity metadata into DynamoDB for fast lookups."""
    import boto3

    logger.info("=" * 60)
    logger.info("Loading metadata into DynamoDB")
    logger.info("=" * 60)

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

    # ---- Entity metadata table ----
    entity_table = dynamodb.Table(DYNAMODB_ENTITY_TABLE)
    logger.info("Target table: %s", DYNAMODB_ENTITY_TABLE)

    # Load entities and deduplicate
    entities = []
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entities.append(json.loads(line))

    # Deduplicate: keep best description per entity name
    entity_map = {}
    for ent in entities:
        name = ent["name"]
        if name not in entity_map or len(ent.get("description", "")) > len(entity_map[name].get("description", "")):
            entity_map[name] = ent

    unique_entities = list(entity_map.values())
    logger.info("Unique entities to load: %d", len(unique_entities))

    start_time = time.time()
    loaded = 0

    # Batch write entities (table key: entity_type + entity_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    with entity_table.batch_writer() as batch:
        for ent in unique_entities:
            entity_type = ent.get("type", "Unknown")
            entity_name = ent["name"]
            # Use name as entity_id (URL-safe slug)
            entity_id = entity_name.replace(" ", "_").lower()
            item = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "description": ent.get("description", ""),
                "source_doc_id": ent.get("source_doc_id", ""),
                "source_title": ent.get("source_title", ""),
                "updated_at": now_iso,
            }
            batch.put_item(Item=item)
            loaded += 1
            if loaded % 500 == 0:
                logger.info("  DynamoDB entities: %d/%d", loaded, len(unique_entities))

    logger.info("  DynamoDB entities: %d/%d loaded", loaded, len(unique_entities))

    # ---- Alias mapping table ----
    alias_table = dynamodb.Table(DYNAMODB_ALIAS_TABLE)
    logger.info("Loading alias mappings into %s", DYNAMODB_ALIAS_TABLE)

    # Build alias mappings from entity names that appear differently across sources
    # Extract from documents that have canonical_name and aliases
    alias_count = 0
    clean_path = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_clean.jsonl")
    if os.path.exists(clean_path):
        with alias_table.batch_writer() as batch:
            with open(clean_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    doc = json.loads(line)
                    canonical = doc.get("canonical_name", "")
                    aliases = doc.get("aliases", [])
                    if canonical and aliases:
                        for alias in aliases:
                            if alias != canonical:
                                batch.put_item(Item={
                                    "alias": alias,
                                    "canonical_name": canonical,
                                    "entity_type": doc.get("entity_type", ""),
                                    "doc_id": doc.get("doc_id", ""),
                                })
                                alias_count += 1

    logger.info("  Alias mappings loaded: %d", alias_count)

    elapsed = time.time() - start_time

    logger.info("DynamoDB load complete:")
    logger.info("  Entities loaded: %d", loaded)
    logger.info("  Aliases loaded: %d", alias_count)
    logger.info("  Elapsed: %.1fs", elapsed)

    return {"entities_loaded": loaded, "aliases_loaded": alias_count, "elapsed": round(elapsed, 1)}


# ============================================================
# Main
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info("LoreMaster-AI ETL Step 9: Load")
    logger.info("=" * 60)

    results = {}

    # 1. Pinecone
    try:
        results["pinecone"] = load_pinecone()
    except Exception as e:
        logger.error("Pinecone load failed: %s", e)
        results["pinecone"] = {"error": str(e)}

    # 2. Neo4j
    try:
        results["neo4j"] = load_neo4j()
    except Exception as e:
        logger.error("Neo4j load failed: %s", e)
        results["neo4j"] = {"error": str(e)}

    # 3. DynamoDB
    try:
        results["dynamodb"] = load_dynamodb()
    except Exception as e:
        logger.error("DynamoDB load failed: %s", e)
        results["dynamodb"] = {"error": str(e)}

    # Write manifest
    manifest = {
        "load_time": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    manifest_path = os.path.join(PROJECT_ROOT, "data/metadata/load_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("All loads complete!")
    logger.info("Manifest: %s", manifest_path)
    logger.info("=" * 60)

    return manifest


if __name__ == "__main__":
    main()
