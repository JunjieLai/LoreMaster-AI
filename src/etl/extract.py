"""
LoreMaster-AI ETL - Step 8: Extract

Extracts knowledge graph entities and relationship triples from
cleaned documents using Claude Sonnet 4. Processes core documents
within a $10 budget with checkpoint/resume support.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import anthropic

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_clean.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data/processed/triples")
ENTITIES_PATH = os.path.join(OUTPUT_DIR, "entities.jsonl")
TRIPLES_PATH = os.path.join(OUTPUT_DIR, "triples.jsonl")
RAW_PATH = os.path.join(OUTPUT_DIR, "extract_raw.jsonl")
CHECKPOINT_PATH = os.path.join(OUTPUT_DIR, ".extract_checkpoint")

# Model config
MODEL = "claude-sonnet-4-20250514"
MAX_CONTENT_CHARS = 4000
MAX_RETRIES = 5
RETRY_DELAY = 5
REQUEST_DELAY = 0.3  # seconds between API calls

# Budget control (total across all runs, including resumed)
BUDGET_USD = 14.0
INPUT_COST_PER_M = 3.0   # $/1M input tokens (Sonnet 4)
OUTPUT_COST_PER_M = 15.0  # $/1M output tokens

# Document selection config
# Priority: process all docs of these types (high lore value)
PRIORITY_TYPES = {"PlayableCharacter", "Book", "Character"}

# Capped: process up to N docs sorted by content length
CAPPED_TYPES = {
    "NPC": 150,
    "Enemy": 80,
    "Location": 80,
    "Quest": 60,
    "Weapon": 50,
    "Artifact": 40,
    "Concept": 60,
    "Item": 50,
    "Event": 30,
}

# Skip: no relationship extraction value
SKIP_TYPES = {
    "Constellation", "Talent", "Achievement", "Furnishing",
    "Soundtrack", "Food", "Material", "TCG Card", "TCG",
    "Dialogue", "Other",
}

EXTRACTION_PROMPT = """You are a knowledge graph extraction expert for Genshin Impact lore (Sumeru region focus).

Given the following wiki document, extract ALL meaningful entities and relationships.

Document Title: {title}
Entity Type: {entity_type}
Region: {regions}

Content:
{content}

Extract entities and relationships as JSON.

ENTITY TYPES:
- Character: Any named character (playable, NPC, historical figure)
- Location: Named places (cities, regions, domains, landmarks)
- Organization: Factions, nations, groups (Akademiya, Fatui, etc.)
- Event: Historical or story events
- Item: Named weapons, artifacts, books, important objects
- Concept: Elements, powers, lore concepts (Gnosis, Vision, Irminsul, etc.)

RELATION TYPES:
- AFFILIATED_WITH: character belongs to an organization
- MEMBER_OF: character is member of a group/faction
- LOCATED_IN: entity is located in a place
- PART_OF: location is part of a larger region
- RULES: character rules/governs a location or organization
- CREATED: character created an item or concept
- WIELDER_OF: character wields a weapon or element
- POSSESSES: character possesses an item or power
- SUCCEEDED: character succeeded another in a role
- MENTOR_OF: character mentored another
- ALLY_OF: characters are allies
- ENEMY_OF: characters are enemies/adversaries
- SIBLING_OF: characters are siblings
- PARENT_OF: character is parent of another
- PARTICIPATED_IN: character participated in an event
- ORIGINATED_FROM: character/entity originates from a location
- TRANSFORMED_INTO: entity transformed into another form
- SEALED: character sealed another entity
- RELATED_TO: general significant relationship (use sparingly)

Return ONLY valid JSON (no markdown fences) with this exact structure:
{{"entities": [{{"name": "Entity Name", "type": "Character", "description": "Brief description"}}], "triples": [{{"head": "Entity A", "relation": "RELATION_TYPE", "tail": "Entity B", "evidence": "Brief quote or paraphrase from text"}}]}}

Rules:
1. Use canonical names consistently across entities and triples
2. Only extract relationships explicitly stated or strongly implied in the text
3. Every entity mentioned in a triple must also appear in the entities list
4. Keep descriptions under 30 words, evidence under 40 words
5. Always extract the document's main subject as an entity
6. Prefer specific relation types over RELATED_TO"""


def select_documents(docs):
    """Select documents based on the $10 budget plan."""
    selected = []

    # Group by entity type
    by_type = {}
    for doc in docs:
        et = doc["entity_type"]
        if et not in by_type:
            by_type[et] = []
        by_type[et].append(doc)

    # Priority types: take all
    for et in sorted(PRIORITY_TYPES):
        if et in by_type:
            selected.extend(by_type[et])
            logger.info("  %-20s %4d docs (all)", et, len(by_type[et]))

    # Capped types: take top N by content length
    for et in sorted(CAPPED_TYPES.keys()):
        if et in by_type:
            max_n = CAPPED_TYPES[et]
            sorted_docs = sorted(by_type[et], key=lambda d: len(d.get("content", "")), reverse=True)
            take = sorted_docs[:max_n]
            selected.extend(take)
            logger.info("  %-20s %4d / %4d docs (top by length)", et, len(take), len(by_type[et]))

    # Skip types
    for et in sorted(SKIP_TYPES):
        if et in by_type:
            logger.info("  %-20s      SKIP (%d docs)", et, len(by_type[et]))

    # Uncategorized types: include all
    for et in sorted(by_type.keys()):
        if et not in PRIORITY_TYPES and et not in CAPPED_TYPES and et not in SKIP_TYPES:
            selected.extend(by_type[et])
            logger.info("  %-20s %4d docs (other, included)", et, len(by_type[et]))

    return selected


def load_checkpoint():
    """Load checkpoint for resume support."""
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            data = json.loads(f.read().strip())
            return data.get("index", 0), data.get("input_tokens", 0), data.get("output_tokens", 0)
    return 0, 0, 0


def save_checkpoint(index, input_tokens, output_tokens):
    """Save progress checkpoint."""
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump({"index": index, "input_tokens": input_tokens, "output_tokens": output_tokens}, f)


def parse_json_response(text):
    """Extract JSON from LLM response, handling various formats including truncated output."""
    # Strip code fence markers if present
    cleaned = text.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        cleaned = '\n'.join(lines).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence (with closing)
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Find JSON content between first { and last }
    start = cleaned.find('{')
    if start < 0:
        return None

    end = cleaned.rfind('}')
    if end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Handle truncated JSON: try to close incomplete arrays/objects
    json_text = cleaned[start:]
    # Remove trailing comma and incomplete entries
    json_text = re.sub(r',\s*\{[^}]*$', '', json_text)  # Remove last incomplete object
    json_text = re.sub(r',\s*$', '', json_text)  # Remove trailing comma

    # Count open brackets and close them
    open_brackets = json_text.count('[') - json_text.count(']')
    open_braces = json_text.count('{') - json_text.count('}')
    json_text += ']' * max(0, open_brackets) + '}' * max(0, open_braces)

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass

    # Ultra last resort: extract entities and triples separately
    result = {"entities": [], "triples": []}
    for key in ("entities", "triples"):
        pattern = rf'"{key}"\s*:\s*\[(.*?)(?:\]|$)'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            arr_text = '[' + match.group(1).strip()
            # Clean up and close
            arr_text = re.sub(r',\s*\{[^}]*$', '', arr_text)
            arr_text = re.sub(r',\s*$', '', arr_text)
            if not arr_text.endswith(']'):
                arr_text += ']'
            try:
                result[key] = json.loads(arr_text)
            except json.JSONDecodeError:
                pass

    if result["entities"] or result["triples"]:
        return result

    return None


def extract_from_doc(client, doc):
    """Call Claude to extract entities and triples from a document."""
    title = doc.get("canonical_name", doc.get("title", ""))
    entity_type = doc["entity_type"]
    regions = ", ".join(doc.get("regions", []))

    content = doc.get("content", "")
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n\n[... truncated ...]"

    prompt = EXTRACTION_PROMPT.format(
        title=title,
        entity_type=entity_type,
        regions=regions,
        content=content,
    )

    input_tokens = 0
    output_tokens = 0
    raw_text = ""

    parse_retries = 0
    max_parse_retries = 2  # Limit parse-failure retries to save budget

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = response.content[0].text
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens

            result = parse_json_response(raw_text)
            if result is not None:
                return result, input_tokens, output_tokens, raw_text

            # JSON parse failed
            parse_retries += 1
            if parse_retries < max_parse_retries:
                logger.warning("JSON parse failed for '%s' (attempt %d), retrying...", title, attempt + 1)
                time.sleep(RETRY_DELAY)
            else:
                logger.error("JSON parse failed for '%s' after %d parse attempts, skipping", title, parse_retries)
                return None, input_tokens, output_tokens, raw_text

        except anthropic.RateLimitError as e:
            wait = RETRY_DELAY * (2 ** attempt)
            logger.warning("Rate limit for '%s' (attempt %d): %s. Waiting %ds...", title, attempt + 1, e, wait)
            time.sleep(wait)
        except anthropic.BadRequestError as e:
            # Credit balance too low or other non-retryable errors
            logger.error("Non-retryable error for '%s': %s", title, e)
            raise
        except anthropic.APIError as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (2 ** attempt)
                logger.warning("API error for '%s' (attempt %d): %s. Retrying in %ds...", title, attempt + 1, e, wait)
                time.sleep(wait)
            else:
                raise

    return None, input_tokens, output_tokens, raw_text


def compute_cost(input_tokens, output_tokens):
    """Compute cost in USD."""
    return (input_tokens / 1_000_000 * INPUT_COST_PER_M +
            output_tokens / 1_000_000 * OUTPUT_COST_PER_M)


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Add it to .env file.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    logger.info("=" * 60)
    logger.info("LoreMaster-AI ETL Step 8: Extract")
    logger.info("=" * 60)
    logger.info("Model: %s", MODEL)
    logger.info("Budget: $%.2f", BUDGET_USD)
    logger.info("Max content chars: %d", MAX_CONTENT_CHARS)

    # Load all clean documents
    logger.info("Loading documents from %s ...", INPUT_PATH)
    all_docs = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_docs.append(json.loads(line))
    logger.info("Loaded %d documents total", len(all_docs))

    # Select core documents
    logger.info("Selecting core documents:")
    docs = select_documents(all_docs)
    logger.info("Selected %d documents for extraction", len(docs))

    # Sort by doc_id for deterministic ordering
    docs.sort(key=lambda d: d["doc_id"])

    # Resume from checkpoint
    start_idx, total_input_tokens, total_output_tokens = load_checkpoint()
    if start_idx > 0:
        logger.info("Resuming from checkpoint: doc %d, tokens in=%d out=%d",
                     start_idx, total_input_tokens, total_output_tokens)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    mode = "a" if start_idx > 0 else "w"
    entity_count = 0
    triple_count = 0
    failed_count = 0
    processed_count = 0
    start_time = time.time()

    with open(ENTITIES_PATH, mode, encoding="utf-8") as f_ent, \
         open(TRIPLES_PATH, mode, encoding="utf-8") as f_tri, \
         open(RAW_PATH, mode, encoding="utf-8") as f_raw:

        for i in range(start_idx, len(docs)):
            doc = docs[i]
            doc_id = doc["doc_id"]
            title = doc.get("canonical_name", doc.get("title", ""))

            # Budget check (95% guard)
            cost = compute_cost(total_input_tokens, total_output_tokens)
            if cost >= BUDGET_USD * 0.95:
                logger.warning("Budget limit approaching: $%.2f / $%.2f. Stopping.", cost, BUDGET_USD)
                break

            # Extract
            result, in_tok, out_tok, raw_text = extract_from_doc(client, doc)
            total_input_tokens += in_tok
            total_output_tokens += out_tok
            processed_count += 1

            # Save raw output for debugging
            f_raw.write(json.dumps({
                "doc_id": doc_id, "title": title,
                "input_tokens": in_tok, "output_tokens": out_tok,
                "raw": raw_text,
            }, ensure_ascii=False) + "\n")

            if result is None:
                failed_count += 1
                save_checkpoint(i + 1, total_input_tokens, total_output_tokens)
                time.sleep(REQUEST_DELAY)
                continue

            # Write entities
            for ent in result.get("entities", []):
                record = {
                    "name": ent.get("name", ""),
                    "type": ent.get("type", "Unknown"),
                    "description": ent.get("description", ""),
                    "source_doc_id": doc_id,
                    "source_title": title,
                }
                f_ent.write(json.dumps(record, ensure_ascii=False) + "\n")
                entity_count += 1

            # Write triples
            for tri in result.get("triples", []):
                record = {
                    "head": tri.get("head", ""),
                    "relation": tri.get("relation", ""),
                    "tail": tri.get("tail", ""),
                    "evidence": tri.get("evidence", ""),
                    "source_doc_id": doc_id,
                    "source_title": title,
                }
                f_tri.write(json.dumps(record, ensure_ascii=False) + "\n")
                triple_count += 1

            # Checkpoint
            save_checkpoint(i + 1, total_input_tokens, total_output_tokens)

            # Progress log every 10 docs
            if processed_count % 10 == 0 or i == len(docs) - 1:
                elapsed = time.time() - start_time
                cost = compute_cost(total_input_tokens, total_output_tokens)
                rate = processed_count / elapsed if elapsed > 0 else 0
                pct = 100 * (i + 1) / len(docs)
                logger.info(
                    "  [%5.1f%%] %d/%d docs | %d entities | %d triples | $%.2f | %.1f docs/min",
                    pct, i + 1, len(docs), entity_count, triple_count, cost, rate * 60,
                )

            time.sleep(REQUEST_DELAY)

    elapsed = time.time() - start_time
    cost = compute_cost(total_input_tokens, total_output_tokens)

    # Remove checkpoint on full completion
    final_idx = min(start_idx + processed_count, len(docs))
    if final_idx >= len(docs) and os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)

    logger.info("=" * 60)
    logger.info("Extraction complete!")
    logger.info("  Documents processed: %d / %d", final_idx, len(docs))
    logger.info("  Entities extracted: %d", entity_count)
    logger.info("  Triples extracted: %d", triple_count)
    logger.info("  Failed docs: %d", failed_count)
    logger.info("  Input tokens: %d", total_input_tokens)
    logger.info("  Output tokens: %d", total_output_tokens)
    logger.info("  Cost: $%.4f", cost)
    logger.info("  Elapsed: %.1f seconds (%.1f minutes)", elapsed, elapsed / 60)
    logger.info("  Output: %s", OUTPUT_DIR)
    logger.info("=" * 60)

    # Write manifest
    manifest = {
        "extraction_time": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "documents_selected": len(docs),
        "documents_processed": final_idx,
        "entities_extracted": entity_count,
        "triples_extracted": triple_count,
        "failed_docs": failed_count,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": round(cost, 4),
        "elapsed_seconds": round(elapsed, 1),
        "budget_usd": BUDGET_USD,
        "max_content_chars": MAX_CONTENT_CHARS,
    }
    manifest_path = os.path.join(PROJECT_ROOT, "data/metadata/extraction_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("Manifest: %s", manifest_path)

    return manifest


if __name__ == "__main__":
    main()
