"""
LoreMaster-AI - RAG Pipeline

Main entry point for the LoreMaster Q&A system.
Integrates all components: Query Processing → Retrieval → Context Assembly → Answer Generation

Optimizations applied:
- SemanticAnswerCache: identical/similar questions skip the full pipeline (<100ms, zero cost)
- SessionManager: multi-turn conversation history injected into generation
"""

import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from src.agent.query_processor import QueryProcessor
from src.agent.retriever import HybridRetriever
from src.agent.context_assembler import ContextAssembler
from src.agent.answer_generator import AnswerGenerator
from src.agent.query_cache import SemanticAnswerCache, get_answer_cache
from src.agent.session_manager import Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class LoreMasterPipeline:
    """
    Main RAG pipeline for Genshin Impact lore Q&A.

    Architecture:
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │ Query Processor │ ──▶ │ Hybrid Retriever│ ──▶ │Context Assembler│
    │                 │     │                 │     │                 │
    │ • Entity Extract│     │ • Vector Search │     │ • Format Graph  │
    │ • Alias Resolve │     │ • Graph Search  │     │ • Format Text   │
    │ • Query Classify│     │ • Path Discovery│     │ • Token Control │
    │ • Embed Query   │     │ • Circuit Breaker     │                 │
    └─────────────────┘     └─────────────────┘     └─────────────────┘
                                                            │
                                                            ▼
                                                    ┌─────────────────┐
                                                    │Answer Generator │
                                                    │                 │
                                                    │ • Claude Sonnet │
                                                    │ • Prompt Cache  │
                                                    │ • Streaming     │
                                                    └─────────────────┘
    """

    def __init__(
        self,
        vector_top_k: int = 8,
        graph_max_relations: int = 15,
        verbose: bool = False,
    ):
        self.vector_top_k = vector_top_k
        self.graph_max_relations = graph_max_relations
        self.verbose = verbose

        logger.info("Initializing LoreMaster Pipeline...")

        self.query_processor = QueryProcessor()
        self.retriever = HybridRetriever()
        self.context_assembler = ContextAssembler()
        self.answer_generator = AnswerGenerator()
        self.answer_cache = get_answer_cache()

        logger.info("Pipeline ready!")

    def close(self):
        """Close database connections."""
        self.retriever.close()

    def answer(self, question: str, session: Optional[Session] = None) -> dict:
        """
        Answer a user question using the full RAG pipeline.

        Args:
            question: User's question about Genshin Impact lore
            session: Optional Session object for multi-turn conversation context

        Returns:
            Dict containing answer, sources, entities, query_type, timing, usage
        """
        result = {
            "question": question,
            "answer": "",
            "sources": [],
            "entities": [],
            "query_type": "",
            "path": None,
            "timing": {},
            "usage": {},
            "cache_hit": False,
        }

        total_start = time.time()

        # ============================================
        # Step 0: Semantic Cache Check
        # Check cache before any expensive API calls.
        # embed_query uses LRU so repeated questions are instant.
        # ============================================
        embedding_for_cache = self.query_processor.embed_query(question)
        cached_result = self.answer_cache.lookup(embedding_for_cache, question=question)
        if cached_result is not None:
            cached_copy = dict(cached_result)
            cached_copy["cache_hit"] = True
            cached_copy["timing"] = {"total": round(time.time() - total_start, 3)}
            return cached_copy

        # ============================================
        # Step 1: Query Processing (parallel API calls)
        # ============================================
        step_start = time.time()

        # Apply coreference resolution if session history exists
        resolved_question = question
        if session and session.turns:
            from src.agent.session_manager import get_session_manager
            sm = get_session_manager()
            resolved_question = sm.resolve_coreferences(question, session)

        processed = self.query_processor.process(resolved_question)

        result["entities"] = processed["canonical_entities"]
        result["query_type"] = processed["query_type"]
        result["timing"]["query_processing"] = round(time.time() - step_start, 3)

        if self.verbose:
            logger.info("Query processed: entities=%s, type=%s",
                       processed["canonical_entities"], processed["query_type"])

        # ============================================
        # Step 2: Hybrid Retrieval
        # ============================================
        step_start = time.time()

        retrieval_results = self.retriever.retrieve(
            query=resolved_question,
            embedding=processed["embedding"],
            entities=processed["canonical_entities"],
            query_type=processed["query_type"],
            vector_top_k=self.vector_top_k,
            graph_max_relations=self.graph_max_relations,
        )

        result["sources"] = [
            {"title": r["title"], "score": r["score"]}
            for r in retrieval_results["vector_results"]
        ]
        result["_vector_results"] = retrieval_results["vector_results"]

        path_results = retrieval_results.get("path_results")
        if path_results and path_results.get("found"):
            result["path"] = {
                "nodes": path_results.get("nodes", []),
                "relations": path_results.get("relations", []),
                "evidences": path_results.get("evidences", []),
                "alternative_paths": [
                    {"nodes": alt.get("nodes", []), "relations": alt.get("relations", [])}
                    for alt in path_results.get("alternative_paths", [])
                ],
            }

        result["timing"]["retrieval"] = round(time.time() - step_start, 3)

        # ============================================
        # Step 3: Context Assembly
        # ============================================
        step_start = time.time()

        context = self.context_assembler.assemble(
            vector_results=retrieval_results["vector_results"],
            graph_results=retrieval_results["graph_results"],
            path_results=retrieval_results.get("path_results"),
            query_type=processed["query_type"],
            query_entities=processed["canonical_entities"],
        )

        result["timing"]["context_assembly"] = round(time.time() - step_start, 3)
        result["context_stats"] = context["stats"]

        # ============================================
        # Step 4: Answer Generation (with Prompt Cache + session history)
        # ============================================
        step_start = time.time()

        history = ""
        if session:
            from src.agent.session_manager import get_session_manager
            history = get_session_manager().get_history_context(session)

        answer_result = self.answer_generator.generate(
            question=question,
            context=context["full_context"],
            history=history,
        )

        result["answer"] = answer_result["answer"]
        result["usage"] = answer_result["usage"]
        result["timing"]["answer_generation"] = round(time.time() - step_start, 3)

        # ============================================
        # Finalize + Cache Store
        # ============================================
        result["timing"]["total"] = round(time.time() - total_start, 3)

        # Store in semantic cache (don't cache session-contextualized answers)
        if not session or not session.turns:
            self.answer_cache.store(embedding_for_cache, question, result)

        return result

    def answer_batch(self, questions: List[str]) -> List[dict]:
        """Answer multiple questions."""
        return [self.answer(q) for q in questions]


def demo():
    """Run a demo of the pipeline."""
    pipeline = LoreMasterPipeline(verbose=True)

    test_questions = [
        "What is the relationship between Scaramouche and Raiden Shogun?",
        "Who is Nahida?",
        "为什么流浪者要从世界树抹除自己的存在？",
    ]

    for question in test_questions:
        print("\n" + "=" * 70)
        print(f"Q: {question}")
        print("=" * 70)

        result = pipeline.answer(question)

        print(f"\nA: {result['answer']}")
        print(f"\n--- Metadata ---")
        print(f"Entities: {result['entities']}")
        print(f"Query Type: {result['query_type']}")
        print(f"Cache Hit: {result['cache_hit']}")
        if result['path']:
            print(f"Path: {result['path']}")
        print(f"Sources: {[s['title'] for s in result['sources'][:3]]}")
        print(f"Timing: {result['timing']}")
        print(f"Cost: ${result['usage'].get('cost_usd', 0):.6f}")

    pipeline.close()


if __name__ == "__main__":
    demo()
