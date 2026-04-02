"""
Phase 3 Ablation Evaluator

Scores each system answer against gold_references.jsonl using Claude Opus as judge.

Metrics per answer:
  fact_score      — fraction of gold key_facts covered   (0.0–1.0)
  min_facts_met   — bool: did answer meet min_acceptable_facts threshold
  trap_score      — 1 - (traps_triggered / total_traps)   (0.0–1.0)
  overall_score   — 0.6 * fact_score + 0.4 * trap_score

Usage:
    # Dry-run: show token/cost estimate
    python src/ablation/run_eval.py --dry-run

    # Evaluate all 8 configs
    python src/ablation/run_eval.py

    # Evaluate specific configs only
    python src/ablation/run_eval.py --configs S4-LLM S4-VEC

    # Resume (skip already-scored answers)
    python src/ablation/run_eval.py --resume

    # Print summary table after eval
    python src/ablation/run_eval.py --summary
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

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
GOLD_PATH   = os.path.join(PROJECT_ROOT, "data/ablation/gold_references.jsonl")
RUNS_DIR    = os.path.join(PROJECT_ROOT, "data/ablation/runs")
EVAL_DIR    = os.path.join(PROJECT_ROOT, "data/ablation/eval")
os.makedirs(EVAL_DIR, exist_ok=True)

JUDGE_MODEL = "claude-opus-4-6"
SLEEP_BETWEEN = 0.5     # seconds between API calls

STUDY_CONFIGS = ["S4-LLM", "S4-VEC", "S4-GRF", "S4-HYB",
                 "G4-LLM", "G4-VEC", "G4-GRF", "G4-HYB"]

# ─────────────────────────────────────────────
# Judge prompt
# ─────────────────────────────────────────────

JUDGE_SYSTEM = """You are an expert factual evaluator for a RAG Q&A system about Genshin Impact video game lore.

Your tasks:
1. FACT COVERAGE: Determine which gold key facts are covered by the candidate answer.
   - Mark a fact as COVERED if the answer explicitly states it, paraphrases it correctly, OR the answer's reasoning chain clearly and directly leads to it.
   - Mark a fact as MISSED if the answer omits it, gets it wrong, or only mentions it so vaguely it adds no real information.

2. HALLUCINATION TRAPS: Determine whether the answer fell into any known hallucination traps.
   - Mark a trap as TRIGGERED only if the answer actively makes the specific incorrect claim (or a clearly equivalent one).
   - Do NOT trigger a trap merely because the answer omits the correct information — omission is not hallucination.

Be thorough and fair. Complex multi-hop answers that synthesize correct information across sources should receive credit."""

JUDGE_USER_TMPL = """QUESTION: {question}

GOLD KEY FACTS (indexed 0-based):
{facts_block}

HALLUCINATION TRAPS (indexed 0-based):
{traps_block}

CANDIDATE ANSWER:
{answer}

---
Respond ONLY with a JSON object, no markdown fences:
{{
  "facts_covered": [list of 0-based indices of gold facts clearly covered by the answer],
  "traps_triggered": [list of 0-based indices of hallucination traps the answer fell into],
  "reasoning": "one sentence summary of evaluation"
}}"""


def build_judge_prompt(question: str, gold: dict, answer: str) -> str:
    facts = gold.get("key_facts", [])
    traps = gold.get("hallucination_traps", [])

    facts_block = "\n".join(
        f"[{i}] {f['fact']}" for i, f in enumerate(facts)
    )
    traps_block = "\n".join(
        f"[{i}] TRAP: {t['trap']}\n    CORRECT: {t['correct']}"
        for i, t in enumerate(traps)
    )
    if not traps_block:
        traps_block = "(none defined)"

    return JUDGE_USER_TMPL.format(
        question=question,
        facts_block=facts_block,
        traps_block=traps_block,
        answer=answer,
    )


# ─────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────

def compute_scores(parsed: dict, gold: dict) -> dict:
    facts = gold.get("key_facts", [])
    traps = gold.get("hallucination_traps", [])
    min_acc = gold.get("min_acceptable_facts", 1)

    covered = set(parsed.get("facts_covered", []))
    triggered = set(parsed.get("traps_triggered", []))

    n_facts = len(facts)
    n_traps = len(traps)

    fact_score  = len(covered) / max(1, n_facts)
    trap_score  = 1.0 - len(triggered) / max(1, n_traps) if n_traps > 0 else 1.0
    overall     = 0.6 * fact_score + 0.4 * trap_score
    min_met     = len(covered) >= min_acc

    return {
        "fact_score":    round(fact_score,  4),
        "facts_covered": len(covered),
        "facts_total":   n_facts,
        "min_facts_met": min_met,
        "trap_score":    round(trap_score,  4),
        "traps_triggered": len(triggered),
        "traps_total":   n_traps,
        "overall_score": round(overall,     4),
    }


# ─────────────────────────────────────────────
# File helpers
# ─────────────────────────────────────────────

def eval_output_path(config_name: str) -> str:
    return os.path.join(EVAL_DIR, f"{config_name}.jsonl")

def eval_checkpoint_path(config_name: str) -> str:
    return os.path.join(EVAL_DIR, f"{config_name}.checkpoint.json")

def load_completed_eval(config_name: str) -> Set[str]:
    path = eval_checkpoint_path(config_name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_completed_eval(config_name: str, completed: Set[str]):
    with open(eval_checkpoint_path(config_name), "w", encoding="utf-8") as f:
        json.dump(sorted(completed), f, indent=2)

def append_eval_result(config_name: str, record: dict):
    with open(eval_output_path(config_name), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def load_gold() -> dict:
    """Returns dict: question_id -> gold entry"""
    gold = {}
    with open(GOLD_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entry = json.loads(line)
                qid = entry.get("question_id") or entry.get("_meta", {}).get("question_id", "?")
                gold[qid] = entry
    return gold

def load_run_answers(config_name: str) -> List[dict]:
    path = os.path.join(RUNS_DIR, f"{config_name}.jsonl")
    answers = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                answers.append(json.loads(line))
    return answers

def extract_json(text: str) -> Optional[dict]:
    """Extract JSON from model response, stripping any markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        import re
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Find outermost { ... }
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


# ─────────────────────────────────────────────
# Dry-run estimate
# ─────────────────────────────────────────────

def dry_run_estimate(config_names: List[str], gold: dict):
    # Rough token estimates
    AVG_QUESTION_TOKENS     = 30
    AVG_KEY_FACTS_TOKENS    = 400   # ~10 facts × 40 tokens
    AVG_TRAPS_TOKENS        = 400   # ~5 traps × 80 tokens
    AVG_ANSWER_TOKENS       = 600
    AVG_OUTPUT_TOKENS       = 80

    INPUT_PRICE  = 15.00  # $/1M   Opus input
    OUTPUT_PRICE = 75.00  # $/1M   Opus output

    per_call_in  = AVG_QUESTION_TOKENS + AVG_KEY_FACTS_TOKENS + AVG_TRAPS_TOKENS + AVG_ANSWER_TOKENS
    per_call_out = AVG_OUTPUT_TOKENS
    cost_per_call = (per_call_in * INPUT_PRICE + per_call_out * OUTPUT_PRICE) / 1e6

    n_questions = len(gold)
    total_calls = n_questions * len(config_names)
    total_cost  = cost_per_call * total_calls

    print(f"\n{'='*55}")
    print("DRY-RUN COST ESTIMATE — Phase 3 Evaluator")
    print(f"{'='*55}")
    print(f"  Judge model:     {JUDGE_MODEL}")
    print(f"  Configs:         {len(config_names)}")
    print(f"  Questions each:  {n_questions}")
    print(f"  Total API calls: {total_calls}")
    print(f"  Est tokens/call: {per_call_in} in + {per_call_out} out")
    print(f"  Cost/call:       ${cost_per_call:.5f}")
    print(f"  Est total cost:  ${total_cost:.3f}")
    total_sec = total_calls * (SLEEP_BETWEEN + 1.5)  # ~1.5s per Haiku call
    print(f"  Est runtime:     ~{total_sec/60:.0f} min")
    print(f"{'='*55}\n")


# ─────────────────────────────────────────────
# Evaluate one config
# ─────────────────────────────────────────────

def eval_config(
    config_name: str,
    answers: List[dict],
    gold: dict,
    client: anthropic.Anthropic,
    resume: bool,
    force: bool = False,
) -> dict:
    if force:
        for p in [eval_output_path(config_name), eval_checkpoint_path(config_name)]:
            if os.path.exists(p):
                os.remove(p)
        completed = set()
    elif resume:
        completed = load_completed_eval(config_name)
    else:
        completed = set()
    pending = [a for a in answers if a["question_id"] not in completed]

    print(f"\n{'='*60}")
    print(f"EVAL: {config_name}   Pending: {len(pending)} | Done: {len(completed)}")
    print(f"{'='*60}")

    if not pending:
        print("  All already evaluated. Skipping.")
        return {"config": config_name, "total": 0, "cost": 0.0, "errors": 0}

    total_cost   = 0.0
    total_tokens = 0
    errors       = 0

    for i, ans_record in enumerate(pending, 1):
        qid      = ans_record["question_id"]
        question = ans_record["question"]
        answer   = ans_record.get("answer", "")
        tier     = ans_record.get("tier", 1)

        gold_entry = gold.get(qid)
        if not gold_entry:
            print(f"  [{i}/{len(pending)}] {qid}: ⚠ no gold reference — skipping")
            errors += 1
            completed.add(qid)
            save_completed_eval(config_name, completed)
            continue

        print(f"  [{i}/{len(pending)}] {qid}: {question[:55]}...")

        # Skip answers that errored out in run phase
        if not answer or ans_record.get("_error"):
            print(f"    ⚠ empty/error answer → score 0")
            record = {
                "question_id":     qid,
                "tier":            tier,
                "config":          config_name,
                "fact_score":      0.0,
                "facts_covered":   0,
                "facts_total":     len(gold_entry.get("key_facts", [])),
                "min_facts_met":   False,
                "trap_score":      1.0,
                "traps_triggered": 0,
                "traps_total":     len(gold_entry.get("hallucination_traps", [])),
                "overall_score":   0.0,
                "reasoning":       "answer was empty or errored",
                "_skip":           True,
            }
            append_eval_result(config_name, record)
            completed.add(qid)
            save_completed_eval(config_name, completed)
            continue

        user_msg = build_judge_prompt(question, gold_entry, answer)

        try:
            response = client.messages.create(
                model=JUDGE_MODEL,
                max_tokens=600,
                system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            raw_text = response.content[0].text
            parsed   = extract_json(raw_text)

            in_tok  = response.usage.input_tokens
            out_tok = response.usage.output_tokens
            cost    = (in_tok * 15.00 + out_tok * 75.00) / 1e6

            total_cost   += cost
            total_tokens += in_tok + out_tok

            if parsed is None:
                print(f"    ✗ parse failure: {raw_text[:80]}")
                scores = {"fact_score": 0.0, "facts_covered": 0,
                          "facts_total": len(gold_entry.get("key_facts", [])),
                          "min_facts_met": False, "trap_score": 0.0,
                          "traps_triggered": 0,
                          "traps_total": len(gold_entry.get("hallucination_traps", [])),
                          "overall_score": 0.0}
                reasoning = "_parse_error"
                errors += 1
            else:
                scores    = compute_scores(parsed, gold_entry)
                reasoning = parsed.get("reasoning", "")
                print(f"    ✓ overall={scores['overall_score']:.2f} "
                      f"facts={scores['facts_covered']}/{scores['facts_total']} "
                      f"traps={scores['traps_triggered']}/{scores['traps_total']} "
                      f"${cost:.5f}")

            record = {
                "question_id":     qid,
                "tier":            tier,
                "config":          config_name,
                **scores,
                "reasoning":       reasoning,
                "usage": {
                    "input_tokens":  in_tok,
                    "output_tokens": out_tok,
                    "cost_usd":      round(cost, 6),
                },
            }
            append_eval_result(config_name, record)
            completed.add(qid)
            save_completed_eval(config_name, completed)

        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            errors += 1
            completed.add(qid)
            save_completed_eval(config_name, completed)

        if i < len(pending):
            time.sleep(SLEEP_BETWEEN)

    print(f"\n  ✓ {config_name} eval done | Cost: ${total_cost:.4f} | Tokens: {total_tokens:,} | Errors: {errors}")
    return {
        "config":  config_name,
        "total":   len(pending),
        "cost":    total_cost,
        "tokens":  total_tokens,
        "errors":  errors,
    }


# ─────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────

def print_summary(config_names: List[str]):
    """Load all eval results and print aggregated score table."""
    import csv

    all_rows = []
    for name in config_names:
        path = eval_output_path(name)
        if not os.path.exists(path):
            continue
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        all_rows.extend(rows)

    if not all_rows:
        print("No eval results found.")
        return

    # Aggregate by config
    from collections import defaultdict
    stats = defaultdict(lambda: {"overall": [], "fact": [], "trap": [],
                                 "min_met": [], "by_tier": defaultdict(list)})
    for r in all_rows:
        cfg  = r["config"]
        tier = int(r.get("tier", 0))
        stats[cfg]["overall"].append(r.get("overall_score", 0))
        stats[cfg]["fact"].append(r.get("fact_score", 0))
        stats[cfg]["trap"].append(r.get("trap_score", 1.0))
        stats[cfg]["min_met"].append(int(r.get("min_facts_met", False)))
        stats[cfg]["by_tier"][tier].append(r.get("overall_score", 0))

    def mean(lst):
        return sum(lst) / len(lst) if lst else 0.0

    print(f"\n{'='*80}")
    print("ABLATION STUDY RESULTS — Phase 3 Evaluation Summary")
    print(f"{'='*80}")
    print(f"{'Config':<12} {'Overall':>8} {'FactScore':>10} {'TrapScore':>10} "
          f"{'MinFact%':>9} {'T1':>6} {'T2':>6} {'T3':>6} {'T4':>6}")
    print("-"*80)

    csv_rows = []
    for name in config_names:
        if name not in stats:
            continue
        s   = stats[name]
        ov  = mean(s["overall"])
        fs  = mean(s["fact"])
        ts  = mean(s["trap"])
        mf  = mean(s["min_met"]) * 100
        t1  = mean(s["by_tier"].get(1, [0]))
        t2  = mean(s["by_tier"].get(2, [0]))
        t3  = mean(s["by_tier"].get(3, [0]))
        t4  = mean(s["by_tier"].get(4, [0]))
        n   = len(s["overall"])
        print(f"  {name:<10} {ov:>8.3f} {fs:>10.3f} {ts:>10.3f} "
              f"{mf:>8.1f}% {t1:>6.3f} {t2:>6.3f} {t3:>6.3f} {t4:>6.3f}  (n={n})")
        csv_rows.append({
            "config": name, "overall": round(ov,4), "fact_score": round(fs,4),
            "trap_score": round(ts,4), "min_facts_pct": round(mf,1),
            "tier1": round(t1,4), "tier2": round(t2,4),
            "tier3": round(t3,4), "tier4": round(t4,4), "n": n,
        })

    print(f"{'='*80}\n")

    # Write CSV
    csv_path = os.path.join(EVAL_DIR, "summary.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"Summary CSV saved to: {csv_path}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase 3: Evaluate ablation run results")
    parser.add_argument("--configs", nargs="+", default=None,
                        choices=STUDY_CONFIGS,
                        help="Configs to evaluate (default: all 8)")
    parser.add_argument("--resume",   action="store_true",
                        help="Skip already-evaluated answers")
    parser.add_argument("--force",    action="store_true",
                        help="Delete existing eval results and re-run from scratch")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Estimate cost without running")
    parser.add_argument("--summary",  action="store_true",
                        help="Print summary table and exit (no new evaluation)")
    args = parser.parse_args()

    config_names = args.configs or STUDY_CONFIGS
    gold = load_gold()
    print(f"Loaded {len(gold)} gold references")
    print(f"Configs: {config_names}")

    if args.dry_run:
        dry_run_estimate(config_names, gold)
        return

    if args.summary:
        print_summary(config_names)
        return

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    grand_cost = 0.0
    summaries  = []

    for j, name in enumerate(config_names, 1):
        run_path = os.path.join(RUNS_DIR, f"{name}.jsonl")
        if not os.path.exists(run_path):
            print(f"\n  ⚠ {name}: no run file found at {run_path} — skipping")
            continue

        answers = load_run_answers(name)
        summary = eval_config(name, answers, gold, client, resume=args.resume, force=args.force)
        summaries.append(summary)
        grand_cost += summary.get("cost", 0)

        if j < len(config_names):
            time.sleep(1.0)  # brief pause between configs

    print(f"\n{'='*60}")
    print("PHASE 3 EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"{'Config':<12} {'Evaluated':<12} {'Cost':<12} {'Errors'}")
    print("-"*50)
    for s in summaries:
        print(f"  {s['config']:<10} {s.get('total',0):<12} "
              f"${s.get('cost',0):<11.4f} {s.get('errors',0)}")
    print("-"*50)
    print(f"  {'TOTAL':<10} {sum(s.get('total',0) for s in summaries):<12} ${grand_cost:.4f}")
    print(f"\nOutput directory: {EVAL_DIR}")

    # Auto-print summary after eval
    print("\n")
    print_summary(config_names)


if __name__ == "__main__":
    main()
