"""
LoreMaster-AI ETL - Step 6: Upload to S3

Uploads all processed ETL outputs to S3 with proper organization.
Generates a manifest documenting the upload.
"""

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import S3_BUCKET, AWS_REGION

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATE_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")

# Files to upload with their S3 destinations
UPLOAD_MANIFEST = [
    # Processed documents
    {
        "local": "data/processed/documents/wiki_parsed.jsonl",
        "s3_key": f"processed/documents/{DATE_TAG}/wiki_parsed.jsonl",
        "description": "Full parsed wiki documents (22K)",
    },
    {
        "local": "data/processed/documents/wiki_sumeru.jsonl",
        "s3_key": f"processed/documents/{DATE_TAG}/wiki_sumeru.jsonl",
        "description": "Sumeru-filtered documents",
    },
    {
        "local": "data/processed/documents/wiki_clean.jsonl",
        "s3_key": f"processed/documents/{DATE_TAG}/wiki_clean.jsonl",
        "description": "Cleaned Sumeru documents",
    },
    # Chunks
    {
        "local": "data/processed/chunks/wiki_chunks.jsonl",
        "s3_key": f"processed/chunks/{DATE_TAG}/wiki_chunks.jsonl",
        "description": "Retrieval-ready text chunks",
    },
    # Metadata
    {
        "local": "data/metadata/wiki_full_manifest.json",
        "s3_key": f"metadata/{DATE_TAG}/wiki_full_manifest.json",
        "description": "Full dataset collection manifest",
    },
    {
        "local": "data/metadata/wiki_schema.json",
        "s3_key": f"metadata/{DATE_TAG}/wiki_schema.json",
        "description": "Wiki data schema analysis",
    },
]


def compute_sha256(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(131072), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def count_lines(filepath):
    """Count lines in a JSONL file."""
    if not filepath.endswith(".jsonl"):
        return None
    count = 0
    with open(filepath, "rb") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def upload_file(s3_client, local_path, s3_key):
    """Upload a single file to S3."""
    full_path = os.path.join(PROJECT_ROOT, local_path)
    if not os.path.exists(full_path):
        logger.warning("File not found, skipping: %s", local_path)
        return None

    file_size = os.path.getsize(full_path)
    logger.info("Uploading %s (%.2f MB) -> s3://%s/%s",
                local_path, file_size / 1e6, S3_BUCKET, s3_key)

    try:
        s3_client.upload_file(full_path, S3_BUCKET, s3_key)
        sha256 = compute_sha256(full_path)
        line_count = count_lines(full_path)

        return {
            "local_path": local_path,
            "s3_uri": f"s3://{S3_BUCKET}/{s3_key}",
            "s3_key": s3_key,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / 1e6, 2),
            "sha256": sha256,
            "record_count": line_count,
            "upload_time": datetime.now(timezone.utc).isoformat(),
        }
    except ClientError as e:
        logger.error("Upload failed for %s: %s", local_path, e)
        return None


def main():
    if not S3_BUCKET:
        logger.error("S3_BUCKET not configured. Set it in .env file.")
        return

    logger.info("=" * 60)
    logger.info("LoreMaster-AI ETL Step 6: Upload to S3")
    logger.info("=" * 60)
    logger.info("Bucket: %s", S3_BUCKET)
    logger.info("Region: %s", AWS_REGION)
    logger.info("Date tag: %s", DATE_TAG)

    s3 = boto3.client("s3", region_name=AWS_REGION)

    results = []
    total_size = 0
    success_count = 0

    for item in UPLOAD_MANIFEST:
        result = upload_file(s3, item["local"], item["s3_key"])
        if result:
            result["description"] = item["description"]
            results.append(result)
            total_size += result["file_size_bytes"]
            success_count += 1

    # Write upload manifest
    manifest = {
        "upload_time": datetime.now(timezone.utc).isoformat(),
        "date_tag": DATE_TAG,
        "s3_bucket": S3_BUCKET,
        "aws_region": AWS_REGION,
        "files_uploaded": success_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1e6, 2),
        "files": results,
    }

    manifest_path = os.path.join(PROJECT_ROOT, "data/metadata/s3_upload_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Also upload the manifest itself
    manifest_s3_key = f"metadata/{DATE_TAG}/s3_upload_manifest.json"
    s3.upload_file(manifest_path, S3_BUCKET, manifest_s3_key)

    logger.info("=" * 60)
    logger.info("Upload complete!")
    logger.info("  Files: %d", success_count)
    logger.info("  Total size: %.2f MB", total_size / 1e6)
    logger.info("  Manifest: %s", manifest_path)
    logger.info("  S3 manifest: s3://%s/%s", S3_BUCKET, manifest_s3_key)
    logger.info("=" * 60)

    # Print summary table
    logger.info("\nUpload Summary:")
    logger.info("-" * 80)
    for r in results:
        records = f"{r['record_count']:,} records" if r['record_count'] else ""
        logger.info("  %-40s %8.2f MB  %s", r['s3_key'].split('/')[-1], r['file_size_mb'], records)

    return manifest


if __name__ == "__main__":
    main()
