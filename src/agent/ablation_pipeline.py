"""
LoreMaster-AI - Ablation-Aware Pipeline

Pipeline wrapper that respects ablation configuration for experiments.
"""

import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import anthropic
from openai import OpenAI

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from src.agent.ablation_config import AblationConfig, LLMProvider, ClassifierModel
from src.agent.query_processor import QueryProcessor
from src.agent.retriever import HybridRetriever
from src.agent.context_assembler import ContextAssembler
from src.agent.adaptive_depth import AdaptiveDepthManager
from config.settings import ANTHROPIC_API_KEY, OPENAI_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class AblationPipeline:
    """
    RAG Pipeline with ablation experiment support.

    Allows fine-grained control over which features are enabled/disabled
    for systematic evaluation of each component's contribution.
    """

    def __init__(self, config: Optional[AblationConfig] = None, verbose: bool = False):
        """
        Initialize pipeline with ablation configuration.

        Args:
            config: Ablation configuration. If None, uses full pipeline.
            verbose: Enable detailed logging.
        """
        self.config = config or AblationConfig.full_pipeline()
        self.verbose = verbose

        logger.info(f"Initializing AblationPipeline: {self.config.experiment_name}")

        # Initialize components with config-aware settings
        self._init_query_processor()
        self._init_retriever()
        self._init_context_assembler()
        self._init_answer_generator()

        # #10: Adaptive depth manager
        self.depth_manager = AdaptiveDepthManager() if self.config.use_adaptive_depth else None

        logger.info("AblationPipeline ready!")
        if verbose:
            print(self.config.summary())

    def _init_query_processor(self):
        """Initialize query processor with ablation settings."""
        self.query_processor = QueryProcessor(
            use_semantic_classification=self.config.use_semantic_classification,
            use_query_expansion=self.config.use_query_expansion,
        )
        # Control embedding cache
        if not self.config.use_embedding_cache:
            self.query_processor._embedding_cache.maxsize = 0  # Disable cache

    def _init_retriever(self):
        """Initialize retriever (only if needed)."""
        if self.config.use_vector_search or self.config.use_graph_search:
            self.retriever = HybridRetriever()
        else:
            self.retriever = None

    def _init_context_assembler(self):
        """Initialize context assembler with ablation settings."""
        self.context_assembler = ContextAssembler(
            max_tokens=self.config.max_context_tokens,
            graph_budget=self.config.graph_token_budget,
            text_budget=self.config.text_token_budget,
            use_reranking=self.config.use_context_reranking,
        )
        # Control tiktoken usage
        if not self.config.use_tiktoken:
            # Force estimation mode
            from src.agent import context_assembler as ca
            ca.TIKTOKEN_AVAILABLE = False

    def _init_answer_generator(self):
        """Initialize LLM client based on config."""
        self.answer_model = self.config.answer_model

        if self.answer_model in [LLMProvider.CLAUDE_SONNET, LLMProvider.CLAUDE_HAIKU]:
            self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            self.openai_client = None
        else:
            self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
            self.anthropic_client = None

    def close(self):
        """Close database connections."""
        if self.retriever:
            self.retriever.close()

    def _generate_answer(self, question: str, context: str) -> dict:
        """Generate answer using configured model."""
        prompt = self._build_prompt(question, context)

        start_time = time.time()

        if self.answer_model in [LLMProvider.CLAUDE_SONNET, LLMProvider.CLAUDE_HAIKU]:
            response = self.anthropic_client.messages.create(
                model=self.answer_model.value,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Calculate cost based on model
            if self.answer_model == LLMProvider.CLAUDE_SONNET:
                cost = (input_tokens / 1e6 * 3) + (output_tokens / 1e6 * 15)
            else:  # Haiku
                cost = (input_tokens / 1e6 * 0.25) + (output_tokens / 1e6 * 1.25)

        else:  # OpenAI models
            response = self.openai_client.chat.completions.create(
                model=self.answer_model.value,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # GPT-4o pricing
            if self.answer_model == LLMProvider.GPT_4O:
                cost = (input_tokens / 1e6 * 2.5) + (output_tokens / 1e6 * 10)
            else:  # GPT-4o-mini
                cost = (input_tokens / 1e6 * 0.15) + (output_tokens / 1e6 * 0.6)

        return {
            "answer": answer,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": round(cost, 6),
            },
            "model": self.answer_model.value,
            "generation_time": round(time.time() - start_time, 3),
        }

    def _build_prompt(self, question: str, context: str) -> str:
        """Build answer generation prompt."""
        return f"""You are LoreMaster, an expert on Genshin Impact lore.

## Context
{context}

## Question
{question}

## Guidelines
- Answer in the same language as the question
- Cite sources using [Source: Page Title] format
- Only use information from the provided context
- If context is insufficient, clearly state this

## Grounding Rules (CRITICAL — follow strictly)
- ONLY assert facts that are explicitly stated in the provided context above.
- If the question asks about a specific event, case, named example, or named person that does NOT appear anywhere in the provided context, explicitly state: "The available documents contain no record of this." Do NOT fabricate a plausible example or event.
- For inferences that go beyond what the documents directly state, always use hedging language ("This may suggest...", "It can be inferred...", "Based on the available evidence..."). NEVER present an inference as a confirmed fact.
- For specific names, dates, titles, or numerical facts, only state what is directly documented. If unsure, say so.
- It is better to give a shorter, accurate answer than a longer answer that invents details.

## Answer"""

    def answer(self, question: str) -> dict:
        """
        Answer a question using the ablation-configured pipeline.

        Args:
            question: User's question

        Returns:
            Dict with answer, metadata, and timing breakdown
        """
        result = {
            "question": question,
            "answer": "",
            "config": self.config.experiment_name,
            "sources": [],
            "entities": [],
            "query_type": "",
            "path": None,
            "timing": {},
            "usage": {},
            "ablation_flags": self.config.to_dict(),
        }

        total_start = time.time()

        # ============================================
        # Step 1: Query Processing
        # ============================================
        step_start = time.time()
        processed = self.query_processor.process(question)

        result["entities"] = processed["canonical_entities"]
        result["query_type"] = processed["query_type"]
        result["expansions"] = processed.get("expansions", [])
        result["timing"]["query_processing"] = round(time.time() - step_start, 3)

        # ============================================
        # Step 2: Retrieval (respecting ablation config)
        # ============================================
        step_start = time.time()
        retrieval_results = self._perform_retrieval(processed)

        result["sources"] = [
            {"title": r.get("title", "Unknown"), "score": r.get("score", 0)}
            for r in retrieval_results.get("vector_results", [])
        ]

        path_results = retrieval_results.get("path_results")
        if path_results and path_results.get("found"):
            result["path"] = path_results["path_steps"]

        result["timing"]["retrieval"] = round(time.time() - step_start, 3)

        # ============================================
        # Step 3: Context Assembly
        # ============================================
        step_start = time.time()
        context = self.context_assembler.assemble(
            vector_results=retrieval_results.get("vector_results", []),
            graph_results=retrieval_results.get("graph_results", []),
            path_results=retrieval_results.get("path_results"),
            query_type=processed["query_type"],
            query_entities=processed["canonical_entities"],
        )

        result["timing"]["context_assembly"] = round(time.time() - step_start, 3)
        result["context_stats"] = context["stats"]

        # ============================================
        # Step 4: Answer Generation
        # ============================================
        step_start = time.time()
        answer_result = self._generate_answer(question, context["full_context"])

        result["answer"] = answer_result["answer"]
        result["usage"] = answer_result["usage"]
        result["timing"]["answer_generation"] = round(time.time() - step_start, 3)

        # ============================================
        # Finalize
        # ============================================
        result["timing"]["total"] = round(time.time() - total_start, 3)

        return result

    def _perform_retrieval(self, processed: dict) -> dict:
        """Perform retrieval respecting ablation configuration."""
        results = {
            "vector_results": [],
            "graph_results": [],
            "path_results": None,
        }

        if not self.retriever:
            return results

        entities = processed["canonical_entities"]
        embedding = processed["embedding"]
        query_type = processed["query_type"]

        # Vector search
        if self.config.use_vector_search:
            results["vector_results"] = self.retriever.vector_search(
                embedding=embedding,
                top_k=self.config.vector_top_k,
            )
            # Optionally skip full text enrichment
            if not self.config.use_full_text_enrichment:
                for r in results["vector_results"]:
                    r["full_text"] = r.get("text", "")  # Use chunk text only

        # Graph search
        if self.config.use_graph_search and entities:
            results["graph_results"] = self.retriever.graph_search_multi_entity(
                entities=entities,
                max_relations_per_entity=self.config.graph_max_relations,
            )

            # Apply ranking if enabled
            if self.config.use_graph_ranking:
                results["graph_results"] = self.retriever._rank_graph_results(
                    results["graph_results"],
                    query_entities=entities,
                )

        # Path discovery
        if (self.config.use_path_discovery and
            query_type in ["RELATIONSHIP", "MULTI_HOP"] and
            len(entities) >= 2):

            # #10: Use adaptive depth if enabled
            if self.depth_manager:
                depth_params = self.depth_manager.get_search_params(
                    query=processed.get("original_query", ""),
                    entities=entities,
                    query_type=query_type,
                )
                max_hops = depth_params["max_hops"]
                max_paths = depth_params["max_paths"]
                results["depth_analysis"] = depth_params["analysis"]
            else:
                max_hops = self.config.max_hops
                max_paths = self.config.max_paths if self.config.use_multi_path else 1

            results["path_results"] = self.retriever.graph_search_path(
                entity1=entities[0],
                entity2=entities[1],
                max_hops=max_hops,
                max_paths=max_paths,
            )

        return results


def run_ablation_experiment(
    questions: List[str],
    configs: List[AblationConfig],
    output_file: Optional[str] = None,
) -> List[dict]:
    """
    Run ablation experiments with multiple configurations.

    Args:
        questions: List of test questions
        configs: List of ablation configurations to test
        output_file: Optional path to save results as JSON

    Returns:
        List of experiment results
    """
    all_results = []

    for config in configs:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running experiment: {config.experiment_name}")
        logger.info(f"{'='*60}")

        pipeline = AblationPipeline(config=config, verbose=True)

        config_results = {
            "config": config.to_dict(),
            "results": [],
        }

        for i, question in enumerate(questions, 1):
            logger.info(f"\n[{i}/{len(questions)}] {question[:50]}...")
            result = pipeline.answer(question)
            config_results["results"].append(result)

            logger.info(f"  Time: {result['timing']['total']}s | Cost: ${result['usage']['cost_usd']:.4f}")

        pipeline.close()
        all_results.append(config_results)

    # Save results
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        logger.info(f"\nResults saved to: {output_file}")

    return all_results


if __name__ == "__main__":
    from src.agent.ablation_config import ABLATION_PRESETS

    # Test with a single question and multiple configs
    test_questions = [
        "What is the relationship between King Deshret and Nabu Malikata?",
    ]

    configs_to_test = [
        ABLATION_PRESETS["full_pipeline"],
        ABLATION_PRESETS["baseline"],
        ABLATION_PRESETS["vector_only"],
    ]

    results = run_ablation_experiment(
        questions=test_questions,
        configs=configs_to_test,
        output_file="ablation_results.json",
    )

    # Print summary
    print("\n" + "="*60)
    print("ABLATION EXPERIMENT SUMMARY")
    print("="*60)
    for exp in results:
        config_name = exp["config"]["experiment_name"]
        avg_time = sum(r["timing"]["total"] for r in exp["results"]) / len(exp["results"])
        avg_cost = sum(r["usage"]["cost_usd"] for r in exp["results"]) / len(exp["results"])
        print(f"\n{config_name}:")
        print(f"  Avg Time: {avg_time:.2f}s")
        print(f"  Avg Cost: ${avg_cost:.4f}")
