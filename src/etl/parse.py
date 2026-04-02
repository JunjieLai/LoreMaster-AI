"""
LoreMaster-AI ETL - Step 2: Parse

Converts raw Wiki JSONL into a standardized document format.
Extracts entity names, infers entity types from categories,
cleans markdown content, and computes content hashes.
"""

import hashlib
import json
import logging
import os
import re
import sys
from urllib.parse import unquote

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = os.path.join(PROJECT_ROOT, "data/raw/wiki/genshin_wiki_full.jsonl")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/processed/documents/wiki_parsed.jsonl")

# Category -> entity_type mapping (first match wins)
ENTITY_TYPE_RULES = [
    # Must check specific categories before generic ones
    (lambda cats: "Playable Characters" in cats, "PlayableCharacter"),
    (lambda cats: any("Archons" in c for c in cats), "Character"),
    (lambda cats: "NPCs" in cats or any("NPC" in c for c in cats), "NPC"),
    (lambda cats: "Characters" in cats, "Character"),
    (lambda cats: "Enemies" in cats or any("Boss" in c for c in cats), "Enemy"),
    (lambda cats: "Locations" in cats or any("Location" in c for c in cats), "Location"),
    (lambda cats: "Quests" in cats, "Quest"),
    (lambda cats: "Achievements" in cats, "Achievement"),
    (lambda cats: any("Soundtrack" in c for c in cats), "Soundtrack"),
    (lambda cats: "Furnishings" in cats, "Furnishing"),
    (lambda cats: any("Weapon" in c for c in cats), "Weapon"),
    (lambda cats: any("Artifact" in c for c in cats), "Artifact"),
    (lambda cats: any("Food" in c or "Dish" in c for c in cats), "Food"),
    (lambda cats: any("Material" in c for c in cats), "Material"),
    (lambda cats: "Talents" in cats, "Talent"),
    (lambda cats: "Constellations" in cats, "Constellation"),
    (lambda cats: any("TCG" in c or "Genius Invokation" in c for c in cats), "TCG"),
    (lambda cats: any("Book" in c or "Readable" in c for c in cats), "Book"),
    (lambda cats: "Terminology" in cats, "Concept"),
    (lambda cats: "Dialogue" in cats, "Dialogue"),
    (lambda cats: any("Item" in c for c in cats), "Item"),
]

# Region detection from categories
REGION_KEYWORDS = {
    "Mondstadt": "Mondstadt",
    "Liyue": "Liyue",
    "Inazuma": "Inazuma",
    "Sumeru": "Sumeru",
    "Fontaine": "Fontaine",
    "Natlan": "Natlan",
    "Snezhnaya": "Snezhnaya",
    "Khaenri'ah": "Khaenri'ah",
    "Enkanomiya": "Enkanomiya",
    "The Chasm": "The Chasm",
    "Golden Apple": "Golden Apple Archipelago",
    "Dragonspine": "Dragonspine",
}

# Markdown image/link pattern for cleaning
RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^\)]+\)")
RE_MD_HR = re.compile(r"^---+\s*$", re.MULTILINE)
RE_MULTI_NEWLINE = re.compile(r"\n{3,}")


def extract_title(record):
    """Extract entity title from sections[0].title or URL."""
    sections = record.get("sections", [])
    if sections and sections[0].get("title"):
        return sections[0]["title"].strip().strip('"')

    # Fallback: extract from URL
    url = record.get("url", "")
    if "/wiki/" in url:
        slug = url.split("/wiki/")[-1]
        return unquote(slug).replace("_", " ")

    return "Unknown"


def infer_entity_type(categories):
    """Infer entity type from category tags."""
    for rule_fn, etype in ENTITY_TYPE_RULES:
        if rule_fn(categories):
            return etype
    return "Other"


def detect_regions(categories):
    """Detect which game regions are associated with this document."""
    regions = []
    cat_str = " ".join(categories).lower()
    for keyword, region_name in REGION_KEYWORDS.items():
        if keyword.lower() in cat_str:
            regions.append(region_name)
    return regions


def clean_markdown(text):
    """Clean markdown text for downstream processing."""
    # Remove image references (keep alt text if meaningful)
    text = RE_MD_IMAGE.sub("", text)
    # Remove horizontal rules
    text = RE_MD_HR.sub("", text)
    # Collapse excessive newlines
    text = RE_MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def parse_sections(raw_sections):
    """Convert raw sections array to clean section list."""
    parsed = []
    for sec in raw_sections:
        title = sec.get("title", "").strip()
        md = sec.get("markdown", "").strip()
        level = sec.get("level", 0)

        # Skip empty sections and info card boilerplate
        content = clean_markdown(md)
        # Remove the heading line itself from content
        lines = content.split("\n")
        if lines and lines[0].startswith("#"):
            content = "\n".join(lines[1:]).strip()

        if not content:
            continue

        parsed.append({
            "title": title,
            "level": level,
            "content": content,
        })
    return parsed


def make_doc_id(url):
    """Generate a stable doc_id from URL."""
    if "/wiki/" in url:
        slug = url.split("/wiki/")[-1]
        return "wiki_" + unquote(slug).replace(" ", "_").replace("/", "_")
    return "wiki_" + hashlib.md5(url.encode()).hexdigest()[:12]


def parse_record(record):
    """Parse a single raw record into standardized document format."""
    url = record.get("url", "")
    categories = record.get("category", [])
    markdown = record.get("markdown", "")
    raw_sections = record.get("sections", [])

    title = extract_title(record)
    entity_type = infer_entity_type(categories)
    regions = detect_regions(categories)
    content = clean_markdown(markdown)
    sections = parse_sections(raw_sections)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return {
        "doc_id": make_doc_id(url),
        "title": title,
        "content": content,
        "source_url": url,
        "categories": categories,
        "entity_type": entity_type,
        "regions": regions,
        "sections": sections,
        "content_length": len(content),
        "content_hash": content_hash,
    }


def main():
    logger.info("Parsing %s ...", INPUT_PATH)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    count = 0
    type_counts = {}
    region_counts = {}

    with open(INPUT_PATH, encoding="utf-8") as fin, \
         open(OUTPUT_PATH, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            doc = parse_record(raw)
            fout.write(json.dumps(doc, ensure_ascii=False) + "\n")
            count += 1

            et = doc["entity_type"]
            type_counts[et] = type_counts.get(et, 0) + 1
            for r in doc["regions"]:
                region_counts[r] = region_counts.get(r, 0) + 1

    logger.info("Parsed %d records -> %s", count, OUTPUT_PATH)
    logger.info("Entity type distribution:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info("  %5d  %s", c, t)
    logger.info("Region distribution:")
    for r, c in sorted(region_counts.items(), key=lambda x: -x[1]):
        logger.info("  %5d  %s", c, r)

    return count, type_counts, region_counts


if __name__ == "__main__":
    main()
