"""
LoreMaster-AI - Retrieval Demo

Demonstrates the full retrieval pipeline:
1. Text Loader (P3) - Full text enrichment
2. Query Processor - Entity extraction, alias resolution, query classification
3. Hybrid Retriever - Vector + Graph search
"""

import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from src.agent.text_loader import TextLoader
from src.agent.query_processor import QueryProcessor
from src.agent.retriever import HybridRetriever


def demo_text_loader():
    """Demo: Text Loader (P3)"""
    print("\n" + "=" * 70)
    print("STEP 1: TEXT LOADER (P3)")
    print("=" * 70)

    loader = TextLoader()
    stats = loader.get_stats()

    print(f"\nLoaded {stats['total_chunks']} chunks into memory")
    print(f"  Avg text length: {stats['avg_text_length']} chars")
    print(f"  Max text length: {stats['max_text_length']} chars")

    # Show comparison: truncated vs full
    print("\n--- P3 Benefit: Truncated vs Full Text ---")

    # Simulate Pinecone result (truncated at 1000 chars)
    sample_id = list(loader.chunk_index.keys())[0]
    full_data = loader.get_chunk_metadata(sample_id)

    print(f"\nChunk ID: {sample_id}")
    print(f"Title: {full_data['title']}")
    print(f"\nPinecone metadata (truncated to 1000 chars):")
    print(f"  Length: 1000 chars")
    print(f"  Preview: {full_data['text'][:200]}...")

    print(f"\nFull text (via P3 TextLoader):")
    print(f"  Length: {len(full_data['text'])} chars")
    print(f"  Complete: YES")

    return loader


def demo_query_processor():
    """Demo: Query Processor"""
    print("\n" + "=" * 70)
    print("STEP 2: QUERY PROCESSOR")
    print("=" * 70)

    processor = QueryProcessor()

    test_queries = [
        ("Who is Nahida?", "English factual"),
        ("What is the relationship between Scaramouche and Raiden Shogun?", "English relationship"),
        ("散兵和纳西妲有什么关系？", "Chinese relationship"),
        ("Why did Wanderer erase himself from Irminsul?", "Multi-hop reasoning"),
    ]

    for query, desc in test_queries:
        print(f"\n--- Query: {query} ---")
        print(f"Description: {desc}")

        result = processor.process(query)

        print(f"\n  [Entity Extraction]")
        print(f"    Raw entities: {result['entities']}")

        print(f"\n  [Alias Resolution]")
        for orig, canonical in result['resolved_entities'].items():
            if orig != canonical:
                print(f"    '{orig}' -> '{canonical}' (alias resolved)")
            else:
                print(f"    '{orig}' (canonical)")

        print(f"\n  [Query Classification]")
        print(f"    Type: {result['query_type']}")

        print(f"\n  [Embedding]")
        print(f"    Dimension: {len(result['embedding'])}")
        print(f"    Sample: [{result['embedding'][0]:.4f}, {result['embedding'][1]:.4f}, ...]")

    return processor


def demo_hybrid_retriever(processor):
    """Demo: Hybrid Retriever"""
    print("\n" + "=" * 70)
    print("STEP 3: HYBRID RETRIEVER")
    print("=" * 70)

    retriever = HybridRetriever()

    # Test relationship query
    query = "What is the relationship between Scaramouche and Raiden Shogun?"
    print(f"\nQuery: {query}")

    # Process
    processed = processor.process(query)

    # Retrieve
    results = retriever.retrieve(
        query=query,
        embedding=processed["embedding"],
        entities=processed["canonical_entities"],
        query_type=processed["query_type"],
        vector_top_k=5,
    )

    # Show vector results
    print(f"\n--- Vector Search Results (Pinecone) ---")
    print(f"Found: {len(results['vector_results'])} chunks")

    for i, r in enumerate(results['vector_results'][:3]):
        print(f"\n  [{i+1}] Score: {r['score']:.3f}")
        print(f"      Title: {r['title']}")
        print(f"      Section: {r['section_title']}")
        print(f"      Full text length: {r['text_length']} chars (P3 enriched)")
        print(f"      Preview: {r['full_text'][:150]}...")

    # Show graph results
    print(f"\n--- Graph Search Results (Neo4j) ---")

    for entity_result in results['graph_results']:
        ent = entity_result["entity"]
        rels = entity_result["relationships"]
        print(f"\n  Entity: {ent['name']} ({ent['type']})")
        print(f"  Description: {(ent['description'] or 'N/A')[:100]}...")
        print(f"  Relationships ({len(rels)} found):")

        for rel in rels[:5]:
            if rel["direction"] == "outgoing":
                print(f"    -> [{rel['relation']}] -> {rel['target']} ({rel['target_type']})")
            else:
                print(f"    <- [{rel['relation']}] <- {rel['source']} ({rel['source_type']})")

    # Show path results
    if results["path_results"]:
        print(f"\n--- Path Discovery ---")
        path = results["path_results"]

        if path["found"]:
            print(f"  Path found! Length: {path['path_length']} hops")
            print(f"  Connection chain:")
            for i, step in enumerate(path["path_steps"]):
                print(f"    {i+1}. {step}")
        else:
            print(f"  No direct path found between entities")

    retriever.close()
    return results


def main():
    print("=" * 70)
    print("LOREMASTER-AI RETRIEVAL PIPELINE DEMO")
    print("=" * 70)

    # Step 1: Text Loader
    loader = demo_text_loader()

    # Step 2: Query Processor
    processor = demo_query_processor()

    # Step 3: Hybrid Retriever
    results = demo_hybrid_retriever(processor)

    # Summary
    print("\n" + "=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)
    print(f"""
Components implemented:
  1. TextLoader (P3): {loader.get_stats()['total_chunks']} chunks indexed
  2. QueryProcessor: Entity extraction + Alias resolution + Classification
  3. HybridRetriever: Vector search + Graph search + Path discovery

Ready for:
  - Step 4: Context Assembler
  - Step 5: Answer Generator
  - Step 6: Full Pipeline Integration
""")


if __name__ == "__main__":
    main()
