"""
LoreMaster-AI - Hybrid Retriever

Combines vector search (Pinecone) and graph search (Neo4j)
for comprehensive context retrieval.

Improvements:
#4 - Graph result ranking (evidence quality, relation type, target relevance)
#7 - Multi-path discovery (find alternative paths)
"""

import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from pinecone import Pinecone
from neo4j import GraphDatabase

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import (
    PINECONE_API_KEY, PINECONE_INDEX, PINECONE_HOST,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
)
from src.agent.text_loader import get_text_loader
from src.agent.circuit_breaker import CircuitBreaker, CircuitOpenError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# #4: Relation type importance weights (higher = more important)
RELATION_WEIGHTS = {
    # Family/Origin relations (high importance)
    "CREATED_BY": 1.0,
    "CHILD_OF": 1.0,
    "SIBLING_OF": 0.95,
    "FAMILY_OF": 0.9,
    # Direct relationships
    "MASTER_OF": 0.9,
    "SERVANT_OF": 0.9,
    "ALLY_OF": 0.85,
    "ENEMY_OF": 0.85,
    # Organizational
    "MEMBER_OF": 0.8,
    "LEADER_OF": 0.85,
    "BELONGS_TO": 0.75,
    # Location
    "LOCATED_IN": 0.6,
    "RULES": 0.8,
    # General
    "RELATED_TO": 0.5,
    "ASSOCIATED_WITH": 0.5,
}


class HybridRetriever:
    """Combines vector and graph retrieval for comprehensive context."""

    def __init__(self):
        """Initialize connections to Pinecone and Neo4j."""
        # Circuit breakers first — needed before any connectivity check
        self._pinecone_cb = CircuitBreaker("pinecone", failure_threshold=3, recovery_timeout=60)
        self._neo4j_cb = CircuitBreaker("neo4j", failure_threshold=3, recovery_timeout=60)

        # Pinecone
        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        self.index = self.pc.Index(PINECONE_INDEX, host=PINECONE_HOST)

        # Neo4j
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        try:
            self.driver.verify_connectivity()
        except Exception as e:
            logger.warning("Neo4j connectivity check failed at init (will retry at query time): %s", e)
            self._neo4j_cb._on_failure(e)

        # Text loader for full text enrichment (P3)
        self.text_loader = get_text_loader()

        logger.info("HybridRetriever: Connected to Pinecone and Neo4j")

    # ========================================
    # #4: Graph Result Ranking
    # ========================================

    def _score_relationship(
        self,
        rel: dict,
        query_entities: List[str] = None
    ) -> float:
        """
        Score a relationship based on evidence quality, relation type, and target relevance.

        Scoring factors:
        1. Evidence quality (0-0.4): Length and presence of evidence text
        2. Relation type (0-0.3): Importance weight of relationship type
        3. Target relevance (0-0.3): Whether target entity is in query

        Returns:
            Score between 0 and 1
        """
        score = 0.0
        query_entities = query_entities or []
        query_entities_lower = [e.lower() for e in query_entities]

        # Factor 1: Evidence quality (0-0.4)
        evidence = rel.get("evidence", "")
        if evidence:
            # Longer evidence with more detail scores higher
            evidence_len = len(evidence)
            if evidence_len >= 100:
                score += 0.4
            elif evidence_len >= 50:
                score += 0.3
            elif evidence_len >= 20:
                score += 0.2
            else:
                score += 0.1
        # No evidence = 0 for this factor

        # Factor 2: Relation type importance (0-0.3)
        relation_type = rel.get("relation", "RELATED_TO")
        weight = RELATION_WEIGHTS.get(relation_type, 0.5)
        score += weight * 0.3

        # Factor 3: Target relevance (0-0.3)
        target = rel.get("target", "") or rel.get("source", "")
        if target and target.lower() in query_entities_lower:
            score += 0.3
        else:
            # Partial match bonus
            for entity in query_entities_lower:
                if entity in target.lower() or target.lower() in entity:
                    score += 0.15
                    break

        return round(score, 3)

    def _rank_graph_results(
        self,
        graph_results: List[dict],
        query_entities: List[str] = None
    ) -> List[dict]:
        """
        Rank graph results by scoring each relationship.

        Args:
            graph_results: List of entity relationship dicts
            query_entities: Entities mentioned in query

        Returns:
            Ranked graph results with scores
        """
        for entity_result in graph_results:
            relationships = entity_result.get("relationships", [])
            # Score each relationship
            for rel in relationships:
                rel["relevance_score"] = self._score_relationship(rel, query_entities)
            # Sort relationships by score (descending)
            entity_result["relationships"] = sorted(
                relationships,
                key=lambda x: x.get("relevance_score", 0),
                reverse=True
            )
        return graph_results

    def close(self):
        """Close database connections."""
        self.driver.close()

    # ========================================
    # Vector Search (Pinecone)
    # ========================================

    def vector_search(
        self,
        embedding: List[float],
        top_k: int = 10,
        filter_dict: Optional[dict] = None
    ) -> List[dict]:
        """
        Search Pinecone for similar chunks.

        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of enriched results with full text
        """
        query_params = {
            "vector": embedding,
            "top_k": top_k,
            "include_metadata": True,
        }
        if filter_dict:
            query_params["filter"] = filter_dict

        try:
            response = self._pinecone_cb.call(self.index.query, **query_params)
        except CircuitOpenError:
            logger.warning("Pinecone circuit OPEN — returning empty vector results")
            return []
        except Exception:
            logger.warning("Pinecone query failed — returning empty vector results")
            return []

        # Convert to list of dicts
        results = []
        for match in response.matches:
            results.append({
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata,
            })

        # Enrich with full text (P3)
        enriched = self.text_loader.enrich_pinecone_results(results)

        return enriched

    # ========================================
    # Graph Search (Neo4j)
    # ========================================

    def graph_search_entity(self, entity_name: str, max_relations: int = 20) -> dict:
        """
        Get all relationships for a single entity.

        Args:
            entity_name: Entity name to search
            max_relations: Maximum relationships to return

        Returns:
            Dict with entity info and relationships
        """
        if not self._neo4j_cb.is_available():
            logger.warning("Neo4j circuit OPEN — skipping graph search for '%s'", entity_name)
            return {"entity": None, "relationships": []}

        try:
            return self._graph_search_entity_inner(entity_name, max_relations)
        except CircuitOpenError:
            return {"entity": None, "relationships": []}
        except Exception as e:
            self._neo4j_cb._on_failure(e)
            logger.warning("Neo4j entity search failed: %s", e)
            return {"entity": None, "relationships": []}

    def _graph_search_entity_inner(self, entity_name: str, max_relations: int = 20) -> dict:
        """Inner implementation of graph_search_entity (actual Neo4j calls)."""
        with self.driver.session() as session:
            # Get entity info (case-insensitive matching)
            result = session.run("""
                MATCH (e:Entity)
                WHERE toLower(e.name) = toLower($name)
                RETURN e.name AS name, e.type AS type, e.description AS description
            """, name=entity_name)

            record = result.single()
            if not record:
                return {"entity": None, "relationships": []}

            # Use the actual entity name from the database
            actual_name = record["name"]
            entity_info = {
                "name": actual_name,
                "type": record["type"],
                "description": record["description"],
            }

            # Get outgoing relationships (use actual name from DB)
            result = session.run("""
                MATCH (e:Entity {name: $name})-[r]->(t:Entity)
                RETURN type(r) AS relation, t.name AS target, t.type AS target_type,
                       r.evidence AS evidence
                LIMIT $limit
            """, name=actual_name, limit=max_relations)

            relationships = []
            for rec in result:
                relationships.append({
                    "direction": "outgoing",
                    "relation": rec["relation"],
                    "target": rec["target"],
                    "target_type": rec["target_type"],
                    "evidence": rec["evidence"],
                })

            # Get incoming relationships (use actual name from DB)
            result = session.run("""
                MATCH (s:Entity)-[r]->(e:Entity {name: $name})
                RETURN type(r) AS relation, s.name AS source, s.type AS source_type,
                       r.evidence AS evidence
                LIMIT $limit
            """, name=actual_name, limit=max_relations)

            for rec in result:
                relationships.append({
                    "direction": "incoming",
                    "relation": rec["relation"],
                    "source": rec["source"],
                    "source_type": rec["source_type"],
                    "evidence": rec["evidence"],
                })

            return {
                "entity": entity_info,
                "relationships": relationships,
            }

    def graph_search_path(
        self,
        entity1: str,
        entity2: str,
        max_hops: int = 3,
        max_paths: int = 3
    ) -> dict:
        """
        #7: Find multiple paths between two entities.

        Args:
            entity1: Starting entity name
            entity2: Ending entity name
            max_hops: Maximum path length
            max_paths: Maximum number of alternative paths to find

        Returns:
            Dict with path information including alternative paths
        """
        _not_found = {"found": False, "entity1": entity1, "entity2": entity2, "path": None, "alternative_paths": []}
        if not self._neo4j_cb.is_available():
            logger.warning("Neo4j circuit OPEN — skipping path search")
            return _not_found
        try:
            return self._graph_search_path_inner(entity1, entity2, max_hops, max_paths)
        except CircuitOpenError:
            return _not_found
        except Exception as e:
            self._neo4j_cb._on_failure(e)
            logger.warning("Neo4j path search failed: %s", e)
            return _not_found

    def _graph_search_path_inner(self, entity1: str, entity2: str, max_hops: int = 3, max_paths: int = 3) -> dict:
        """Inner implementation of graph_search_path (actual Neo4j calls)."""
        with self.driver.session() as session:
            # Find multiple paths (not just shortest)
            # Use case-insensitive matching for entity names
            result = session.run(f"""
                MATCH path = (a:Entity)-[*1..{max_hops}]-(b:Entity)
                WHERE toLower(a.name) = toLower($name1) AND toLower(b.name) = toLower($name2)
                WITH path,
                     [n IN nodes(path) | n.name] AS node_names,
                     [r IN relationships(path) | type(r)] AS rel_types,
                     [r IN relationships(path) | r.evidence] AS evidences,
                     length(path) AS path_length
                RETURN node_names, rel_types, evidences, path_length
                ORDER BY path_length ASC
                LIMIT $max_paths
            """, name1=entity1, name2=entity2, max_paths=max_paths)

            records = list(result)
            if not records:
                return {
                    "found": False,
                    "entity1": entity1,
                    "entity2": entity2,
                    "path": None,
                    "alternative_paths": [],
                }

            # Build all paths
            all_paths = []
            for record in records:
                nodes = record["node_names"]
                rels = record["rel_types"]
                evidences = record["evidences"]

                path_steps = []
                for i in range(len(rels)):
                    step = f"{nodes[i]} -[{rels[i]}]-> {nodes[i+1]}"
                    path_steps.append(step)

                all_paths.append({
                    "path_length": record["path_length"],
                    "nodes": nodes,
                    "relations": rels,
                    "evidences": [e for e in evidences if e],  # Filter None
                    "path_steps": path_steps,
                })

            # Primary path is the shortest
            primary = all_paths[0]
            alternatives = all_paths[1:] if len(all_paths) > 1 else []

            return {
                "found": True,
                "entity1": entity1,
                "entity2": entity2,
                "path_length": primary["path_length"],
                "nodes": primary["nodes"],
                "relations": primary["relations"],
                "path_steps": primary["path_steps"],
                "evidences": primary["evidences"],
                "alternative_paths": alternatives,
            }

    def graph_search_multi_entity(
        self,
        entities: List[str],
        max_relations_per_entity: int = 10
    ) -> List[dict]:
        """
        Get relationships for multiple entities.

        Args:
            entities: List of entity names
            max_relations_per_entity: Max relations per entity

        Returns:
            List of entity relationship dicts
        """
        results = []
        for entity in entities:
            entity_result = self.graph_search_entity(entity, max_relations_per_entity)
            if entity_result["entity"]:
                results.append(entity_result)
        return results

    # ========================================
    # Hybrid Retrieval
    # ========================================

    def retrieve(
        self,
        query: str,
        embedding: List[float],
        entities: List[str],
        query_type: str,
        vector_top_k: int = 10,
        graph_max_relations: int = 15,
    ) -> dict:
        """
        Perform hybrid retrieval combining vector and graph search.

        Args:
            query: Original query text
            embedding: Query embedding
            entities: Extracted canonical entity names
            query_type: Query classification (FACTUAL, RELATIONSHIP, etc.)
            vector_top_k: Number of vector search results
            graph_max_relations: Max relations per entity

        Returns:
            Dict containing:
            - vector_results: Enriched Pinecone results
            - graph_results: Neo4j relationship results
            - path_results: Path between entities (for RELATIONSHIP queries)
        """
        result = {
            "query": query,
            "query_type": query_type,
            "vector_results": [],
            "graph_results": [],
            "path_results": None,
        }

        # 1. Vector search
        result["vector_results"] = self.vector_search(embedding, top_k=vector_top_k)

        # 2. Graph search based on query type
        if query_type == "RELATIONSHIP" and len(entities) >= 2:
            # Try to find path between first two entities (max_hops=5 allows 6-node paths)
            result["path_results"] = self.graph_search_path(
                entities[0], entities[1], max_hops=5
            )
            # Also get individual entity relationships
            result["graph_results"] = self.graph_search_multi_entity(
                entities, max_relations_per_entity=graph_max_relations
            )

        elif entities:
            # Get relationships for all mentioned entities
            result["graph_results"] = self.graph_search_multi_entity(
                entities, max_relations_per_entity=graph_max_relations
            )

        # #4: Rank graph results by relevance
        if result["graph_results"]:
            result["graph_results"] = self._rank_graph_results(
                result["graph_results"],
                query_entities=entities
            )

        return result


# Singleton instance
_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    """Get or create singleton HybridRetriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever


if __name__ == "__main__":
    from src.agent.query_processor import QueryProcessor

    # Test the retriever
    processor = QueryProcessor()
    retriever = HybridRetriever()

    test_query = "What is the relationship between Scaramouche and Raiden Shogun?"

    print(f"Query: {test_query}")
    print("=" * 60)

    # Process query
    processed = processor.process(test_query)
    print(f"Entities: {processed['canonical_entities']}")
    print(f"Query Type: {processed['query_type']}")

    # Retrieve
    results = retriever.retrieve(
        query=test_query,
        embedding=processed["embedding"],
        entities=processed["canonical_entities"],
        query_type=processed["query_type"],
    )

    print(f"\n--- Vector Results ({len(results['vector_results'])} chunks) ---")
    for i, r in enumerate(results["vector_results"][:3]):
        print(f"{i+1}. [{r['score']:.3f}] {r['title']}")
        print(f"   Text: {r['full_text'][:150]}...")

    print(f"\n--- Graph Results ---")
    for entity_result in results["graph_results"]:
        ent = entity_result["entity"]
        print(f"\n{ent['name']} ({ent['type']})")
        for rel in entity_result["relationships"][:5]:
            if rel["direction"] == "outgoing":
                print(f"  -> {rel['relation']} -> {rel['target']}")
            else:
                print(f"  <- {rel['relation']} <- {rel['source']}")

    if results["path_results"]:
        print(f"\n--- Path Results ---")
        path = results["path_results"]
        if path["found"]:
            print(f"Path length: {path['path_length']}")
            for step in path["path_steps"]:
                print(f"  {step}")
        else:
            print(f"No path found between {path['entity1']} and {path['entity2']}")

    retriever.close()
