# Loremaster AI — 项目详细介绍

---

## 一、项目背景

### 领域背景

《原神》是由米哈游开发的开放世界RPG，其世界观构建极为复杂：7个国家（蒙德、璃月、稻妻、须弥、枫丹、纳塔、至冬）各有独立神话体系、政治结构、历史事件和数以百计的NPC，对应现实文化原型（须弥 → 南亚/中东），拥有数万条维基百科词条。

**核心问题**：玩家提问"纳希达与赤王有什么关系？"时，现有大语言模型存在两类失败模式：
1. **幻觉**：凭训练记忆捏造细节，给出看似合理但错误的答案
2. **知识截止**：训练数据中原神内容稀疏，尤其须弥（2022年后版本）相关内容覆盖不全

**解决思路**：构建以须弥为核心的**专用知识库**，结合**向量检索 + 知识图谱**的混合RAG（Retrieval-Augmented Generation）架构，使LLM在正确事实上下文中生成答案，从根本上抑制幻觉。

---

## 二、相关理论

### 2.1 RAG（检索增强生成）

RAG = 检索器（Retriever）+ 生成器（Generator）。核心思想：将外部知识检索为上下文注入LLM提示词，避免依赖参数化记忆。

```
Query → Retrieve(DB) → Context → LLM → Answer
```

本项目扩展为**GraphRAG**：在标准向量检索基础上叠加知识图谱路径，支持多跳推理。

### 2.2 知识图谱（Knowledge Graph）

将实体（Entity）和关系（Relation）结构化存储为有向图：
```
(Nahida) -[IS_ARCHON_OF]→ (Sumeru)
(Scaramouche) -[ENEMY_OF]→ (Fatui)
```
支持精确关系查询（"A和B有什么关系？"）和路径发现（"从X到Y的关联链"），弥补向量检索无法处理精确关系的缺陷。

### 2.3 混合检索（Hybrid Retrieval）

将向量相似度检索（Semantic）与图谱路径检索（Structural）融合，取长补短：
- **向量检索**：擅长语义模糊匹配、开放域检索
- **图谱检索**：擅长精确实体关系、多跳推理
- **混合**：二者互补，应对复杂问题

### 2.4 LLM-as-Judge 评估

使用更强的LLM（Claude Opus 4.6）作为评判者，对比候选答案与黄金参考答案，替代人工标注。量化指标：
- **事实覆盖率**（Fact Score）：金标准事实中被覆盖的比例
- **幻觉规避率**（Trap Score）：已知幻觉陷阱中未触发的比例

---

## 三、技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| **大模型** | Claude Sonnet 4.6 / Claude Opus 4.6 | 实体提取、答案生成、评估评判 |
| **大模型** | GPT-4o / GPT-4o-mini | 消融对照模型 |
| **向量数据库** | Pinecone | 4059条文档的语义检索 |
| **图数据库** | Neo4j | 知识图谱存储与Cypher查询 |
| **关系数据库** | AWS DynamoDB | 实体元数据 + 别名映射表 |
| **对象存储** | AWS S3 | 数据资产归档 |
| **嵌入模型** | OpenAI text-embedding-3-small (1536维) | 文档和查询向量化 |
| **后端框架** | FastAPI | REST API服务 |
| **前端框架** | React 18 + TypeScript + TailwindCSS | 聊天界面 |
| **图可视化** | react-force-graph-2d | 知识图谱力导向渲染 |
| **动画** | Framer Motion | 界面动效 |
| **Token计数** | tiktoken (cl100k_base) | 精确上下文预算控制 |
| **运行时** | Python 3.9 | 后端 + ETL + 消融实验 |

---

## 四、项目框架

```
loremaster-ai/
├── backend/
│   └── main.py              # FastAPI服务，5个REST端点
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # 主应用壳，可调整面板布局
│   │   ├── components/
│   │   │   ├── ChatMessage.tsx        # 消息渲染 + Markdown
│   │   │   ├── ConstellationGraph.tsx # 关系路径可视化
│   │   │   ├── GraphExplorer.tsx      # 全屏知识图谱浏览器
│   │   │   ├── SourceCard.tsx         # 来源文档卡片
│   │   │   └── ChatInput.tsx          # 输入框
│   │   ├── hooks/
│   │   │   ├── useGraphData.ts        # 图谱数据拉取
│   │   │   └── useThumbnail.ts        # 实体缩略图
│   │   └── types/index.ts            # TypeScript类型定义
├── src/
│   ├── agent/
│   │   ├── pipeline.py          # 主RAG管道
│   │   ├── query_processor.py   # 查询处理（实体提取/分类/扩展）
│   │   ├── retriever.py         # 混合检索器
│   │   ├── context_assembler.py # 上下文组装（Token预算+重排序）
│   │   ├── answer_generator.py  # 答案生成
│   │   ├── ablation_config.py   # 8种消融配置
│   │   ├── ablation_pipeline.py # 消融实验专用管道
│   │   ├── adaptive_depth.py    # 自适应图谱遍历深度
│   │   └── text_loader.py       # 全文本块索引
│   ├── etl/
│   │   ├── collect_wiki_full.py # 原始数据采集
│   │   ├── parse.py             # 结构化解析
│   │   ├── filter_sumeru.py     # 须弥过滤
│   │   ├── clean.py             # 清洗去重
│   │   ├── chunk.py             # 分块
│   │   └── build_alias_mapping.py # 别名映射
│   ├── embed/
│   │   └── embed.py             # 向量化
│   ├── graph/
│   │   ├── extract.py           # 三元组提取（Claude）
│   │   ├── load.py              # 加载到Pinecone/Neo4j/DynamoDB
│   │   ├── reclassify_relations.py
│   │   └── migrate_neo4j_relations.py
│   └── ablation/
│       ├── run_oracle.py        # Phase 1: 生成黄金参考答案
│       ├── run_experiment.py    # Phase 2: 运行8种配置
│       ├── run_eval.py          # Phase 3: Opus评估评分
│       ├── fetch_docs.py        # 3层文档检索
│       ├── generate_gold.py     # 黄金标准生成
│       ├── prompts.py           # 提示词库
│       └── repair_gold.py       # JSON修复工具
├── config/
│   └── settings.py             # 环境变量统一加载
├── data/                        # 所有数据资产（见第六节）
├── requirements.txt
└── .env.example
```

---

## 五、ETL 详细步骤

完整的9步数据管道，将原始维基百科数据转化为可检索的知识库：

### Step 1 — 原始数据采集
**脚本**：`src/etl/collect_wiki_full.py`

从HuggingFace数据集 `mrzjy/multimodal-genshin-impact` 流式下载全量原始数据：
- 原始规模：22,162页维基条目
- 保存格式：`data/raw/wiki/genshin_wiki_full.jsonl`
- 元数据清单：`data/metadata/wiki_schema.json`

### Step 2 — 结构化解析
**脚本**：`src/etl/parse.py`

将原始JSON解析为标准化格式：
- **实体类型推断**：从分类标签识别（PlayableCharacter、NPC、Location、Organization、Event、Weapon、Artifact、Boss...）
- **地区检测**：识别所属地区（须弥/璃月/蒙德/稻妻/枫丹）
- **内容清洗**：去除Markdown模板标签，计算内容哈希用于去重
- 输出：`data/processed/documents/wiki_parsed.jsonl`

### Step 3 — 须弥过滤
**脚本**：`src/etl/filter_sumeru.py`

多策略过滤，仅保留须弥相关内容：
- 关键词匹配（纳希达、学者会、草神、雨林、Alhaitham等）
- 分类标签检测
- 标题和内容双重检验
- 输出：`data/processed/documents/wiki_sumeru.jsonl`

### Step 4 — 清洗去重
**脚本**：`src/etl/clean.py`

高质量清洗：
- **内容哈希去重**：相同内容仅保留一份
- **别名标准化**：Scaramouche→Wanderer，流浪者→Wanderer 等约100条映射
- **版块过滤**：删除无信息版块（Info Card、Navigation、Gallery、版本历史）
- **空白规范化**：统一换行、去除冗余空格
- 最终输出：**4059条** `data/processed/documents/wiki_clean.jsonl`

### Step 5 — 章节感知分块
**脚本**：`src/etl/chunk.py`

保持语义完整性的智能分块：
- 配置：512 tokens，50 token重叠
- **章节边界感知**：优先在章节标题处切分
- **段落回退**：章节过长时在段落边界切分
- **句子回退**：最后回退到句子级别
- 每个chunk携带完整元数据：doc_id、title、section_title、entity_type、regions
- 输出：`data/processed/chunks/wiki_chunks.jsonl`

### Step 6 — 别名映射构建
**脚本**：`src/etl/build_alias_mapping.py`

构建实体别名解析表并写入DynamoDB：
- 支持中英文别名互查
- 运行时查询时自动将 "流浪者" → "Wanderer" 等解析为标准实体名

### Step 7 — 向量嵌入
**脚本**：`src/embed/embed.py`

批量生成语义向量：
- 模型：OpenAI `text-embedding-3-small`（1536维）
- 批量大小：100 chunks/次，含指数退避重试
- 断点续传：checkpoint支持中断恢复
- 成本控制：全量约$0.5
- 输出：`data/processed/embeddings/wiki_embeddings.jsonl`

### Step 8 — 知识图谱三元组提取
**脚本**：`src/graph/extract.py`

使用Claude Sonnet 4从文档提取结构化三元组：
- 优先处理~150个核心实体文档，其余按预算选取
- 总预算约$14
- 提取格式：`{"subject": "Nahida", "relation": "IS_ARCHON_OF", "object": "Sumeru", "evidence": "..."}`
- 输出：`data/processed/triples/entities.jsonl` + `triples.jsonl`

### Step 9 — 多目标加载
**脚本**：`src/graph/load.py`

一次性将数据加载至三个数据库：
1. **Pinecone**：批量upsert所有4059条向量+元数据
2. **Neo4j**：CREATE Entity节点 + MERGE关系边（Cypher批操作）
3. **DynamoDB**：实体元数据表 + 别名映射表

---

## 六、数据资产

```
data/
├── raw/
│   └── wiki/
│       ├── genshin_wiki_full.jsonl    # 22,162条原始维基条目
│       └── sample.jsonl              # 开发用小样本
│
├── processed/
│   ├── documents/
│   │   ├── wiki_clean.jsonl          # ★ 4,059条最终文档
│   │   ├── wiki_sumeru.jsonl         # 须弥过滤后（步骤3输出）
│   │   └── wiki_parsed.jsonl         # 解析后（步骤2输出）
│   ├── chunks/
│   │   └── wiki_chunks.jsonl         # ★ 分块后（步骤5输出）
│   ├── embeddings/
│   │   └── wiki_embeddings.jsonl     # ★ 向量化结果（4059条×1536维）
│   └── triples/
│       ├── entities.jsonl            # ★ ~1000+个实体
│       ├── triples.jsonl             # ★ ~2000+条关系三元组
│       └── extract_raw.jsonl         # LLM原始提取输出
│
├── metadata/
│   ├── wiki_schema.json              # 字段结构定义
│   ├── embedding_manifest.json       # 嵌入运行元数据
│   ├── extraction_manifest.json      # 三元组提取统计
│   └── load_manifest.json            # 数据库加载统计
│
└── ablation/
    ├── questions.jsonl               # ★ 50道测试问题（T1×10/T2×15/T3×13/T4×12）
    ├── gold_references.jsonl         # ★ 50条黄金参考答案（Phase 1）
    ├── oracle_checkpoint.json        # Oracle运行断点
    ├── runs/                         # Phase 2: 400条模型答案
    │   ├── S4-LLM.jsonl  S4-VEC.jsonl  S4-GRF.jsonl  S4-HYB.jsonl
    │   └── G4-LLM.jsonl  G4-VEC.jsonl  G4-GRF.jsonl  G4-HYB.jsonl
    └── eval/                         # Phase 3: 评估结果
        ├── S4-LLM.jsonl  ...  G4-HYB.jsonl  （逐题评分）
        └── summary.csv               # ★ 汇总得分表
```

**关键数字**：
- 原始文档：22,162条 → 过滤清洗后：4,059条（保留率18.3%）
- Neo4j实体节点：~1,000+，关系边：~2,000+
- Pinecone索引：4,059个向量，1536维
- 测试集：50题 × 8配置 = 400个模型答案

---

## 七、Agent 功能设计

### 整体架构

```
用户提问
    ↓
QueryProcessor（查询预处理）
    ├── 实体提取 & 别名解析
    ├── 查询类型分类（FACTUAL/RELATIONSHIP/MULTI_HOP/LIST/COMPARISON）
    └── 查询扩展（生成改写版本）
    ↓
HybridRetriever（混合检索）
    ├── [VEC] Pinecone语义检索
    ├── [GRF] Neo4j图谱路径查询
    └── [HYB] 两路融合 + 图谱重排序
    ↓
ContextAssembler（上下文组装）
    ├── Token预算分配（总6000：图1500 + 文4500）
    ├── 文档重排序（实体相关度评分）
    └── 格式化为提示词
    ↓
AnswerGenerator（答案生成）
    └── Claude Sonnet 4.6 → 含引用的结构化答案
```

### 7.1 QueryProcessor（查询处理器）

| 功能 | 实现 |
|------|------|
| **实体提取** | 正则 + Claude Haiku识别角色/地点/组织名 |
| **别名解析** | DynamoDB查表，"流浪者"→"Wanderer" |
| **查询分类** | Haiku语义分类（5种类型），决定检索策略 |
| **查询扩展** | 生成2-3个改写问题，扩大召回面 |
| **嵌入缓存** | LRU缓存，相同查询跳过API调用 |

### 7.2 HybridRetriever（混合检索器）

**向量检索路径**：
- Pinecone top_k语义检索（默认10条）
- 全文本块索引补充（text_loader.py）

**图谱检索路径**：
- Cypher查询实体直接关系（深度1-2）
- 最短路径发现（两实体间的关联链）
- 图谱排序：按证据质量、关系类型、目标相关度打分

**自适应深度控制**（adaptive_depth.py）：
- FACTUAL查询：深度1
- RELATIONSHIP查询：深度2
- MULTI_HOP查询：深度4
- 关键词触发器："间接"/"链"/"联系"等词→自动加深

### 7.3 ContextAssembler（上下文组装器）

- **Token预算管理**：图谱三元组1500 token + 文本段落4500 token
- **精确计数**：tiktoken cl100k_base，避免截断
- **重排序**：实体提及度 × 章节相关性评分
- **输出格式**：
  ```
  [Graph Relations]
  Nahida IS_ARCHON_OF Sumeru
  Nahida ALLY_OF Traveler

  [Context]
  [1] 《原神·须弥》Nahida is the current Dendro Archon...
  ```

### 7.4 AnswerGenerator（答案生成器）

- 模型：Claude Sonnet 4.6（消融对照：GPT-4o）
- 语言自动检测（中文问题→中文回答）
- 引用格式：`[Source: 文档标题]` / `[Relation: A → B]`
- 结构化返回：answer + sources + entities + path + timing + cost

---

## 八、消融实验结果

### 8.1 实验设计

| 配置代码 | 模型 | 检索策略 | 特点 |
|---------|------|---------|------|
| S4-LLM | Claude Sonnet 4 | 无检索 | 纯参数记忆基线 |
| S4-VEC | Claude Sonnet 4 | 向量检索 | 语义召回 |
| S4-GRF | Claude Sonnet 4 | 图谱检索 | 结构化关系 |
| S4-HYB | Claude Sonnet 4 | 混合检索 | 向量+图谱融合 |
| G4-LLM/VEC/GRF/HYB | GPT-4o | 同上四种 | 对照模型 |

评分公式：`总分 = 0.6 × 事实覆盖率 + 0.4 × 幻觉规避率`

评判模型：**Claude Opus 4.6**（Haiku理解能力不足，会错误惩罚多跳推理中的正确推理链）

### 8.2 最终结果

| 配置 | 总分 | 事实覆盖 | 幻觉规避 | T1 | T2 | T3 | T4 |
|------|------|---------|---------|----|----|----|----|
| **S4-HYB** | **0.683** | 0.566 | 0.858 | 0.772 | 0.625 | 0.756 | 0.601 |
| S4-VEC | 0.674 | 0.565 | 0.838 | 0.778 | 0.636 | 0.718 | 0.587 |
| S4-GRF | 0.516 | 0.242 | 0.929 | 0.534 | 0.560 | 0.520 | 0.443 |
| S4-LLM | 0.410 | 0.016 | 1.000 | 0.430 | 0.412 | 0.400 | 0.400 |
| **G4-HYB** | **0.583** | 0.430 | 0.813 | 0.644 | 0.604 | 0.606 | 0.481 |
| G4-VEC | 0.554 | 0.382 | 0.832 | 0.671 | 0.534 | 0.545 | 0.491 |
| G4-GRF | 0.476 | 0.174 | 0.930 | 0.513 | 0.528 | 0.431 | 0.431 |
| G4-LLM | 0.409 | 0.015 | 1.000 | 0.415 | 0.412 | 0.408 | 0.400 |

### 8.3 核心结论

**① HYB > VEC > GRF > LLM（对两个模型均成立）**

混合检索是最优策略；图谱三元组单独使用效果较差（缺乏散文上下文，模型难以组织连贯答案）。

**② LLM-only的"0.40地板效应"**

事实覆盖率≈0，但幻觉规避率=1.000，总分约0.41。两个模型对须弥世界观的参数记忆几乎为零——它们选择不作答，而非乱答。**这证明测试集设计有效，问题具有足够专业性**。

**③ Claude Sonnet 4全面领先GPT-4o，差距随检索丰富度变化**

| 检索级别 | S4得分 | G4得分 | 差值 |
|---------|-------|-------|------|
| LLM-only | 0.410 | 0.409 | +0.001 |
| VEC | 0.674 | 0.554 | +0.120 |
| GRF | 0.516 | 0.476 | +0.040 |
| HYB | 0.683 | 0.583 | +0.100 |

VEC差距最大（S4对检索文档利用效率更高）；HYB时GPT-4o追赶，差距从+0.120收窄至+0.100。

**④ T3复杂推理是HYB的主要贡献场景**

S4-HYB在T3上得0.756 vs S4-VEC的0.718（+0.038），证明图谱在需要跨实体推理的复杂问题上有明显加成。

**⑤ T4多跳推理是全局瓶颈**

所有配置T4得分最低，最优S4-HYB也仅0.601。多跳链式推理仍是未来需重点改进的方向。

---

## 九、总实验成本汇总

| 阶段 | 内容 | 成本 |
|------|------|------|
| ETL Step 7 | 4059条文档向量化 | ~$0.50 |
| ETL Step 8 | 三元组提取（Claude Sonnet） | ~$14.00 |
| Phase 1 | 50条黄金参考答案（Opus） | ~$22.46（估） |
| Phase 2 | 400条模型答案 | $4.32 |
| Phase 3 | 400条Opus评估 | $14.12 |
| **合计** | | **~$55** |
