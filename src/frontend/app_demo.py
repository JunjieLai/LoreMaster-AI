"""
LoreMaster-AI - Frontend Demo
Genshin Impact styled Q&A interface with expandable sources and relationship graph.
"""

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config
import time

# ============================================
# Page Configuration
# ============================================
st.set_page_config(
    page_title="LoreMaster-AI | 原神考据助手",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================
# Genshin Impact Styled CSS
# ============================================
GENSHIN_CSS = """
<style>
/* Import fonts */
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500&display=swap');

/* Root variables */
:root {
    --genshin-gold: #D4A053;
    --genshin-gold-light: #E8C87A;
    --genshin-dark: #1B1D2A;
    --genshin-panel: #2A2D3E;
    --genshin-panel-light: #363A4F;
    --genshin-text: #E8E4DC;
    --genshin-text-dim: #9A9A9A;
    --genshin-accent: #6BB5FF;
    --sumeru-green: #7BC86C;
    --pyro-red: #EF7A35;
    --electro-purple: #B07BCC;
}

/* Global styles */
.stApp {
    background: linear-gradient(135deg, #1B1D2A 0%, #0D0F1A 100%);
    font-family: 'Noto Sans SC', sans-serif;
}

/* Hide Streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display: none;}

/* Header styling */
.main-header {
    text-align: center;
    padding: 1.5rem 0;
    border-bottom: 2px solid var(--genshin-gold);
    margin-bottom: 2rem;
    background: linear-gradient(180deg, rgba(212, 160, 83, 0.1) 0%, transparent 100%);
}

.main-header h1 {
    font-family: 'Noto Serif SC', serif;
    color: var(--genshin-gold);
    font-size: 2.5rem;
    margin: 0;
    text-shadow: 0 0 20px rgba(212, 160, 83, 0.3);
}

.main-header .subtitle {
    color: var(--genshin-text-dim);
    font-size: 1rem;
    margin-top: 0.5rem;
}

/* Chat container */
.chat-container {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 1rem;
}

/* Message bubbles */
.user-message {
    background: linear-gradient(135deg, var(--genshin-panel) 0%, var(--genshin-panel-light) 100%);
    border: 1px solid var(--genshin-gold);
    border-radius: 12px 12px 4px 12px;
    padding: 1rem 1.2rem;
    margin: 1rem 0;
    color: var(--genshin-text);
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}

.ai-message {
    background: linear-gradient(135deg, #1E2030 0%, var(--genshin-panel) 100%);
    border: 1px solid rgba(212, 160, 83, 0.3);
    border-radius: 12px 12px 12px 4px;
    padding: 1.2rem;
    margin: 1rem 0;
    color: var(--genshin-text);
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}

.ai-message .answer-text {
    line-height: 1.8;
    font-size: 1rem;
}

/* Source cards */
.sources-section {
    margin-top: 1.5rem;
    border-top: 1px solid rgba(212, 160, 83, 0.2);
    padding-top: 1rem;
}

.sources-header {
    color: var(--genshin-gold);
    font-size: 0.9rem;
    font-weight: 600;
    margin-bottom: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.source-card {
    background: var(--genshin-panel);
    border: 1px solid rgba(212, 160, 83, 0.2);
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin: 0.5rem 0;
    transition: all 0.3s ease;
    cursor: pointer;
}

.source-card:hover {
    border-color: var(--genshin-gold);
    box-shadow: 0 0 15px rgba(212, 160, 83, 0.2);
    transform: translateY(-2px);
}

.source-card .card-header {
    display: flex;
    align-items: center;
    gap: 0.8rem;
}

.source-card .entity-icon {
    font-size: 1.5rem;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(212, 160, 83, 0.1);
    border-radius: 8px;
}

.source-card .card-title {
    color: var(--genshin-gold-light);
    font-weight: 600;
    font-size: 1rem;
}

.source-card .card-meta {
    color: var(--genshin-text-dim);
    font-size: 0.8rem;
    margin-top: 0.2rem;
}

.source-card .relevance-badge {
    margin-left: auto;
    background: rgba(107, 181, 255, 0.2);
    color: var(--genshin-accent);
    padding: 0.2rem 0.6rem;
    border-radius: 12px;
    font-size: 0.75rem;
}

.source-card .card-content {
    margin-top: 0.8rem;
    padding-top: 0.8rem;
    border-top: 1px solid rgba(255,255,255,0.1);
    color: var(--genshin-text);
    font-size: 0.9rem;
    line-height: 1.6;
}

.source-card .wiki-link {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    color: var(--genshin-accent);
    text-decoration: none;
    font-size: 0.85rem;
    margin-top: 0.8rem;
    padding: 0.4rem 0.8rem;
    background: rgba(107, 181, 255, 0.1);
    border-radius: 6px;
    transition: all 0.2s;
}

.source-card .wiki-link:hover {
    background: rgba(107, 181, 255, 0.2);
}

/* Graph section */
.graph-section {
    margin-top: 1.5rem;
    border-top: 1px solid rgba(212, 160, 83, 0.2);
    padding-top: 1rem;
}

.graph-header {
    color: var(--genshin-gold);
    font-size: 0.9rem;
    font-weight: 600;
    margin-bottom: 0.8rem;
}

.graph-container {
    background: rgba(0,0,0,0.3);
    border-radius: 12px;
    padding: 1rem;
    border: 1px solid rgba(212, 160, 83, 0.2);
}

/* Config selector */
.config-selector {
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 1000;
}

/* Input area */
.stTextInput input {
    background: var(--genshin-panel) !important;
    border: 2px solid rgba(212, 160, 83, 0.3) !important;
    border-radius: 12px !important;
    color: var(--genshin-text) !important;
    padding: 0.8rem 1rem !important;
    font-size: 1rem !important;
}

.stTextInput input:focus {
    border-color: var(--genshin-gold) !important;
    box-shadow: 0 0 15px rgba(212, 160, 83, 0.3) !important;
}

.stButton button {
    background: linear-gradient(135deg, var(--genshin-gold) 0%, #C49347 100%) !important;
    color: var(--genshin-dark) !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    font-weight: 600 !important;
    transition: all 0.3s !important;
}

.stButton button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 15px rgba(212, 160, 83, 0.4) !important;
}

/* Expander styling */
.streamlit-expanderHeader {
    background: var(--genshin-panel) !important;
    border: 1px solid rgba(212, 160, 83, 0.3) !important;
    border-radius: 8px !important;
    color: var(--genshin-text) !important;
}

/* Select box */
.stSelectbox > div > div {
    background: var(--genshin-panel) !important;
    border-color: rgba(212, 160, 83, 0.3) !important;
    color: var(--genshin-text) !important;
}

/* Metadata badges */
.metadata-container {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 1rem;
}

.metadata-badge {
    background: rgba(123, 200, 108, 0.15);
    color: var(--sumeru-green);
    padding: 0.3rem 0.8rem;
    border-radius: 12px;
    font-size: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.3rem;
}

.metadata-badge.timing {
    background: rgba(107, 181, 255, 0.15);
    color: var(--genshin-accent);
}

.metadata-badge.cost {
    background: rgba(239, 122, 53, 0.15);
    color: var(--pyro-red);
}

/* Path visualization */
.path-container {
    background: rgba(0,0,0,0.2);
    border-radius: 8px;
    padding: 1rem;
    margin-top: 1rem;
}

.path-step {
    display: flex;
    align-items: center;
    padding: 0.5rem 0;
}

.path-node {
    background: var(--genshin-panel);
    border: 1px solid var(--genshin-gold);
    border-radius: 8px;
    padding: 0.4rem 0.8rem;
    color: var(--genshin-gold-light);
    font-weight: 500;
}

.path-arrow {
    color: var(--genshin-text-dim);
    margin: 0 0.5rem;
    font-size: 0.9rem;
}

.path-relation {
    color: var(--genshin-accent);
    font-size: 0.85rem;
    font-style: italic;
}

/* Animation keyframes */
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.animate-fade-in {
    animation: fadeInUp 0.5s ease-out;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

.loading-indicator {
    animation: pulse 1.5s infinite;
    color: var(--genshin-gold);
}
</style>
"""

# ============================================
# Entity Type Icons
# ============================================
ENTITY_ICONS = {
    "Character": "🎭",
    "NPC": "👤",
    "Location": "🏛️",
    "Region": "🗺️",
    "Lore": "📜",
    "Quest": "📖",
    "Weapon": "⚔️",
    "Artifact": "🔮",
    "Organization": "🏰",
    "Event": "⚡",
    "Concept": "💫",
    "default": "📄"
}

def get_entity_icon(entity_type: str) -> str:
    return ENTITY_ICONS.get(entity_type, ENTITY_ICONS["default"])

# ============================================
# Mock Data for Demo
# ============================================
DEMO_RESPONSE = {
    "answer": """赤王（King Deshret）与花神纳布·玛丽卡塔（Nabu Malikata）的关系是原神须弥深层叙事中最重要的三角关系之一。

**关系概述**：
赤王、花神和大慈树王（Greater Lord Rukkhadevata）曾是亲密的盟友，共同治理须弥沙漠地区。赤王与花神之间存在深厚的情感羁绊，根据游戏内文本暗示，这份关系超越了普通的同盟。

**关键历史事件**：
1. **共同统治时期**：三位神明曾共同建立繁荣的沙漠文明
2. **禁忌知识事件**：花神为保护赤王，以身殉道，吸收了被禁止的知识
3. **赤王的堕落**：失去花神后，赤王陷入疯狂，最终导致沙漠文明的毁灭

[Source: King Deshret and the Three Magi]
[Source: The Lay of Al-Ahmar]""",
    "sources": [
        {
            "title": "King Deshret",
            "entity_type": "Character",
            "section": "Lore",
            "score": 0.92,
            "text": "King Deshret, also known as Al-Ahmar, was one of the three God-Kings who ruled Sumeru in ancient times. He was known for his pursuit of forbidden knowledge and his tragic love for the Goddess of Flowers...",
            "source_url": "https://genshin-impact.fandom.com/wiki/King_Deshret",
            "region": "Sumeru"
        },
        {
            "title": "Nabu Malikata",
            "entity_type": "Character",
            "section": "History",
            "score": 0.89,
            "text": "Nabu Malikata, the Goddess of Flowers, was a divine being who ruled alongside King Deshret and Greater Lord Rukkhadevata. She sacrificed herself to protect King Deshret from the forbidden knowledge...",
            "source_url": "https://genshin-impact.fandom.com/wiki/Nabu_Malikata",
            "region": "Sumeru"
        },
        {
            "title": "The Lay of Al-Ahmar",
            "entity_type": "Lore",
            "section": "Content",
            "score": 0.85,
            "text": "An ancient poem that tells the story of King Deshret's rise and fall, his relationship with the Goddess of Flowers, and the destruction of the desert civilization...",
            "source_url": "https://genshin-impact.fandom.com/wiki/The_Lay_of_Al-Ahmar",
            "region": "Sumeru"
        },
    ],
    "path": {
        "nodes": ["King Deshret", "Nabu Malikata"],
        "relations": ["LOVED"],
        "evidences": ["The Goddess of Flowers sacrificed herself for King Deshret"],
        "alternative_paths": [
            {
                "nodes": ["King Deshret", "Greater Lord Rukkhadevata", "Nabu Malikata"],
                "relations": ["ALLIED_WITH", "FRIEND_OF"]
            }
        ]
    },
    "entities": ["King Deshret", "Nabu Malikata", "Greater Lord Rukkhadevata"],
    "query_type": "RELATIONSHIP",
    "timing": {"total": 2.45, "retrieval": 0.82, "generation": 1.63},
    "usage": {"cost_usd": 0.0045}
}

# ============================================
# UI Components
# ============================================

def render_header():
    st.markdown(GENSHIN_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="main-header">
        <h1>📜 LoreMaster-AI</h1>
        <div class="subtitle">原神考据助手 · Genshin Impact Lore Expert</div>
    </div>
    """, unsafe_allow_html=True)

def render_source_card(source: dict, expanded: bool = False):
    icon = get_entity_icon(source.get("entity_type", "default"))
    score_pct = int(source["score"] * 100)

    with st.expander(f"{icon} **{source['title']}** · {source.get('entity_type', 'Unknown')} · 相关度 {score_pct}%", expanded=expanded):
        st.markdown(f"""
        <div style="color: #9A9A9A; font-size: 0.85rem; margin-bottom: 0.5rem;">
            📍 {source.get('region', 'Teyvat')} · 📑 {source.get('section', 'General')}
        </div>
        """, unsafe_allow_html=True)

        st.markdown(source["text"])

        if source.get("source_url"):
            st.markdown(f"[🔗 查看Wiki原文]({source['source_url']})")

def render_relationship_graph(path_data: dict):
    if not path_data:
        return

    nodes = []
    edges = []

    # Create nodes
    node_colors = {
        0: "#D4A053",  # Gold for first
        -1: "#6BB5FF",  # Blue for last
    }

    for i, node_name in enumerate(path_data["nodes"]):
        color = node_colors.get(i, node_colors.get(-1 if i == len(path_data["nodes"])-1 else None, "#7BC86C"))
        nodes.append(Node(
            id=node_name,
            label=node_name,
            size=30,
            color=color,
            font={"color": "#E8E4DC", "size": 14}
        ))

    # Create edges
    for i, rel in enumerate(path_data.get("relations", [])):
        if i < len(path_data["nodes"]) - 1:
            edges.append(Edge(
                source=path_data["nodes"][i],
                target=path_data["nodes"][i + 1],
                label=rel,
                color="#D4A053",
                font={"color": "#9A9A9A", "size": 10}
            ))

    # Add alternative paths if exist
    for alt_path in path_data.get("alternative_paths", [])[:1]:
        for i, rel in enumerate(alt_path.get("relations", [])):
            if i < len(alt_path["nodes"]) - 1:
                # Add missing nodes
                for node_name in alt_path["nodes"]:
                    if node_name not in [n.id for n in nodes]:
                        nodes.append(Node(
                            id=node_name,
                            label=node_name,
                            size=25,
                            color="#363A4F",
                            font={"color": "#E8E4DC", "size": 12}
                        ))
                edges.append(Edge(
                    source=alt_path["nodes"][i],
                    target=alt_path["nodes"][i + 1],
                    label=rel,
                    color="#6BB5FF",
                    dashes=True
                ))

    config = Config(
        width=700,
        height=300,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#D4A053",
        collapsible=False,
        node={'labelProperty': 'label'},
        link={'labelProperty': 'label', 'renderLabel': True}
    )

    return agraph(nodes=nodes, edges=edges, config=config)

def render_metadata_badges(response: dict):
    timing = response.get("timing", {})
    usage = response.get("usage", {})

    st.markdown(f"""
    <div class="metadata-container">
        <span class="metadata-badge">🎯 {response.get('query_type', 'FACTUAL')}</span>
        <span class="metadata-badge">👥 {len(response.get('entities', []))} 实体</span>
        <span class="metadata-badge timing">⏱️ {timing.get('total', 0):.2f}s</span>
        <span class="metadata-badge cost">💰 ${usage.get('cost_usd', 0):.4f}</span>
    </div>
    """, unsafe_allow_html=True)

def render_ai_response(response: dict):
    st.markdown('<div class="ai-message animate-fade-in">', unsafe_allow_html=True)

    # Answer text
    st.markdown(response["answer"])

    # Metadata badges
    render_metadata_badges(response)

    # Relationship Graph
    if response.get("path"):
        st.markdown("---")
        st.markdown("**📊 实体关系图**")
        render_relationship_graph(response["path"])

    # Sources section
    st.markdown("---")
    st.markdown("**📚 参考来源**")
    for i, source in enumerate(response.get("sources", [])):
        render_source_card(source, expanded=(i == 0))

    st.markdown('</div>', unsafe_allow_html=True)

# ============================================
# Main App
# ============================================

def main():
    render_header()

    # Config selector in sidebar
    with st.sidebar:
        st.markdown("### ⚙️ 配置选择")
        config_name = st.selectbox(
            "Pipeline配置",
            ["full_pipeline", "fast_mode", "gpt4o_mode", "vector_only", "graph_only", "baseline"],
            index=0
        )
        st.markdown(f"当前配置: **{config_name}**")

        st.markdown("---")
        st.markdown("### 📊 系统状态")
        st.markdown("""
        - 📦 Pinecone: 17,235 vectors
        - 🔗 Neo4j: 3,494 nodes
        - 📝 DynamoDB: 3,483 entities
        """)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f"""
            <div class="user-message">
                <strong>🧑 你的问题:</strong><br>{message["content"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            render_ai_response(message["content"])

    # Chat input
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns([6, 1])
    with col1:
        user_input = st.text_input(
            "询问原神世界的任何问题...",
            placeholder="例如: 赤王和花神是什么关系？",
            label_visibility="collapsed",
            key="user_input"
        )
    with col2:
        send_button = st.button("发送 ✨", use_container_width=True)

    # Handle input
    if send_button and user_input:
        # Add user message
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Show loading
        with st.spinner("🔮 正在查阅提瓦特大陆的知识..."):
            time.sleep(1.5)  # Simulate API call

        # Add AI response (using demo data)
        st.session_state.messages.append({"role": "assistant", "content": DEMO_RESPONSE})

        # Rerun to update display
        st.rerun()

    # Example questions
    if not st.session_state.messages:
        st.markdown("---")
        st.markdown("### 💡 示例问题")

        example_cols = st.columns(2)
        examples = [
            "赤王和花神是什么关系？",
            "流浪者为什么要抹除自己的存在？",
            "须弥沙漠的古文明是如何毁灭的？",
            "愚人众和冰之女皇有什么关联？"
        ]

        for i, example in enumerate(examples):
            with example_cols[i % 2]:
                if st.button(example, key=f"example_{i}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": example})
                    with st.spinner("🔮 正在查阅..."):
                        time.sleep(1.5)
                    st.session_state.messages.append({"role": "assistant", "content": DEMO_RESPONSE})
                    st.rerun()


if __name__ == "__main__":
    main()
