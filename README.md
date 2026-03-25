# Loremaster AI — Project Overview

---

## 1. Background

### Domain Context

*Genshin Impact* is an open-world RPG developed by miHoYo. Its lore is exceptionally rich: 7 nations (Mondstadt, Liyue, Inazuma, Sumeru, Fontaine, Natlan, Snezhnaya), each with its own mythology, political structures, historical events, and hundreds of NPCs — drawing from real-world cultural archetypes (Sumeru → South Asia / Middle East). The game's wiki spans tens of thousands of articles.

**The core problem**: When a player asks "What is the relationship between Nahida and the Scarlet King?", current LLMs exhibit two failure modes:
1. **Hallucination** — the model fabricates plausible-sounding but incorrect details from training memory
2. **Knowledge cutoff** — Genshin Impact content is sparse in pre-training data, especially Sumeru (post-2022 content)

**Solution**: Build a Sumeru-focused **dedicated knowledge base** and combine **vector retrieval + knowledge graph** in a hybrid GraphRAG (Retrieval-Augmented Generation) architecture, grounding LLM generation in verified facts to eliminate hallucination at the source.

---

## 2. Theoretical Foundations

### 2.1 RAG (Retrieval-Augmented Generation)

RAG = Retriever + Generator. The core idea: retrieve external knowledge as context injected into the LLM prompt, avoiding reliance on parametric memory.

```
Query → Retrieve(DB) → Context → LLM → Answer
```

This project extends the standard RAG into **GraphRAG**: layering knowledge graph path retrieval on top of vector search to enable multi-hop reasoning.

### 2.2 Knowledge Graph

Entities and relations are stored as a directed graph:
```
(Nahida) -[IS_ARCHON_OF]→ (Sumeru)
(Scaramouche) -[ENEMY_OF]→ (Fatui)
```
This supports precise relationship queries ("What is the connection between A and B?") and path discovery ("What links X to Y?"), compensating for vector search's inability to handle structured relational queries.

### 2.3 Hybrid Retrieval

Semantic vector retrieval and structural graph path retrieval are combined to leverage their complementary strengths:
- **Vector search**: excels at fuzzy semantic matching and open-domain recall
- **Graph search**: excels at precise entity relations and multi-hop reasoning
- **Hybrid**: addresses complex questions that require both

### 2.4 LLM-as-Judge Evaluation

A stronger LLM (Claude Opus 4.6) acts as an automated evaluator, comparing candidate answers against gold-standard references — replacing expensive human annotation. Two quantitative metrics:
- **Fact Score**: fraction of gold key-facts covered by the answer
- **Trap Score**: fraction of known hallucination traps not triggered by the answer

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **LLM** | Claude Sonnet 4.6 / Claude Opus 4.6 | Entity extraction, answer generation, evaluation judging |
| **LLM** | GPT-4o / GPT-4o-mini | Ablation study control models |
| **Vector DB** | Pinecone | Semantic retrieval over 4,059 documents |
| **Graph DB** | Neo4j | Knowledge graph storage and Cypher queries |
| **Key-value DB** | AWS DynamoDB | Entity metadata + alias resolution table |
| **Object storage** | AWS S3 | Data asset archiving |
| **Embedding model** | OpenAI text-embedding-3-small (1536-dim) | Document and query vectorization |
| **Backend** | FastAPI | REST API server |
| **Frontend** | React 18 + TypeScript + TailwindCSS | Chat interface |
| **Graph viz** | react-force-graph-2d | Force-directed knowledge graph rendering |
| **Animation** | Framer Motion | UI transitions |
| **Token counting** | tiktoken (cl100k_base) | Precise context budget management |
| **Runtime** | Python 3.9 | Backend + ETL + ablation study |

---

## 4. Project Structure

```
loremaster-ai/
├── backend/
│   └── main.py              # FastAPI server — 5 REST endpoints
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # App shell with resizable panels
│   │   ├── components/
│   │   │   ├── ChatMessage.tsx        # Message rendering + Markdown
│   │   │   ├── ConstellationGraph.tsx # Relationship path visualization
│   │   │   ├── GraphExplorer.tsx      # Full-screen knowledge graph browser
│   │   │   ├── SourceCard.tsx         # Source document card
│   │   │   └── ChatInput.tsx          # Input textarea
│   │   ├── hooks/
│   │   │   ├── useGraphData.ts        # Graph data fetching
│   │   │   └── useThumbnail.ts        # Entity thumbnail fetching
│   │   └── types/index.ts            # TypeScript type definitions
├── src/
│   ├── agent/
│   │   ├── pipeline.py          # Main RAG pipeline
│   │   ├── query_processor.py   # Query processing (extraction / classification / expansion)
│   │   ├── retriever.py         # Hybrid retriever
│   │   ├── context_assembler.py # Context assembly (token budget + reranking)
│   │   ├── answer_generator.py  # Answer generation
│   │   ├── ablation_config.py   # 8 ablation study configurations
│   │   ├── ablation_pipeline.py # Ablation-specific pipeline wrapper
│   │   ├── adaptive_depth.py    # Adaptive graph traversal depth
│   │   └── text_loader.py       # In-memory full-text chunk index
│   ├── etl/
│   │   ├── collect_wiki_full.py # Raw data collection
│   │   ├── parse.py             # Structured parsing
│   │   ├── filter_sumeru.py     # Sumeru-region filtering
│   │   ├── clean.py             # Deduplication and cleaning
│   │   ├── chunk.py             # Section-aware chunking
│   │   └── build_alias_mapping.py # Alias table construction
│   ├── embed/
│   │   └── embed.py             # Vector embedding
│   ├── graph/
│   │   ├── extract.py           # Triple extraction (Claude)
│   │   ├── load.py              # Load into Pinecone / Neo4j / DynamoDB
│   │   ├── reclassify_relations.py
│   │   └── migrate_neo4j_relations.py
│   └── ablation/
│       ├── run_oracle.py        # Phase 1: Generate gold references
│       ├── run_experiment.py    # Phase 2: Run 8 configurations
│       ├── run_eval.py          # Phase 3: Opus evaluation scoring
│       ├── fetch_docs.py        # 3-layer document retrieval
│       ├── generate_gold.py     # Gold standard generation
│       ├── prompts.py           # Prompt library
│       └── repair_gold.py       # JSON repair utility
├── config/
│   └── settings.py             # Centralized environment variable loading
├── data/                        # All data assets (see Section 6)
├── requirements.txt
└── .env.example
```

---

## 5. ETL Pipeline — Step by Step

A complete 9-step data pipeline transforming raw wiki content into a searchable knowledge base:

### Step 1 — Raw Data Collection
**Script**: `src/etl/collect_wiki_full.py`

Streams the full dataset from HuggingFace `mrzjy/multimodal-genshin-impact`:
- Raw scale: 22,162 wiki pages
- Output: `data/raw/wiki/genshin_wiki_full.jsonl`
- Metadata manifest: `data/metadata/wiki_schema.json`

### Step 2 — Structured Parsing
**Script**: `src/etl/parse.py`

Converts raw JSON into a standardized schema:
- **Entity type inference**: identified from category labels (PlayableCharacter, NPC, Location, Organization, Event, Weapon, Artifact, Boss, ...)
- **Region detection**: classifies into Sumeru / Liyue / Mondstadt / Inazuma / Fontaine
- **Content cleaning**: removes Markdown template tags; computes content hash for deduplication
- Output: `data/processed/documents/wiki_parsed.jsonl`

### Step 3 — Sumeru Filtering
**Script**: `src/etl/filter_sumeru.py`

Multi-strategy filtering to retain only Sumeru-relevant content:
- Keyword matching (Nahida, Akademiya, Dendro Archon, Alhaitham, rainforest, ...)
- Category-tag detection
- Title and body double-check
- Output: `data/processed/documents/wiki_sumeru.jsonl`

### Step 4 — Cleaning and Deduplication
**Script**: `src/etl/clean.py`

High-quality cleaning pass:
- **Content-hash deduplication**: identical content is stored only once
- **Alias normalization**: ~100 mappings (Scaramouche → Wanderer, etc.)
- **Boilerplate removal**: drops uninformative sections (Info Card, Navigation, Gallery, version history)
- **Whitespace normalization**: unifies line endings, strips redundant spaces
- Final output: **4,059 documents** → `data/processed/documents/wiki_clean.jsonl`

### Step 5 — Section-Aware Chunking
**Script**: `src/etl/chunk.py`

Semantics-preserving chunking:
- Config: 512 tokens, 50-token overlap
- **Section boundary priority**: splits at section headings first
- **Paragraph fallback**: splits at paragraph boundaries if section is too long
- **Sentence fallback**: final fallback to sentence boundaries
- Each chunk carries full metadata: doc_id, title, section_title, entity_type, regions
- Output: `data/processed/chunks/wiki_chunks.jsonl`

### Step 6 — Alias Mapping Construction
**Script**: `src/etl/build_alias_mapping.py`

Builds the entity alias resolution table and writes it to DynamoDB:
- Supports bidirectional Chinese-English alias lookup
- At query time, automatically resolves "Wanderer", "流浪者", "Kunikuzushi" → canonical entity name

### Step 7 — Vector Embedding
**Script**: `src/embed/embed.py`

Batch-generates semantic vectors:
- Model: OpenAI `text-embedding-3-small` (1,536 dims)
- Batch size: 100 chunks/request, with exponential-backoff retries
- Checkpoint/resume support for interrupted runs
- Total cost: ~$0.50
- Output: `data/processed/embeddings/wiki_embeddings.jsonl`

### Step 8 — Knowledge Graph Triple Extraction
**Script**: `src/graph/extract.py`

Uses Claude Sonnet 4 to extract structured triples from documents:
- Prioritizes ~150 high-importance entity documents; selects others within budget
- Total budget: ~$14
- Triple format: `{"subject": "Nahida", "relation": "IS_ARCHON_OF", "object": "Sumeru", "evidence": "..."}`
- Output: `data/processed/triples/entities.jsonl` + `triples.jsonl`

### Step 9 — Multi-Target Loading
**Script**: `src/graph/load.py`

Loads all data into three databases in one run:
1. **Pinecone**: batch-upserts all 4,059 vectors with metadata
2. **Neo4j**: `CREATE` Entity nodes + `MERGE` relationship edges (Cypher batch operations)
3. **DynamoDB**: entity metadata table + alias mapping table

---

## 6. Data Assets

```
data/
├── raw/
│   └── wiki/
│       ├── genshin_wiki_full.jsonl    # 22,162 raw wiki entries
│       └── sample.jsonl              # Small development sample
│
├── processed/
│   ├── documents/
│   │   ├── wiki_clean.jsonl          # ★ 4,059 final documents
│   │   ├── wiki_sumeru.jsonl         # After Sumeru filter (Step 3)
│   │   └── wiki_parsed.jsonl         # After parsing (Step 2)
│   ├── chunks/
│   │   └── wiki_chunks.jsonl         # ★ After chunking (Step 5)
│   ├── embeddings/
│   │   └── wiki_embeddings.jsonl     # ★ Vectors — 4,059 × 1,536 dims
│   └── triples/
│       ├── entities.jsonl            # ★ ~1,000+ entities
│       ├── triples.jsonl             # ★ ~2,000+ relationship triples
│       └── extract_raw.jsonl         # Raw LLM extraction output
│
├── metadata/
│   ├── wiki_schema.json              # Field schema definition
│   ├── embedding_manifest.json       # Embedding run metadata
│   ├── extraction_manifest.json      # Triple extraction statistics
│   └── load_manifest.json            # Database load statistics
│
└── ablation/
    ├── questions.jsonl               # ★ 50 test questions (T1×10 / T2×15 / T3×13 / T4×12)
    ├── gold_references.jsonl         # ★ 50 gold reference answers (Phase 1)
    ├── oracle_checkpoint.json        # Oracle run checkpoint
    ├── runs/                         # Phase 2: 400 model answers
    │   ├── S4-LLM.jsonl  S4-VEC.jsonl  S4-GRF.jsonl  S4-HYB.jsonl
    │   └── G4-LLM.jsonl  G4-VEC.jsonl  G4-GRF.jsonl  G4-HYB.jsonl
    └── eval/                         # Phase 3: evaluation results
        ├── S4-LLM.jsonl  ...  G4-HYB.jsonl  (per-question scores)
        └── summary.csv               # ★ Aggregate score table
```

**Key numbers**:
- Raw documents: 22,162 → after filtering and cleaning: 4,059 (18.3% retention)
- Neo4j entity nodes: ~1,000+; relationship edges: ~2,000+
- Pinecone index: 4,059 vectors, 1,536 dims
- Test set: 50 questions × 8 configurations = 400 model answers

---

## 7. Agent Design

### Overall Architecture

```
User Query
    ↓
QueryProcessor
    ├── Entity extraction & alias resolution
    ├── Query type classification (FACTUAL / RELATIONSHIP / MULTI_HOP / LIST / COMPARISON)
    └── Query expansion (paraphrase generation)
    ↓
HybridRetriever
    ├── [VEC] Pinecone semantic search
    ├── [GRF] Neo4j graph path query
    └── [HYB] Merged results + graph reranking
    ↓
ContextAssembler
    ├── Token budget allocation (6,000 total: 1,500 graph + 4,500 text)
    ├── Document reranking (entity relevance scoring)
    └── Prompt formatting
    ↓
AnswerGenerator
    └── Claude Sonnet 4.6 → cited, structured answer
```

### 7.1 QueryProcessor

| Feature | Implementation |
|---------|---------------|
| **Entity extraction** | Regex + Claude Haiku to detect character / location / organization names |
| **Alias resolution** | DynamoDB lookup — "Wanderer" / "流浪者" / "Kunikuzushi" → canonical name |
| **Query classification** | Haiku semantic classification (5 types) — drives retrieval strategy |
| **Query expansion** | Generates 2–3 paraphrased variants to broaden recall |
| **Embedding cache** | LRU cache — skips API call for repeated queries |

### 7.2 HybridRetriever

**Vector retrieval path**:
- Pinecone top_k semantic search (default k=10)
- Full-text chunk index supplement (`text_loader.py`)

**Graph retrieval path**:
- Cypher queries for direct entity relationships (depth 1–2)
- Shortest-path discovery between entity pairs
- Graph ranking by evidence quality, relation type, and target relevance

**Adaptive depth control** (`adaptive_depth.py`):
- FACTUAL queries: depth 1
- RELATIONSHIP queries: depth 2
- MULTI_HOP queries: depth 4
- Keyword triggers: "indirect", "chain", "connection", etc. → auto-increase depth

### 7.3 ContextAssembler

- **Token budget**: 1,500 tokens for graph triples + 4,500 tokens for text passages
- **Precise counting**: tiktoken cl100k_base prevents silent truncation
- **Reranking**: entity mention frequency × section relevance score
- **Output format**:
  ```
  [Graph Relations]
  Nahida IS_ARCHON_OF Sumeru
  Nahida ALLY_OF Traveler

  [Context]
  [1] [Nahida] Nahida is the current Dendro Archon of Sumeru...
  ```

### 7.4 AnswerGenerator

- Model: Claude Sonnet 4.6 (ablation control: GPT-4o)
- Language auto-detection (Chinese question → Chinese answer)
- Citation format: `[Source: document title]` / `[Relation: A → B]`
- Structured return: `answer` + `sources` + `entities` + `path` + `timing` + `cost`

---

## 8. Ablation Study Results

### 8.1 Experimental Design

| Config | Model | Retrieval Strategy | Description |
|--------|-------|-------------------|-------------|
| S4-LLM | Claude Sonnet 4 | None | Parametric memory baseline |
| S4-VEC | Claude Sonnet 4 | Vector search | Semantic recall only |
| S4-GRF | Claude Sonnet 4 | Graph search | Structured relations only |
| S4-HYB | Claude Sonnet 4 | Hybrid | Vector + graph fusion |
| G4-LLM/VEC/GRF/HYB | GPT-4o | Same four strategies | Control model |

Scoring formula: `overall = 0.6 × fact_score + 0.4 × trap_score`

Judge model: **Claude Opus 4.6** (Claude Haiku was too strict — it incorrectly penalized correct reasoning chains in multi-hop answers)

### 8.2 Final Results

| Config | Overall | Fact Score | Trap Score | T1 | T2 | T3 | T4 |
|--------|---------|-----------|-----------|----|----|----|----|
| **S4-HYB** | **0.683** | 0.566 | 0.858 | 0.772 | 0.625 | 0.756 | 0.601 |
| S4-VEC | 0.674 | 0.565 | 0.838 | 0.778 | 0.636 | 0.718 | 0.587 |
| S4-GRF | 0.516 | 0.242 | 0.929 | 0.534 | 0.560 | 0.520 | 0.443 |
| S4-LLM | 0.410 | 0.016 | 1.000 | 0.430 | 0.412 | 0.400 | 0.400 |
| **G4-HYB** | **0.583** | 0.430 | 0.813 | 0.644 | 0.604 | 0.606 | 0.481 |
| G4-VEC | 0.554 | 0.382 | 0.832 | 0.671 | 0.534 | 0.545 | 0.491 |
| G4-GRF | 0.476 | 0.174 | 0.930 | 0.513 | 0.528 | 0.431 | 0.431 |
| G4-LLM | 0.409 | 0.015 | 1.000 | 0.415 | 0.412 | 0.408 | 0.400 |

### 8.3 Key Findings

**① HYB > VEC > GRF > LLM — consistent across both models**

Hybrid retrieval is the optimal strategy. Graph triples alone perform poorly: without prose context, models struggle to compose coherent answers from bare `(subject, relation, object)` fragments.

**② The LLM-only "0.40 floor effect"**

Fact score ≈ 0, but trap score = 1.000, yielding an overall score of ~0.41. Both models have essentially zero parametric memory of Sumeru lore — they decline to answer rather than hallucinate. **This validates the test set design: the questions are specific enough that LLMs cannot guess their way through.**

**③ Claude Sonnet 4 consistently outperforms GPT-4o — gap varies with retrieval richness**

| Retrieval Level | S4 Score | G4 Score | Gap |
|----------------|---------|---------|-----|
| LLM-only | 0.410 | 0.409 | +0.001 |
| VEC | 0.674 | 0.554 | +0.120 |
| GRF | 0.516 | 0.476 | +0.040 |
| HYB | 0.683 | 0.583 | +0.100 |

The gap is largest at VEC (S4 utilizes retrieved documents more efficiently); GPT-4o partially closes the gap at HYB, indicating it benefits more from richer hybrid context.

**④ T3 complex reasoning is where graph retrieval contributes most**

S4-HYB scores 0.756 on T3 vs. S4-VEC's 0.718 (+0.038), demonstrating that graph paths provide meaningful gains on questions requiring cross-entity reasoning.

**⑤ T4 multi-hop reasoning remains the global bottleneck**

All configurations score lowest on T4. Even the best configuration (S4-HYB) only reaches 0.601. Multi-hop chain reasoning is the primary area for future improvement.

---

## 9. Total Experiment Cost

| Phase | Description | Cost |
|-------|-------------|------|
| ETL Step 7 | Embedding 4,059 documents | ~$0.50 |
| ETL Step 8 | Triple extraction (Claude Sonnet) | ~$14.00 |
| Phase 1 | 50 gold reference answers (Opus) | ~$22.46 (est.) |
| Phase 2 | 400 model answers | $4.32 |
| Phase 3 | 400 Opus evaluations | $14.12 |
| **Total** | | **~$55** |
