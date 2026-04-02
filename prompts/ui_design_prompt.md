# UI/UX Design Consultation for LoreMaster-AI

## Project Overview

LoreMaster-AI is a GraphRAG-based question-answering system specialized in Genshin Impact game lore. It combines vector search (Pinecone), knowledge graph (Neo4j), and entity database (DynamoDB) to provide comprehensive answers about game characters, locations, events, and relationships.

## Tech Stack

- **Framework**: React 18 + TypeScript + Vite
- **Styling**: Tailwind CSS with custom Genshin Impact-themed color palette
- **Animation**: Framer Motion
- **Icons**: Lucide React
- **Backend**: FastAPI (Python) for API proxy and thumbnail fetching

## Current Component Architecture

```
App.tsx
├── Header.tsx (config selector, branding)
├── ParticleBackground.tsx (ambient floating particles)
├── ChatInput.tsx (input field + preset questions on focus)
├── ChatMessage.tsx (message container)
│   ├── ConstellationGraph.tsx (SVG-based entity relationship visualization)
│   └── SourceCard.tsx (expandable source cards with thumbnails)
```

## Current Design Language

- **Theme**: Dark fantasy inspired by Genshin Impact's aesthetic
- **Color Palette**:
  - Primary Gold: #D4A053 (genshin-gold)
  - Background: #0D0F1A (deep navy/black)
  - Glass morphism effects with backdrop blur
  - Element colors: Pyro (#EF7A35), Hydro (#4CC2FF), Electro (#B07BCC), Dendro (#7BC86C), etc.
- **Typography**: "Noto Sans SC" for CJK support
- **Effects**: Subtle glow effects, floating animations, star-field background

## Current Features

1. **Chat Interface**: Single-page chat with user/assistant message bubbles
2. **Constellation Graph**: SVG visualization showing entity relationships
   - Main path nodes (horizontally arranged)
   - Alternative path nodes (positioned above)
   - Animated connection lines with flowing particles
   - Relation labels on edges
3. **Source Cards**: Expandable cards showing retrieved sources
   - Entity thumbnails fetched from Fandom Wiki API
   - Relevance score badges
   - Entity type icons with color coding
   - Region and section metadata
4. **Metadata Display**: Query type, entity count, response time, cost badges

## Data Structures

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;           // Markdown-formatted answer
  sources?: Source[];        // Retrieved wiki sources
  path?: PathData;          // Knowledge graph path
  entities?: string[];       // Detected entities
  queryType?: string;        // RELATIONSHIP, FACTUAL, etc.
  timing?: { total, retrieval, generation };
  cost?: number;
}

interface PathData {
  nodes: string[];           // Entity names in path
  relations: string[];       // Relation types between nodes
  evidences?: string[];      // Supporting text evidence
  alternative_paths?: { nodes, relations }[];
}

interface Source {
  title: string;
  entity_type: string;       // Character, Location, Lore, etc.
  section?: string;
  score: number;             // Relevance 0-1
  text: string;
  source_url?: string;
  region?: string;
}
```

## Design Challenges to Address

1. **Information Density**: How to present rich structured data (graph paths, multiple sources, metadata) without overwhelming users
2. **Visual Hierarchy**: Balancing the constellation graph, answer text, and source cards
3. **Responsive Design**: Currently optimized for desktop; mobile experience needs consideration
4. **Interactive Exploration**: The constellation graph is currently static after render; could benefit from more interactivity
5. **Loading States**: Current loading indicator is basic; opportunity for more engaging skeleton/shimmer states
6. **Empty State**: Welcome screen could be more engaging and guide users better

## Specific Design Questions

1. **Layout Architecture**: Is the current vertical stack (answer → graph → sources) optimal, or would a different arrangement (side panels, tabs, progressive disclosure) work better?

2. **Constellation Graph Enhancement**:
   - Should nodes show entity thumbnails instead of just colored circles?
   - How to handle graphs with many nodes (>5) without clutter?
   - Should the graph be zoomable/pannable?

3. **Source Card Optimization**:
   - All sources expanded by default vs. collapsed?
   - Grid layout vs. list layout for multiple sources?
   - How prominent should relevance scores be?

4. **Microinteractions**: What subtle animations or transitions would enhance the "magical lore discovery" feeling?

5. **Accessibility**: Current contrast ratios and focus states may need improvement

## Design Goals

- **Immersive**: Feel like exploring an ancient archive or constellation map
- **Informative**: Clearly present structured knowledge without cognitive overload
- **Delightful**: Subtle animations and interactions that reward exploration
- **Performant**: Animations should be smooth; avoid layout thrashing
- **Accessible**: WCAG 2.1 AA compliance where possible

## Deliverables Requested

Please provide:
1. Critique of current design with specific improvement suggestions
2. Alternative layout concepts (can be described or sketched in ASCII/markdown)
3. Component-level enhancement ideas with implementation considerations
4. Animation/microinteraction recommendations
5. Mobile adaptation strategy
6. Any innovative UI patterns that could elevate the "lore discovery" experience

## Reference Materials

The application displays information similar to:
- Graph visualization tools (Neo4j Browser, Obsidian graph view)
- AI chat interfaces (ChatGPT, Claude)
- Wiki/documentation browsers
- Game companion apps (HoYoLAB, game wikis)

Please think deeply about how to create a UI that feels both functional as a knowledge tool and magical as a lore exploration experience.
