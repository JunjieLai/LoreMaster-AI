"""
LoreMaster-AI - Adaptive Graph Depth

Dynamically adjusts graph traversal depth based on query complexity.
Prevents over-fetching for simple queries while allowing deep exploration for complex ones.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class DepthConfig:
    """Configuration for adaptive depth."""
    min_hops: int = 1
    max_hops: int = 5
    default_hops: int = 3

    # Complexity thresholds
    entity_count_threshold: int = 2  # More entities = deeper search
    keyword_bonus: int = 1  # Bonus depth for complexity keywords

    # Performance limits
    max_paths_shallow: int = 2  # Fewer paths for shallow search
    max_paths_deep: int = 5     # More paths for deep search


class AdaptiveDepthManager:
    """
    Determines optimal graph traversal depth based on query characteristics.

    Strategy:
    1. Base depth from query type
    2. Adjust based on entity count
    3. Boost for complexity keywords
    4. Cap at configured maximum
    """

    # Keywords indicating need for deeper traversal
    COMPLEXITY_KEYWORDS = {
        # English
        "indirect", "through", "via", "chain", "eventually", "ultimately",
        "how did", "why did", "what led to", "connection between",
        "influence", "impact", "affect", "cause", "result",
        # Chinese
        "间接", "通过", "导致", "影响", "联系", "最终", "如何", "为什么",
        "起因", "结果", "关联", "牵连",
    }

    # Query type base depths
    QUERY_TYPE_DEPTHS = {
        "FACTUAL": 1,
        "RELATIONSHIP": 2,
        "MULTI_HOP": 4,
        "LIST": 2,
        "COMPARISON": 3,
    }

    def __init__(self, config: Optional[DepthConfig] = None):
        self.config = config or DepthConfig()

    def estimate_complexity(
        self,
        query: str,
        entities: List[str],
        query_type: str
    ) -> Tuple[int, dict]:
        """
        Estimate query complexity and return recommended depth.

        Args:
            query: Original query text
            entities: Detected entities
            query_type: Query classification

        Returns:
            Tuple of (recommended_hops, analysis_dict)
        """
        analysis = {
            "query_type": query_type,
            "entity_count": len(entities),
            "complexity_keywords_found": [],
            "base_depth": 0,
            "adjustments": [],
            "final_depth": 0,
        }

        # Step 1: Base depth from query type
        base_depth = self.QUERY_TYPE_DEPTHS.get(query_type, 2)
        analysis["base_depth"] = base_depth
        depth = base_depth

        # Step 2: Entity count adjustment
        entity_count = len(entities)
        if entity_count >= 3:
            depth += 2
            analysis["adjustments"].append(f"+2 for {entity_count} entities")
        elif entity_count == 2:
            depth += 1
            analysis["adjustments"].append(f"+1 for {entity_count} entities")

        # Step 3: Complexity keyword bonus
        query_lower = query.lower()
        found_keywords = []
        for keyword in self.COMPLEXITY_KEYWORDS:
            if keyword in query_lower:
                found_keywords.append(keyword)

        if found_keywords:
            depth += self.config.keyword_bonus
            analysis["complexity_keywords_found"] = found_keywords[:3]  # Limit for logging
            analysis["adjustments"].append(f"+{self.config.keyword_bonus} for complexity keywords")

        # Step 4: Cap at limits
        depth = max(self.config.min_hops, min(depth, self.config.max_hops))
        analysis["final_depth"] = depth

        return depth, analysis

    def get_search_params(
        self,
        query: str,
        entities: List[str],
        query_type: str
    ) -> dict:
        """
        Get optimized search parameters based on query complexity.

        Returns:
            Dict with max_hops, max_paths, and analysis
        """
        depth, analysis = self.estimate_complexity(query, entities, query_type)

        # Adjust max_paths based on depth (deeper = more paths to explore)
        if depth <= 2:
            max_paths = self.config.max_paths_shallow
        else:
            max_paths = self.config.max_paths_deep

        return {
            "max_hops": depth,
            "max_paths": max_paths,
            "analysis": analysis,
        }


def demo():
    """Demonstrate adaptive depth for various queries."""
    manager = AdaptiveDepthManager()

    test_cases = [
        # (query, entities, query_type)
        ("Who is Nahida?", ["Nahida"], "FACTUAL"),
        ("What is the relationship between Scaramouche and Raiden Shogun?",
         ["Wanderer", "Raiden Shogun"], "RELATIONSHIP"),
        ("How did King Deshret's fall ultimately affect the Akademiya?",
         ["King Deshret", "Akademiya"], "MULTI_HOP"),
        ("What is the connection between the Fatui, Tsaritsa, and the fall of Khaenri'ah?",
         ["Fatui", "Tsaritsa", "Khaenri'ah"], "MULTI_HOP"),
        ("为什么流浪者从世界树抹除自己会影响到稻妻的历史?",
         ["Wanderer", "Irminsul", "Inazuma"], "MULTI_HOP"),
    ]

    print("=" * 70)
    print("ADAPTIVE GRAPH DEPTH DEMO")
    print("=" * 70)

    for query, entities, query_type in test_cases:
        params = manager.get_search_params(query, entities, query_type)
        print(f"\nQuery: {query[:60]}...")
        print(f"Entities: {entities}")
        print(f"Type: {query_type}")
        print(f"→ Recommended depth: {params['max_hops']} hops, {params['max_paths']} paths")
        print(f"  Analysis: {params['analysis']['adjustments']}")


if __name__ == "__main__":
    demo()
