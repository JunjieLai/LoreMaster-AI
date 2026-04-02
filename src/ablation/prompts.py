"""
Oracle Generation Prompts
All prompt templates for Phase 1: Gold Reference generation and QC self-verification.
"""

# ---------------------------------------------------------------------------
# Oracle Generation Prompt
# ---------------------------------------------------------------------------

ORACLE_SYSTEM = """\
你是一个严谨的知识图谱评估专家，专门为原神（Genshin Impact）须弥剧情设计评测基准。

你的黄金准则：
1. 你的唯一知识来源是下方提供的参考文档原文。
2. 严禁使用你自身对原神剧情的训练记忆——如果文档中没有明确依据，必须标注 "verified": false。
3. 每一个 key_fact 必须注明来自哪篇文档（doc_source 字段填写文档标题）。
4. 如果文档信息不足以回答某部分，在 coverage_notes 中明确说明具体缺口。
"""

ORACLE_USER = """\
## 参考文档
{docs_text}

---

## 评估题目（ID: {question_id}，Tier {tier}，类型: {question_type}）
{question}

---

## 输出要求
请严格基于以上参考文档，生成结构化 Gold Reference。
对于 counterfactual 类型的题目，key_facts 应聚焦于推理所需的事实前提，
required_reasoning_steps 字段替代 required_relations。

请严格输出以下 JSON 格式，不要添加任何 Markdown 代码块标记：

{{
  "question_id": "{question_id}",
  "tier": {tier},
  "question_type": "{question_type}",
  "key_facts": [
    {{"fact": "具体事实描述", "doc_source": "文档标题", "verified": true}},
    ...
  ],
  "required_entities": ["实体1", "实体2", ...],
  "required_relations": [
    {{"head": "实体A", "relation": "关系类型", "tail": "实体B", "doc_source": "文档标题"}}
  ],
  "required_reasoning_steps": [],
  "hallucination_traps": [
    {{"trap": "常见错误/混淆描述", "correct": "正确内容"}}
  ],
  "min_acceptable_facts": 3,
  "coverage_notes": "如有信息缺口，在此列出具体缺失内容；若文档充分，写 none"
}}
"""

# ---------------------------------------------------------------------------
# QC Self-Verification Prompt (appended in same session)
# ---------------------------------------------------------------------------

QC_VERIFY = """\
请对你刚才生成的 Gold Reference 进行自我审查，完成以下三项检查：

**检查1 — 来源验证**
逐条审查每个 key_fact。对于任何依据来自你的训练记忆（而非上方提供文档）的条目，
将其 verified 字段改为 false，并在该条目末尾添加 "memory_source": true。

**检查2 — 幻觉陷阱完整性**
评估 hallucination_traps 是否覆盖了以下两类风险：
  a) 将训练数据中的常见错误信息带入此题
  b) 将其他角色/地点/事件的相似细节混淆代入
如有遗漏，直接补充到列表中。

**检查3 — 信息缺口**
题目要求的哪些具体信息，在提供的文档中完全找不到依据？
在 coverage_notes 中用要点格式列出（如："缺：XXX 的具体称号来源文档"）。

请直接输出修订后的完整 JSON（保持原有结构，只修改有问题的字段）。
输出纯 JSON，不要任何 Markdown 标记。
"""

# ---------------------------------------------------------------------------
# Haiku Entity Extraction Prompt
# ---------------------------------------------------------------------------

ENTITY_EXTRACT_SYSTEM = """\
你是一个信息抽取助手。从用户提供的问题中提取所有原神相关的专有名词，
包括：角色名、地点名、组织名、事件名、物品名、系统名。
输出纯 JSON 数组，不要任何其他内容。
"""

ENTITY_EXTRACT_USER = """\
请从以下问题中提取所有原神相关专有名词（包括中英文名称）：

{question}

输出格式（纯 JSON 数组）：["实体1", "实体2", ...]
"""
