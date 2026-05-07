"""
LoreMaster-AI - Answer Generator

Generates answers using Claude based on assembled context.
Implements prompt engineering for accurate, cited responses.

Optimizations:
- Static instructions extracted to system= parameter for Anthropic Prompt Cache
  (cache hit: $0.30/M vs full price $3/M, ~30% cost reduction)
- generate_stream() for streaming token-by-token responses (TTFB <500ms)
"""

import logging
import os
import sys
from typing import Dict, Generator, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import anthropic

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import ANTHROPIC_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1500

# Static system prompt — never changes between requests → Anthropic caches it automatically.
# Cached tokens billed at $0.30/M (read) vs $3/M (new), ~10x cheaper.
SYSTEM_PROMPT = """You are LoreMaster, an expert on Genshin Impact lore, especially the Sumeru region.

## Your Knowledge Sources
You have access to:
1. **Knowledge Graph**: Entity relationships extracted from official wiki
2. **Wiki Passages**: Relevant text passages from Genshin Impact Wiki

## Response Guidelines

### Language
- ALWAYS respond in English, regardless of the language of the user's question

### Citation Format
- Cite sources inline using [Source: Page Title] format
- For relationship claims, reference the connection: [Relation: Entity1 → Entity2]

### Answer Structure
1. **Direct Answer**: Start with a clear, concise answer to the question
2. **Supporting Evidence**: Provide specific details from the context
3. **Connections**: For relationship questions, explain each link in the chain

### Honesty Rules
- ONLY use information from the provided context
- If the context doesn't contain sufficient information, clearly state: "Based on the available information, I cannot fully answer this question."
- NEVER invent facts not present in the context
- Distinguish between confirmed facts and reasonable inferences

### Special Handling
- For "what is the relationship between A and B" questions:
  → Trace the connection path step by step
  → Explain the nature of each relationship

- For factual questions ("Who is X?", "What is Y?"):
  → Provide key identifying information first
  → Add relevant context and relationships"""


def _build_user_message(context: str, question: str, history: str = "") -> str:
    """Build the dynamic user message with context and question."""
    parts = []
    if history:
        parts.append(f"## Conversation History\n{history}")
    parts.append(f"## Context\n{context}")
    parts.append(f"## Question\n{question}")
    return "\n\n".join(parts)


class AnswerGenerator:
    """Generates answers using Claude with retrieved context."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model

    def generate(
        self,
        question: str,
        context: str,
        max_tokens: int = MAX_TOKENS,
        history: str = "",
    ) -> dict:
        """
        Generate an answer based on the question and context.

        Args:
            question: User's question
            context: Assembled context from retrieval
            max_tokens: Maximum response tokens
            history: Optional formatted conversation history

        Returns:
            Dict with answer, usage, model
        """
        user_content = _build_user_message(context, question, history)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        answer = response.content[0].text

        # Token usage — Prompt Cache fields may be present
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        # Sonnet pricing: $3/M input, $15/M output, $0.30/M cache_read, $3.75/M cache_write
        cost = (
            (input_tokens - cache_read - cache_write) / 1e6 * 3.00
            + cache_read / 1e6 * 0.30
            + cache_write / 1e6 * 3.75
            + output_tokens / 1e6 * 15.00
        )

        return {
            "answer": answer,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                "cost_usd": round(cost, 6),
            },
            "model": self.model,
        }

    def generate_stream(
        self,
        question: str,
        context: str,
        max_tokens: int = MAX_TOKENS,
        history: str = "",
    ) -> Generator[str, None, None]:
        """
        Stream answer tokens one by one.

        Yields raw text chunks as they arrive from the API.
        TTFB drops from 3-5s to <500ms.
        """
        user_content = _build_user_message(context, question, history)

        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    def generate_with_retry(
        self,
        question: str,
        context: str,
        max_retries: int = 3,
        history: str = "",
    ) -> dict:
        """Generate answer with retry on failure."""
        last_error = None

        for attempt in range(max_retries):
            try:
                return self.generate(question, context, history=history)
            except anthropic.RateLimitError as e:
                logger.warning("Rate limit (attempt %d): %s", attempt + 1, e)
                last_error = e
                import time
                time.sleep(2 ** attempt)
            except anthropic.APIError as e:
                logger.error("API error (attempt %d): %s", attempt + 1, e)
                last_error = e

        return {
            "answer": f"Error generating answer: {last_error}",
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0},
            "model": self.model,
            "error": str(last_error),
        }


# Singleton instance
_generator: Optional[AnswerGenerator] = None


def get_answer_generator() -> AnswerGenerator:
    """Get or create singleton AnswerGenerator instance."""
    global _generator
    if _generator is None:
        _generator = AnswerGenerator()
    return _generator
