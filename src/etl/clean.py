"""
LoreMaster-AI ETL - Step 4: Clean

Deduplicates documents by content hash, applies alias normalization,
removes boilerplate sections, and normalizes text.
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

INPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_sumeru.jsonl")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_clean.jsonl")

# Known aliases -> canonical name
ALIAS_MAP = {
    # Characters
    "Scaramouche": "Wanderer",
    "Balladeer": "Wanderer",
    "Kunikuzushi": "Wanderer",
    "Lesser Lord Kusanali": "Nahida",
    "Buer": "Nahida",
    "Shouki no Kami": "Wanderer",
    # Organizations
    "The Akademiya": "Akademiya",
    "Sumeru Akademiya": "Akademiya",
    # Locations
    "The Chasm: Underground Mines": "The Chasm",
}

# Sections to skip (boilerplate)
SKIP_SECTIONS = {
    "Info Card", "Navigation", "Change History", "Version History",
    "References", "External Links", "See Also", "Gallery",
    "Other Languages", "Trivia",  # Trivia kept only if substantial
}

# Minimum content length to keep a document
MIN_CONTENT_LENGTH = 50

# Regex to clean wiki template artifacts
RE_TEMPLATE = re.compile(r"\{\{[^}]*\}\}")
RE_EXTRA_SPACES = re.compile(r"[ \t]+")
RE_TRAILING_WHITESPACE = re.compile(r"[ \t]+$", re.MULTILINE)


def normalize_text(text):
    """Normalize text content."""
    # Remove any leftover wiki template artifacts
    text = RE_TEMPLATE.sub("", text)
    # Normalize whitespace
    text = RE_EXTRA_SPACES.sub(" ", text)
    text = RE_TRAILING_WHITESPACE.sub("", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_sections(sections):
    """Remove boilerplate sections and clean remaining ones."""
    cleaned = []
    for sec in sections:
        title = sec.get("title", "")
        # Skip boilerplate
        if title in SKIP_SECTIONS:
            continue
        # Skip Trivia if very short
        if title == "Trivia" and len(sec.get("content", "")) < 100:
            continue

        content = normalize_text(sec.get("content", ""))
        if not content:
            continue

        cleaned.append({
            "title": title,
            "level": sec.get("level", 0),
            "content": content,
        })
    return cleaned


def apply_alias(doc):
    """Apply alias normalization to title."""
    title = doc.get("title", "")
    if title in ALIAS_MAP:
        doc["canonical_name"] = ALIAS_MAP[title]
        doc["aliases"] = [title]
    else:
        doc["canonical_name"] = title
        doc["aliases"] = []
    return doc


def main():
    logger.info("Cleaning %s ...", INPUT_PATH)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    total = 0
    kept = 0
    deduped = 0
    too_short = 0
    seen_hashes = set()

    with open(INPUT_PATH, encoding="utf-8") as fin, \
         open(OUTPUT_PATH, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total += 1
            doc = json.loads(line)

            # Deduplicate by content_hash
            content_hash = doc.get("content_hash", "")
            if content_hash in seen_hashes:
                deduped += 1
                continue
            seen_hashes.add(content_hash)

            # Clean content
            doc["content"] = normalize_text(doc["content"])
            doc["sections"] = clean_sections(doc["sections"])

            # Rebuild content_length
            doc["content_length"] = len(doc["content"])

            # Skip too-short documents
            if doc["content_length"] < MIN_CONTENT_LENGTH:
                too_short += 1
                continue

            # Apply alias normalization
            doc = apply_alias(doc)

            fout.write(json.dumps(doc, ensure_ascii=False) + "\n")
            kept += 1

    logger.info("Clean complete: %d input -> %d output", total, kept)
    logger.info("  Deduplicated: %d", deduped)
    logger.info("  Too short (<%d chars): %d", MIN_CONTENT_LENGTH, too_short)
    logger.info("Output: %s", OUTPUT_PATH)

    return kept, deduped, too_short


if __name__ == "__main__":
    main()
