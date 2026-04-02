"""
LoreMaster-AI - P0 Optimization: Migrate Neo4j Relationship Types

Converts generic RELATES_TO relationships with `relation` property
into native Neo4j relationship types for better query performance
and Cypher pattern matching support.

Before: (a)-[:RELATES_TO {relation: "LOCATED_IN"}]->(b)
After:  (a)-[:LOCATED_IN]->(b)
"""

import logging
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Valid relationship types to migrate
VALID_REL_TYPES = {
    "LOCATED_IN",
    "PART_OF",
    "PARTICIPATED_IN",
    "POSSESSES",
    "RELATED_TO",
    "MEMBER_OF",
    "CREATED",
    "ORIGINATED_FROM",
    "AFFILIATED_WITH",
    "ALLY_OF",
    "WIELDER_OF",
    "ENEMY_OF",
    "RULES",
    "TRANSFORMED_INTO",
    "PARENT_OF",
    "MENTOR_OF",
    "SIBLING_OF",
    "SEALED",
    "SUCCEEDED",
    "POSSESSED",
    "POSSESSED_BY",
}


def migrate_relationships():
    """Migrate RELATES_TO relationships to native types."""
    logger.info("=" * 60)
    logger.info("Neo4j Relationship Type Migration")
    logger.info("=" * 60)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    logger.info("Connected to Neo4j: %s", NEO4J_URI)

    start_time = time.time()

    with driver.session() as session:
        # Get distinct relation types
        result = session.run("""
            MATCH ()-[r:RELATES_TO]->()
            RETURN DISTINCT r.relation AS rel_type, count(*) AS count
            ORDER BY count DESC
        """)
        rel_counts = {r["rel_type"]: r["count"] for r in result}
        logger.info("Found %d distinct relation types to migrate", len(rel_counts))

        total_migrated = 0

        for rel_type, count in rel_counts.items():
            if rel_type not in VALID_REL_TYPES:
                logger.warning("Skipping unknown relation type: %s (%d)", rel_type, count)
                continue

            logger.info("  Migrating %s (%d relationships)...", rel_type, count)

            # Create new relationships with native type
            # Using APOC would be faster, but we'll use pure Cypher for compatibility
            query = f"""
                MATCH (h)-[r:RELATES_TO {{relation: $rel_type}}]->(t)
                WITH h, t, r, r.evidence AS evidence, r.source_doc_id AS source_doc_id
                DELETE r
                CREATE (h)-[new:{rel_type}]->(t)
                SET new.evidence = evidence,
                    new.source_doc_id = source_doc_id
                RETURN count(*) AS migrated
            """

            result = session.run(query, rel_type=rel_type)
            migrated = result.single()["migrated"]
            total_migrated += migrated
            logger.info("    Migrated: %d", migrated)

    # Verify migration
    with driver.session() as session:
        result = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS rel_type, count(*) AS count
            ORDER BY count DESC
        """)
        logger.info("\nPost-migration relationship types:")
        for r in result:
            logger.info("  %-20s %5d", r["rel_type"], r["count"])

        # Check if any RELATES_TO remain
        result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS count")
        remaining = result.single()["count"]
        if remaining > 0:
            logger.warning("Warning: %d RELATES_TO relationships still remain", remaining)

    elapsed = time.time() - start_time
    driver.close()

    logger.info("=" * 60)
    logger.info("Migration complete!")
    logger.info("  Relationships migrated: %d", total_migrated)
    logger.info("  Elapsed: %.1fs", elapsed)
    logger.info("=" * 60)

    return total_migrated


def create_indexes():
    """Create indexes for common relationship queries."""
    logger.info("Creating indexes for relationship properties...")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        # Index on Entity name (should already exist from load.py)
        try:
            session.run("CREATE INDEX entity_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.name)")
            logger.info("  Created index: entity_name_idx")
        except Exception as e:
            logger.info("  Index entity_name_idx: %s", e)

        # Index on Entity type
        try:
            session.run("CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.type)")
            logger.info("  Created index: entity_type_idx")
        except Exception as e:
            logger.info("  Index entity_type_idx: %s", e)

    driver.close()
    logger.info("Index creation complete.")


def verify_queries():
    """Test some common graph queries after migration."""
    logger.info("\nVerifying graph queries...")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        # Test 1: Find all locations in Sumeru
        result = session.run("""
            MATCH (e:Entity)-[:LOCATED_IN]->(loc:Entity {name: 'Sumeru'})
            RETURN e.name AS entity LIMIT 5
        """)
        entities = [r["entity"] for r in result]
        logger.info("  Query 1 (LOCATED_IN Sumeru): %d results - %s", len(entities), entities[:3])

        # Test 2: Find Nahida's relationships
        result = session.run("""
            MATCH (n:Entity {name: 'Nahida'})-[r]->(m:Entity)
            RETURN type(r) AS rel, m.name AS target LIMIT 5
        """)
        rels = [(r["rel"], r["target"]) for r in result]
        logger.info("  Query 2 (Nahida's relations): %s", rels[:3])

        # Test 3: Two-hop query (characters affiliated with organizations in Sumeru)
        result = session.run("""
            MATCH (c:Character)-[:AFFILIATED_WITH]->(o:Organization)-[:LOCATED_IN]->(l:Location)
            WHERE l.name CONTAINS 'Sumeru' OR l.name = 'Akademiya'
            RETURN DISTINCT c.name AS character, o.name AS org LIMIT 5
        """)
        pairs = [(r["character"], r["org"]) for r in result]
        logger.info("  Query 3 (2-hop affiliation): %s", pairs[:3])

    driver.close()
    logger.info("Query verification complete.")


if __name__ == "__main__":
    migrate_relationships()
    create_indexes()
    verify_queries()
