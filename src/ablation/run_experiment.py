"""
Phase 2 Ablation Experiment Runner

Runs 8 configurations × 50 questions = 400 queries.
Each config's results are saved to data/ablation/runs/<config_name>.jsonl

Usage:
    # Dry-run: estimate cost for all 8 configs
    python src/ablation/run_experiment.py --dry-run

    # Run all 8 configs
    python src/ablation/run_experiment.py

    # Run specific configs only
    python src/ablation/run_experiment.py --configs S4-LLM S4-VEC G4-LLM

    # Resume (skip already-completed questions per config)
    python src/ablation/run_experiment.py --resume

    # Run a single config for smoke-test (first 3 questions)
    python src/ablation/run_experiment.py --configs S4-LLM --limit 3
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

from src.agent.ablation_config import AblationConfig, ABLATION_PRESETS, STUDY_CONFIGS
from src.agent.ablation_pipeline import AblationPipeline

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
QUESTIONS_PATH = os.path.join(PROJECT_ROOT, "data/ablation/questions.jsonl")
RUNS_DIR = os.path.join(PROJECT_ROOT, "data/ablation/runs")
os.makedirs(RUNS_DIR, exist_ok=True)

# Rate limiting
SLEEP_BETWEEN_QUESTIONS = 1.0   # seconds between questions (same config)
SLEEP_BETWEEN_CONFIGS   = 3.0   # seconds between configs

# ─────────────────────────────────────────────
# Cost constants (per 1M tokens)
# ─────────────────────────────────────────────
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0,  "output": 15.0},
    "gpt-4o":                   {"input": 2.5,  "output": 10.0},
    "claude-3-haiku-20240307":  {"input": 0.25, "output": 1.25},  # classifier
    "gpt-4o-mini":              {"input": 0.15, "output": 0.60},  # classifier
}

# Rough token estimates for dry-run (actual measured from first pass)
DRY_RUN_TOKENS = {
    "LLM": {"context_in": 800,   "answer_out": 500},   # no retrieval context
    "VEC": {"context_in": 5500,  "answer_out": 700},   # vector docs
    "GRF": {"context_in": 3500,  "answer_out": 600},   # graph triples
    "HYB": {"context_in": 7000,  "answer_out": 800},   # vector + graph
}
# Overhead: query classification + embedding call (Haiku/mini)
DRY_RUN_CLASSIFIER_IN  = 300
DRY_RUN_CLASSIFIER_OUT = 50


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def load_questions(limit: Optional[int] = None) -> List[dict]:
    questions = []
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions[:limit] if limit else questions


def run_output_path(config_name: str) -> str:
    return os.path.join(RUNS_DIR, f"{config_name}.jsonl")


def checkpoint_path(config_name: str) -> str:
    return os.path.join(RUNS_DIR, f"{config_name}.checkpoint.json")


def load_completed(config_name: str) -> Set[str]:
    path = checkpoint_path(config_name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_completed(config_name: str, completed: Set[str]):
    with open(checkpoint_path(config_name), "w", encoding="utf-8") as f:
        json.dump(sorted(completed), f, indent=2)


def append_result(config_name: str, record: dict):
    with open(run_output_path(config_name), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────
# Dry-run cost estimation
# ─────────────────────────────────────────────

def dry_run_estimate(config_names: List[str], questions: List[dict]):
    print("\n" + "="*65)
    print("DRY-RUN COST ESTIMATE")
    print("="*65)
    print(f"{'Config':<12} {'Model':<30} {'Q':<5} {'Est $/Q':<10} {'Est Total'}")
    print("-"*65)

    grand_total = 0.0
    summary_rows = []

    for name in config_names:
        cfg = ABLATION_PRESETS[name]
        model = cfg.answer_model.value
        prices = PRICING[model]

        # Determine retrieval tier
        if not cfg.use_vector_search and not cfg.use_graph_search:
            tier = "LLM"
        elif cfg.use_vector_search and not cfg.use_graph_search:
            tier = "VEC"
        elif not cfg.use_vector_search and cfg.use_graph_search:
            tier = "GRF"
        else:
            tier = "HYB"

        tok = DRY_RUN_TOKENS[tier]
        n_q = len(questions)

        # Answer generation cost
        ans_cost_per_q = (tok["context_in"] / 1e6 * prices["input"] +
                          tok["answer_out"] / 1e6 * prices["output"])

        # Classifier overhead (only if retrieval enabled)
        clf_model = cfg.classifier_model.value
        clf_prices = PRICING.get(clf_model, PRICING["claude-3-haiku-20240307"])
        clf_cost_per_q = (DRY_RUN_CLASSIFIER_IN / 1e6 * clf_prices["input"] +
                          DRY_RUN_CLASSIFIER_OUT / 1e6 * clf_prices["output"])

        # Query expansion (Haiku/mini) only if enabled and retrieval present
        exp_cost_per_q = 0.0
        if cfg.use_query_expansion:
            exp_cost_per_q = clf_cost_per_q  # same model, similar tokens

        cost_per_q = ans_cost_per_q + clf_cost_per_q + exp_cost_per_q
        total = cost_per_q * n_q
        grand_total += total

        print(f"  {name:<10} {model:<30} {n_q:<5} ${cost_per_q:<9.4f} ${total:.3f}")
        summary_rows.append((name, tier, model, cost_per_q, total))

    print("-"*65)
    print(f"  {'TOTAL':<10} {'':30} {len(questions)*len(config_names):<5} {'':10} ${grand_total:.2f}")
    print()

    # Breakdown by model
    s4_total = sum(r[4] for r in summary_rows if "claude" in r[2])
    g4_total = sum(r[4] for r in summary_rows if "gpt" in r[2])
    print(f"  Claude Sonnet 4 configs: ${s4_total:.2f}")
    print(f"  GPT-4o configs:          ${g4_total:.2f}")
    print(f"  Grand total:             ${grand_total:.2f}")
    print()

    # Estimated runtime
    retrieval_time = {"LLM": 1.5, "VEC": 4.0, "GRF": 3.5, "HYB": 6.0}  # sec/question
    total_seconds = sum(retrieval_time[r[1]] * len(questions) for r in summary_rows)
    total_seconds += SLEEP_BETWEEN_QUESTIONS * len(questions) * len(config_names)
    total_seconds += SLEEP_BETWEEN_CONFIGS * len(config_names)
    print(f"  Estimated runtime:       ~{total_seconds/60:.0f} min")
    print("="*65)


# ─────────────────────────────────────────────
# Main experiment loop
# ─────────────────────────────────────────────

def run_config(
    config_name: str,
    cfg: AblationConfig,
    questions: List[dict],
    resume: bool,
) -> dict:
    """Run one config against all questions. Returns summary stats."""
    completed = load_completed(config_name) if resume else set()
    pending = [q for q in questions if q["id"] not in completed]

    print(f"\n{'='*60}")
    print(f"CONFIG: {config_name}  ({cfg.description})")
    print(f"  Pending: {len(pending)} | Done: {len(completed)}")
    print(f"{'='*60}")

    if not pending:
        print("  All questions already done. Skipping.")
        return {"config": config_name, "total": 0, "cost": 0.0, "errors": 0}

    pipeline = AblationPipeline(config=cfg, verbose=False)

    total_cost = 0.0
    total_tokens = 0
    errors = 0

    for i, q_obj in enumerate(pending, 1):
        qid = q_obj["id"]
        question = q_obj["question"]
        print(f"  [{i}/{len(pending)}] {qid}: {question[:60]}...")

        try:
            result = pipeline.answer(question)

            record = {
                "question_id": qid,
                "tier": q_obj["tier"],
                "question": question,
                "config": config_name,
                "answer": result["answer"],
                "query_type": result.get("query_type", ""),
                "entities": result.get("entities", []),
                "sources": result.get("sources", []),
                "timing": result.get("timing", {}),
                "usage": result.get("usage", {}),
            }

            append_result(config_name, record)
            completed.add(qid)
            save_completed(config_name, completed)

            cost = result.get("usage", {}).get("cost_usd", 0)
            tokens = result.get("usage", {}).get("total_tokens", 0)
            total_cost += cost
            total_tokens += tokens

            t = result.get("timing", {}).get("total", 0)
            print(f"    ✓ {t:.1f}s | ${cost:.4f} | {tokens} tok")

        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            errors += 1
            error_record = {
                "question_id": qid,
                "tier": q_obj["tier"],
                "question": question,
                "config": config_name,
                "answer": "",
                "_error": str(e),
            }
            append_result(config_name, error_record)
            completed.add(qid)
            save_completed(config_name, completed)

        if i < len(pending):
            time.sleep(SLEEP_BETWEEN_QUESTIONS)

    pipeline.close()

    print(f"\n  ✓ {config_name} done | Cost: ${total_cost:.3f} | Tokens: {total_tokens:,} | Errors: {errors}")
    return {
        "config": config_name,
        "total": len(pending),
        "cost": total_cost,
        "tokens": total_tokens,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 2: Run ablation experiment")
    parser.add_argument("--configs", nargs="+", default=None,
                        choices=list(ABLATION_PRESETS.keys()),
                        help="Configs to run (default: all 8 STUDY_CONFIGS)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-completed questions per config")
    parser.add_argument("--dry-run", action="store_true",
                        help="Estimate cost without running any queries")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N questions (for smoke-test)")
    args = parser.parse_args()

    config_names = args.configs or STUDY_CONFIGS
    questions = load_questions(limit=args.limit)

    print(f"Loaded {len(questions)} questions")
    print(f"Configs: {config_names}")

    if args.dry_run:
        dry_run_estimate(config_names, questions)
        return

    # ─────────────────────────────────────────────
    # Run experiment
    # ─────────────────────────────────────────────
    grand_cost = 0.0
    grand_tokens = 0
    summaries = []

    for j, name in enumerate(config_names, 1):
        cfg = ABLATION_PRESETS[name]
        summary = run_config(name, cfg, questions, resume=args.resume)
        summaries.append(summary)
        grand_cost += summary.get("cost", 0)
        grand_tokens += summary.get("tokens", 0)

        if j < len(config_names):
            time.sleep(SLEEP_BETWEEN_CONFIGS)

    # ─────────────────────────────────────────────
    # Final summary
    # ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 2 COMPLETE")
    print(f"{'='*60}")
    print(f"{'Config':<12} {'Questions':<12} {'Cost':<12} {'Errors'}")
    print("-"*50)
    for s in summaries:
        print(f"  {s['config']:<10} {s.get('total', 0):<12} ${s.get('cost', 0):<11.3f} {s.get('errors', 0)}")
    print("-"*50)
    print(f"  {'TOTAL':<10} {sum(s.get('total',0) for s in summaries):<12} ${grand_cost:.3f}")
    print(f"\nOutput directory: {RUNS_DIR}")


if __name__ == "__main__":
    main()
