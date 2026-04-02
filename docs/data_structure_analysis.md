# LoreMaster-AI Data Structure Analysis Report

Generated: 2026-02-02 22:11 UTC


## 1. Dataset Overview

| Dataset | Records | Fields |

|---------|---------|--------|

| Wiki Sample | 200 | 4 |

| Dialog Sample | 200 | 29 |


## 2. Wiki Data Field Analysis


| Field | Type | Non-null Rate | Unique Count | Avg Length |

|-------|------|---------------|--------------|------------|

| `category` | array | 100.0% | - | - |

| `markdown` | string | 100.0% | 200 | 3361.7 |

| `sections` | array | 100.0% | - | - |

| `url` | string | 100.0% | 200 | 62.1 |


### 2.1 Field Details

**`category`** (array)

- Non-null rate: 100.0%

- Array length: min=2, max=21, avg=7.4

- Examples: `["Characters", "NPCs", "Open-World NPCs", "Sumpter Beast NPCs", "Sumeru Characters", "NPCs Located in Sumeru", "Released in Version 3.1"]`


**`markdown`** (string)

- Non-null rate: 100.0%

- String length: min=158, max=41865, avg=3361.7, median=1557

- Format: contains markdown

- Examples: `# "Cyrus"

"Cyrus" is a Desert Sumpter Beast and an NPC located in Aaru Village, Sumeru. It will only appear after completing the *Golden Slumber* World Quest series.

## Info Card
"Cyrus"
---

![NPC ...`


**`sections`** (array)

- Non-null rate: 100.0%

- Array length: min=3, max=23, avg=8.5

- Examples: `[{"title": "\"Cyrus\"", "level": 0, "markdown": "# \"Cyrus\""}, {"title": "", "level": -1, "markdown": "\"Cyrus\" is a Desert Sumpter Beast and an NPC located in Aaru Village, Sumeru. It will only app...`


**`url`** (string)

- Non-null rate: 100.0%

- String length: min=43, max=96, avg=62.1, median=61

- Examples: `https://genshin-impact.fandom.com/wiki/%22Cyrus%22`


## 3. Dialog Data Field Analysis


| Field | Type | Non-null Rate | Unique Count | Avg Length |

|-------|------|---------------|--------------|------------|

| `_language` | string | 100.0% | 2 | 2.6 |

| `_source_file` | string | 100.0% | 18 | 32.7 |

| `_source_type` | string | 100.0% | 9 | 7.1 |

| `avatarConstellationAfter` | string | 3.5% | 7 | 5.6 |

| `avatarConstellationBefor` | string | 62.0% | 123 | 6.1 |

| `avatarDetail` | string | 62.0% | 124 | 56.9 |

| `avatarNative` | string | 62.0% | 87 | 7.8 |

| `avatarTitle` | string | 61.5% | 123 | 8.6 |

| `avatarVisionAfter` | string | 3.5% | 6 | 1.6 |

| `avatarVisionBefor` | string | 62.0% | 15 | 2.1 |

| `chapterNum` | object | 3.0% | - | - |

| `chapterTitle` | object | 3.0% | - | - |

| `character_name` | string | 62.0% | 124 | 3.9 |

| `cvChinese` | string | 62.0% | 78 | 2.9 |

| `cvEnglish` | string | 62.0% | 122 | 9.2 |

| `cvJapanese` | string | 62.0% | 112 | 4.3 |

| `cvKorean` | string | 62.0% | 119 | 6.0 |

| `desc` | string | 62.0% | 124 | 56.9 |

| `dialogList` | array | 15.0% | - | - |

| `id` | integer | 15.0% | 16 | - |

| `infoBirthDay` | string | 61.5% | 30 | 1.8 |

| `infoBirthMonth` | string | 61.5% | 12 | 1.2 |

| `mainQuestDesp` | object | 3.0% | - | - |

| `mainQuestId` | integer | 3.0% | 3 | - |

| `mainQuestTitle` | object | 3.0% | - | - |

| `sayings` | array | 62.0% | - | - |

| `story` | array | 62.0% | - | - |

| `subQuests` | array | 3.0% | - | - |

| `turns` | array | 20.0% | - | - |


### 3.1 Field Details

**`_language`** (string)

- Non-null rate: 100.0%

- String length: min=2, max=3, avg=2.6

- Values: CHS, EN

- Examples: `CHS`


**`_source_file`** (string)

- Non-null rate: 100.0%

- String length: min=30, max=38, avg=32.7

- Values: extracted_avatar/avatar_CHS.json, extracted_avatar/avatar_EN.json, extracted_dialog/dialog_CHS.jsonl, extracted_dialog/dialog_EN.jsonl, extracted_dialog/raw_dialog_CHS.jsonl, extracted_dialog/raw_dialog_EN.jsonl, extracted_quest/quest_CHS.jsonl, extracted_quest/quest_EN.jsonl, extracted_talk/talk_activity_CHS.jsonl, extracted_talk/talk_activity_EN.jsonl, extracted_talk/talk_blossom_CHS.jsonl, extracted_talk/talk_blossom_EN.jsonl, extracted_talk/talk_coop_CHS.jsonl, extracted_talk/talk_coop_EN.jsonl, extracted_talk/talk_gadget_CHS.jsonl, extracted_talk/talk_gadget_EN.jsonl, extracted_talk/talk_npc_CHS.jsonl, extracted_talk/talk_npc_EN.jsonl

- Examples: `extracted_dialog/dialog_CHS.jsonl`


**`_source_type`** (string)

- Non-null rate: 100.0%

- String length: min=5, max=13, avg=7.1

- Values: avatar, dialog, quest, raw_dialog, talk_activity, talk_blossom, talk_coop, talk_gadget, talk_npc

- Examples: `dialog`


**`avatarConstellationAfter`** (string)

- Non-null rate: 3.5%

- String length: min=3, max=15, avg=5.6

- Values: Animula Choragi, 原海巨灵座, 司颂座, 天下人座, 岩王帝君座, 智慧主座, 歌仙座

- Examples: `歌仙座`


**`avatarConstellationBefor`** (string)

- Non-null rate: 62.0%

- String length: min=3, max=21, avg=6.1

- Examples: `三清铃座`


**`avatarDetail`** (string)

- Non-null rate: 62.0%

- String length: min=15, max=254, avg=56.9

- Examples: `药庐「不卜庐」的采药姑娘兼学徒，面色苍白如纸的不死之人。话很少，也没有什么表情。`


**`avatarNative`** (string)

- Non-null rate: 62.0%

- String length: min=1, max=43, avg=7.8

- Examples: `不卜庐`


**`avatarTitle`** (string)

- Non-null rate: 61.5%

- String length: min=3, max=32, avg=8.6

- Examples: `冻冻回魂夜`


**`avatarVisionAfter`** (string)

- Non-null rate: 3.5%

- String length: min=1, max=5, avg=1.6

- Values: Hydro, 岩, 水, 草, 雷, 风

- Examples: `风`


**`avatarVisionBefor`** (string)

- Non-null rate: 62.0%

- String length: min=1, max=7, avg=2.1

- Values: Anemo, Cryo, Dendro, Electro, Geo, Hydro, Pyro, 冰, 岩, 无, 水, 火, 草, 雷, 风

- Examples: `冰`


**`chapterNum`** (object)

- Non-null rate: 3.0%

- Examples: `{"textId": "第一章 第一幕", "textType": "ChapterNum"}`


**`chapterTitle`** (object)

- Non-null rate: 3.0%

- Examples: `{"textId": "浮世浮生千岩间", "textType": "ChapterTitle"}`


**`character_name`** (string)

- Non-null rate: 62.0%

- String length: min=1, max=16, avg=3.9

- Examples: `七七`


**`cvChinese`** (string)

- Non-null rate: 62.0%

- String length: min=2, max=10, avg=2.9

- Examples: `宴宁`


**`cvEnglish`** (string)

- Non-null rate: 62.0%

- String length: min=1, max=26, avg=9.2

- Examples: `克莉斯蒂·凯特`


**`cvJapanese`** (string)

- Non-null rate: 62.0%

- String length: min=3, max=11, avg=4.3

- Examples: `田村由加莉`


**`cvKorean`** (string)

- Non-null rate: 62.0%

- String length: min=2, max=25, avg=6.0

- Examples: `李露`


**`desc`** (string)

- Non-null rate: 62.0%

- String length: min=15, max=254, avg=56.9

- Examples: `药庐「不卜庐」的采药姑娘兼学徒，面色苍白如纸的不死之人。话很少，也没有什么表情。`


**`dialogList`** (array)

- Non-null rate: 15.0%

- Array length: min=1, max=13, avg=4.0

- Examples: `[{"id": 10002221, "nextDialogs": [10002222], "role": "调查岩王帝君尸体", "content": "（巨大的仙体已经失去气息…）", "role_type": "TALK_ROLE_NPC"}, {"id": 10002222, "nextDialogs": null, "role": "调查岩王帝君尸体", "content": "（那时候，...`


**`id`** (integer)

- Non-null rate: 15.0%

- Values: 1, 10, 100, 100103, 100805, 100898, 1101925, 1101926, 1101927, 4002015, 4002115, 4002212, 5900003, 5900004, 5900007, 7

- Examples: `100103`


**`infoBirthDay`** (string)

- Non-null rate: 61.5%

- String length: min=1, max=2, avg=1.8

- Examples: `3`


**`infoBirthMonth`** (string)

- Non-null rate: 61.5%

- String length: min=1, max=2, avg=1.2

- Values: 1, 10, 11, 12, 2, 3, 4, 5, 6, 7, 8, 9

- Examples: `3`


**`mainQuestDesp`** (object)

- Non-null rate: 3.0%

- Examples: `{"textId": "在璃月之地的海边，有一座伫立于坚岩的城市，「璃月港」。庇护着这座城市与璃月全境的，是你所要寻找的岩之神摩拉克斯，又名「岩王帝君」。你抵达璃月港时，恰逢一年一度的「七星请仙典仪」。每年的这一日里，岩王帝君都会赐下神谕，指引这一年璃月经营的方向。", "textType": "MainQuestDesp"}`


**`mainQuestId`** (integer)

- Non-null rate: 3.0%

- Values: 1000, 1002, 1003

- Examples: `1000`


**`mainQuestTitle`** (object)

- Non-null rate: 3.0%

- Examples: `{"textId": "请仙", "textType": "MainQuestTitle"}`


**`sayings`** (array)

- Non-null rate: 62.0%

- Array length: min=57, max=410, avg=74.3

- Examples: `["初次见面…\t我是七七，是个僵尸…啊，还要说什么来着。", "闲聊·自言自语\t咦，刚刚…我想说什么来着…", "闲聊·怕热\t想去凉快点的地方。", "闲聊·锻炼\t七二三四，七二三四…五六七七，五六七七…", "下雨的时候…\t又忘记带伞了。", "下雪的时候…\t想堆雪人…可以陪我吗？", "阳光很好…\t今天不该出门的。", "起风的时候…\t凉凉的，很舒服。", "刮大风了…\t拉手...`


**`story`** (array)

- Non-null rate: 62.0%

- Array length: min=6, max=16, avg=8.0

- Examples: `["角色详细\t因为是僵尸，所以缺乏面部表情也是可以原谅的吧。\n别看是僵尸，其实一直有认真在锻炼身体。\n记忆力极差。忘性太大也是对人冰冷的原因之一。\n外表永远停留在了逝去那年，年龄不可考。\n僵尸需要听从敕令行动。但因为某些原因，七七现在是自己给自己下敕令的状态。", "角色故事1\t通常来说，僵尸的躯体又冷又僵，使得他们只能一跳一跳地行动。\n为了保持接近正常人的状态，七七一直在做柔软体操...`


**`subQuests`** (array)

- Non-null rate: 3.0%

- Array length: min=4, max=15, avg=11.0

- Examples: `[{"subQuestTitle": {"textId": "前往璃月港", "textType": "SubQuestTitle"}}, {"subQuestTitle": {"textId": "与派蒙交谈", "textType": "SubQuestTitle"}, "items": [{"itemId": 3, "itemType": "SingleDialog", "nextItemI...`


**`turns`** (array)

- Non-null rate: 20.0%

- Array length: min=2, max=32, avg=5.8

- Examples: `[{"role": "便条", "content": "「有朋友来找我喝酒。暂时歇业。店主 留」"}, {"role": "派蒙", "content": "蒙德人真的这么喜欢喝酒吗？"}]`


## 4. Entity Identification Analysis


### 4.1 Entity ID Candidates

- **`markdown`**: type=string, null_rate=0.0, unique_count=200

- **`url`**: type=string, null_rate=0.0, unique_count=200


### 4.2 Entity Name Candidates

No fields with 'name' or 'title' in their name found. Will need to identify naming fields from content.


### 4.3 Category / Tag Fields

- **`category`**: type=array

- **`sections`**: type=array


## 5. Relationship Clue Analysis


- Cross-page references (wiki-links `[[...]]`): **No**

- No explicit relationship fields found. Relationships will need to be extracted from text content using NER + LLM.


## 6. Text Content Analysis


### 6.1 Primary Text Fields

- **`markdown`**: avg_length=3361.7, max_length=41865

  - Contains: markdown


### 6.2 Text Format Summary

Detected formats in text fields: **markdown**


## 7. ETL Design Recommendations


### 7.1 Parse Stage

- Convert raw JSONL to standardised Parquet format.

- Map fields to a unified document schema (doc_id, title, content, source_url, categories, etc.).


### 7.2 Filter Stage (Sumeru)

Recommended filtering strategy for Sumeru-scoped Demo:

- **Category-based filtering**: Use fields `category, sections` to match Sumeru categories.

- **Keyword-based filtering**: Scan title and content fields for Sumeru keywords.

- **Whitelist-based filtering**: Maintain an explicit entity whitelist for known Sumeru characters/locations.


### 7.3 Clean Stage

- Deduplicate records using content hash (SHA256).

- Entity disambiguation: Build alias mapping (e.g., 纳西妲 / 小吉祥草王 / 草神 → Nahida).

- Standardise text encoding and normalise whitespace.


### 7.4 Chunk Stage

- Longest text field has max_length=41865, avg_length=3361.7.

- With chunk_size=512 tokens (~2048 chars), most documents will produce 1-20 chunks.

- Use recursive text splitter with section-aware boundaries.

- Preserve metadata (entity_id, section heading) in each chunk.


### 7.5 Extract Stage (Knowledge Graph)

- Use NER to identify entity mentions in text.

- Use LLM (Claude) with structured prompts to extract (subject, relation, object) triples.

- Map extracted entities to the canonical entity IDs via alias table.

- Target schema: 6 node types (Character, Location, Organisation, Event, Item, Concept).

- Target relations: CREATED, BORN_FROM, SUCCEEDED, MEMBER_OF, LOCATED_IN, CONFINED, etc.

