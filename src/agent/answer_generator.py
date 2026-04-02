"""
LoreMaster-AI - Answer Generator

Generates answers using Claude based on assembled context.
Implements prompt engineering for accurate, cited responses.
"""

import logging
import os
import sys
from typing import Dict, Optional

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

# Main answer generation prompt
ANSWER_PROMPT = """You are LoreMaster, an expert on Genshin Impact lore, especially the Sumeru region.

## Your Knowledge Sources
You have access to:
1. **Knowledge Graph**: Entity relationships extracted from official wiki
2. **Wiki Passages**: Relevant text passages from Genshin Impact Wiki

## Context Provided

{context}

## User Question
{question}

## Response Guidelines

### Language
- Respond in the SAME language as the user's question
- If question is in Chinese, answer in Chinese
- If question is in English, answer in English

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
  → Add relevant context and relationships

## Answer"""


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
    ) -> dict:
        """
        Generate an answer based on the question and context.

        Args:
            question: User's question
            context: Assembled context from retrieval
            max_tokens: Maximum response tokens

        Returns:
            Dict with:
            - answer: Generated answer text
            - usage: Token usage statistics
            - model: Model used
        """
        prompt = ANSWER_PROMPT.format(
            context=context,
            question=question,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        answer = response.content[0].text

        # Calculate cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        # Sonnet pricing: $3/M input, $15/M output
        cost = (input_tokens / 1e6 * 3) + (output_tokens / 1e6 * 15)

        return {
            "answer": answer,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": round(cost, 6),
            },
            "model": self.model,
        }

    def generate_with_retry(
        self,
        question: str,
        context: str,
        max_retries: int = 3,
    ) -> dict:
        """Generate answer with retry on failure."""
        last_error = None

        for attempt in range(max_retries):
            try:
                return self.generate(question, context)
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
