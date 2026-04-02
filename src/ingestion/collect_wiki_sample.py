"""
LoreMaster-AI - Wiki Data Sample Collection

Collects 100-200 sample records from the HuggingFace dataset
`mrzjy/multimodal-genshin-impact` (genshin.jsonl file).
Prioritizes Sumeru-related content by streaming the JSONL directly.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

import requests
from huggingface_hub import hf_hub_url
from tqdm import tqdm

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import HF_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sumeru keywords for prioritisation
# ---------------------------------------------------------------------------
SUMERU_KEYWORDS = [
    # Characters
    "Nahida", "纳西妲", "Alhaitham", "艾尔海森", "Tighnari", "提纳里",
    "Cyno", "赛诺", "Nilou", "妮露", "Dehya", "迪希雅", "Dori", "多莉",
    "Collei", "柯莱", "Candace", "坎蒂丝", "Layla", "莱依拉",
    "Scaramouche", "散兵", "Wanderer", "流浪者", "Kaveh", "卡维",
    # Locations
    "Sumeru", "须弥", "Sanctuary of Surasthana", "净善宫",
    "Akademiya", "教令院", "Vanarana", "桓那兰那",
    # Organisations
    "Fatui", "愚人众", "镀金旅团",
    # Concepts
    "Forbidden Knowledge", "禁忌知识", "Irminsul", "世界树",
    "Dendro Archon", "草神", "Greater Lord Rukkhadevata", "大慈树王",
]

SUMERU_KEYWORDS_LOWER = [k.lower() for k in SUMERU_KEYWORDS]

OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/raw/wiki/sample.jsonl")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "data/metadata/wiki_sample_manifest.json")

TARGET_TOTAL = 200
TARGET_SUMERU = 120
MAX_SCAN = 22200  # scan up to the full dataset


def is_sumeru_related(record: dict) -> bool:
    """Check whether a record is related to Sumeru."""
    # Check categories
    for cat in record.get("category", []):
        if isinstance(cat, str):
            lower = cat.lower()
            if any(kw in lower for kw in ["sumeru", "dendro", "akademiya"]):
                return True

    # Check URL / title
    url = record.get("url", "").lower()
    for kw in SUMERU_KEYWORDS_LOWER:
        if kw in url:
            return True

    # Check markdown content (first 2000 chars for speed)
    markdown = record.get("markdown", "")[:2000].lower()
    for kw in SUMERU_KEYWORDS_LOWER:
        if kw in markdown:
            return True

    return False


def stream_records():
    """Stream records from the HuggingFace JSONL file."""
    url = hf_hub_url(
        "mrzjy/multimodal-genshin-impact",
        "genshin.jsonl",
        repo_type="dataset",
    )
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    logger.info("Streaming from %s ...", url)
    resp = requests.get(url, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    buf = b""
    for chunk in resp.iter_content(chunk_size=65536):
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                try:
                    yield json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue


def collect_samples():
    sumeru_records: list[dict] = []
    other_records: list[dict] = []
    scanned = 0
    need_other = TARGET_TOTAL - TARGET_SUMERU

    logger.info("Scanning records (target: %d total, >= %d Sumeru) ...", TARGET_TOTAL, TARGET_SUMERU)

    for record in tqdm(stream_records(), desc="Scanning", unit="rec", total=MAX_SCAN):
        scanned += 1

        if is_sumeru_related(record):
            if len(sumeru_records) < TARGET_SUMERU:
                sumeru_records.append(record)
        else:
            if len(other_records) < need_other:
                other_records.append(record)

        if len(sumeru_records) >= TARGET_SUMERU and len(other_records) >= need_other:
            break

        if scanned >= MAX_SCAN:
            break

    all_records = sumeru_records + other_records
    logger.info(
        "Collected %d records (%d Sumeru, %d other) from %d scanned.",
        len(all_records), len(sumeru_records), len(other_records), scanned,
    )

    # ------------------------------------------------------------------
    # Write JSONL
    # ------------------------------------------------------------------
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info("Wrote %d records to %s", len(all_records), OUTPUT_PATH)

    # ------------------------------------------------------------------
    # Write manifest
    # ------------------------------------------------------------------
    manifest = {
        "source": "mrzjy/multimodal-genshin-impact",
        "source_file": "genshin.jsonl",
        "platform": "HuggingFace",
        "collection_time": datetime.now(timezone.utc).isoformat(),
        "records_collected": len(all_records),
        "sumeru_related": len(sumeru_records),
        "non_sumeru": len(other_records),
        "total_scanned": scanned,
        "output_file": "data/raw/wiki/sample.jsonl",
        "data_fields": ["url", "sections", "category", "markdown"],
        "sumeru_keywords_used": SUMERU_KEYWORDS,
    }

    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info("Wrote manifest to %s", MANIFEST_PATH)
    return manifest


if __name__ == "__main__":
    collect_samples()
