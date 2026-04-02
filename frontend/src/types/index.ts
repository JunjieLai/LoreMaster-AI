export interface Source {
  title: string;
  entity_type: string;
  section?: string;
  score: number;
  text: string;
  source_url?: string;
  region?: string;
}

export interface PathData {
  nodes: string[];
  relations: string[];
  evidences?: string[];
  alternative_paths?: {
    nodes: string[];
    relations: string[];
  }[];
}

export interface GraphNode {
  id: string;
  name: string;
  type?: string;
  val?: number;
  color?: string;
  isMain?: boolean;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  isAlternative?: boolean;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  path?: PathData;
  entities?: string[];
  queryType?: string;
  timing?: {
    total: number;
    retrieval?: number;
    generation?: number;
  };
  cost?: number;
}

export interface Config {
  name: string;
  description: string;
  icon: string;
}

export const CONFIGS: Config[] = [
  { name: 'full_pipeline', description: 'Full Pipeline (Recommended)', icon: '🚀' },
  { name: 'fast_mode', description: 'Fast Mode', icon: '⚡' },
  { name: 'gpt4o_mode', description: 'GPT-4o Mode', icon: '🤖' },
  { name: 'vector_only', description: 'Vector Search Only', icon: '🔍' },
  { name: 'graph_only', description: 'Graph Search Only', icon: '🕸️' },
  { name: 'baseline', description: 'Baseline', icon: '📊' },
];

export const ENTITY_ICONS: Record<string, string> = {
  Character: '🎭',
  NPC: '👤',
  Location: '🏛️',
  Region: '🗺️',
  Lore: '📜',
  Quest: '📖',
  Weapon: '⚔️',
  Artifact: '🔮',
  Organization: '🏰',
  Event: '⚡',
  Concept: '💫',
  default: '📄',
};

export const ENTITY_COLORS: Record<string, string> = {
  Character: '#EF7A35',  // Pyro
  NPC: '#74C2A8',        // Anemo
  Location: '#F0B232',   // Geo
  Region: '#4CC2FF',     // Hydro
  Lore: '#B07BCC',       // Electro
  Quest: '#7BC86C',      // Dendro
  default: '#D4A053',    // Gold
};
