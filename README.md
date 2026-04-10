# Loremaster AI — GraphRAG Q&A System for Genshin Impact Lore

[中文版](README_CN.md) | **English**

---

## 1. Background

### Domain Context

*Genshin Impact* is an open-world RPG developed by miHoYo. Its lore is exceptionally rich: 7 nations (Mondstadt, Liyue, Inazuma, Sumeru, Fontaine, Natlan, Snezhnaya), each with its own mythology, political structures, historical events, and hundreds of NPCs — drawing from real-world cultural archetypes (Sumeru → South Asia / Middle East). The game's wiki spans tens of thousands of articles.

**The core problem**: When a player asks "What is the relationship between Nahida and the Scarlet King?", current LLMs exhibit two failure modes:
1. **Hallucination** — the model fabricates plausible-sounding but incorrect details from training memory
2. **Knowledge cutoff** — Genshin Impact content is sparse in pre-training data, especially Sumeru (post-2022 content)

**Solution**: Build a Sumeru-focused **dedicated knowledge base** and combine **vector retrieval + knowledge graph** in a hybrid GraphRAG architecture, grounding LLM generation in verified facts to eliminate hallucination at the source.

---

## 2. Theoretical Foundations

### 2.1 RAG (Retrieval-Augmented Generation)

RAG = Retriever + Generator. The core idea: retrieve external knowledge as context injected into the LLM prompt, avoiding reliance on parametric memory.

```
Query → Retrieve(DB) → Context → LLM → Answer
```

This project extends standard RAG into **GraphRAG**: layering knowledge graph path retrieval on top of vector search to enable multi-hop reasoning.

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
| **Backend** | FastAPI | REST API server with streaming support |
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
│   └── main.py              # FastAPI server — REST endpoints + SSE streaming
├── frontend/
│   ├── src/
│   │   ├── App.tsx                        # App shell with resizable split panels
│   │   ├── components/
│   │   │   ├── ChatMessage.tsx            # Message rendering + Markdown
│   │   │   ├── ConstellationGraph.tsx     # Relationship path visualization
│   │   │   ├── GraphExplorer.tsx          # Full-screen knowledge graph browser
│   │   │   ├── HistoryExplorer.tsx        # Conversation history & cache explorer
│   │   │   ├── SourceRegistry.tsx         # Source document registry panel
│   │   │   └── ChatInput.tsx              # Input textarea
│   │   ├── hooks/
│   │   │   ├── useGraphData.ts            # Graph data fetching
│   │   │   └── useThumbnail.ts            # Entity thumbnail fetching
│   │   └── types/index.ts                # TypeScript type definitions
├── src/
│   ├── agent/
│   │   ├── pipeline.py          # Main RAG pipeline (streaming)
│   │   ├── query_processor.py   # Query processing (extraction / classification / expansion)
│   │   ├── retriever.py         # Hybrid retriever (vector + graph)
│   │   ├── context_assembler.py # Context assembly (token budget + reranking)
│   │   ├── answer_generator.py  # Streaming answer generation
│   │   ├── session_manager.py   # Multi-turn session state + background compression
│   │   ├── query_cache.py       # Semantic answer cache (cosine similarity)
│   │   ├── circuit_breaker.py   # Circuit breaker for DB failure protection
│   │   ├── ablation_config.py   # 8 ablation study configurations
│   │   ├── ablation_pipeline.py # Ablation-specific pipeline wrapper
│   │   ├── adaptive_depth.py    # Adaptive graph traversal depth
│   │   └── text_loader.py       # In-memory full-text chunk index
│   ├── etl/                     # 9-step ETL pipeline (see Section 5)
│   ├── embed/
│   │   └── embed.py             # Vector embedding
│   ├── graph/
│   │   ├── extract.py           # Triple extraction (Claude)
│   │   └── load.py              # Load into Pinecone / Neo4j / DynamoDB
│   └── ablation/
│       ├── run_oracle.py        # Phase 1: Generate gold references
│       ├── run_experiment.py    # Phase 2: Run 8 configurations × 50 questions
│       ├── run_eval.py          # Phase 3: Opus evaluation scoring + summary
│       ├── fetch_docs.py        # 3-layer document retrieval for gold generation
│       ├── generate_gold.py     # Gold standard generation
│       └── prompts.py           # Prompt library
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

### Step 2 — Structured Parsing
**Script**: `src/etl/parse.py`

Converts raw JSON into a standardized schema:
- **Entity type inference**: identified from category labels (PlayableCharacter, NPC, Location, Organization, Event, Weapon, Artifact, Boss, ...)
- **Region detection**: classifies into Sumeru / Liyue / Mondstadt / Inazuma / Fontaine
- **Content cleaning**: removes Markdown template tags; computes content hash for deduplication

### Step 3 — Sumeru Filtering
**Script**: `src/etl/filter_sumeru.py`

Multi-strategy filtering to retain only Sumeru-relevant content:
- Keyword matching (Nahida, Akademiya, Dendro Archon, Alhaitham, rainforest, ...)
- Category-tag detection + title and body double-check

### Step 4 — Cleaning and Deduplication
**Script**: `src/etl/clean.py`

- **Content-hash deduplication**: identical content stored only once
- **Alias normalization**: ~100 mappings (Scaramouche → Wanderer, etc.)
- **Boilerplate removal**: drops Gallery, Navigation, version history sections
- Final output: **4,059 documents** → `data/processed/documents/wiki_clean.jsonl`

### Step 5 — Section-Aware Chunking
**Script**: `src/etl/chunk.py`

- Config: 512 tokens, 50-token overlap
- **Section boundary priority**: splits at section headings → paragraph → sentence
- Each chunk carries full metadata: doc_id, title, section_title, entity_type, regions

### Step 6 — Alias Mapping Construction
**Script**: `src/etl/build_alias_mapping.py`

Builds the entity alias resolution table and writes it to DynamoDB:
- Bidirectional Chinese-English alias lookup
- Resolves "Wanderer", "流浪者", "Kunikuzushi" → canonical entity name at query time

### Step 7 — Vector Embedding
**Script**: `src/embed/embed.py`

- Model: OpenAI `text-embedding-3-small` (1,536 dims)
- Batch size: 100 chunks/request with exponential-backoff retries
- Checkpoint/resume support; total cost: ~$0.50

### Step 8 — Knowledge Graph Triple Extraction
**Script**: `src/graph/extract.py`

Uses Claude Sonnet 4 to extract structured triples from documents:
- Triple format: `{"subject": "Nahida", "relation": "IS_ARCHON_OF", "object": "Sumeru", "evidence": "..."}`
- 3,494 entities, 4,199 relationship triples extracted

### Step 9 — Multi-Target Loading
**Script**: `src/graph/load.py`

Loads all data into three databases in one run:
1. **Pinecone**: batch-upserts all 4,059 vectors with metadata
2. **Neo4j**: `CREATE` Entity nodes + `MERGE` relationship edges (Cypher batch operations)
3. **DynamoDB**: entity metadata table + alias mapping table

---

## 6. Data Assets

### 6.1 Directory Structure

```
data/
├── raw/
│   └── wiki/
│       └── genshin_wiki_full.jsonl       # 22,162 raw wiki entries  [Step 1]
│
├── processed/
│   ├── documents/
│   │   ├── wiki_parsed.jsonl             # After structured parsing  [Step 2]
│   │   ├── wiki_sumeru.jsonl             # After Sumeru filtering     [Step 3]
│   │   └── wiki_clean.jsonl             # ★ 4,059 final documents    [Step 4]
│   ├── chunks/
│   │   └── wiki_chunks.jsonl            # ★ Section-aware chunks     [Step 5]
│   ├── embeddings/
│   │   └── wiki_embeddings.jsonl        # ★ 4,059 × 1,536-dim vectors [Step 7]
│   └── triples/
│       ├── extract_raw.jsonl            # Raw LLM extraction output
│       ├── entities.jsonl               # ★ 3,494 entities             [Step 8]
│       └── triples.jsonl               # ★ 4,199 relationship triples  [Step 8]
│
├── metadata/
│   ├── wiki_schema.json                 # Field schema definition
│   ├── embedding_manifest.json          # Embedding run metadata
│   ├── extraction_manifest.json         # Triple extraction statistics
│   └── load_manifest.json               # Database load statistics
│
└── ablation/
    ├── questions.jsonl                  # ★ 50 test questions (T1×10 / T2×15 / T3×13 / T4×12)
    ├── gold_references.jsonl            # ★ 50 gold reference answers
    ├── oracle_checkpoint.json           # Oracle run checkpoint
    ├── runs/                            # Phase 2: 400 model answers (8 configs × 50 questions)
    │   ├── S4-LLM.jsonl  S4-VEC.jsonl  S4-GRF.jsonl  S4-HYB.jsonl
    │   └── G4-LLM.jsonl  G4-VEC.jsonl  G4-GRF.jsonl  G4-HYB.jsonl
    └── eval/
        ├── S4-LLM.jsonl  ...  G4-HYB.jsonl  # Per-question scores with judge reasoning
        └── summary.csv                  # ★ Aggregate score table
```

### 6.2 ETL Data Flow

Each step reads from the previous step's output and writes to the next:

```
HuggingFace dataset (22,162 pages)
    │
    │  Step 1 — collect_wiki_full.py
    ▼
raw/wiki/genshin_wiki_full.jsonl
    │  [raw JSON, unstructured]
    │
    │  Step 2 — parse.py
    │  · Standardize schema: id, title, entity_type, regions, content, content_hash
    │  · Infer entity types from category labels
    │  · Detect region tags (Sumeru / Liyue / Inazuma / …)
    ▼
processed/documents/wiki_parsed.jsonl  (22,162 docs)
    │
    │  Step 3 — filter_sumeru.py
    │  · Keep docs matching any of: Sumeru keywords, category tags, title/body keywords
    │  · Drops ~82% of corpus — retains Sumeru-relevant pages only
    ▼
processed/documents/wiki_sumeru.jsonl  (~5,500 docs)
    │
    │  Step 4 — clean.py
    │  · Content-hash deduplication (identical body → keep one)
    │  · Alias normalization (~100 rules: Scaramouche → Wanderer, …)
    │  · Boilerplate removal (Gallery, Navigation, version history sections)
    │  · Whitespace normalization
    ▼
processed/documents/wiki_clean.jsonl  (4,059 docs)  ★
    │
    ├──────────────────────────────────────────────────────────┐
    │                                                          │
    │  Step 5 — chunk.py                                       │  Step 6 — build_alias_mapping.py
    │  · 512-token chunks, 50-token overlap                    │  · Build entity alias table
    │  · Split priority: section → paragraph → sentence        │  · Write to DynamoDB
    │  · Each chunk inherits parent doc metadata               │  · Supports CN/EN bidirectional lookup
    ▼                                                          ▼
processed/chunks/wiki_chunks.jsonl                        DynamoDB alias table  ★
    │
    │  Step 7 — embed.py
    │  · OpenAI text-embedding-3-small (1,536 dims)
    │  · Batch size 100, exponential-backoff retries
    │  · Checkpoint/resume support
    │  · Cost: ~$0.50
    ▼
processed/embeddings/wiki_embeddings.jsonl  (4,059 vectors)  ★
    │
    │  [parallel branch from wiki_clean.jsonl]
    │
    │  Step 8 — extract.py
    │  · Claude Sonnet 4 extracts (subject, relation, object, evidence) triples
    │  · Prioritizes ~150 high-importance entity docs; selects others within budget
    │  · Cost: ~$14
    ▼
processed/triples/entities.jsonl + triples.jsonl  ★
    │
    │  Step 9 — load.py  [single run, three targets]
    ├──▶  Pinecone:  batch-upsert 4,059 vectors with metadata
    ├──▶  Neo4j:     CREATE 3,494 entity nodes + MERGE 4,199 relationship edges
    └──▶  DynamoDB:  entity metadata table + alias mapping table
```

### 6.3 Key Numbers

| Stage | Count | Note |
|-------|-------|------|
| Raw wiki pages | 22,162 | From HuggingFace |
| After Sumeru filter | ~5,500 | ~25% retention |
| After deduplication & cleaning | **4,059** | 18.3% of raw |
| Vector chunks | 4,059 | 1,536 dims each |
| Neo4j entity nodes | **3,494** | Character×1157, Item×851, Concept×463, Location×443, Event×390, Organization×190 |
| Neo4j relationship edges | **4,199** | 21 relation types; top: LOCATED_IN×879, PARTICIPATED_IN×564, PART_OF×514 |
| Test questions | 50 | T1×10 / T2×15 / T3×13 / T4×12 |
| Ablation answers | 400 | 8 configs × 50 questions |
| Opus evaluations | 400 | One per answer |

---

## 7. Agent Design

### Overall Architecture

```
User Query
    ↓
QueryProcessor
    ├── Entity extraction & alias resolution (DynamoDB)
    ├── Query type classification (FACTUAL / RELATIONSHIP / MULTI_HOP / LIST / COMPARISON)
    └── Query expansion (2–3 paraphrased variants for broader recall)
    ↓
HybridRetriever
    ├── [VEC] Pinecone semantic search
    ├── [GRF] Neo4j graph path query + graph ranking
    └── [HYB] Merged results with adaptive depth control
    ↓
ContextAssembler
    ├── Token budget allocation (6,000 total: 1,500 graph + 4,500 text)
    ├── Entity-aware document reranking
    └── Prompt formatting
    ↓
AnswerGenerator (streaming)
    └── Claude Sonnet 4.6 → cited, structured answer via SSE
```

### 7.1 QueryProcessor

| Feature | Implementation |
|---------|---------------|
| **Entity extraction** | Regex + Claude Haiku for character / location / organization detection |
| **Alias resolution** | DynamoDB lookup — "Wanderer" / "流浪者" / "Kunikuzushi" → canonical name |
| **Query classification** | Haiku semantic classification (5 types) — drives retrieval strategy |
| **Query expansion** | Generates 2–3 paraphrased variants to broaden recall |
| **Embedding cache** | LRU cache — skips re-embedding for repeated or similar queries |

### 7.2 HybridRetriever

**Vector retrieval**: Pinecone top-k semantic search (default k=8–10) + full-text chunk index supplement

**Graph retrieval**: Cypher queries for direct entity relationships (depth 1–4) + shortest-path discovery between entity pairs + evidence-quality ranking

**Adaptive depth control** (`adaptive_depth.py`):
- FACTUAL → depth 1 | RELATIONSHIP → depth 2 | MULTI_HOP → depth 4
- Keyword triggers ("chain", "indirect", "connection") automatically increase depth

**Circuit breaker** (`circuit_breaker.py`):
- After 3 consecutive DB failures, circuit opens and returns degraded results immediately
- CLOSED → OPEN → (60s) → HALF_OPEN → CLOSED state machine
- Prevents cascading timeouts from hanging the entire request pipeline

### 7.3 ContextAssembler

- **Token budget**: 1,500 tokens for graph triples + 4,500 tokens for text passages, precisely tracked via tiktoken
- **Reranking**: multi-factor scoring — vector similarity (40%) + entity mention density (30%) + section relevance (20%) + query-type bonus (10%)
- **Evidence expansion**: relationship triples include up to 220 chars of source text evidence for richer grounding

### 7.4 AnswerGenerator

- Model: Claude Sonnet 4.6 with streaming (SSE to frontend)
- Language auto-detection (Chinese question → Chinese answer)
- Citation format: `[Source: document title]`
- Grounding rules: strict fact-only assertions with hedged inference marking

### 7.5 Session Manager

Multi-turn conversation support (`session_manager.py`):
- Per-session turn history with accumulated entity tracking
- **Coreference resolution**: "他" / "她" / "it" → resolved to the last mentioned entity
- **Background compression**: when history exceeds 8 turns × 6,000 chars, Haiku summarizes older turns in a daemon thread — never blocks the request
- **Dual-threshold compression**: triggers only when both turn count AND char count thresholds are met (avoids compressing short sessions)
- Session TTL: 1 hour idle expiry; max 50 turns in memory

### 7.6 Semantic Answer Cache

Persistent answer cache (`query_cache.py`):
- Cosine similarity index over query embeddings
- Cache hit threshold: configurable (default ≥ 0.92 similarity)
- On hit: returns stored answer in <100ms with zero API cost
- Thread-safe atomic writes; deduplication guard prevents concurrent race conditions

---

## 8. Frontend Features

### 8.1 Chat Interface

The React frontend provides a multi-panel, resizable layout:

| Panel | Description |
|-------|-------------|
| **Chat** | Streaming Q&A with Markdown rendering, source citations, and cost/timing display |
| **Source Sidebar** | Per-answer source document cards with relevance scores and wiki links |
| **Constellation Graph** | Force-directed visualization of entity relationship paths from the answer |
| **Right Sidebar** | Tabs for Sources, Path, and Graph data per answer |

All split panels are independently resizable with drag handles.

### 8.2 Graph Explorer

Full-screen, interactive knowledge graph browser:
- Visualizes the entire Neo4j knowledge graph (3,494 nodes, 4,199 edges)
- Filter by entity type (Character, NPC, Location, Region, Lore, Quest)
- Click any node to inspect all its relationships and evidence text
- Force-directed layout with physics simulation

### 8.3 History Explorer

Persistent conversation history with two views:

**Conversations tab**:
- Each session is stored as one card (not per-message) with a turn selector strip
- Survives page refresh — persisted to `localStorage`
- Up to 20 past sessions retained
- Per-turn display reuses the full source/path/graph sidebar layout

**Cache tab**:
- Browsable view of all semantically cached answers
- Shows original query, answer preview, timestamp, and cache hit statistics

### 8.4 Source Registry

Aggregated view of all source documents surfaced across conversations:
- Grouped by entity type and region
- Deduplication across multiple answers that referenced the same document
- Direct links to source wiki pages

---

## 9. Ablation Study

### 9.1 Experimental Design

**8 configurations** = 2 models × 4 retrieval strategies:

| Config | Model | Retrieval | Description |
|--------|-------|-----------|-------------|
| S4-LLM | Claude Sonnet 4 | None | Parametric memory baseline |
| S4-VEC | Claude Sonnet 4 | Vector search | Semantic recall only |
| S4-GRF | Claude Sonnet 4 | Graph search | Structured relations only |
| **S4-HYB** | Claude Sonnet 4 | **Hybrid** | Vector + graph fusion |
| G4-LLM | GPT-4o | None | GPT baseline |
| G4-VEC | GPT-4o | Vector search | — |
| G4-GRF | GPT-4o | Graph search | — |
| **G4-HYB** | GPT-4o | **Hybrid** | — |

**Test set**: 50 questions across 4 difficulty tiers:
- T1 (×10): Single entity facts
- T2 (×15): Direct entity relationships
- T3 (×13): Complex cross-entity reasoning
- T4 (×12): Multi-hop chains (hardest)

**Scoring formula**: `overall = 0.6 × fact_score + 0.4 × trap_score`

**Judge**: Claude Opus 4.6 with a nuanced evaluation prompt — credits correct multi-hop reasoning chains; only flags hallucinations for actively wrong claims, not mere omissions.

**Gold references**: 3-layer retrieval (title match + Pinecone top-20 + co-mention graph) to ensure gold answers are fully grounded in the knowledge base.

### 9.2 Gold Reference Construction

Gold-standard reference answers are built through a reproducible three-layer retrieval + Opus generation pipeline (`src/ablation/run_oracle.py`), with human review for complex questions.

**Layer A — Title match**: Retrieves documents whose titles directly contain the question's key entities (e.g. `NPC Nahida`, `Nahida/Lore`).

**Layer B — Semantic recall**: For T3/T4 questions, supplements with Pinecone top-20 vector search to catch relevant sections missed by title matching.

**Layer C — Co-mention graph expansion**: For T4 multi-hop questions only, expands via Neo4j to include pages of entities co-occurring with known entities, ensuring intermediate reasoning-chain nodes are covered.

The merged documents are fed to Claude Opus 4.6 to generate the structured gold reference. The pipeline automatically flags high-risk assertions and document coverage gaps (`_review_flags`) for human inspection. **T3/T4 reasoning steps and hallucination traps are manually verified** to ensure accuracy of multi-hop logic chains and trap design.

Average construction cost: ~28,500 tokens per question ($0.65); total $22.46.

#### Gold Reference Structure

Each record in `gold_references.jsonl`:

| Field | Type | Description |
|-------|------|-------------|
| `key_facts` | list | Core facts, avg **9.8 per question** (up to 22 for T4). Each entry has `fact`, `doc_source`, and `verified`. Judge checks coverage fact-by-fact |
| `required_entities` | list | Entity names the correct answer must mention |
| `required_relations` | list | Directional entity relationships the answer must reflect, with source document |
| `required_reasoning_steps` | list | **T3/T4 only.** Step-by-step breakdown of the correct reasoning chain, to help the judge credit valid multi-hop answers |
| `hallucination_traps` | list | Avg **5.8 per question**. Each entry has `trap` (wrong claim) and `correct` (truth). Designed around known confusion points (e.g. who created the Akasha System) |
| `min_acceptable_facts` | int | Minimum facts required to pass (usually 3). MinFact% measures the rate of answers that meet this bar |
| `coverage_notes` | string | Documents known gaps in source material, preventing the judge from penalizing answers for information the corpus genuinely lacks |
| `_review_flags` | list | Auto-flagged high-risk items and coverage gaps from the Oracle pipeline; all T3/T4 flags manually reviewed |
| `_meta` | object | Construction metadata: documents fetched per layer, token usage, cost |

#### System Answer Structure

Each record in `runs/<config>.jsonl`:

| Field | Type | Description |
|-------|------|-------------|
| `question_id` / `tier` | string/int | Question ID and difficulty tier, matched against gold reference |
| `config` | string | Configuration that generated this answer (e.g. `S4-HYB`) |
| `answer` | string | Full answer text with `[Source: ...]` citation markers |
| `query_type` | string | Pipeline-classified query type (FACTUAL / RELATIONSHIP / MULTI_HOP etc.), determines retrieval strategy |
| `entities` | list | Canonical entity names extracted by QueryProcessor |
| `sources` | list | Retrieved documents with title and relevance score (0–1) |
| `timing` | object | Per-stage latency breakdown: `query_processing` / `retrieval` / `context_assembly` / `answer_generation` / `total` (seconds) |
| `usage` | object | Token consumption: `input_tokens` / `output_tokens` / `total_tokens` / `cost_usd` |

### 9.3 Scoring Process

For each system answer, Claude Opus 4.6 receives: the original question, the gold `key_facts` list (0-indexed), and the gold `hallucination_traps` list (0-indexed), plus the full answer text. It outputs:

```json
{
  "facts_covered": [0, 1, 2, 4, 6, 7, 8, 9, 10],
  "traps_triggered": [1],
  "reasoning": "one-sentence evaluation summary"
}
```

The scoring script then computes:

| Metric | Formula | What it measures |
|--------|---------|-----------------|
| **Fact Score** | `len(facts_covered) / len(key_facts)` | Recall — what fraction of required facts the answer covered |
| **Trap Score** | `1 − len(traps_triggered) / len(hallucination_traps)` | Precision — what fraction of hallucination traps the answer avoided |
| **Min Facts Met** | `len(facts_covered) >= min_acceptable_facts` | Boolean: did the answer clear the minimum completeness bar |
| **Overall Score** | `0.6 × fact_score + 0.4 × trap_score` | Weighted aggregate; fact coverage weighted higher |

**Fact coverage rules**: A fact is marked covered if the answer explicitly states it, correctly paraphrases it, or clearly reasons to it. A fact is marked missed if omitted, wrong, or mentioned too vaguely to be informative.

**Trap trigger rules**: A trap is triggered only if the answer actively makes the specific wrong claim. Omitting the correct information does not trigger a trap — silence is not hallucination.

### 9.4 Results

> **Note on test set design**: The 50 questions were deliberately designed to stress-test the system — skewing toward edge cases, secondary lore, cross-character reasoning, and questions unlikely to be answered correctly by parametric memory alone. This is a worst-case evaluation by design. Scores on typical player queries (main storyline characters, commonly asked relationships) are expected to be meaningfully higher than the numbers below.

| Config | Overall | Fact Score | Trap Score | MinFact% | T1 | T2 | T3 | T4 |
|--------|---------|-----------|-----------|----------|----|----|----|----|
| **S4-HYB** | **0.683** | **0.566** | 0.858 | **84%** | 0.772 | 0.625 | **0.756** | **0.601** |
| S4-VEC | 0.674 | 0.565 | 0.838 | 84% | **0.778** | 0.636 | 0.718 | 0.587 |
| S4-GRF | 0.516 | 0.242 | **0.929** | 32% | 0.534 | 0.560 | 0.520 | 0.443 |
| S4-LLM | 0.410 | 0.016 | 1.000 | 0% | 0.430 | 0.412 | 0.400 | 0.400 |
| **G4-HYB** | **0.583** | 0.430 | 0.813 | **72%** | 0.644 | 0.604 | 0.606 | 0.481 |
| G4-VEC | 0.554 | 0.382 | 0.832 | 56% | 0.671 | 0.534 | 0.545 | 0.491 |
| G4-GRF | 0.476 | 0.174 | 0.930 | 20% | 0.513 | 0.528 | 0.431 | 0.431 |
| G4-LLM | 0.409 | 0.015 | 1.000 | 0% | 0.415 | 0.412 | 0.408 | 0.400 |

### 9.5 Key Findings

**① RAG delivers a decisive lift — hybrid retrieval is the clear winner**

The 0.40 floor for both LLM-only configs (fact score ≈ 0, trap score = 1.000) confirms that Sumeru lore is effectively absent from both models' parametric memory. Neither model guesses its way through — they simply don't know. RAG transforms this:

| Config | Overall | vs LLM baseline | Improvement |
|--------|---------|----------------|-------------|
| S4-LLM | 0.410 | — | — |
| S4-VEC | 0.674 | +0.264 | **+64%** |
| S4-HYB | 0.683 | +0.273 | **+67%** |
| G4-LLM | 0.409 | — | — |
| G4-VEC | 0.554 | +0.145 | **+35%** |
| G4-HYB | 0.583 | +0.174 | **+42%** |

Hybrid retrieval consistently tops vector-only, validating that graph structure contributes complementary information that prose alone cannot provide.

**② MinFact% — the completeness gap is stark**

MinFact% measures whether the answer covered at least the minimum acceptable number of key facts:

| Strategy | S4 MinFact% | G4 MinFact% |
|----------|-------------|-------------|
| HYB | **84%** | **72%** |
| VEC | 84% | 56% |
| GRF | 32% | 20% |
| LLM | **0%** | **0%** |

LLM-only systems fail to meet even the minimum bar on every single question. Hybrid retrieval brings both models to high completeness rates.

**③ Graph retrieval enables complex reasoning — T3 is where it matters most**

On T3 questions (cross-entity reasoning), the graph-augmented system shows its greatest advantage over pure vector search:

| Config | T3 Score |
|--------|----------|
| S4-HYB | **0.756** |
| S4-VEC | 0.718 |
| G4-HYB | 0.606 |
| G4-VEC | 0.545 |

The +0.038 gain (S4: HYB vs VEC) on T3 reflects cases where relationship paths in the knowledge graph provide the connecting evidence that vector-retrieved prose cannot explicitly state.

**④ RAG substantially narrows the model gap between Claude Sonnet 4 and GPT-4o**

Without retrieval, the two models are statistically indistinguishable (0.410 vs 0.409). RAG reveals — and amplifies — Claude Sonnet 4's advantage in utilizing retrieved context:

| Retrieval Level | S4 | G4 | S4 advantage |
|----------------|----|----|-------------|
| LLM-only | 0.410 | 0.409 | +0.001 |
| VEC | 0.674 | 0.554 | **+0.120** |
| GRF | 0.516 | 0.476 | +0.040 |
| HYB | 0.683 | 0.583 | **+0.100** |

Claude Sonnet 4 is significantly better at synthesizing multi-source retrieved evidence into accurate, fact-dense answers — a gap invisible from parametric benchmarks alone.

**⑤ T4 multi-hop reasoning is the frontier**

All configurations score lowest on T4 (hardest tier). Even S4-HYB reaches only 0.601. The primary bottleneck is iterative reasoning over chains of 3+ hops — a target for future retrieval improvements (confidence-gated iterative retrieval, chain-of-thought graph traversal).

---

## 10. Total Experiment Cost

| Phase | Description | Cost |
|-------|-------------|------|
| ETL Step 7 | Embedding 4,059 documents | ~$0.50 |
| ETL Step 8 | Triple extraction (Claude Sonnet) | ~$14.00 |
| Phase 1 | 50 gold reference answers (Opus) | ~$22.46 |
| Phase 2 | 400 model answers (8 configs × 50 questions) | $4.32 |
| Phase 3 | 400 Opus evaluations | $14.12 |
| **Total** | | **~$55** |
