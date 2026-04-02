# LoreMaster-AI 项目 - 数据采集与结构分析任务

## 项目背景

我正在开发 LoreMaster-AI，一个基于 GraphRAG 的原神（Genshin Impact）世界观智能问答系统。这是 UIUC IS596 云数据工程课程的 capstone 项目。

系统目标：
- 回答关于游戏剧情的事实性问题
- 展示角色间的复杂关系网络
- 进行多跳逻辑推理（如"散兵和纳西妲有什么联系"）
- 验证并纠正用户的错误认知

Demo 范围聚焦须弥（Sumeru）地区，约 70 个实体和 200-500 个关系。

## 已完成的基础设施

所有服务已配置并通过验证测试：

### AWS 服务
- S3 Bucket: `loremaster-ai-{netid}`，已创建完整目录结构
  - `raw/wiki/`, `raw/api/`, `raw/github/`
  - `processed/documents/`, `processed/chunks/`, `processed/embeddings/`, `processed/triples/`
  - `metadata/schemas/`, `metadata/manifests/`
  - `config/filters/`
- DynamoDB 表：
  - `loremaster-entity-metadata` (PK: entity_type, SK: entity_id)
  - `loremaster-data-versions` (PK: source_id, SK: resource_id)
  - `loremaster-alias-mapping` (PK: alias)
- IAM 角色 `LoreMasterLambdaRole` 已创建

### 外部服务
- Neo4j AuraDB: 免费实例已创建，用于知识图谱存储
- Pinecone: Serverless 索引已创建，维度 1536，用于向量检索
- HuggingFace: Token 已配置
- Anthropic: API Key 已配置

### 本地项目结构
```
loremaster-ai/
├── data/
│   ├── raw/wiki/, raw/api/, raw/github/
│   ├── processed/
│   └── metadata/
├── src/
│   ├── ingestion/
│   ├── etl/
│   └── agent/
├── config/
│   ├── __init__.py
│   └── settings.py      # 所有配置项，从 .env 加载
├── tests/
│   ├── __init__.py
│   └── test_setup.py    # 验证脚本，已通过
├── docs/
├── .env                 # 包含所有凭证
├── .env.example
├── .gitignore
├── requirements.txt     # 已安装所有依赖
├── PROJECT_CONTEXT.md   # 项目上下文文档
└── venv/                # Python 虚拟环境
```

## 数据源信息

### 1. Fandom Wiki 数据集（主要数据源）
- HuggingFace: `mrzjy/multimodal-genshin-impact`
- 规模：22,162 个 Wiki 页面
- 格式：JSONL
- 内容：角色、地点、剧情、物品等百科内容

### 2. GenshinDialog 对话语料
- GitHub: `mrzjy/GenshinDialog`
- 规模：170,202 条对话
- 内容：游戏内角色对话

### 3. genshin-db 结构化数据
- NPM/GitHub: `theBowja/genshin-db`
- 内容：角色属性、武器、材料等结构化数据

## 当前任务

**目标**：采集少量样本数据并分析数据结构，为 ETL 流水线设计提供前置信息。

### 任务 1：采集 Wiki 数据样本

从 HuggingFace 下载 100-200 条 Wiki 数据：
- 使用 streaming 模式避免下载全量数据
- 优先获取包含须弥相关内容的记录（关键词：Sumeru, 须弥, Nahida, 纳西妲, Akademiya, 教令院）
- 保存原始 JSON 结构到 `data/raw/wiki/sample.jsonl`
- 记录采集元数据到 `data/metadata/wiki_sample_manifest.json`

### 任务 2：采集对话数据样本

从 GitHub 下载 GenshinDialog 的样本数据：
- 下载 100-200 条对话记录
- 保存到 `data/raw/github/dialog_sample.jsonl`

### 任务 3：分析数据结构

对采集的数据进行深度分析，输出：

1. **字段分析** (`data/metadata/wiki_schema.json`)
   - 所有字段名称和数据类型
   - 各字段的非空率
   - 示例值

2. **实体识别分析**
   - 哪些字段可作为实体 ID
   - 哪些字段包含实体名称
   - 分类/标签字段

3. **关系线索分析**
   - 是否有引用其他页面的字段
   - 是否有明确的关系描述字段

4. **文本内容分析**
   - 主要文本字段识别
   - 平均文本长度
   - 文本格式（Markdown/HTML/纯文本）

5. **分析报告** (`docs/data_structure_analysis.md`)
   - 人类可读的完整分析报告
   - 对 ETL 设计的建议
   - 须弥数据筛选策略建议

## 须弥筛选关键词参考
```python
SUMERU_KEYWORDS = {
    "characters": [
        "纳西妲", "Nahida", "艾尔海森", "Alhaitham", "提纳里", "Tighnari",
        "赛诺", "Cyno", "妮露", "Nilou", "迪希雅", "Dehya", "多莉", "Dori",
        "柯莱", "Collei", "坎蒂丝", "Candace", "莱依拉", "Layla",
        "散兵", "Scaramouche", "流浪者", "Wanderer", "卡维", "Kaveh"
    ],
    "locations": [
        "须弥", "Sumeru", "净善宫", "Sanctuary of Surasthana",
        "教令院", "Akademiya", "桓那兰那", "Vanarana", "须弥城"
    ],
    "organizations": [
        "须弥教令院", "愚人众", "Fatui", "镀金旅团"
    ],
    "concepts": [
        "禁忌知识", "Forbidden Knowledge", "世界树", "Irminsul",
        "草神", "Dendro Archon", "大慈树王", "Greater Lord Rukkhadevata"
    ]
}
```

## 知识图谱 Schema 参考

### 节点类型
- Character（角色）
- Location（地点）
- Organization（组织）
- Event（事件）
- Item（物品）
- Concept（概念）

### 关系类型
- CREATED, BORN_FROM, SUCCEEDED, MEMBER_OF, LOCATED_IN
- CONFINED, CONSPIRED_AGAINST, CAUSED, DESTROYED, ALLIED_WITH

## 技术要求

- 使用 `config/settings.py` 中的配置
- 使用虚拟环境中已安装的依赖
- 代码放在 `src/ingestion/` 目录
- 遵循 Python 最佳实践，添加适当的错误处理和日志

## 预期产出

1. `src/ingestion/collect_wiki_sample.py` - Wiki 数据采集脚本
2. `src/ingestion/collect_dialog_sample.py` - 对话数据采集脚本
3. `src/ingestion/analyze_data_structure.py` - 数据结构分析脚本
4. `data/raw/wiki/sample.jsonl` - Wiki 样本数据
5. `data/raw/github/dialog_sample.jsonl` - 对话样本数据
6. `data/metadata/wiki_schema.json` - Wiki 数据 Schema
7. `data/metadata/dialog_schema.json` - 对话数据 Schema
8. `data/metadata/wiki_sample_manifest.json` - 采集元数据
9. `docs/data_structure_analysis.md` - 完整分析报告

请先阅读 `config/settings.py` 和 `PROJECT_CONTEXT.md` 了解项目配置，然后开始执行任务。
