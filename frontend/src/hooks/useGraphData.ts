import { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000';

export interface GraphNodeData {
  id: string;
  name: string;
  type: string;
}

export interface GraphLinkData {
  source: string;
  target: string;
  relation: string;
}

export interface GraphStats {
  total_nodes: number;
  total_links: number;
  by_type: Record<string, number>;
  by_relation: Record<string, number>;
}

export interface GraphData {
  nodes: GraphNodeData[];
  links: GraphLinkData[];
  stats: GraphStats;
}

// Module-level cache — persists across modal open/close
let cachedData: GraphData | null = null;
let fetchPromise: Promise<GraphData> | null = null;

async function fetchGraphData(): Promise<GraphData> {
  if (cachedData) return cachedData;
  if (fetchPromise) return fetchPromise;

  fetchPromise = fetch(`${API_BASE}/api/graph`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<GraphData>;
    })
    .then(data => {
      cachedData = data;
      fetchPromise = null;
      return data;
    })
    .catch(err => {
      fetchPromise = null;
      throw err;
    });

  return fetchPromise;
}

export function useGraphData() {
  const [data, setData] = useState<GraphData | null>(cachedData);
  const [isLoading, setIsLoading] = useState(!cachedData);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cachedData) return;

    setIsLoading(true);
    fetchGraphData()
      .then(d => {
        setData(d);
        setIsLoading(false);
      })
      .catch(e => {
        setError(e.message);
        setIsLoading(false);
      });
  }, []);

  return { data, isLoading, error };
}
