"""
LoreMaster-AI - Ablation Experiment Configuration

Provides fine-grained control over pipeline features for ablation studies.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LLMProvider(Enum):
    """Supported LLM providers for answer generation."""
    CLAUDE_SONNET = "claude-sonnet-4-20250514"
    CLAUDE_HAIKU = "claude-3-haiku-20240307"
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"


class ClassifierModel(Enum):
    """Model for query classification."""
    HAIKU = "claude-3-haiku-20240307"
    REGEX = "regex"  # Fallback to regex-based classification
    GPT_4O_MINI = "gpt-4o-mini"


@dataclass
class AblationConfig:
    """
    Configuration for ablation experiments.

    Each feature can be toggled on/off to measure its impact on:
    - Answer quality (accuracy, completeness)
    - Latency (response time)
    - Cost (API calls, tokens)

    Example usage:
        # Full pipeline (default)
        config = AblationConfig()

        # Vector-only (no graph)
        config = AblationConfig(use_graph_search=False, use_path_discovery=False)

        # Graph-only (no vector)
        config = AblationConfig(use_vector_search=False)

        # Baseline (no improvements)
        config = AblationConfig.baseline()
    """

    # ==========================================
    # Data Source Controls
    # ==========================================
    use_vector_search: bool = True       # Pinecone vector search
    use_graph_search: bool = True        # Neo4j entity relationships
    use_path_discovery: bool = True      # Neo4j shortest path (#7)
    use_full_text_enrichment: bool = True  # P3 full text loading

    # ==========================================
    # Query Processing Improvements
    # ==========================================
    use_embedding_cache: bool = True     # #2: LRU cache for embeddings
    use_semantic_classification: bool = True  # #8: Haiku-based classification
    use_query_expansion: bool = True     # #5: Haiku-based query expansion

    # ==========================================
    # Retrieval Improvements
    # ==========================================
    use_graph_ranking: bool = True       # #4: Evidence-based graph ranking
    use_multi_path: bool = True          # #7: Find alternative paths

    # ==========================================
    # Context Assembly Improvements
    # ==========================================
    use_context_reranking: bool = True   # #6: Entity-aware passage reranking
    use_tiktoken: bool = True            # #9: Precise token counting

    # ==========================================
    # Model Selection
    # ==========================================
    answer_model: LLMProvider = LLMProvider.CLAUDE_SONNET
    classifier_model: ClassifierModel = ClassifierModel.HAIKU

    # ==========================================
    # Retrieval Parameters
    # ==========================================
    vector_top_k: int = 8
    graph_max_relations: int = 15
    max_paths: int = 3
    max_hops: int = 3
    use_adaptive_depth: bool = True  # #10: Dynamic graph depth based on query complexity

    # ==========================================
    # Context Budget
    # ==========================================
    max_context_tokens: int = 6000
    graph_token_budget: int = 1500
    text_token_budget: int = 4500

    # ==========================================
    # Experiment Metadata
    # ==========================================
    experiment_name: str = "default"
    description: str = ""

    @classmethod
    def baseline(cls) -> "AblationConfig":
        """
        Baseline configuration with all improvements disabled.
        Uses only basic vector + graph search.
        """
        return cls(
            # Disable all improvements
            use_embedding_cache=False,
            use_semantic_classification=False,
            use_query_expansion=False,
            use_graph_ranking=False,
            use_multi_path=False,
            use_context_reranking=False,
            use_tiktoken=False,
            use_adaptive_depth=False,
            # Keep core functionality
            use_vector_search=True,
            use_graph_search=True,
            use_path_discovery=True,
            use_full_text_enrichment=True,
            # Metadata
            experiment_name="baseline",
            description="Baseline: no improvements, basic hybrid retrieval"
        )

    @classmethod
    def vector_only(cls) -> "AblationConfig":
        """Configuration using only vector search (no graph)."""
        return cls(
            use_graph_search=False,
            use_path_discovery=False,
            use_graph_ranking=False,
            use_multi_path=False,
            experiment_name="vector_only",
            description="Vector search only, no knowledge graph"
        )

    @classmethod
    def graph_only(cls) -> "AblationConfig":
        """Configuration using only graph search (no vector)."""
        return cls(
            use_vector_search=False,
            use_context_reranking=False,  # No passages to rerank
            experiment_name="graph_only",
            description="Knowledge graph only, no vector search"
        )

    @classmethod
    def full_pipeline(cls) -> "AblationConfig":
        """Full pipeline with all improvements enabled."""
        return cls(
            experiment_name="full_pipeline",
            description="Full pipeline with all improvements"
        )

    @classmethod
    def fast_mode(cls) -> "AblationConfig":
        """Optimized for speed: uses Haiku, disables expensive features."""
        return cls(
            answer_model=LLMProvider.CLAUDE_HAIKU,
            use_query_expansion=False,  # Save one API call
            use_multi_path=False,       # Faster graph queries
            vector_top_k=5,             # Fewer results
            graph_max_relations=10,
            experiment_name="fast_mode",
            description="Speed-optimized: Haiku model, reduced retrieval"
        )

    @classmethod
    def gpt4o_mode(cls) -> "AblationConfig":
        """Use GPT-4o for answer generation."""
        return cls(
            answer_model=LLMProvider.GPT_4O,
            classifier_model=ClassifierModel.GPT_4O_MINI,
            experiment_name="gpt4o_mode",
            description="GPT-4o for generation, GPT-4o-mini for classification"
        )

    @classmethod
    def gpt4o_mini_mode(cls) -> "AblationConfig":
        """Use GPT-4o-mini for cost-effective answer generation."""
        return cls(
            answer_model=LLMProvider.GPT_4O_MINI,
            classifier_model=ClassifierModel.GPT_4O_MINI,
            experiment_name="gpt4o_mini_mode",
            description="GPT-4o-mini for cost-effective generation"
        )

    @classmethod
    def llm_only(cls) -> "AblationConfig":
        """Pure LLM — no retrieval at all. Measures raw model knowledge."""
        return cls(
            use_vector_search=False,
            use_graph_search=False,
            use_path_discovery=False,
            use_full_text_enrichment=False,
            use_graph_ranking=False,
            use_multi_path=False,
            use_context_reranking=False,
            use_query_expansion=False,
            use_adaptive_depth=False,
            experiment_name="llm_only",
            description="No retrieval — pure model knowledge baseline"
        )

    # ==========================================
    # 8 Study Configurations
    # ==========================================

    @classmethod
    def s4_llm(cls) -> "AblationConfig":
        """Claude Sonnet 4, no retrieval."""
        c = cls.llm_only()
        c.answer_model = LLMProvider.CLAUDE_SONNET
        c.experiment_name = "S4-LLM"
        c.description = "Claude Sonnet 4 — pure LLM, no retrieval"
        return c

    @classmethod
    def s4_vec(cls) -> "AblationConfig":
        """Claude Sonnet 4, vector-only retrieval."""
        c = cls.vector_only()
        c.answer_model = LLMProvider.CLAUDE_SONNET
        c.experiment_name = "S4-VEC"
        c.description = "Claude Sonnet 4 — Pinecone vector search only"
        return c

    @classmethod
    def s4_grf(cls) -> "AblationConfig":
        """Claude Sonnet 4, graph-only retrieval."""
        c = cls.graph_only()
        c.answer_model = LLMProvider.CLAUDE_SONNET
        c.experiment_name = "S4-GRF"
        c.description = "Claude Sonnet 4 — Neo4j graph search only"
        return c

    @classmethod
    def s4_hyb(cls) -> "AblationConfig":
        """Claude Sonnet 4, full hybrid retrieval."""
        c = cls.full_pipeline()
        c.answer_model = LLMProvider.CLAUDE_SONNET
        c.experiment_name = "S4-HYB"
        c.description = "Claude Sonnet 4 — full hybrid (vector + graph)"
        return c

    @classmethod
    def g4_llm(cls) -> "AblationConfig":
        """GPT-4o, no retrieval."""
        c = cls.llm_only()
        c.answer_model = LLMProvider.GPT_4O
        c.classifier_model = ClassifierModel.GPT_4O_MINI
        c.experiment_name = "G4-LLM"
        c.description = "GPT-4o — pure LLM, no retrieval"
        return c

    @classmethod
    def g4_vec(cls) -> "AblationConfig":
        """GPT-4o, vector-only retrieval."""
        c = cls.vector_only()
        c.answer_model = LLMProvider.GPT_4O
        c.classifier_model = ClassifierModel.GPT_4O_MINI
        c.experiment_name = "G4-VEC"
        c.description = "GPT-4o — Pinecone vector search only"
        return c

    @classmethod
    def g4_grf(cls) -> "AblationConfig":
        """GPT-4o, graph-only retrieval."""
        c = cls.graph_only()
        c.answer_model = LLMProvider.GPT_4O
        c.classifier_model = ClassifierModel.GPT_4O_MINI
        c.experiment_name = "G4-GRF"
        c.description = "GPT-4o — Neo4j graph search only"
        return c

    @classmethod
    def g4_hyb(cls) -> "AblationConfig":
        """GPT-4o, full hybrid retrieval."""
        c = cls.full_pipeline()
        c.answer_model = LLMProvider.GPT_4O
        c.classifier_model = ClassifierModel.GPT_4O_MINI
        c.experiment_name = "G4-HYB"
        c.description = "GPT-4o — full hybrid (vector + graph)"
        return c

    @classmethod
    def s4_hyb_p0(cls) -> "AblationConfig":
        """Claude Sonnet 4, full hybrid — P0 grounding prompt."""
        c = cls.full_pipeline()
        c.answer_model = LLMProvider.CLAUDE_SONNET
        c.experiment_name = "S4-HYB-P0"
        c.description = "Claude Sonnet 4 — hybrid + P0 grounding rules"
        return c

    def to_dict(self) -> dict:
        """Convert config to dictionary for logging/serialization."""
        return {
            # Data sources
            "use_vector_search": self.use_vector_search,
            "use_graph_search": self.use_graph_search,
            "use_path_discovery": self.use_path_discovery,
            "use_full_text_enrichment": self.use_full_text_enrichment,
            # Query processing
            "use_embedding_cache": self.use_embedding_cache,
            "use_semantic_classification": self.use_semantic_classification,
            "use_query_expansion": self.use_query_expansion,
            # Retrieval
            "use_graph_ranking": self.use_graph_ranking,
            "use_multi_path": self.use_multi_path,
            "use_adaptive_depth": self.use_adaptive_depth,
            # Context
            "use_context_reranking": self.use_context_reranking,
            "use_tiktoken": self.use_tiktoken,
            # Models
            "answer_model": self.answer_model.value,
            "classifier_model": self.classifier_model.value,
            # Parameters
            "vector_top_k": self.vector_top_k,
            "graph_max_relations": self.graph_max_relations,
            "max_paths": self.max_paths,
            # Metadata
            "experiment_name": self.experiment_name,
            "description": self.description,
        }

    def summary(self) -> str:
        """Generate a human-readable summary of the configuration."""
        enabled = []
        disabled = []

        features = [
            ("Vector Search", self.use_vector_search),
            ("Graph Search", self.use_graph_search),
            ("Path Discovery", self.use_path_discovery),
            ("Embedding Cache (#2)", self.use_embedding_cache),
            ("Graph Ranking (#4)", self.use_graph_ranking),
            ("Query Expansion (#5)", self.use_query_expansion),
            ("Context Reranking (#6)", self.use_context_reranking),
            ("Multi-Path (#7)", self.use_multi_path),
            ("Semantic Classification (#8)", self.use_semantic_classification),
            ("Tiktoken (#9)", self.use_tiktoken),
            ("Adaptive Depth (#10)", self.use_adaptive_depth),
        ]

        for name, flag in features:
            if flag:
                enabled.append(name)
            else:
                disabled.append(name)

        lines = [
            f"=== {self.experiment_name} ===",
            f"Description: {self.description}" if self.description else "",
            f"Answer Model: {self.answer_model.value}",
            f"Classifier: {self.classifier_model.value}",
            f"",
            f"Enabled ({len(enabled)}): {', '.join(enabled)}",
            f"Disabled ({len(disabled)}): {', '.join(disabled) if disabled else 'None'}",
        ]
        return "\n".join(line for line in lines if line)


# Pre-defined experiment configurations
ABLATION_PRESETS = {
    "baseline": AblationConfig.baseline(),
    "vector_only": AblationConfig.vector_only(),
    "graph_only": AblationConfig.graph_only(),
    "full_pipeline": AblationConfig.full_pipeline(),
    "fast_mode": AblationConfig.fast_mode(),
    "gpt4o_mode": AblationConfig.gpt4o_mode(),
    "gpt4o_mini_mode": AblationConfig.gpt4o_mini_mode(),
    "llm_only": AblationConfig.llm_only(),
    # 8 study configurations
    "S4-LLM": AblationConfig.s4_llm(),
    "S4-VEC": AblationConfig.s4_vec(),
    "S4-GRF": AblationConfig.s4_grf(),
    "S4-HYB": AblationConfig.s4_hyb(),
    "G4-LLM": AblationConfig.g4_llm(),
    "G4-VEC": AblationConfig.g4_vec(),
    "G4-GRF": AblationConfig.g4_grf(),
    "G4-HYB": AblationConfig.g4_hyb(),
    # P0 improvement configurations
    "S4-HYB-P0": AblationConfig.s4_hyb_p0(),
}

# Ordered list for the ablation study run
STUDY_CONFIGS = [
    "S4-LLM", "S4-VEC", "S4-GRF", "S4-HYB",
    "G4-LLM", "G4-VEC", "G4-GRF", "G4-HYB",
]


def get_preset(name: str) -> AblationConfig:
    """Get a pre-defined ablation configuration by name."""
    if name not in ABLATION_PRESETS:
        available = ", ".join(ABLATION_PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    return ABLATION_PRESETS[name]
