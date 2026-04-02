"""
Gold Oracle Generator

For each question:
  1. Fetch docs via 3-layer retrieval (fetch_docs.py)
  2. Call Claude Opus 4.6 to generate structured Gold Reference
  3. Call same session for QC self-verification
  4. Flag items that need human review
"""

import json
import os
import sys
import re
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import anthropic
from config.settings import ANTHROPIC_API_KEY
from src.ablation.fetch_docs import fetch_docs_for_question, format_doc_for_oracle
from src.ablation.prompts import (
    ORACLE_SYSTEM, ORACLE_USER, QC_VERIFY,
    ENTITY_EXTRACT_SYSTEM, ENTITY_EXTRACT_USER,
)

ORACLE_MODEL = "claude-opus-4-6"
HAIKU_MODEL = "claude-3-haiku-20240307"

# Fields that always need human review regardless of verified flag
HIGH_RISK_PATTERNS = [
    r"\d+\s*年",          # specific year numbers
    r"第[一二三四五六七八九十\d]+",  # ordinal numbers
    r"先知|Harbinger",    # Fatui ranks
    r"\d+\s*个",          # counts
]


def _extract_json(text: str) -> Optional[dict]:
    """Extract first JSON object from model output (handles markdown fences and extra text)."""
    text = text.strip()

    # Strip ```json ... ``` or ``` ... ``` markdown fences
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost { ... } block using brace matching
    start = text.find('{')
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break
    return None


def _flag_review_items(gold: dict) -> dict:
    """
    Flag key_facts and relations that need human review:
    - verified=False items
    - Items containing high-risk patterns (specific numbers, ranks)
    """
    review_flags = []

    for i, fact in enumerate(gold.get("key_facts", [])):
        if not fact.get("verified", True):
            review_flags.append(f"key_facts[{i}]: verified=false — {fact.get('fact', '')[:60]}")
        elif any(re.search(p, fact.get("fact", "")) for p in HIGH_RISK_PATTERNS):
            review_flags.append(f"key_facts[{i}]: high-risk pattern — {fact.get('fact', '')[:60]}")

    if gold.get("coverage_notes", "none").lower() != "none":
        review_flags.append(f"coverage_notes: {gold['coverage_notes'][:100]}")

    gold["_review_flags"] = review_flags
    gold["_needs_human_review"] = len(review_flags) > 0
    return gold


def haiku_extract_entities(question: str, client: anthropic.Anthropic) -> list[str]:
    """Use Haiku to extract entities from question text (cheap fallback for empty explicit_entities)."""
    resp = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=300,
        system=ENTITY_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": ENTITY_EXTRACT_USER.format(question=question)}],
    )
    text = resp.content[0].text.strip()
    try:
        entities = json.loads(text)
        if isinstance(entities, list):
            return [str(e) for e in entities]
    except json.JSONDecodeError:
        pass
    return []


def generate_gold_reference(
    question_obj: dict,
    client: anthropic.Anthropic,
    verbose: bool = True,
) -> dict:
    """
    Full pipeline for one question:
      Step 1: Fetch docs (3 layers)
      Step 2: Oracle generation (Opus)
      Step 3: QC self-verification (Opus, same session)
      Step 4: Flag review items

    Returns the final Gold Reference dict with metadata.
    """
    qid = question_obj["id"]
    if verbose:
        print(f"\n[Oracle] Processing {qid}: {question_obj['question'][:60]}...")

    # ----------------------------------------------------------------
    # Step 1: Fetch documents
    # ----------------------------------------------------------------
    # Ensure we have entities — use Haiku fallback if explicit_entities empty
    if not question_obj.get("explicit_entities"):
        question_obj["explicit_entities"] = haiku_extract_entities(
            question_obj["question"], client
        )

    docs, fetch_stats = fetch_docs_for_question(question_obj)
    if verbose:
        print(f"  Docs: A={fetch_stats['layer_a']} B={fetch_stats['layer_b']} "
              f"C={fetch_stats['layer_c']} total={fetch_stats['total']}")

    docs_text = "\n\n".join(format_doc_for_oracle(d) for d in docs)
    if not docs_text:
        docs_text = "（未找到相关文档）"

    # ----------------------------------------------------------------
    # Step 2: Oracle generation
    # ----------------------------------------------------------------
    oracle_user_content = ORACLE_USER.format(
        docs_text=docs_text,
        question_id=qid,
        tier=question_obj["tier"],
        question_type=question_obj["question_type"],
        question=question_obj["question"],
    )

    messages = [{"role": "user", "content": oracle_user_content}]

    # Tier 3-4 need more output tokens (complex multi-hop answers)
    tier = question_obj.get("tier", 1)
    oracle_max_tokens = 4096 if tier >= 3 else 2000

    response = client.messages.create(
        model=ORACLE_MODEL,
        max_tokens=oracle_max_tokens,
        system=ORACLE_SYSTEM,
        messages=messages,
    )
    oracle_raw = response.content[0].text
    oracle_input_tokens = response.usage.input_tokens
    oracle_output_tokens = response.usage.output_tokens

    gold = _extract_json(oracle_raw)
    if not gold:
        print(f"  [WARNING] Failed to parse Oracle JSON for {qid}. Saving raw output.")
        gold = {"question_id": qid, "_parse_error": True, "_raw": oracle_raw}

    # ----------------------------------------------------------------
    # Step 3: QC self-verification (continue conversation)
    # ----------------------------------------------------------------
    messages.append({"role": "assistant", "content": oracle_raw})
    messages.append({"role": "user", "content": QC_VERIFY})

    qc_response = client.messages.create(
        model=ORACLE_MODEL,
        max_tokens=oracle_max_tokens,
        system=ORACLE_SYSTEM,
        messages=messages,
    )
    qc_raw = qc_response.content[0].text
    qc_input_tokens = qc_response.usage.input_tokens
    qc_output_tokens = qc_response.usage.output_tokens

    gold_qc = _extract_json(qc_raw)
    if gold_qc:
        gold = gold_qc  # Use QC-revised version
    else:
        print(f"  [WARNING] QC parse failed for {qid}, keeping original Oracle output.")

    # ----------------------------------------------------------------
    # Step 4: Flag review items
    # ----------------------------------------------------------------
    gold = _flag_review_items(gold)

    # ----------------------------------------------------------------
    # Attach metadata
    # ----------------------------------------------------------------
    total_input = oracle_input_tokens + qc_input_tokens
    total_output = oracle_output_tokens + qc_output_tokens
    # Opus 4.6 pricing: $15/1M input, $75/1M output
    cost = (total_input / 1e6 * 15) + (total_output / 1e6 * 75)

    gold["_meta"] = {
        "question_id": qid,
        "tier": question_obj["tier"],
        "question": question_obj["question"],
        "docs_fetched": fetch_stats,
        "tokens": {
            "oracle_in": oracle_input_tokens,
            "oracle_out": oracle_output_tokens,
            "qc_in": qc_input_tokens,
            "qc_out": qc_output_tokens,
            "total": total_input + total_output,
        },
        "cost_usd": round(cost, 4),
    }

    if verbose:
        flags = gold.get("_review_flags", [])
        status = f"⚠️  {len(flags)} flags" if flags else "✅ clean"
        print(f"  Cost: ${cost:.3f} | Tokens: {total_input + total_output} | {status}")

    return gold
