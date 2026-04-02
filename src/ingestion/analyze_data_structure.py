"""
LoreMaster-AI - Data Structure Analysis

Analyzes the collected Wiki and Dialog sample data to produce:
1. data/metadata/wiki_schema.json   - Wiki field schema
2. data/metadata/dialog_schema.json - Dialog field schema
3. docs/data_structure_analysis.md  - Human-readable analysis report
"""

import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

WIKI_PATH = os.path.join(PROJECT_ROOT, "data/raw/wiki/sample.jsonl")
DIALOG_PATH = os.path.join(PROJECT_ROOT, "data/raw/github/dialog_sample.jsonl")
WIKI_SCHEMA_PATH = os.path.join(PROJECT_ROOT, "data/metadata/wiki_schema.json")
DIALOG_SCHEMA_PATH = os.path.join(PROJECT_ROOT, "data/metadata/dialog_schema.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "docs/data_structure_analysis.md")


# ======================================================================
# Helper functions
# ======================================================================

def load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def infer_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def analyze_field(field_name: str, values: list) -> dict:
    """Analyze a single field across all records."""
    total = len(values)
    non_null = [v for v in values if v is not None and v != "" and v != []]
    non_null_count = len(non_null)

    # Type distribution
    type_counts = Counter(infer_type(v) for v in values)

    # Primary type (most common non-null type)
    non_null_types = Counter(infer_type(v) for v in non_null)
    primary_type = non_null_types.most_common(1)[0][0] if non_null_types else "null"

    result = {
        "field_name": field_name,
        "primary_type": primary_type,
        "type_distribution": dict(type_counts),
        "total_count": total,
        "non_null_count": non_null_count,
        "null_rate": round(1 - non_null_count / total, 4) if total > 0 else 1.0,
        "examples": [],
    }

    # Collect up to 3 example values
    examples_seen = set()
    for v in non_null:
        if isinstance(v, str):
            ex = truncate(v)
        elif isinstance(v, (list, dict)):
            ex = truncate(json.dumps(v, ensure_ascii=False))
        else:
            ex = str(v)
        if ex not in examples_seen:
            examples_seen.add(ex)
            result["examples"].append(ex)
        if len(result["examples"]) >= 3:
            break

    # String-specific stats
    if primary_type == "string" and non_null:
        str_vals = [v for v in non_null if isinstance(v, str)]
        if str_vals:
            lengths = [len(s) for s in str_vals]
            result["string_stats"] = {
                "min_length": min(lengths),
                "max_length": max(lengths),
                "avg_length": round(sum(lengths) / len(lengths), 1),
                "median_length": sorted(lengths)[len(lengths) // 2],
            }
            # Detect format hints
            has_html = any("<" in s and ">" in s for s in str_vals[:50])
            has_markdown = any(("#" in s or "[[" in s or "**" in s) for s in str_vals[:50])
            has_wikitext = any(("{{" in s or "[[" in s) for s in str_vals[:50])
            result["format_hints"] = {
                "contains_html": has_html,
                "contains_markdown": has_markdown,
                "contains_wikitext": has_wikitext,
            }

    # Array-specific stats
    if primary_type == "array" and non_null:
        arr_vals = [v for v in non_null if isinstance(v, list)]
        if arr_vals:
            lengths = [len(a) for a in arr_vals]
            result["array_stats"] = {
                "min_length": min(lengths),
                "max_length": max(lengths),
                "avg_length": round(sum(lengths) / len(lengths), 1),
            }

    # Unique value count for low-cardinality fields
    if primary_type in ("string", "integer", "boolean") and non_null:
        unique_vals = set(str(v) for v in non_null)
        result["unique_count"] = len(unique_vals)
        if len(unique_vals) <= 30:
            result["unique_values"] = sorted(unique_vals)

    return result


def analyze_dataset(records: list[dict], dataset_name: str) -> dict:
    """Analyze all fields in a dataset."""
    if not records:
        return {"dataset": dataset_name, "record_count": 0, "fields": []}

    # Gather all field names
    all_fields = set()
    for rec in records:
        all_fields.update(rec.keys())

    # Analyze each field
    field_analyses = []
    for field in sorted(all_fields):
        values = [rec.get(field) for rec in records]
        field_analyses.append(analyze_field(field, values))

    schema = {
        "dataset": dataset_name,
        "record_count": len(records),
        "field_count": len(all_fields),
        "fields": field_analyses,
        "analysis_time": datetime.now(timezone.utc).isoformat(),
    }

    return schema


# ======================================================================
# Entity & Relationship analysis (Wiki-specific)
# ======================================================================

def analyze_entity_potential(wiki_schema: dict, wiki_records: list[dict]) -> dict:
    """Analyze which fields could serve as entity IDs, names, categories."""
    fields = {f["field_name"]: f for f in wiki_schema["fields"]}

    entity_id_candidates = []
    entity_name_candidates = []
    category_candidates = []
    text_content_candidates = []
    reference_candidates = []

    for fname, finfo in fields.items():
        ptype = finfo["primary_type"]
        null_rate = finfo["null_rate"]
        unique_count = finfo.get("unique_count", 0)
        total = finfo["total_count"]

        lower_name = fname.lower()

        # ID candidates: low null rate, high uniqueness, string/int
        if ptype in ("string", "integer") and null_rate < 0.05 and unique_count > total * 0.8:
            entity_id_candidates.append({
                "field": fname,
                "type": ptype,
                "null_rate": null_rate,
                "unique_count": unique_count,
            })

        # Name candidates
        if ptype == "string" and any(kw in lower_name for kw in ("name", "title", "label")):
            entity_name_candidates.append({
                "field": fname,
                "null_rate": null_rate,
                "unique_count": unique_count,
            })

        # Category candidates: low cardinality string fields
        if ptype == "string" and unique_count and unique_count <= 30 and null_rate < 0.3:
            category_candidates.append({
                "field": fname,
                "unique_count": unique_count,
                "values": finfo.get("unique_values", []),
            })

        # Array fields that might be categories/tags
        if ptype == "array":
            category_candidates.append({
                "field": fname,
                "type": "array",
                "avg_length": finfo.get("array_stats", {}).get("avg_length", 0),
            })

        # Text content: long string fields
        if ptype == "string":
            avg_len = finfo.get("string_stats", {}).get("avg_length", 0)
            if avg_len > 200:
                text_content_candidates.append({
                    "field": fname,
                    "avg_length": avg_len,
                    "max_length": finfo.get("string_stats", {}).get("max_length", 0),
                    "format_hints": finfo.get("format_hints", {}),
                })

        # Reference candidates: fields with URLs, IDs, or wiki-links
        if ptype == "string":
            examples = finfo.get("examples", [])
            has_refs = any(
                "http" in str(e) or "[[" in str(e) or "wiki" in str(e).lower()
                for e in examples
            )
            if has_refs:
                reference_candidates.append({
                    "field": fname,
                    "examples": examples[:2],
                })

    return {
        "entity_id_candidates": entity_id_candidates,
        "entity_name_candidates": entity_name_candidates,
        "category_candidates": category_candidates,
        "text_content_candidates": text_content_candidates,
        "reference_candidates": reference_candidates,
    }


def analyze_relationship_clues(wiki_records: list[dict]) -> dict:
    """Look for relationship patterns in the data."""
    clues = {
        "cross_page_references": False,
        "explicit_relationship_fields": [],
        "link_patterns": [],
    }

    # Sample a few records to check for patterns
    for rec in wiki_records[:20]:
        for key, val in rec.items():
            if not isinstance(val, str):
                continue
            # Check for wiki-links [[...]]
            if "[[" in val and "]]" in val:
                clues["cross_page_references"] = True
                if key not in clues["link_patterns"]:
                    clues["link_patterns"].append(key)
            # Check for relationship-like fields
            lower_key = key.lower()
            if any(kw in lower_key for kw in ("relation", "link", "ref", "parent", "child", "connect")):
                if key not in clues["explicit_relationship_fields"]:
                    clues["explicit_relationship_fields"].append(key)

    return clues


# ======================================================================
# Report generation
# ======================================================================

def generate_report(
    wiki_schema: dict,
    dialog_schema: dict,
    wiki_records: list[dict],
    dialog_records: list[dict],
    entity_analysis: dict,
    relationship_clues: dict,
) -> str:
    """Generate the full Markdown analysis report."""
    lines = []

    def h1(t): lines.append(f"# {t}\n")
    def h2(t): lines.append(f"## {t}\n")
    def h3(t): lines.append(f"### {t}\n")
    def p(t): lines.append(f"{t}\n")
    def blank(): lines.append("")

    h1("LoreMaster-AI Data Structure Analysis Report")
    p(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    blank()

    # ---- Overview ----
    h2("1. Dataset Overview")
    p(f"| Dataset | Records | Fields |")
    p(f"|---------|---------|--------|")
    p(f"| Wiki Sample | {wiki_schema['record_count']} | {wiki_schema['field_count']} |")
    p(f"| Dialog Sample | {dialog_schema['record_count']} | {dialog_schema['field_count']} |")
    blank()

    # ---- Wiki Field Analysis ----
    h2("2. Wiki Data Field Analysis")
    blank()
    p("| Field | Type | Non-null Rate | Unique Count | Avg Length |")
    p("|-------|------|---------------|--------------|------------|")
    for f in wiki_schema["fields"]:
        null_pct = f"{(1 - f['null_rate']) * 100:.1f}%"
        unique = f.get("unique_count", "-")
        avg_len = f.get("string_stats", {}).get("avg_length", "-")
        p(f"| `{f['field_name']}` | {f['primary_type']} | {null_pct} | {unique} | {avg_len} |")
    blank()

    h3("2.1 Field Details")
    for f in wiki_schema["fields"]:
        p(f"**`{f['field_name']}`** ({f['primary_type']})")
        p(f"- Non-null rate: {(1 - f['null_rate']) * 100:.1f}%")
        if f.get("string_stats"):
            ss = f["string_stats"]
            p(f"- String length: min={ss['min_length']}, max={ss['max_length']}, avg={ss['avg_length']}, median={ss['median_length']}")
        if f.get("format_hints"):
            fh = f["format_hints"]
            hints = [k.replace("contains_", "") for k, v in fh.items() if v]
            if hints:
                p(f"- Format: contains {', '.join(hints)}")
        if f.get("array_stats"):
            arr = f["array_stats"]
            p(f"- Array length: min={arr['min_length']}, max={arr['max_length']}, avg={arr['avg_length']}")
        if f.get("unique_values") and len(f["unique_values"]) <= 20:
            p(f"- Values: {', '.join(f['unique_values'][:20])}")
        if f.get("examples"):
            p(f"- Examples: `{f['examples'][0]}`")
        blank()

    # ---- Dialog Field Analysis ----
    h2("3. Dialog Data Field Analysis")
    blank()
    p("| Field | Type | Non-null Rate | Unique Count | Avg Length |")
    p("|-------|------|---------------|--------------|------------|")
    for f in dialog_schema["fields"]:
        null_pct = f"{(1 - f['null_rate']) * 100:.1f}%"
        unique = f.get("unique_count", "-")
        avg_len = f.get("string_stats", {}).get("avg_length", "-")
        p(f"| `{f['field_name']}` | {f['primary_type']} | {null_pct} | {unique} | {avg_len} |")
    blank()

    h3("3.1 Field Details")
    for f in dialog_schema["fields"]:
        p(f"**`{f['field_name']}`** ({f['primary_type']})")
        p(f"- Non-null rate: {(1 - f['null_rate']) * 100:.1f}%")
        if f.get("string_stats"):
            ss = f["string_stats"]
            p(f"- String length: min={ss['min_length']}, max={ss['max_length']}, avg={ss['avg_length']}")
        if f.get("array_stats"):
            arr = f["array_stats"]
            p(f"- Array length: min={arr['min_length']}, max={arr['max_length']}, avg={arr['avg_length']}")
        if f.get("unique_values") and len(f["unique_values"]) <= 20:
            p(f"- Values: {', '.join(f['unique_values'][:20])}")
        if f.get("examples"):
            p(f"- Examples: `{f['examples'][0]}`")
        blank()

    # ---- Entity Identification ----
    h2("4. Entity Identification Analysis")
    blank()

    h3("4.1 Entity ID Candidates")
    if entity_analysis["entity_id_candidates"]:
        for c in entity_analysis["entity_id_candidates"]:
            p(f"- **`{c['field']}`**: type={c['type']}, null_rate={c['null_rate']}, unique_count={c['unique_count']}")
    else:
        p("No strong entity ID candidates found.")
    blank()

    h3("4.2 Entity Name Candidates")
    if entity_analysis["entity_name_candidates"]:
        for c in entity_analysis["entity_name_candidates"]:
            p(f"- **`{c['field']}`**: null_rate={c['null_rate']}, unique_count={c['unique_count']}")
    else:
        p("No fields with 'name' or 'title' in their name found. Will need to identify naming fields from content.")
    blank()

    h3("4.3 Category / Tag Fields")
    if entity_analysis["category_candidates"]:
        for c in entity_analysis["category_candidates"]:
            if "values" in c and c["values"]:
                p(f"- **`{c['field']}`**: {c.get('unique_count', '?')} unique values — {', '.join(str(v) for v in c['values'][:10])}")
            else:
                p(f"- **`{c['field']}`**: type={c.get('type', 'string')}")
    else:
        p("No obvious category fields found.")
    blank()

    # ---- Relationship Clues ----
    h2("5. Relationship Clue Analysis")
    blank()

    p(f"- Cross-page references (wiki-links `[[...]]`): **{'Yes' if relationship_clues['cross_page_references'] else 'No'}**")
    if relationship_clues["link_patterns"]:
        p(f"- Fields containing wiki-links: {', '.join(f'`{f}`' for f in relationship_clues['link_patterns'])}")
    if relationship_clues["explicit_relationship_fields"]:
        p(f"- Explicit relationship fields: {', '.join(f'`{f}`' for f in relationship_clues['explicit_relationship_fields'])}")
    else:
        p("- No explicit relationship fields found. Relationships will need to be extracted from text content using NER + LLM.")
    blank()

    # ---- Text Content Analysis ----
    h2("6. Text Content Analysis")
    blank()

    h3("6.1 Primary Text Fields")
    if entity_analysis["text_content_candidates"]:
        for c in entity_analysis["text_content_candidates"]:
            p(f"- **`{c['field']}`**: avg_length={c['avg_length']}, max_length={c['max_length']}")
            fh = c.get("format_hints", {})
            formats = [k.replace("contains_", "") for k, v in fh.items() if v]
            if formats:
                p(f"  - Contains: {', '.join(formats)}")
    else:
        p("No long text fields identified (avg > 200 chars). May need to combine fields or look at array contents.")
    blank()

    h3("6.2 Text Format Summary")
    all_formats = set()
    for c in entity_analysis.get("text_content_candidates", []):
        for k, v in c.get("format_hints", {}).items():
            if v:
                all_formats.add(k.replace("contains_", ""))
    if all_formats:
        p(f"Detected formats in text fields: **{', '.join(sorted(all_formats))}**")
        if "wikitext" in all_formats:
            p("Wiki-text markup (`[[links]]`, `{{templates}}`) is present. The ETL Parse stage needs a wikitext parser.")
        if "html" in all_formats:
            p("HTML tags are present. The ETL Parse stage should strip or convert HTML.")
    else:
        p("No special formatting detected in text fields.")
    blank()

    # ---- ETL Recommendations ----
    h2("7. ETL Design Recommendations")
    blank()

    h3("7.1 Parse Stage")
    p("- Convert raw JSONL to standardised Parquet format.")
    if all_formats:
        if "wikitext" in all_formats:
            p("- **Required**: Wikitext parser to extract plain text and resolve `[[links]]`.")
        if "html" in all_formats:
            p("- **Required**: HTML stripper (e.g., BeautifulSoup) for clean text extraction.")
    p("- Map fields to a unified document schema (doc_id, title, content, source_url, categories, etc.).")
    blank()

    h3("7.2 Filter Stage (Sumeru)")
    p("Recommended filtering strategy for Sumeru-scoped Demo:")
    if entity_analysis["category_candidates"]:
        cat_fields = [c["field"] for c in entity_analysis["category_candidates"]]
        p(f"- **Category-based filtering**: Use fields `{', '.join(cat_fields)}` to match Sumeru categories.")
    p("- **Keyword-based filtering**: Scan title and content fields for Sumeru keywords.")
    p("- **Whitelist-based filtering**: Maintain an explicit entity whitelist for known Sumeru characters/locations.")
    blank()

    h3("7.3 Clean Stage")
    p("- Deduplicate records using content hash (SHA256).")
    p("- Entity disambiguation: Build alias mapping (e.g., 纳西妲 / 小吉祥草王 / 草神 → Nahida).")
    p("- Standardise text encoding and normalise whitespace.")
    blank()

    h3("7.4 Chunk Stage")
    if entity_analysis["text_content_candidates"]:
        max_len = max(c["max_length"] for c in entity_analysis["text_content_candidates"])
        avg_len = max(c["avg_length"] for c in entity_analysis["text_content_candidates"])
        p(f"- Longest text field has max_length={max_len}, avg_length={avg_len}.")
        p(f"- With chunk_size=512 tokens (~2048 chars), most documents will produce 1-{max(1, int(max_len / 2048))} chunks.")
    p("- Use recursive text splitter with section-aware boundaries.")
    p("- Preserve metadata (entity_id, section heading) in each chunk.")
    blank()

    h3("7.5 Extract Stage (Knowledge Graph)")
    p("- Use NER to identify entity mentions in text.")
    p("- Use LLM (Claude) with structured prompts to extract (subject, relation, object) triples.")
    p("- Map extracted entities to the canonical entity IDs via alias table.")
    p("- Target schema: 6 node types (Character, Location, Organisation, Event, Item, Concept).")
    p("- Target relations: CREATED, BORN_FROM, SUCCEEDED, MEMBER_OF, LOCATED_IN, CONFINED, etc.")
    blank()

    return "\n".join(lines)


# ======================================================================
# Main
# ======================================================================

def main():
    # Load data
    logger.info("Loading wiki sample from %s ...", WIKI_PATH)
    wiki_records = load_jsonl(WIKI_PATH)
    logger.info("Loaded %d wiki records.", len(wiki_records))

    logger.info("Loading dialog sample from %s ...", DIALOG_PATH)
    dialog_records = load_jsonl(DIALOG_PATH)
    logger.info("Loaded %d dialog records.", len(dialog_records))

    # Analyze schemas
    logger.info("Analyzing wiki data structure ...")
    wiki_schema = analyze_dataset(wiki_records, "Wiki (mrzjy/multimodal-genshin-impact)")

    logger.info("Analyzing dialog data structure ...")
    dialog_schema = analyze_dataset(dialog_records, "Dialog (mrzjy/GenshinDialog)")

    # Entity & relationship analysis (wiki only)
    logger.info("Analyzing entity identification potential ...")
    entity_analysis = analyze_entity_potential(wiki_schema, wiki_records)

    logger.info("Analyzing relationship clues ...")
    relationship_clues = analyze_relationship_clues(wiki_records)

    # Write schema JSONs
    os.makedirs(os.path.dirname(WIKI_SCHEMA_PATH), exist_ok=True)
    with open(WIKI_SCHEMA_PATH, "w", encoding="utf-8") as f:
        json.dump(wiki_schema, f, ensure_ascii=False, indent=2)
    logger.info("Wrote wiki schema to %s", WIKI_SCHEMA_PATH)

    with open(DIALOG_SCHEMA_PATH, "w", encoding="utf-8") as f:
        json.dump(dialog_schema, f, ensure_ascii=False, indent=2)
    logger.info("Wrote dialog schema to %s", DIALOG_SCHEMA_PATH)

    # Generate report
    logger.info("Generating analysis report ...")
    report = generate_report(
        wiki_schema, dialog_schema,
        wiki_records, dialog_records,
        entity_analysis, relationship_clues,
    )

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("Wrote analysis report to %s", REPORT_PATH)

    logger.info("Analysis complete.")


if __name__ == "__main__":
    main()
