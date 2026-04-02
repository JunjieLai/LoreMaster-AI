"""
Repair & deduplicate gold_references.jsonl

1. Deduplicates: for each question_id, keep the LAST occurrence (most recent run)
2. Repairs parse errors: fixes unescaped quotes + markdown fences in _raw field
3. Re-applies _flag_review_items on repaired entries

Usage:
    python src/ablation/repair_gold.py
"""

import json
import os
import re
import sys
import shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from src.ablation.generate_gold import _flag_review_items

GOLD_PATH = os.path.join(PROJECT_ROOT, "data/ablation/gold_references.jsonl")
BACKUP_PATH = GOLD_PATH + ".bak"


def strip_fence(text: str) -> str:
    """Remove ```json ... ``` markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


def fix_unescaped_quotes(text: str) -> str:
    """
    Use a state machine to find unescaped double quotes inside JSON string values
    and escape them. Handles Chinese quotation marks used as "..."  inside strings.
    """
    result = []
    i = 0
    n = len(text)
    in_string = False

    while i < n:
        ch = text[i]

        # Handle escape sequences inside strings
        if in_string and ch == '\\' and i + 1 < n:
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue

        if ch == '"':
            if not in_string:
                # Opening a string
                in_string = True
                result.append(ch)
            else:
                # We're inside a string: is this a structural closing quote?
                # Look ahead: skip whitespace and see what follows
                j = i + 1
                while j < n and text[j] in ' \t\r\n':
                    j += 1
                next_ch = text[j] if j < n else ''

                if next_ch in (',', '}', ']', ':'):
                    # Structural closing quote — ends the string
                    in_string = False
                    result.append(ch)
                else:
                    # Internal quote (e.g., Chinese quotation mark) — escape it
                    result.append('\\"')
        else:
            result.append(ch)

        i += 1

    return ''.join(result)


def fix_trailing_commas(text: str) -> str:
    """Remove trailing commas before ] or } (common model mistake)."""
    return re.sub(r',\s*([}\]])', r'\1', text)


def extract_json_robust(raw: str):
    """Try multiple strategies to extract a valid JSON object."""
    # Strategy 1: strip fence, direct parse
    text = strip_fence(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fix trailing commas
    text2 = fix_trailing_commas(text)
    try:
        return json.loads(text2)
    except json.JSONDecodeError:
        pass

    # Strategy 3: fix unescaped quotes + trailing commas
    text3 = fix_trailing_commas(fix_unescaped_quotes(text))
    try:
        return json.loads(text3)
    except json.JSONDecodeError:
        pass

    # Strategy 4: brace matching on original
    start = raw.find('{')
    if start != -1:
        depth = 0
        for idx, ch in enumerate(raw[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = fix_trailing_commas(
                        fix_unescaped_quotes(raw[start:idx + 1])
                    )
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    return None


def main():
    # Read all entries
    entries = []
    with open(GOLD_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    print(f"Read {len(entries)} entries from gold_references.jsonl")

    # Deduplicate: keep last occurrence of each question_id
    seen = {}
    for entry in entries:
        qid = entry.get("question_id") or entry.get("_meta", {}).get("question_id", "?")
        seen[qid] = entry

    deduped = list(seen.values())
    print(f"After dedup: {len(deduped)} unique questions")

    # Repair parse errors
    repaired = 0
    still_broken = []
    for qid, entry in seen.items():
        if not entry.get("_parse_error"):
            continue
        raw = entry.get("_raw", "")
        if not raw:
            still_broken.append(qid)
            continue

        parsed = extract_json_robust(raw)
        if parsed:
            parsed["_meta"] = entry.get("_meta", {})
            parsed = _flag_review_items(parsed)
            seen[qid] = parsed
            repaired += 1
            print(f"  Repaired: {qid}")
        else:
            still_broken.append(qid)
            print(f"  Still unparseable: {qid}")

    print(f"\nRepaired {repaired} / {repaired + len(still_broken)} parse errors")

    # Backup and write cleaned file
    shutil.copy(GOLD_PATH, BACKUP_PATH)
    print(f"Backup saved to {BACKUP_PATH}")

    final = list(seen.values())
    with open(GOLD_PATH, "w", encoding="utf-8") as f:
        for entry in final:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote {len(final)} entries to {GOLD_PATH}")

    parse_errors = sum(1 for e in final if e.get("_parse_error"))
    clean = sum(1 for e in final if not e.get("_parse_error") and not e.get("_needs_human_review"))
    flagged = sum(1 for e in final if not e.get("_parse_error") and e.get("_needs_human_review"))
    print(f"\nFinal state:")
    print(f"  Clean (no flags):       {clean}")
    print(f"  Flagged (needs review): {flagged}")
    print(f"  Still parse errors:     {parse_errors}")
    if still_broken:
        print(f"  Broken IDs: {still_broken}")


if __name__ == "__main__":
    main()
