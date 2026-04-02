"""
LoreMaster-AI Configuration Settings

This module loads environment variables and provides
centralized configuration for the entire project.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================
# AWS Settings
# ============================================
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET")

# ============================================
# DynamoDB Tables
# ============================================
DYNAMODB_ENTITY_TABLE = os.getenv("DYNAMODB_ENTITY_TABLE", "loremaster-entity-metadata")
DYNAMODB_VERSION_TABLE = os.getenv("DYNAMODB_VERSION_TABLE", "loremaster-data-versions")
DYNAMODB_ALIAS_TABLE = os.getenv("DYNAMODB_ALIAS_TABLE", "loremaster-alias-mapping")

# ============================================
# Neo4j Settings
# ============================================
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# ============================================
# Pinecone Settings
# ============================================
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "loremaster-index")
PINECONE_HOST = os.getenv("PINECONE_HOST")

# ============================================
# HuggingFace Settings
# ============================================
HF_TOKEN = os.getenv("HF_TOKEN")

# ============================================
# Anthropic Settings
# ============================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ============================================
# OpenAI Settings (for embeddings)
# ============================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ============================================
# S3 Path Prefixes
# ============================================
S3_RAW_PREFIX = "raw/"
S3_PROCESSED_PREFIX = "processed/"
S3_METADATA_PREFIX = "metadata/"
S3_CONFIG_PREFIX = "config/"

# ============================================
# Demo Settings
# ============================================
DEMO_MODE = True
DEMO_REGION = "Sumeru"

# ============================================
# Processing Settings
# ============================================
CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50  # tokens
EMBEDDING_DIMENSION = 1536


def validate_config():
    """Validate that required configuration is set."""
    required = {
        "S3_BUCKET": S3_BUCKET,
        "NEO4J_URI": NEO4J_URI,
        "NEO4J_PASSWORD": NEO4J_PASSWORD,
        "PINECONE_API_KEY": PINECONE_API_KEY,
    }
    
    missing = [key for key, value in required.items() if not value]
    
    if missing:
        print(f"Warning: Missing required configuration: {', '.join(missing)}")
        return False
    return True


if __name__ == "__main__":
    # Print current configuration (for debugging)
    print("Current Configuration:")
    print(f"  AWS_REGION: {AWS_REGION}")
    print(f"  S3_BUCKET: {S3_BUCKET}")
    print(f"  NEO4J_URI: {NEO4J_URI[:30] + '...' if NEO4J_URI else 'Not set'}")
    print(f"  PINECONE_INDEX: {PINECONE_INDEX}")
    print(f"  DEMO_MODE: {DEMO_MODE}")
    print()
    validate_config()
