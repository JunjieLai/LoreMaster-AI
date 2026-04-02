"""
LoreMaster-AI ETL - Step 3: Filter

Extracts the Sumeru-related subset from the full parsed dataset.
Uses category-based detection plus title/content keyword matching
to capture all Sumeru-relevant documents.
"""

import json
import logging
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_parsed.jsonl")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_sumeru.jsonl")

# Sumeru-related keywords for broader matching
SUMERU_KEYWORDS = [
    # Region names
    "Sumeru", "Dharma Forest", "Avidya Forest", "Ardravi Valley",
    "Lokapala Jungle", "Ashavan Realm", "Vissudha Field",
    "Vanarana", "Gandharva Ville", "Port Ormos", "Chatrakam Cave",
    "Apam Woods", "Devantaka Mountain", "Chinvat Ravine",
    "Mawtiyima Forest",
    # Desert areas
    "Great Red Sand", "Desert of Hadramaveth", "Girdle of the Sands",
    "Hypostyle Desert", "Land of Lower Setekh", "Land of Upper Setekh",
    "Realm of Farakhkert", "Gavireh Lajavard",
    # Key locations
    "Sumeru City", "Akademiya", "Sanctuary of Surasthana",
    "Pardis Dhyai", "Irminsul", "Aaru Village",
    # Characters (Sumeru playable)
    "Nahida", "Alhaitham", "Tighnari", "Cyno", "Nilou", "Dehya",
    "Dori", "Collei", "Candace", "Layla", "Kaveh", "Faruzan",
    "Wanderer", "Scaramouche", "Baizhu", "Sethos",
    # Important NPCs/entities
    "Greater Lord Rukkhadevata", "King Deshret", "Nabu Malikata",
    "Goddess of Flowers",
    # Concepts
    "Dendro Archon", "Forbidden Knowledge", "Akasha",
    "Aranara", "Eremite", "The Eremites",
    # Tribes/groups
    "Vahumana", "Rtawahist", "Spantamad", "Haravatat",
    "Amurta", "Kshahrewar",
]

# Pre-compile a single regex for fast matching
SUMERU_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in SUMERU_KEYWORDS),
    re.IGNORECASE,
)


def is_sumeru_related(doc):
    """Check if a document is related to Sumeru."""
    # 1. Check if region detection already found Sumeru
    if "Sumeru" in doc.get("regions", []):
        return True

    # 2. Check categories
    cat_str = " ".join(doc.get("categories", []))
    if SUMERU_PATTERN.search(cat_str):
        return True

    # 3. Check title
    title = doc.get("title", "")
    if SUMERU_PATTERN.search(title):
        return True

    # 4. Check content (first 2000 chars for performance)
    content = doc.get("content", "")[:2000]
    if SUMERU_PATTERN.search(content):
        return True

    return False


def main():
    logger.info("Filtering Sumeru subset from %s ...", INPUT_PATH)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    total = 0
    kept = 0
    type_counts = {}
    region_counts = {}

    with open(INPUT_PATH, encoding="utf-8") as fin, \
         open(OUTPUT_PATH, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total += 1
            doc = json.loads(line)

            if not is_sumeru_related(doc):
                continue

            fout.write(json.dumps(doc, ensure_ascii=False) + "\n")
            kept += 1

            et = doc["entity_type"]
            type_counts[et] = type_counts.get(et, 0) + 1
            for r in doc["regions"]:
                region_counts[r] = region_counts.get(r, 0) + 1

    logger.info("Filtered: %d / %d records kept (%.1f%%)", kept, total, 100 * kept / total if total else 0)
    logger.info("Output: %s", OUTPUT_PATH)
    logger.info("Entity type distribution (Sumeru subset):")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info("  %5d  %s", c, t)
    logger.info("Region distribution (Sumeru subset):")
    for r, c in sorted(region_counts.items(), key=lambda x: -x[1]):
        logger.info("  %5d  %s", c, r)

    return kept, type_counts, region_counts


if __name__ == "__main__":
    main()
