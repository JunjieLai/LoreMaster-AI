"""
LoreMaster-AI - Full Wiki Data Collection

Downloads the complete genshin.jsonl (~22K records) from HuggingFace
dataset `mrzjy/multimodal-genshin-impact` via HTTP streaming.

Saves locally and optionally uploads to S3.
"""

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import boto3
import requests
from huggingface_hub import hf_hub_url
from tqdm import tqdm

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import HF_TOKEN, S3_BUCKET, AWS_REGION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/raw/wiki/genshin_wiki_full.jsonl")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "data/metadata/wiki_full_manifest.json")
DATE_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")
S3_KEY = f"raw/wiki/{DATE_TAG}/genshin_wiki_full.jsonl"


def stream_and_save():
    """Stream the full JSONL from HuggingFace and save to disk."""
    url = hf_hub_url(
        "mrzjy/multimodal-genshin-impact",
        "genshin.jsonl",
        repo_type="dataset",
    )
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    logger.info("Fetching %s ...", url)
    resp = requests.get(url, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    total_bytes = int(resp.headers.get("Content-Length", 0))
    logger.info("Content-Length: %s bytes (%.1f MB)", total_bytes, total_bytes / 1e6)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    record_count = 0
    bytes_written = 0
    sha256 = hashlib.sha256()
    category_set = set()

    start_time = time.time()

    with open(OUTPUT_PATH, "wb") as out_f:
        buf = b""
        pbar = tqdm(
            total=total_bytes,
            unit="B",
            unit_scale=True,
            desc="Downloading",
        )
        for chunk in resp.iter_content(chunk_size=131072):
            out_f.write(chunk)
            sha256.update(chunk)
            bytes_written += len(chunk)
            pbar.update(len(chunk))

            # Count records by counting newlines
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if line:
                    record_count += 1
                    # Sample categories from first 100 records
                    if record_count <= 100:
                        try:
                            rec = json.loads(line.decode("utf-8"))
                            for cat in rec.get("category", []):
                                category_set.add(cat)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass

        # Handle remaining buffer
        if buf.strip():
            record_count += 1

        pbar.close()

    elapsed = time.time() - start_time
    file_hash = sha256.hexdigest()

    logger.info(
        "Download complete: %d records, %d bytes (%.1f MB), %.1f seconds",
        record_count, bytes_written, bytes_written / 1e6, elapsed,
    )
    logger.info("SHA256: %s", file_hash)

    return {
        "record_count": record_count,
        "file_size_bytes": bytes_written,
        "sha256": file_hash,
        "elapsed_seconds": round(elapsed, 1),
        "sample_categories": sorted(category_set),
    }


def upload_to_s3():
    """Upload the downloaded file to S3."""
    if not S3_BUCKET:
        logger.warning("S3_BUCKET not configured, skipping upload.")
        return None

    file_size = os.path.getsize(OUTPUT_PATH)
    logger.info("Uploading to s3://%s/%s (%.1f MB) ...", S3_BUCKET, S3_KEY, file_size / 1e6)

    s3 = boto3.client("s3", region_name=AWS_REGION)

    # Use multipart upload for large files
    from boto3.s3.transfer import TransferConfig
    config = TransferConfig(
        multipart_threshold=50 * 1024 * 1024,  # 50MB
        max_concurrency=4,
        multipart_chunksize=50 * 1024 * 1024,
    )

    s3.upload_file(
        OUTPUT_PATH,
        S3_BUCKET,
        S3_KEY,
        Config=config,
        Callback=ProgressCallback(file_size),
    )

    logger.info("Upload complete: s3://%s/%s", S3_BUCKET, S3_KEY)
    return f"s3://{S3_BUCKET}/{S3_KEY}"


class ProgressCallback:
    def __init__(self, total):
        self._total = total
        self._seen = 0
        self._pbar = tqdm(total=total, unit="B", unit_scale=True, desc="Uploading to S3")

    def __call__(self, bytes_amount):
        self._seen += bytes_amount
        self._pbar.update(bytes_amount)
        if self._seen >= self._total:
            self._pbar.close()


def write_manifest(download_info: dict, s3_uri):
    """Write collection manifest."""
    manifest = {
        "source": "mrzjy/multimodal-genshin-impact",
        "source_file": "genshin.jsonl",
        "platform": "HuggingFace",
        "collection_time": datetime.now(timezone.utc).isoformat(),
        "date_tag": DATE_TAG,
        "local_path": "data/raw/wiki/genshin_wiki_full.jsonl",
        "s3_uri": s3_uri,
        "s3_key": S3_KEY if s3_uri else None,
        "record_count": download_info["record_count"],
        "file_size_bytes": download_info["file_size_bytes"],
        "file_size_mb": round(download_info["file_size_bytes"] / 1e6, 1),
        "sha256": download_info["sha256"],
        "download_seconds": download_info["elapsed_seconds"],
        "data_fields": ["url", "sections", "category", "markdown"],
        "sample_categories_first_100": download_info["sample_categories"],
    }

    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info("Manifest written to %s", MANIFEST_PATH)
    return manifest


def main():
    logger.info("=" * 60)
    logger.info("LoreMaster-AI Full Wiki Data Collection")
    logger.info("=" * 60)

    # Step 1: Download
    logger.info("[1/3] Downloading full dataset ...")
    download_info = stream_and_save()

    # Step 2: Upload to S3
    logger.info("[2/3] Uploading to S3 ...")
    s3_uri = upload_to_s3()

    # Step 3: Write manifest
    logger.info("[3/3] Writing manifest ...")
    manifest = write_manifest(download_info, s3_uri)

    logger.info("=" * 60)
    logger.info("Collection complete!")
    logger.info("  Records: %d", manifest["record_count"])
    logger.info("  Size: %.1f MB", manifest["file_size_mb"])
    logger.info("  Local: %s", manifest["local_path"])
    logger.info("  S3: %s", manifest["s3_uri"] or "not uploaded")
    logger.info("  SHA256: %s", manifest["sha256"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
