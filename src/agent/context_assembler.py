"""
LoreMaster-AI - Context Assembler

Assembles retrieval results into structured context for the LLM.
Controls token budget and formats content for optimal prompt construction.

Improvements:
#6 - Context reranking (reorder passages based on entity mentions and section relevance)
#9 - Precise token counting using tiktoken
"""

import logging
import os
import re
import sys
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

# #9: Try to import tiktoken for precise token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
    # Use cl100k_base encoding (used by Claude and GPT-4)
    _tokenizer = tiktoken.get_encoding("cl100k_base")
except ImportError:
    TIKTOKEN_AVAILABLE = False
    _tokenizer = None
    logging.warning("tiktoken not installed, using approximate token counting")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Token budget allocation
MAX_CONTEXT_TOKENS = 6000
GRAPH_CONTEXT_BUDGET = 1500  # ~25% for graph relationships
TEXT_CONTEXT_BUDGET = 4500   # ~75% for text passages


class ContextAssembler:
    """Assembles retrieval results into LLM context."""

    def __init__(
        self,
        max_tokens: int = MAX_CONTEXT_TOKENS,
        graph_budget: int = GRAPH_CONTEXT_BUDGET,
        text_budget: int = TEXT_CONTEXT_BUDGET,
        use_reranking: bool = True,
    ):
        self.max_tokens = max_tokens
        self.graph_budget = graph_budget
        self.text_budget = text_budget
        self.use_reranking = use_reranking

    def _estimate_tokens(self, text: str) -> int:
        """
        #9: Precise token counting using tiktoken, with fallback to estimation.
        """
        if TIKTOKEN_AVAILABLE and _tokenizer:
            return len(_tokenizer.encode(text))
        # Fallback: rough estimation (4 chars ≈ 1 token)
        return len(text) // 4

    # ========================================
    # #6: Context Reranking
    # ========================================

    def _score_passage(
        self,
        passage: dict,
        query_entities: List[str] = None,
        query_type: str = "FACTUAL"
    ) -> float:
        """
        Score a passage for reranking based on multiple factors.

        Factors:
        1. Original vector similarity score (0-0.4)
        2. Entity mention density (0-0.3)
        3. Section relevance (0-0.2)
        4. Query type bonus (0-0.1)

        Returns:
            Reranking score between 0 and 1
        """
        score = 0.0
        query_entities = query_entities or []

        # Factor 1: Original similarity score (normalized to 0-0.4)
        original_score = passage.get("score", 0)
        score += min(original_score, 1.0) * 0.4

        # Factor 2: Entity mention density (0-0.3)
        text = passage.get("full_text", "") or passage.get("text", "")
        text_lower = text.lower()
        entity_mentions = 0
        for entity in query_entities:
            entity_mentions += text_lower.count(entity.lower())
        # Normalize by text length (mentions per 500 chars)
        if len(text) > 0:
            density = entity_mentions / (len(text) / 500)
            score += min(density * 0.15, 0.3)

        # Factor 3: Section relevance (0-0.2)
        section = passage.get("section_title", "").lower()
        title = passage.get("title", "").lower()
        # Check if any query entity is in the title/section
        for entity in query_entities:
            if entity.lower() in title or entity.lower() in section:
                score += 0.2
                break

        # Factor 4: Query type specific bonus (0-0.1)
        if query_type == "RELATIONSHIP":
            # Favor passages with relationship keywords
            relationship_keywords = ["relationship", "connection", "related", "family",
                                    "created", "allied", "enemy", "关系", "联系"]
            for kw in relationship_keywords:
                if kw in text_lower:
                    score += 0.1
                    break
        elif query_type == "FACTUAL":
            # Favor passages with descriptive content
            if "is a" in text_lower or "was a" in text_lower or "是" in text_lower:
                score += 0.1

        return round(score, 3)

    def rerank_passages(
        self,
        passages: List[dict],
        query_entities: List[str] = None,
        query_type: str = "FACTUAL"
    ) -> List[dict]:
        """
        Rerank passages based on entity mentions, section relevance, and query type.

        Args:
            passages: List of passage dicts from vector search
            query_entities: Entities mentioned in query
            query_type: Query classification

        Returns:
            Reranked list of passages with rerank_score added
        """
        if not self.use_reranking or not passages:
            return passages

        for passage in passages:
            passage["rerank_score"] = self._score_passage(
                passage, query_entities, query_type
            )

        # Sort by rerank_score (descending)
        reranked = sorted(
            passages,
            key=lambda x: x.get("rerank_score", 0),
            reverse=True
        )

        return reranked

    def format_graph_context(
        self,
        graph_results: List[dict],
        path_results: Optional[dict] = None
    ) -> str:
        """
        Format graph search results into readable context.

        Args:
            graph_results: List of entity relationship dicts
            path_results: Optional path discovery results

        Returns:
            Formatted graph context string
        """
        lines = []
        current_tokens = 0

        # Add path information first (most relevant for relationship queries)
        if path_results and path_results.get("found"):
            lines.append("## Connection Path")
            lines.append(f"Direct connection between {path_results['entity1']} and {path_results['entity2']}:")
            for i, step in enumerate(path_results["path_steps"], 1):
                lines.append(f"  {i}. {step}")
            lines.append("")
            current_tokens = self._estimate_tokens("\n".join(lines))

        # Add entity relationships
        if graph_results:
            lines.append("## Entity Relationships")

            for entity_result in graph_results:
                if current_tokens >= self.graph_budget:
                    break

                entity = entity_result.get("entity")
                if not entity:
                    continue

                # Entity header
                entity_line = f"\n### {entity['name']} ({entity['type']})"
                if entity.get("description"):
                    desc = entity["description"][:200]
                    if len(entity["description"]) > 200:
                        desc += "..."
                    entity_line += f"\n{desc}"

                lines.append(entity_line)
                current_tokens += self._estimate_tokens(entity_line)

                # Relationships
                rels = entity_result.get("relationships", [])
                for rel in rels:
                    if current_tokens >= self.graph_budget:
                        break

                    if rel["direction"] == "outgoing":
                        rel_line = f"  • {entity['name']} —[{rel['relation']}]→ {rel['target']}"
                    else:
                        rel_line = f"  • {rel['source']} —[{rel['relation']}]→ {entity['name']}"

                    # Add evidence if available
                    evidence = rel.get("evidence")
                    if evidence:
                        evidence_short = evidence[:100]
                        if len(evidence) > 100:
                            evidence_short += "..."
                        rel_line += f'\n    Evidence: "{evidence_short}"'

                    lines.append(rel_line)
                    current_tokens += self._estimate_tokens(rel_line)

        return "\n".join(lines) if lines else "No graph relationships found."

    def format_text_context(self, vector_results: List[dict]) -> str:
        """
        Format vector search results into readable context.

        Args:
            vector_results: List of enriched Pinecone results

        Returns:
            Formatted text context string
        """
        lines = ["## Relevant Wiki Passages"]
        current_tokens = self._estimate_tokens(lines[0])

        for i, result in enumerate(vector_results):
            if current_tokens >= self.text_budget:
                lines.append(f"\n[{len(vector_results) - i} more passages truncated due to token limit]")
                break

            # Build passage header
            title = result.get("title", "Unknown")
            section = result.get("section_title", "")
            score = result.get("score", 0)
            source_url = result.get("source_url", "")

            header = f"\n### [{i+1}] {title}"
            if section:
                header += f" > {section}"
            header += f" (relevance: {score:.2f})"

            # Get full text
            text = result.get("full_text", "")
            if not text:
                text = result.get("text", "")

            # Build passage
            passage = f"{header}\n{text}"

            # Check token budget
            passage_tokens = self._estimate_tokens(passage)
            if current_tokens + passage_tokens > self.text_budget:
                # Truncate this passage to fit
                remaining_chars = (self.text_budget - current_tokens) * 4
                if remaining_chars > 200:
                    text = text[:remaining_chars - 50] + "... [truncated]"
                    passage = f"{header}\n{text}"
                else:
                    break

            lines.append(passage)

            # Add source reference
            if source_url:
                lines.append(f"[Source: {source_url}]")

            current_tokens += self._estimate_tokens(passage)

        return "\n".join(lines)

    def assemble(
        self,
        vector_results: List[dict],
        graph_results: List[dict],
        path_results: Optional[dict] = None,
        query_type: str = "FACTUAL",
        query_entities: List[str] = None
    ) -> dict:
        """
        Assemble full context from retrieval results.

        Args:
            vector_results: Enriched Pinecone results
            graph_results: Neo4j relationship results
            path_results: Path discovery results (for relationship queries)
            query_type: Query classification
            query_entities: Entities mentioned in query (for #6 reranking)

        Returns:
            Dict with:
            - graph_context: Formatted graph context
            - text_context: Formatted text context
            - full_context: Combined context string
            - stats: Token usage statistics
        """
        # #6: Rerank vector results before formatting
        reranked_results = self.rerank_passages(
            vector_results,
            query_entities=query_entities,
            query_type=query_type
        )

        # Format graph context
        graph_context = self.format_graph_context(graph_results, path_results)
        graph_tokens = self._estimate_tokens(graph_context)

        # Format text context (using reranked results)
        text_context = self.format_text_context(reranked_results)
        text_tokens = self._estimate_tokens(text_context)

        # Combine based on query type
        if query_type == "RELATIONSHIP":
            # Prioritize graph context for relationship queries
            full_context = f"{graph_context}\n\n{text_context}"
        else:
            # Prioritize text context for factual queries
            full_context = f"{text_context}\n\n{graph_context}"

        total_tokens = self._estimate_tokens(full_context)

        return {
            "graph_context": graph_context,
            "text_context": text_context,
            "full_context": full_context,
            "stats": {
                "graph_tokens": graph_tokens,
                "text_tokens": text_tokens,
                "total_tokens": total_tokens,
                "budget_used_pct": round(total_tokens / self.max_tokens * 100, 1),
                "token_method": "tiktoken" if TIKTOKEN_AVAILABLE else "estimate",
                "reranking_applied": self.use_reranking,
            }
        }


# Singleton instance
_assembler: Optional[ContextAssembler] = None


def get_context_assembler() -> ContextAssembler:
    """Get or create singleton ContextAssembler instance."""
    global _assembler
    if _assembler is None:
        _assembler = ContextAssembler()
    return _assembler
