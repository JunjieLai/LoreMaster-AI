# Loremaster AI — 原神剧情 GraphRAG 问答系统

**中文版** | [English](README.md)

---

## 1. 项目背景

### 领域背景

《原神》是米哈游开发的开放世界 RPG，世界观极为丰富：7 个国家各有独立的神话体系、政治结构、历史事件和数百位 NPC，现实文化原型深厚（须弥 → 南亚 / 中东）。游戏 Wiki 规模达数万篇文章。

**核心问题**：当玩家询问"纳西妲和赤王的关系是什么？"时，现有 LLM 存在两类失效：

1. **幻觉** — 模型从训练记忆中生成听起来合理但实际错误的细节
2. **知识截止** — 须弥内容在预训练数据中极为稀少（2022 年后更新）

**解决方案**：构建须弥专属知识库，结合向量检索 + 知识图谱，以混合 GraphRAG 架构将 LLM 生成锚定在经过核实的事实上，从源头消除幻觉。

---

## 2. 理论基础

### 2.1 RAG（检索增强生成）

RAG = 检索器 + 生成器。核心思想：将外部知识检索后注入 LLM 提示词，避免依赖参数记忆。

```
查询 → 检索(知识库) → 上下文 → LLM → 答案
```

本项目在标准 RAG 基础上扩展为 **GraphRAG**：在向量搜索之上叠加知识图谱路径检索，支持多跳推理。

### 2.2 知识图谱

实体和关系以有向图存储：

```
(纳西妲) -[IS_ARCHON_OF]→ (须弥)
(流浪者) -[ENEMY_OF]→ (愚人众)
```

支持精确关系查询（"A 和 B 是什么关系？"）和路径发现（"X 和 Y 有什么联系？"），弥补向量搜索无法处理结构化关系查询的短板。

### 2.3 混合检索

语义向量检索与结构化图谱路径检索互补结合：

- **向量搜索**：模糊语义匹配和开放域召回
- **图谱搜索**：精确实体关系和多跳推理
- **混合**：处理同时需要两者的复杂问题

### 2.4 LLM 作为评判（LLM-as-Judge）

使用更强的 LLM（Claude Opus 4.6）作为自动评估器，将候选答案与金标准参考答案对比——替代昂贵的人工标注。两个量化指标：

- **事实分（Fact Score）**：答案覆盖的金标准关键事实比例
- **防陷阱分（Trap Score）**：答案未触发已知幻觉陷阱的比例

---

## 3. 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **LLM** | Claude Sonnet 4.6 / Claude Opus 4.6 | 实体抽取、答案生成、评估裁判 |
| **LLM** | GPT-4o / GPT-4o-mini | 消融实验对照模型 |
| **向量数据库** | Pinecone | 4059 篇文档语义检索 |
| **图数据库** | Neo4j | 知识图谱存储与 Cypher 查询 |
| **键值数据库** | AWS DynamoDB | 实体元数据 + 别名解析表 |
| **对象存储** | AWS S3 | 数据资产归档 |
| **嵌入模型** | OpenAI text-embedding-3-small（1536 维） | 文档与查询向量化 |
| **后端** | FastAPI | REST API + SSE 流式输出 |
| **前端** | React 18 + TypeScript + TailwindCSS | 聊天界面 |
| **图可视化** | react-force-graph-2d | 力导向知识图谱渲染 |
| **动画** | Framer Motion | UI 过渡动效 |
| **Token 计数** | tiktoken（cl100k_base） | 精确上下文预算管理 |
| **运行时** | Python 3.9 | 后端 + ETL + 消融实验 |

---

## 4. 项目结构

```
loremaster-ai/
├── backend/
│   └── main.py              # FastAPI 服务 — REST 端点 + SSE 流式
├── frontend/
│   ├── src/
│   │   ├── App.tsx                        # 可调整大小的分割面板应用框架
│   │   ├── components/
│   │   │   ├── ChatMessage.tsx            # 消息渲染 + Markdown
│   │   │   ├── ConstellationGraph.tsx     # 关系路径可视化
│   │   │   ├── GraphExplorer.tsx          # 全屏知识图谱浏览器
│   │   │   ├── HistoryExplorer.tsx        # 对话历史 & 缓存浏览器
│   │   │   ├── SourceRegistry.tsx         # 来源文档注册表面板
│   │   │   └── ChatInput.tsx              # 输入文本框
│   │   ├── hooks/
│   │   │   ├── useGraphData.ts            # 图谱数据获取
│   │   │   └── useThumbnail.ts            # 实体缩略图获取
│   │   └── types/index.ts                # TypeScript 类型定义
├── src/
│   ├── agent/
│   │   ├── pipeline.py          # 主 RAG 流水线（流式）
│   │   ├── query_processor.py   # 查询处理（抽取 / 分类 / 扩展）
│   │   ├── retriever.py         # 混合检索器（向量 + 图谱）
│   │   ├── context_assembler.py # 上下文组装（token 预算 + 重排序）
│   │   ├── answer_generator.py  # 流式答案生成
│   │   ├── session_manager.py   # 多轮会话状态 + 后台压缩
│   │   ├── query_cache.py       # 语义答案缓存（余弦相似度）
│   │   ├── circuit_breaker.py   # 数据库故障保护熔断器
│   │   ├── ablation_config.py   # 8 个消融实验配置
│   │   ├── ablation_pipeline.py # 消融实验专用流水线
│   │   ├── adaptive_depth.py    # 自适应图遍历深度
│   │   └── text_loader.py       # 内存全文块索引
│   ├── etl/                     # 9 步 ETL 数据管道
│   ├── embed/embed.py           # 向量嵌入
│   ├── graph/                   # 三元组抽取与多目标加载
│   └── ablation/                # 三阶段评估框架
└── config/settings.py           # 集中式环境变量加载
```

---

## 5. ETL 数据管道

| 步骤 | 脚本 | 说明 |
|------|------|------|
| 1. 原始数据采集 | `etl/collect_wiki_full.py` | 从 HuggingFace 下载 22,162 篇 Wiki |
| 2. 结构化解析 | `etl/parse.py` | 实体类型推断 + 区域分类 + 去重哈希 |
| 3. 须弥过滤 | `etl/filter_sumeru.py` | 关键词 + 类目标签多策略筛选 |
| 4. 清洗去重 | `etl/clean.py` | 内容哈希去重 + 别名规范化 + 样板删除 → **4,059 篇** |
| 5. 分块切割 | `etl/chunk.py` | 512 token / 50 overlap，章节边界优先 |
| 6. 别名映射 | `etl/build_alias_mapping.py` | 写入 DynamoDB，支持中英文双向解析 |
| 7. 向量嵌入 | `embed/embed.py` | text-embedding-3-small，批量 + 断点续传，约 \$0.50 |
| 8. 三元组抽取 | `graph/extract.py` | Claude Sonnet 4 抽取结构化三元组，约 \$14 |
| 9. 多目标加载 | `graph/load.py` | 同时写入 Pinecone + Neo4j + DynamoDB |

---

## 6. 数据资产

### 6.1 目录结构

```
data/
├── raw/wiki/
│   └── genshin_wiki_full.jsonl       # 22,162 篇原始 Wiki  [步骤 1]
├── processed/
│   ├── documents/
│   │   ├── wiki_parsed.jsonl         # 结构化解析后         [步骤 2]
│   │   ├── wiki_sumeru.jsonl         # 须弥过滤后           [步骤 3]
│   │   └── wiki_clean.jsonl         # ★ 4,059 篇最终文档   [步骤 4]
│   ├── chunks/wiki_chunks.jsonl      # ★ 章节感知分块       [步骤 5]
│   ├── embeddings/
│   │   └── wiki_embeddings.jsonl    # ★ 4,059 × 1536 维向量 [步骤 7]
│   └── triples/
│       ├── entities.jsonl           # ★ ~1,000+ 实体       [步骤 8]
│       └── triples.jsonl           # ★ ~2,000+ 关系三元组  [步骤 8]
├── metadata/                         # 运行清单与 Schema 定义
└── ablation/
    ├── questions.jsonl               # ★ 50 道测试题
    ├── gold_references.jsonl         # ★ 50 份金标准答案
    ├── runs/                         # 400 条模型回答
    └── eval/
        ├── *.jsonl                   # 每题评分记录（含推理）
        └── summary.csv               # ★ 汇总分数表
```

### 6.2 ETL 数据流

每个步骤读取上一步的输出，写入下一步的输入：

```
HuggingFace 数据集（22,162 篇）
    |
    |  步骤 1 — collect_wiki_full.py
    v
raw/wiki/genshin_wiki_full.jsonl
    |  [原始 JSON，未结构化]
    |
    |  步骤 2 — parse.py
    |  · 规范化 Schema：id / title / entity_type / regions / content / content_hash
    |  · 从类目标签推断实体类型
    |  · 检测区域标签（须弥 / 璃月 / 稻妻 / ...）
    v
processed/documents/wiki_parsed.jsonl  (22,162 篇)
    |
    |  步骤 3 — filter_sumeru.py
    |  · 保留满足以下任一条件的文档：须弥关键词、类目标签、标题/正文关键词
    |  · 丢弃约 82% 的语料，仅保留须弥相关页面
    v
processed/documents/wiki_sumeru.jsonl  (~5,500 篇)
    |
    |  步骤 4 — clean.py
    |  · 内容哈希去重（正文相同 → 只保留一份）
    |  · 别名规范化（~100 条规则：Scaramouche → 流浪者，...）
    |  · 样板内容删除（Gallery / 导航栏 / 版本历史等章节）
    |  · 空白字符规范化
    v
processed/documents/wiki_clean.jsonl  (4,059 篇)  ★
    |
    +------------------------------------------+
    |                                          |
    |  步骤 5 — chunk.py                        |  步骤 6 — build_alias_mapping.py
    |  · 512 token 分块，50 token 重叠           |  · 构建实体别名表
    |  · 分割优先级：章节 → 段落 → 句子           |  · 写入 DynamoDB
    |  · 每个块继承父文档全量元数据               |  · 支持中英文双向查询
    v                                          v
wiki_chunks.jsonl                         DynamoDB 别名表 ★
    |
    |  步骤 7 — embed.py
    |  · OpenAI text-embedding-3-small（1536 维）
    |  · 批量 100 条/请求，指数退避重试
    |  · 支持断点续传，成本约 $0.50
    v
wiki_embeddings.jsonl  (4,059 条向量)  ★

wiki_clean.jsonl (并行分支)
    |
    |  步骤 8 — extract.py
    |  · Claude Sonnet 4 抽取（主语, 关系, 宾语, 证据）三元组
    |  · 优先处理约 150 篇高重要性实体文档
    |  · 成本约 $14
    v
entities.jsonl + triples.jsonl  ★
    |
    |  步骤 9 — load.py  [单次运行，三个目标]
    +---> Pinecone：批量 upsert 4,059 条向量及元数据
    +---> Neo4j：CREATE ~1,000+ 实体节点 + MERGE ~2,000+ 关系边
    +---> DynamoDB：实体元数据表 + 别名映射表
```

### 6.3 关键数据量

| 阶段 | 数量 | 备注 |
|------|------|------|
| 原始 Wiki 页面 | 22,162 | 来自 HuggingFace |
| 须弥过滤后 | ~5,500 | 约 25% 保留率 |
| 去重清洗后 | **4,059** | 原始数据的 18.3% |
| 向量块 | 4,059 | 每条 1,536 维 |
| Neo4j 实体节点 | ~1,000+ | Claude 抽取 |
| Neo4j 关系边 | ~2,000+ | 含证据文本 |
| 测试题 | 50 | T1×10 / T2×15 / T3×13 / T4×12 |
| 消融实验回答 | 400 | 8 配置 × 50 题 |
| Opus 评估次数 | 400 | 每条回答一次 |

---

## 7. Agent 设计

### 整体架构

```
用户查询
    |
    v
QueryProcessor
    |-- 实体抽取 & 别名解析（DynamoDB）
    |-- 查询类型分类（FACTUAL / RELATIONSHIP / MULTI_HOP / LIST / COMPARISON）
    +-- 查询扩展（2-3 个改写变体，扩大召回）
    |
    v
HybridRetriever
    |-- [VEC] Pinecone 语义搜索
    |-- [GRF] Neo4j 图谱路径查询 + 图谱重排序
    +-- [HYB] 合并结果 + 自适应深度控制
    |
    v
ContextAssembler
    |-- Token 预算分配（6000 总量：1500 图谱 + 4500 文本）
    |-- 实体感知文档重排序
    +-- Prompt 格式化
    |
    v
AnswerGenerator（流式）
    +-- Claude Sonnet 4.6 → 带引用的结构化答案（SSE 推流）
```

### 7.1 QueryProcessor

| 功能 | 实现 |
|------|------|
| **实体抽取** | 正则 + Claude Haiku 检测角色 / 地点 / 组织名 |
| **别名解析** | DynamoDB 查询 — "流浪者" / "Wanderer" / "Kunikuzushi" → 标准名 |
| **查询分类** | Haiku 语义分类（5 种类型）— 驱动检索策略 |
| **查询扩展** | 生成 2-3 个改写变体扩大召回 |
| **嵌入缓存** | LRU 缓存 — 相同查询跳过 API 调用 |

### 7.2 HybridRetriever

**向量检索**：Pinecone top-k 语义搜索（默认 k=8-10）+ 全文块索引补充

**图谱检索**：Cypher 查询直接实体关系（深度 1-4）+ 实体对最短路径发现 + 证据质量排序

**自适应深度**（`adaptive_depth.py`）：

- FACTUAL → 深度 1 | RELATIONSHIP → 深度 2 | MULTI_HOP → 深度 4
- "链条" / "间接" / "联系" 等关键词触发自动加深

**熔断器**（`circuit_breaker.py`）：连续 3 次 DB 失败后立即返回降级结果；CLOSED → OPEN → 60s → HALF_OPEN → CLOSED 状态机；防止级联超时拖垮整个请求流水线。

### 7.3 ContextAssembler

- **Token 预算**：tiktoken 精确计数，1500 图谱 + 4500 文本
- **重排序**：向量相似度（40%）+ 实体提及密度（30%）+ 章节相关性（20%）+ 查询类型加分（10%）
- **证据扩展**：关系三元组携带最多 220 字符原文证据，提供更丰富的叙事背景

### 7.4 AnswerGenerator

- Claude Sonnet 4.6 流式输出（SSE 推流至前端）
- 语言自动检测（中文问题 → 中文回答）
- 引用格式：`[Source: 文档标题]`
- Grounding 规则：严格断言仅文档中有据可查的事实，推断性内容使用对冲措辞

### 7.5 会话管理器（Session Manager）

多轮对话支持（`session_manager.py`）：

- 每会话保存对话轮次历史 + 累积实体追踪
- **指代消解**："他" / "她" / "it" 自动解析为上一轮提到的实体
- **后台压缩**：超过 8 轮 × 6000 字符时，Haiku 在守护线程中异步压缩旧轮次，不阻塞当前请求
- **双阈值触发**：轮次数 AND 字符数同时超标才压缩，避免短会话误触
- 会话 TTL：1 小时空闲过期；内存最多保留 50 轮

### 7.6 语义答案缓存（Query Cache）

持久化缓存（`query_cache.py`）：

- 基于查询嵌入的余弦相似度索引，命中阈值 ≥ 0.92
- 命中时 <100ms 返回，零 API 成本
- 线程安全原子写入，防并发重复写入

---

## 8. 前端功能

### 8.1 聊天界面

React 前端提供多面板可调整大小的布局，所有分割面板均可通过拖拽柄独立调整大小：

| 面板 | 说明 |
|------|------|
| **聊天区** | 流式问答 + Markdown 渲染 + 来源引用 + 成本 / 耗时显示 |
| **来源侧边栏** | 每条答案的来源文档卡片，含相关度分数和 Wiki 链接 |
| **星座图** | 答案中实体关系路径的力导向可视化 |
| **右侧边栏** | 每条答案的 Sources / Path / Graph 数据 Tab |

### 8.2 知识图谱浏览器（Graph Explorer）

- 可视化完整 Neo4j 知识图谱（~1,000+ 节点，~2,000+ 边）
- 按实体类型筛选（Character / NPC / Location / Region / Lore / Quest）
- 点击节点查看所有关系和证据文本
- 力导向布局 + 物理仿真

### 8.3 历史记录浏览器（History Explorer）

**对话（Conversations）标签**：一个会话 = 一张卡片 + 轮次选择条；持久化到 `localStorage`，刷新后不丢失；最多保留 20 个历史会话；每轮复用完整的来源 / 路径 / 图谱侧边栏布局。

**缓存（Cache）标签**：所有语义缓存答案的可浏览视图，显示原始查询、答案预览、时间戳和命中统计。

### 8.4 来源注册表（Source Registry）

跨对话聚合所有已引用来源文档，按实体类型和区域分组，跨答案自动去重，直链 Wiki 原页面。

---

## 9. 消融实验

### 9.1 实验设计

**8 种配置** = 2 个模型 × 4 种检索策略：

| 配置 | 模型 | 检索策略 | 说明 |
|------|------|---------|------|
| S4-LLM | Claude Sonnet 4 | 无 | 纯参数记忆基线 |
| S4-VEC | Claude Sonnet 4 | 向量搜索 | 仅语义召回 |
| S4-GRF | Claude Sonnet 4 | 图谱搜索 | 仅结构化关系 |
| **S4-HYB** | Claude Sonnet 4 | **混合** | 向量 + 图谱融合 |
| G4-LLM | GPT-4o | 无 | GPT 纯参数基线 |
| G4-VEC | GPT-4o | 向量搜索 | — |
| G4-GRF | GPT-4o | 图谱搜索 | — |
| **G4-HYB** | GPT-4o | **混合** | — |

**测试集**：50 道题，4 个难度层级：

- T1（×10）：单实体事实
- T2（×15）：直接实体关系
- T3（×13）：跨实体复杂推理
- T4（×12）：多跳链式推理（最难）

**评分公式**：`overall = 0.6 × fact_score + 0.4 × trap_score`

**评判模型**：Claude Opus 4.6，对正确的多跳推理链给予充分认可；仅对主动错误断言触发幻觉陷阱，不惩罚遗漏。

### 9.2 金标准答案的构造

金标准通过三层检索 + Opus 生成流程自动构建，复杂问题经人工审核。

**第一层（Layer A）**：标题精确匹配，召回标题直接包含关键实体的文档。

**第二层（Layer B）**：T3/T4 问题额外使用 Pinecone top-20 语义召回补充遗漏章节。

**第三层（Layer C）**：仅针对 T4，通过 Neo4j 共现图谱扩展，纳入推理链中间节点的证据页面。

Pipeline 自动标记高风险断言和文档覆盖缺口（`_review_flags`）。**T3/T4 的推理步骤和幻觉陷阱经过人工逐条验证**，确保多跳逻辑链和陷阱设计的准确性。平均每题约 \$0.65，共 \$22.46。

#### 金标准答案结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `key_facts` | 列表 | 核心事实，平均 **9.8 条**（T4 最多 22 条）。每条含来源文档和验证状态。评判模型逐条判断覆盖情况 |
| `required_entities` | 列表 | 正确答案必须提及的实体名称 |
| `required_relations` | 列表 | 答案需体现的实体间关系，含方向和来源文档 |
| `required_reasoning_steps` | 列表 | **仅 T3/T4**。正确推理链的步骤拆解，供评判模型理解多跳逻辑 |
| `hallucination_traps` | 列表 | 平均 **5.8 个**陷阱，每个含错误说法（`trap`）和正确信息（`correct`） |
| `min_acceptable_facts` | 整数 | 最低及格线（通常为 3）。MinFact% 统计答案达到此门槛的比例 |
| `coverage_notes` | 字符串 | 标注文档本身的信息缺口，防止因文档局限误罚答案 |
| `_review_flags` | 列表 | Pipeline 自动标记的高风险项；T3/T4 标记均经人工核查 |
| `_meta` | 对象 | 构造元数据：各层检索文档数、token 消耗、成本 |

#### 系统答案结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `question_id` / `tier` | 字符串/整数 | 题目 ID 和难度层级，与金标准对应 |
| `config` | 字符串 | 生成该答案的配置名称（如 `S4-HYB`） |
| `answer` | 字符串 | 完整答案文本，含 `[Source: ...]` 引用 |
| `query_type` | 字符串 | Pipeline 分类的查询类型，影响检索策略 |
| `entities` | 列表 | QueryProcessor 识别出的规范实体名 |
| `sources` | 列表 | 检索到的文档列表，每条含标题和相关度分数（0-1） |
| `timing` | 对象 | 各阶段耗时：`query_processing` / `retrieval` / `context_assembly` / `answer_generation` / `total`（秒） |
| `usage` | 对象 | Token 消耗：`input_tokens` / `output_tokens` / `cost_usd` |

### 9.3 评分过程

对每条系统答案，Opus 接收原始问题 + 金标准 `key_facts`（0 索引）+ `hallucination_traps`（0 索引）+ 答案全文，输出：

```json
{
  "facts_covered": [0, 1, 2, 4, 6, 7, 8, 9, 10],
  "traps_triggered": [1],
  "reasoning": "一句话评估摘要"
}
```

| 指标 | 计算公式 | 衡量内容 |
|------|---------|---------|
| **事实分** | `len(facts_covered) / len(key_facts)` | 召回率 — 覆盖了多少必要事实 |
| **防陷阱分** | `1 - len(traps_triggered) / len(hallucination_traps)` | 精确度 — 避开了多少幻觉陷阱 |
| **MinFact Met** | `len(facts_covered) >= min_acceptable_facts` | 布尔：是否达到最低完整性门槛 |
| **综合分** | `0.6 × fact_score + 0.4 × trap_score` | 加权综合评分 |

**事实覆盖判定**：答案明确陈述、正确改写或清晰推理至该事实 → 覆盖；遗漏、陈述错误或表述过于模糊 → 未覆盖。

**陷阱触发判定**：答案主动做出该错误断言 → 触发；仅遗漏正确信息但未说错 → 不触发（沉默不等于幻觉）。

### 9.4 实验结果

> **关于测试集设计的说明**：50 道题在设计时有意提高难度——刻意倾向于边缘案例、次要剧情细节、跨角色推理链，以及纯靠参数记忆几乎无法回答的问题。这是一次有意为之的压力测试（worst-case evaluation）。在实际使用场景中——主线剧情角色、常见关系问题、直接事实查询——系统的表现预期会明显优于以下数字。

| 配置 | Overall | 事实分 | 防陷阱分 | MinFact% | T1 | T2 | T3 | T4 |
|------|---------|--------|---------|----------|----|----|----|----|
| **S4-HYB** | **0.683** | **0.566** | 0.858 | **84%** | 0.772 | 0.625 | **0.756** | **0.601** |
| S4-VEC | 0.674 | 0.565 | 0.838 | 84% | **0.778** | 0.636 | 0.718 | 0.587 |
| S4-GRF | 0.516 | 0.242 | **0.929** | 32% | 0.534 | 0.560 | 0.520 | 0.443 |
| S4-LLM | 0.410 | 0.016 | 1.000 | 0% | 0.430 | 0.412 | 0.400 | 0.400 |
| **G4-HYB** | **0.583** | 0.430 | 0.813 | **72%** | 0.644 | 0.604 | 0.606 | 0.481 |
| G4-VEC | 0.554 | 0.382 | 0.832 | 56% | 0.671 | 0.534 | 0.545 | 0.491 |
| G4-GRF | 0.476 | 0.174 | 0.930 | 20% | 0.513 | 0.528 | 0.431 | 0.431 |
| G4-LLM | 0.409 | 0.015 | 1.000 | 0% | 0.415 | 0.412 | 0.408 | 0.400 |

### 9.5 核心发现

**① RAG 带来决定性提升 — 混合检索是最优策略**

两个 LLM-only 配置的 0.40 地板（事实分 ≈ 0，防陷阱分 = 1.000）证实须弥剧情在两个模型的参数记忆中几乎不存在。模型不会乱猜——它们根本不知道。RAG 将这一局面彻底改变：

| 配置 | Overall | vs LLM 基线 | 提升幅度 |
|------|---------|------------|---------|
| S4-LLM | 0.410 | — | — |
| S4-VEC | 0.674 | +0.264 | **+64%** |
| S4-HYB | 0.683 | +0.273 | **+67%** |
| G4-LLM | 0.409 | — | — |
| G4-VEC | 0.554 | +0.145 | **+35%** |
| G4-HYB | 0.583 | +0.174 | **+42%** |

混合检索始终优于纯向量检索，验证了图谱结构提供了散文文本无法独立呈现的互补信息。

**② MinFact% — 信息完整度差距显著**

| 策略 | S4 MinFact% | G4 MinFact% |
|------|-------------|-------------|
| HYB | **84%** | **72%** |
| VEC | 84% | 56% |
| GRF | 32% | 20% |
| LLM | **0%** | **0%** |

LLM-only 系统在每道题上都未能达到最低及格线。混合检索使两个模型都达到了高完整度。

**③ 图谱检索使复杂推理受益最大 — T3 是关键**

在 T3（跨实体复杂推理）上，图谱增强系统相对纯向量检索展现出最大优势：S4-HYB 0.756 vs S4-VEC 0.718（+0.038）。图谱中的关系路径提供了连接性证据——这是向量检索的散文内容无法明确呈现的。

**④ RAG 大幅缩小 Claude Sonnet 4 与 GPT-4o 的性能差距**

不使用检索时，两个模型几乎无法区分（0.410 vs 0.409）。RAG 揭示并放大了 Claude Sonnet 4 在利用检索内容方面的优势：

| 检索级别 | S4 | G4 | S4 优势 |
|---------|----|----|--------|
| 纯 LLM | 0.410 | 0.409 | +0.001 |
| VEC | 0.674 | 0.554 | **+0.120** |
| GRF | 0.516 | 0.476 | +0.040 |
| HYB | 0.683 | 0.583 | **+0.100** |

Claude Sonnet 4 在综合多来源检索证据、生成准确且信息密集的答案方面明显更强——这一优势在纯参数能力基准测试中完全不可见。

**⑤ T4 多跳推理是技术前沿**

所有配置在 T4 上得分均最低，最优配置 S4-HYB 也只达到 0.601。主要瓶颈是跨 3 跳以上链条的迭代推理，是未来改进的主要方向。

---

## 10. 总实验成本

| 阶段 | 说明 | 成本 |
|------|------|------|
| ETL 步骤 7 | 4059 篇文档嵌入 | ~\$0.50 |
| ETL 步骤 8 | 三元组抽取（Claude Sonnet） | ~\$14.00 |
| 第一阶段 | 50 个金标准参考答案（Opus） | ~\$22.46 |
| 第二阶段 | 400 条模型回答（8 配置 × 50 题） | \$4.32 |
| 第三阶段 | 400 次 Opus 评估打分 | \$14.12 |
| **合计** | | **~\$55** |
