"""
LoreMaster-AI - Dialog Data Sample Collection

Downloads dialog records from the GitHub repository `mrzjy/GenshinDialog`.
Collects from all available JSONL files (dialog, quest, talk) for both
CHS and EN languages.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

REPO_OWNER = "mrzjy"
REPO_NAME = "GenshinDialog"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main"

# All known JSONL data files in the repo
DATA_FILES = [
    ("extracted_dialog/dialog_CHS.jsonl", "dialog", "CHS"),
    ("extracted_dialog/dialog_EN.jsonl", "dialog", "EN"),
    ("extracted_dialog/raw_dialog_CHS.jsonl", "raw_dialog", "CHS"),
    ("extracted_dialog/raw_dialog_EN.jsonl", "raw_dialog", "EN"),
    ("extracted_quest/quest_CHS.jsonl", "quest", "CHS"),
    ("extracted_quest/quest_EN.jsonl", "quest", "EN"),
    ("extracted_talk/talk_npc_CHS.jsonl", "talk_npc", "CHS"),
    ("extracted_talk/talk_npc_EN.jsonl", "talk_npc", "EN"),
    ("extracted_talk/talk_activity_CHS.jsonl", "talk_activity", "CHS"),
    ("extracted_talk/talk_activity_EN.jsonl", "talk_activity", "EN"),
    ("extracted_talk/talk_gadget_CHS.jsonl", "talk_gadget", "CHS"),
    ("extracted_talk/talk_gadget_EN.jsonl", "talk_gadget", "EN"),
    ("extracted_talk/talk_coop_CHS.jsonl", "talk_coop", "CHS"),
    ("extracted_talk/talk_coop_EN.jsonl", "talk_coop", "EN"),
    ("extracted_talk/talk_blossom_CHS.jsonl", "talk_blossom", "CHS"),
    ("extracted_talk/talk_blossom_EN.jsonl", "talk_blossom", "EN"),
]

# Also grab the avatar data (JSON, not JSONL)
AVATAR_FILES = [
    ("extracted_avatar/avatar_CHS.json", "avatar", "CHS"),
    ("extracted_avatar/avatar_EN.json", "avatar", "EN"),
]

OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/raw/github/dialog_sample.jsonl")
TARGET_RECORDS = 200


def download_jsonl(file_path: str, source_type: str, language: str) -> list[dict]:
    """Download a JSONL file and return parsed records with metadata."""
    url = f"{RAW_BASE}/{file_path}"
    logger.info("  Downloading %s ...", file_path)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("  Failed: %s", e)
        return []

    records = []
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Normalize: wrap arrays into dicts
        if isinstance(data, list):
            record = {"turns": data}
        elif isinstance(data, dict):
            record = data
        else:
            continue

        record["_source_file"] = file_path
        record["_source_type"] = source_type
        record["_language"] = language
        records.append(record)

    return records


def download_avatar_json(file_path: str, source_type: str, language: str) -> list[dict]:
    """Download avatar JSON (character data) and convert to records."""
    url = f"{RAW_BASE}/{file_path}"
    logger.info("  Downloading %s ...", file_path)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("  Failed: %s", e)
        return []

    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError:
        return []

    records = []
    if isinstance(data, dict):
        for name, info in data.items():
            record = {"character_name": name}
            if isinstance(info, dict):
                record.update(info)
            record["_source_file"] = file_path
            record["_source_type"] = source_type
            record["_language"] = language
            records.append(record)
    return records


def collect_samples():
    all_records: list[dict] = []
    file_stats: dict[str, int] = {}

    logger.info("Collecting dialog data from %s/%s ...", REPO_OWNER, REPO_NAME)

    # Collect from JSONL files
    for file_path, source_type, language in DATA_FILES:
        records = download_jsonl(file_path, source_type, language)
        file_stats[file_path] = len(records)
        all_records.extend(records)
        logger.info("    -> %d records", len(records))

    # Collect avatar/character data
    for file_path, source_type, language in AVATAR_FILES:
        records = download_avatar_json(file_path, source_type, language)
        file_stats[file_path] = len(records)
        all_records.extend(records)
        logger.info("    -> %d records", len(records))

    # Trim to target if needed
    if len(all_records) > TARGET_RECORDS:
        all_records = all_records[:TARGET_RECORDS]

    logger.info("Total records collected: %d", len(all_records))

    # ------------------------------------------------------------------
    # Write JSONL
    # ------------------------------------------------------------------
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info("Wrote %d records to %s", len(all_records), OUTPUT_PATH)

    return {
        "source": f"github.com/{REPO_OWNER}/{REPO_NAME}",
        "files_stats": file_stats,
        "total_from_all_files": sum(file_stats.values()),
        "records_saved": len(all_records),
        "collection_time": datetime.now(timezone.utc).isoformat(),
        "output_file": "data/raw/github/dialog_sample.jsonl",
    }


if __name__ == "__main__":
    result = collect_samples()
    print(json.dumps(result, indent=2, ensure_ascii=False))
