"""
LoreMaster-AI - P1 Optimization: Reclassify RELATED_TO Relations

Uses Claude Sonnet to reclassify generic RELATED_TO relationships
into more specific relationship types.
"""

import json
import logging
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import anthropic
from neo4j import GraphDatabase

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, ANTHROPIC_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
BATCH_SIZE = 30  # Relations per API call

RECLASSIFY_PROMPT = """You are classifying relationships in a Genshin Impact knowledge graph.

For each relationship below, classify it into ONE of these specific types:
- AFFILIATED_WITH: belongs to an organization/faction
- MEMBER_OF: is a member of a group
- LOCATED_IN: is located at a place
- PART_OF: is part of a larger entity
- ALLY_OF: is allied with, helped, cooperated with
- ENEMY_OF: is an enemy of, fought against
- CREATED: created/made something
- PARTICIPATED_IN: participated in an event/quest
- POSSESSES: owns, has, uses something
- WIELDER_OF: wields a weapon or element
- RULES: governs or rules over
- MENTOR_OF: mentored or taught
- ORIGINATED_FROM: comes from a place/origin
- TRANSFORMED_INTO: became or transformed into
- RELATED_TO: keep this ONLY if no other type fits well

Be conservative: if the evidence is weak or ambiguous, keep RELATED_TO.

Relationships to classify:
{relations}

Return ONLY a JSON array:
[{{"idx": 1, "relation": "ALLY_OF"}}]
"""


def get_related_to_relations(driver):
    """Fetch all RELATED_TO relationships from Neo4j."""
    with driver.session() as session:
        result = session.run("""
            MATCH (h:Entity)-[r:RELATED_TO]->(t:Entity)
            RETURN id(r) AS rel_id, h.name AS head, t.name AS tail,
                   h.type AS head_type, t.type AS tail_type, r.evidence AS evidence
        """)
        return [dict(r) for r in result]


def reclassify_batch(client, relations):
    """Call Sonnet to reclassify a batch of relations."""
    relations_text = "\n".join([
        f"{i+1}. {r['head']} ({r['head_type']}) -> {r['tail']} ({r['tail_type']})\n   Evidence: \"{r['evidence'] or 'N/A'}\""
        for i, r in enumerate(relations)
    ])

    prompt = RECLASSIFY_PROMPT.format(relations=relations_text)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    cost = response.usage.input_tokens / 1e6 * 3 + response.usage.output_tokens / 1e6 * 15

    # Parse JSON
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        results = json.loads(cleaned)
        return results, tokens, cost
    except json.JSONDecodeError:
        logger.warning("Failed to parse response: %s", raw[:200])
        return [], tokens, cost


def update_neo4j_relations(driver, relations, reclassifications):
    """Update Neo4j with new relationship types."""
    updated = 0
    kept = 0

    with driver.session() as session:
        for reclass in reclassifications:
            idx = reclass.get("idx", 0) - 1
            new_rel = reclass.get("relation", "RELATED_TO")

            if idx < 0 or idx >= len(relations):
                continue

            rel = relations[idx]

            if new_rel == "RELATED_TO":
                kept += 1
                continue

            # Delete old and create new relationship with native type
            session.run(f"""
                MATCH (h:Entity {{name: $head}})-[r:RELATED_TO]->(t:Entity {{name: $tail}})
                WHERE r.evidence = $evidence OR ($evidence IS NULL AND r.evidence IS NULL)
                DELETE r
                CREATE (h)-[new:{new_rel}]->(t)
                SET new.evidence = $evidence,
                    new.source_doc_id = $source_doc_id
            """, head=rel['head'], tail=rel['tail'],
                evidence=rel.get('evidence'), source_doc_id=rel.get('source_doc_id'))

            updated += 1

    return updated, kept


def main():
    logger.info("=" * 60)
    logger.info("P1: Reclassify RELATED_TO Relations")
    logger.info("=" * 60)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Get all RELATED_TO relations
    relations = get_related_to_relations(driver)
    logger.info("Found %d RELATED_TO relations to reclassify", len(relations))

    if not relations:
        logger.info("No RELATED_TO relations found. Done.")
        driver.close()
        return

    total_tokens = 0
    total_cost = 0
    total_updated = 0
    total_kept = 0
    start_time = time.time()

    # Process in batches
    for batch_start in range(0, len(relations), BATCH_SIZE):
        batch = relations[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(relations) + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info("Processing batch %d/%d (%d relations)...",
                    batch_num, total_batches, len(batch))

        results, tokens, cost = reclassify_batch(client, batch)
        total_tokens += tokens
        total_cost += cost

        if results:
            updated, kept = update_neo4j_relations(driver, batch, results)
            total_updated += updated
            total_kept += kept
            logger.info("  Batch %d: %d updated, %d kept as RELATED_TO",
                        batch_num, updated, kept)
        else:
            total_kept += len(batch)
            logger.warning("  Batch %d: No results, keeping all as RELATED_TO", batch_num)

        # Small delay between batches
        time.sleep(0.5)

    elapsed = time.time() - start_time

    # Verify final state
    with driver.session() as session:
        result = session.run("""
            MATCH ()-[r:RELATED_TO]->()
            RETURN count(r) AS remaining
        """)
        remaining = result.single()["remaining"]

    driver.close()

    logger.info("=" * 60)
    logger.info("Reclassification complete!")
    logger.info("  Total relations processed: %d", len(relations))
    logger.info("  Reclassified to specific types: %d", total_updated)
    logger.info("  Kept as RELATED_TO: %d", total_kept)
    logger.info("  Remaining RELATED_TO in DB: %d", remaining)
    logger.info("  Tokens used: %d", total_tokens)
    logger.info("  Cost: $%.4f", total_cost)
    logger.info("  Elapsed: %.1fs", elapsed)
    logger.info("=" * 60)

    return {
        "processed": len(relations),
        "reclassified": total_updated,
        "kept": total_kept,
        "remaining": remaining,
        "tokens": total_tokens,
        "cost": round(total_cost, 4),
    }


if __name__ == "__main__":
    main()
