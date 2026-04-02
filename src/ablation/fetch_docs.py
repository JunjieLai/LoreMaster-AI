"""
Three-Layer Document Fetcher for Gold Oracle Generation

Layer A: Exact/partial title match in wiki_clean.jsonl (all tiers)
Layer B: Pinecone semantic search, top_k=20 (Tier 3-4)
Layer C: Entity co-mention expansion (Tier 4 only)
"""

import json
import os
import sys
from itertools import combinations
from typing import List, Optional, Set, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

WIKI_CLEAN_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_clean.jsonl")
ORACLE_TOP_K = 20          # Pinecone top_k for Oracle (vs 8 for test system)
MAX_LAYER_C_DOCS = 6       # Maximum co-mention expansion docs
MAX_TOTAL_DOCS = 20        # Hard cap on total docs per question
MAX_CONTENT_CHARS = 3500   # Truncate each doc's content at this length


# ---------------------------------------------------------------------------
# Wiki index (loaded once)
# ---------------------------------------------------------------------------

_wiki_docs: Optional[list[dict]] = None

def _load_wiki() -> list[dict]:
    global _wiki_docs
    if _wiki_docs is None:
        _wiki_docs = []
        with open(WIKI_CLEAN_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    _wiki_docs.append(json.loads(line))
        print(f"[fetch_docs] Loaded {len(_wiki_docs)} wiki documents.")
    return _wiki_docs


# ---------------------------------------------------------------------------
# Layer A: Title-based exact / partial match
# ---------------------------------------------------------------------------

def _score_title_match(entity: str, doc_title: str) -> int:
    """Returns match score: 3=exact, 2=title contains entity, 1=entity contains title."""
    e = entity.lower().strip()
    t = doc_title.lower().strip()
    if e == t:
        return 3
    if e in t or t in e:
        return 2
    return 0


def fetch_layer_a(entities: list[str]) -> list[dict]:
    """
    For each entity, find the best-matching wiki document by title.
    Returns deduplicated list (one doc per entity at most).
    """
    wiki = _load_wiki()
    fetched: dict[str, dict] = {}  # doc_id -> doc

    for entity in entities:
        best_score = 0
        best_doc = None
        for doc in wiki:
            title = doc.get("canonical_name") or doc.get("title", "")
            aliases = doc.get("aliases", [])
            # Check main title and aliases
            names_to_check = [title] + aliases
            score = max(_score_title_match(entity, n) for n in names_to_check if n)
            if score > best_score:
                best_score = score
                best_doc = doc

        if best_doc and best_score > 0 and best_doc["doc_id"] not in fetched:
            fetched[best_doc["doc_id"]] = best_doc

    return list(fetched.values())


# ---------------------------------------------------------------------------
# Layer B: Pinecone semantic search (Tier 3-4)
# ---------------------------------------------------------------------------

def fetch_layer_b(question: str, existing_ids: Set[str]) -> List[dict]:
    """
    Broad semantic retrieval using Pinecone with top_k=ORACLE_TOP_K.
    Returns docs not already in existing_ids, capped at 8 new docs.
    """
    try:
        from openai import OpenAI
        from pinecone import Pinecone
        from config.settings import OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_HOST, PINECONE_INDEX

        oai = OpenAI(api_key=OPENAI_API_KEY)
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX, host=PINECONE_HOST)

        resp = oai.embeddings.create(input=question, model="text-embedding-3-small")
        embedding = resp.data[0].embedding

        results = index.query(vector=embedding, top_k=ORACLE_TOP_K, include_metadata=True)

        wiki = _load_wiki()
        wiki_by_id = {d["doc_id"]: d for d in wiki}

        new_docs = []
        for match in results.matches:
            doc_id = match.metadata.get("doc_id")
            if doc_id and doc_id not in existing_ids and doc_id in wiki_by_id:
                new_docs.append(wiki_by_id[doc_id])
                existing_ids.add(doc_id)
                if len(new_docs) >= 8:
                    break

        return new_docs

    except Exception as e:
        print(f"[fetch_docs] Layer B failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Layer C: Co-mention expansion (Tier 4 only)
# ---------------------------------------------------------------------------

def fetch_layer_c(entities: List[str], existing_ids: Set[str]) -> List[dict]:
    """
    For each entity pair, find wiki docs that mention BOTH entities.
    Prioritizes Quest/Event/Character docs. Caps at MAX_LAYER_C_DOCS.
    """
    wiki = _load_wiki()
    new_docs: dict[str, dict] = {}

    # Only consider first 6 entities to avoid C(n,2) explosion
    top_entities = entities[:6]

    for a, b in combinations(top_entities, 2):
        a_l, b_l = a.lower(), b.lower()
        candidates = []
        for doc in wiki:
            if doc["doc_id"] in existing_ids or doc["doc_id"] in new_docs:
                continue
            content_l = doc.get("content", "").lower()
            if a_l in content_l and b_l in content_l:
                score = content_l.count(a_l) + content_l.count(b_l)
                # Boost quest/event documents where relationships are described
                if doc.get("entity_type") in {"Quest", "Event", "Character", "NPC"}:
                    score += 10
                candidates.append((score, doc))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_doc = candidates[0][1]
            new_docs[best_doc["doc_id"]] = best_doc

        if len(new_docs) >= MAX_LAYER_C_DOCS:
            break

    return list(new_docs.values())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def format_doc_for_oracle(doc: dict) -> str:
    """Format a wiki doc as readable context for the Oracle prompt."""
    title = doc.get("canonical_name") or doc.get("title", "Unknown")
    entity_type = doc.get("entity_type", "")
    content = doc.get("content", "")[:MAX_CONTENT_CHARS]
    return f"### [{entity_type}] {title}\n{content}"


def fetch_docs_for_question(question_obj: dict) -> Tuple[List[dict], dict]:
    """
    Run all applicable layers for a question and return:
      - list of fetched docs
      - stats dict {layer_a, layer_b, layer_c, total}
    """
    layers = question_obj.get("doc_fetch_layers", ["A"])
    entities = question_obj.get("explicit_entities", [])

    all_docs: list[dict] = []
    existing_ids: set[str] = set()
    stats = {"layer_a": 0, "layer_b": 0, "layer_c": 0, "total": 0}

    # Layer A — always
    layer_a = fetch_layer_a(entities)
    all_docs.extend(layer_a)
    existing_ids.update(d["doc_id"] for d in layer_a)
    stats["layer_a"] = len(layer_a)

    # Layer B — Tier 3-4
    if "B" in layers:
        layer_b = fetch_layer_b(question_obj["question"], existing_ids)
        all_docs.extend(layer_b)
        stats["layer_b"] = len(layer_b)

    # Layer C — Tier 4 only
    if "C" in layers:
        layer_c = fetch_layer_c(entities, existing_ids)
        all_docs.extend(layer_c)
        stats["layer_c"] = len(layer_c)

    # Hard cap
    all_docs = all_docs[:MAX_TOTAL_DOCS]
    stats["total"] = len(all_docs)

    return all_docs, stats
