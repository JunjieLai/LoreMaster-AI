"""
Phase 1 Orchestrator — Gold Oracle Generation

Usage:
    # Run all 50 questions
    python src/ablation/run_oracle.py

    # Run specific tiers only
    python src/ablation/run_oracle.py --tiers 3 4

    # Resume from checkpoint (skips already-completed questions)
    python src/ablation/run_oracle.py --resume

    # Dry-run: only fetch docs and estimate cost, no Oracle calls
    python src/ablation/run_oracle.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import anthropic
from config.settings import ANTHROPIC_API_KEY
from src.ablation.fetch_docs import fetch_docs_for_question, format_doc_for_oracle
from src.ablation.generate_gold import generate_gold_reference

# Paths
QUESTIONS_PATH = os.path.join(PROJECT_ROOT, "data/ablation/questions.jsonl")
GOLD_OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/ablation/gold_references.jsonl")
CHECKPOINT_PATH = os.path.join(PROJECT_ROOT, "data/ablation/oracle_checkpoint.json")

# Rate limiting: pause between questions to avoid API overload
SLEEP_BETWEEN_QUESTIONS = 2.0  # seconds


def load_questions(tiers: Optional[List[int]] = None) -> List[dict]:
    questions = []
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                q = json.loads(line)
                if tiers is None or q["tier"] in tiers:
                    questions.append(q)
    return questions


def load_checkpoint() -> Set[str]:
    """Return set of already-completed question IDs."""
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_checkpoint(completed: Set[str]):
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(completed), f, indent=2)


def append_gold(gold: dict):
    with open(GOLD_OUTPUT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(gold, ensure_ascii=False) + "\n")


def dry_run(questions: list[dict]):
    """Estimate token/cost without calling Oracle."""
    print("\n=== DRY RUN: Document Fetch Estimation ===\n")
    total_docs = 0
    total_est_cost = 0.0

    for q in questions:
        docs, stats = fetch_docs_for_question(q)
        # Rough token estimate: avg 800 tokens per doc + 1500 output
        est_input_tokens = stats["total"] * 800 + 500  # prompt overhead
        est_output_tokens = 1500
        # Opus pricing
        est_cost = (est_input_tokens / 1e6 * 15) + (est_output_tokens / 1e6 * 75)
        total_docs += stats["total"]
        total_est_cost += est_cost * 2  # x2 for Oracle + QC round
        print(f"  {q['id']:12s} | T{q['tier']} | docs: A={stats['layer_a']} "
              f"B={stats['layer_b']} C={stats['layer_c']} "
              f"| est_cost: ${est_cost*2:.3f}")

    print(f"\nTotal questions: {len(questions)}")
    print(f"Total docs fetched: {total_docs}")
    print(f"Estimated Oracle cost: ${total_est_cost:.2f}")


def generate_human_review_report(output_path: str):
    """Read gold_references.jsonl and print a QC summary for human reviewers."""
    flagged = []
    total = 0
    with open(output_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            gold = json.loads(line)
            total += 1
            if gold.get("_needs_human_review"):
                flagged.append({
                    "id": gold.get("_meta", {}).get("question_id", "?"),
                    "tier": gold.get("_meta", {}).get("tier", "?"),
                    "flags": gold.get("_review_flags", []),
                })

    print(f"\n{'='*60}")
    print(f"QC REVIEW REPORT: {len(flagged)}/{total} questions need review")
    print(f"{'='*60}")
    for item in sorted(flagged, key=lambda x: int(x["tier"]) if str(x["tier"]).isdigit() else 0, reverse=True):
        print(f"\n⚠️  {item['id']} (Tier {item['tier']})")
        for flag in item["flags"]:
            print(f"    → {flag}")

    print(f"\n{'='*60}")
    print("Review priority:")
    print("  🔴 Tier 4 items — review all")
    print("  🟡 Tier 3 items — review flagged only")
    print("  🟢 Tier 1-2 — skip unless coverage_notes flagged")


def main():
    parser = argparse.ArgumentParser(description="Run Phase 1: Gold Oracle Generation")
    parser.add_argument("--tiers", nargs="+", type=int, default=None,
                        help="Only process specified tiers (e.g. --tiers 3 4)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-completed questions (uses checkpoint file)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch docs and estimate costs without calling Oracle")
    args = parser.parse_args()

    questions = load_questions(tiers=args.tiers)
    print(f"Loaded {len(questions)} questions"
          + (f" (tiers: {args.tiers})" if args.tiers else ""))

    if args.dry_run:
        dry_run(questions)
        return

    # Filter already-completed if resuming
    completed = load_checkpoint() if args.resume else set()
    pending = [q for q in questions if q["id"] not in completed]
    print(f"Pending: {len(pending)} | Already done: {len(completed)}")

    if not pending:
        print("All questions already processed.")
        generate_human_review_report(GOLD_OUTPUT_PATH)
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    total_cost = 0.0
    total_tokens = 0

    print(f"\n{'='*60}")
    print("Starting Gold Oracle Generation")
    print(f"Output: {GOLD_OUTPUT_PATH}")
    print(f"{'='*60}")

    for i, question_obj in enumerate(pending, 1):
        qid = question_obj["id"]
        print(f"\n[{i}/{len(pending)}] {qid}")

        try:
            gold = generate_gold_reference(question_obj, client, verbose=True)
            append_gold(gold)
            completed.add(qid)
            save_checkpoint(completed)

            meta = gold.get("_meta", {})
            total_cost += meta.get("cost_usd", 0)
            total_tokens += meta.get("tokens", {}).get("total", 0)

        except Exception as e:
            print(f"  [ERROR] {qid}: {e}")
            # Save error record to avoid losing progress
            error_record = {
                "_meta": {"question_id": qid, "error": str(e)},
                "_needs_human_review": True,
                "_review_flags": [f"ERROR: {e}"],
            }
            append_gold(error_record)
            completed.add(qid)
            save_checkpoint(completed)

        if i < len(pending):
            time.sleep(SLEEP_BETWEEN_QUESTIONS)

    # Final summary
    print(f"\n{'='*60}")
    print("PHASE 1 COMPLETE")
    print(f"{'='*60}")
    print(f"Questions processed: {len(pending)}")
    print(f"Total tokens used:   {total_tokens:,}")
    print(f"Total Oracle cost:   ${total_cost:.2f}")
    print(f"Output file:         {GOLD_OUTPUT_PATH}")

    generate_human_review_report(GOLD_OUTPUT_PATH)


if __name__ == "__main__":
    main()
