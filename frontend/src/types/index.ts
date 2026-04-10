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

export interface GraphRelationship {
  direction: 'outgoing' | 'incoming';
  relation: string;
  target?: string;
  target_type?: string;
  source?: string;
  source_type?: string;
  evidence?: string;
}

export interface GraphResult {
  entity: {
    name: string;
    type: string;
    description?: string;
  };
  relationships: GraphRelationship[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  path?: PathData;
  graphResults?: GraphResult[];
  entities?: string[];
  queryType?: string;
  timing?: {
    total: number;
    retrieval?: number;
    generation?: number;
  };
  cost?: number;
  streaming?: boolean;
  cacheHit?: boolean;
}

export const ENTITY_COLORS: Record<string, string> = {
  Character: '#EF7A35',  // Pyro
  NPC: '#74C2A8',        // Anemo
  Location: '#F0B232',   // Geo
  Region: '#4CC2FF',     // Hydro
  Lore: '#B07BCC',       // Electro
  Quest: '#7BC86C',      // Dendro
  default: '#D4A053',    // Gold
};
