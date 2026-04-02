"""
LoreMaster-AI Infrastructure Verification Script

This script tests all external service connections:
- AWS (IAM, S3, DynamoDB)
- Neo4j AuraDB
- Pinecone
- HuggingFace
- Anthropic

Usage:
    python tests/test_setup.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AWS_REGION, S3_BUCKET,
    DYNAMODB_ENTITY_TABLE, DYNAMODB_VERSION_TABLE, DYNAMODB_ALIAS_TABLE,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    PINECONE_API_KEY, PINECONE_INDEX,
    HF_TOKEN, ANTHROPIC_API_KEY
)


def test_aws_iam():
    """Test AWS IAM credentials."""
    print("Testing AWS IAM...")
    try:
        import boto3
        sts = boto3.client('sts', region_name=AWS_REGION)
        identity = sts.get_caller_identity()
        print(f"  ✓ Account: {identity['Account']}")
        print(f"  ✓ User ARN: {identity['Arn']}")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_s3():
    """Test S3 bucket access."""
    print("\nTesting S3...")
    
    if not S3_BUCKET:
        print("  ✗ S3_BUCKET not set in .env")
        return False
    
    try:
        import boto3
        s3 = boto3.client('s3', region_name=AWS_REGION)
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix='', Delimiter='/')
        folders = [p['Prefix'] for p in response.get('CommonPrefixes', [])]
        
        expected = ['config/', 'metadata/', 'processed/', 'raw/']
        all_found = True
        
        for folder in expected:
            if folder in folders:
                print(f"  ✓ {folder} exists")
            else:
                print(f"  ✗ {folder} NOT FOUND")
                all_found = False
        
        return all_found
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_dynamodb():
    """Test DynamoDB tables."""
    print("\nTesting DynamoDB...")
    
    try:
        import boto3
        dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)
        tables = [DYNAMODB_ENTITY_TABLE, DYNAMODB_VERSION_TABLE, DYNAMODB_ALIAS_TABLE]
        
        all_ok = True
        for table in tables:
            try:
                response = dynamodb.describe_table(TableName=table)
                status = response['Table']['TableStatus']
                print(f"  ✓ {table}: {status}")
            except Exception as e:
                print(f"  ✗ {table}: {e}")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_neo4j():
    """Test Neo4j AuraDB connection."""
    print("\nTesting Neo4j...")
    
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("  ✗ Neo4j credentials not set in .env")
        return False
    
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            result = session.run("RETURN 'Connected!' AS status")
            record = result.single()
            print(f"  ✓ {record['status']}")
        
        driver.close()
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_pinecone():
    """Test Pinecone connection."""
    print("\nTesting Pinecone...")
    
    if not PINECONE_API_KEY:
        print("  ✗ PINECONE_API_KEY not set in .env")
        return False
    
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        indexes = pc.list_indexes()
        index_names = [idx.name for idx in indexes]
        
        if PINECONE_INDEX in index_names:
            print(f"  ✓ Index '{PINECONE_INDEX}' exists")
            
            index = pc.Index(PINECONE_INDEX)
            stats = index.describe_index_stats()
            print(f"  ✓ Dimension: {stats.dimension}")
            print(f"  ✓ Total vectors: {stats.total_vector_count}")
            return True
        else:
            print(f"  ✗ Index '{PINECONE_INDEX}' not found")
            print(f"    Available indexes: {index_names}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_huggingface():
    """Test HuggingFace token."""
    print("\nTesting HuggingFace...")
    
    if not HF_TOKEN:
        print("  ⚠ HF_TOKEN not set (optional, needed for private datasets)")
        return True  # Optional, so return True
    
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=HF_TOKEN)
        user_info = api.whoami()
        print(f"  ✓ Logged in as: {user_info['name']}")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_anthropic():
    """Test Anthropic API key."""
    print("\nTesting Anthropic...")
    
    if not ANTHROPIC_API_KEY:
        print("  ⚠ ANTHROPIC_API_KEY not set (optional, needed for LLM features)")
        return True  # Optional, so return True
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        # Send minimal request to test
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        print(f"  ✓ API connected, model: {message.model}")
        return True
    except anthropic.AuthenticationError:
        print("  ✗ Invalid API key")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("LoreMaster-AI Infrastructure Verification")
    print("=" * 60)
    
    print(f"\nConfiguration:")
    print(f"  AWS Region:      {AWS_REGION}")
    print(f"  S3 Bucket:       {S3_BUCKET or 'Not set'}")
    print(f"  Neo4j URI:       {(NEO4J_URI[:35] + '...') if NEO4J_URI else 'Not set'}")
    print(f"  Pinecone Index:  {PINECONE_INDEX}")
    print(f"  HF Token:        {'Set' if HF_TOKEN else 'Not set'}")
    print(f"  Anthropic Key:   {'Set' if ANTHROPIC_API_KEY else 'Not set'}")
    print()
    
    results = {}
    results['AWS IAM'] = test_aws_iam()
    results['S3'] = test_s3()
    results['DynamoDB'] = test_dynamodb()
    results['Neo4j'] = test_neo4j()
    results['Pinecone'] = test_pinecone()
    results['HuggingFace'] = test_huggingface()
    results['Anthropic'] = test_anthropic()
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    
    all_passed = True
    for service, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {service}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All services configured correctly!")
        print("\nNext step: Run data collection script")
        return 0
    else:
        print("⚠️  Some services need attention.")
        print("Check the errors above and update your .env file.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
