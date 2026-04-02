import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import { X, Search, Sparkles, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { ENTITY_COLORS } from '../types';
import { useGraphData, GraphNodeData } from '../hooks/useGraphData';

interface GraphExplorerProps {
  onClose: () => void;
}

// Relation type → display color
const RELATION_COLORS: Record<string, string> = {
  ALLY_OF: '#7BC86C',
  ENEMY_OF: '#EF7A35',
  CHILD_OF: '#d4a154',
  PARENT_OF: '#d4a154',
  SIBLING_OF: '#d4a154',
  MEMBER_OF: '#4CC2FF',
  LEADER_OF: '#4CC2FF',
  LOCATED_IN: '#F0B232',
  RULES: '#F0B232',
  CREATED: '#B07BCC',
  CREATED_BY: '#B07BCC',
  AFFILIATED_WITH: '#74C2A8',
  RELATED_TO: '#555e78',
  default: '#3a4460',
};

const ALL_TYPES = ['Character', 'Location', 'Organization', 'Event', 'Item', 'Concept'];

function nodeColor(type: string): string {
  return ENTITY_COLORS[type] || ENTITY_COLORS.default;
}

function relColor(rel: string): string {
  return RELATION_COLORS[rel] || RELATION_COLORS.default;
}

function drawDiamond(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  size: number,
  fill: string,
  stroke: string,
  strokeWidth: number
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(Math.PI / 4);
  ctx.beginPath();
  ctx.rect(-size / 2, -size / 2, size, size);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = strokeWidth;
  ctx.stroke();
  ctx.restore();
}

export function GraphExplorer({ onClose }: GraphExplorerProps) {
  const { data, isLoading, error } = useGraphData();
  const [search, setSearch] = useState('');
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set(ALL_TYPES));
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set());
  const [highlightLinks, setHighlightLinks] = useState<Set<string>>(new Set());
  const graphRef = useRef<ForceGraphMethods | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // ESC to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  // Measure container
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height });
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Build graph data once from raw data — never filtered, so node positions survive type-filter toggles.
  // Filtering is handled via nodeVisibility / linkVisibility props on ForceGraph2D.
  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };

    // Compute degree for node sizing using all links
    const degree: Record<string, number> = {};
    for (const link of data.links) {
      const s = link.source as string;
      const t = link.target as string;
      degree[s] = (degree[s] || 0) + 1;
      degree[t] = (degree[t] || 0) + 1;
    }

    return {
      nodes: data.nodes.map(n => ({ ...n, val: Math.sqrt(degree[n.id] || 1) })),
      // Shallow-copy links so react-force-graph-2d's mutations don't affect the original
      links: data.links.map(l => ({ ...l })),
    };
  }, [data]);

  // Visibility callbacks — these don't recreate the graph, just hide/show
  const nodeVisible = useCallback(
    (node: any) => activeTypes.has(node.type),
    [activeTypes]
  );
  const linkVisible = useCallback(
    (link: any) => {
      const sourceType = typeof link.source === 'object' ? link.source.type
        : data?.nodes.find(n => n.id === link.source)?.type;
      const targetType = typeof link.target === 'object' ? link.target.type
        : data?.nodes.find(n => n.id === link.target)?.type;
      return activeTypes.has(sourceType ?? '') && activeTypes.has(targetType ?? '');
    },
    [activeTypes, data]
  );

  // Build adjacency for selected node panel.
  // After simulation, react-force-graph-2d mutates link.source / link.target from string IDs
  // into node objects, so we must normalise before comparing.
  const linkSourceId = (l: any): string =>
    typeof l.source === 'object' ? l.source.id : l.source;
  const linkTargetId = (l: any): string =>
    typeof l.target === 'object' ? l.target.id : l.target;

  const selectedNodeLinks = useMemo(() => {
    if (!selectedNode || !data) return [];
    return graphData.links.filter(
      l => linkSourceId(l) === selectedNode.id || linkTargetId(l) === selectedNode.id
    );
  }, [selectedNode, graphData.links]);

  // Handle node click — typed as `any` to satisfy react-force-graph-2d's callback signature
  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node);
    // Highlight neighbors — source/target may already be objects after simulation
    const neighborIds = new Set<string>();
    const linkIds = new Set<string>();
    for (const link of graphData.links) {
      const s = linkSourceId(link);
      const t = linkTargetId(link);
      if (s === node.id || t === node.id) {
        neighborIds.add(s);
        neighborIds.add(t);
        linkIds.add(`${s}__${t}`);
      }
    }
    setHighlightNodes(neighborIds);
    setHighlightLinks(linkIds);
    // Zoom to node
    graphRef.current?.centerAt(node.x, node.y, 600);
    graphRef.current?.zoom(4, 600);
  }, [graphData.links]);

  // Handle search
  const handleSearch = useCallback((query: string) => {
    setSearch(query);
    if (!query.trim() || !data) {
      setHighlightNodes(new Set());
      return;
    }
    const lower = query.toLowerCase();
    const matched = new Set(
      data.nodes
        .filter(n => n.name.toLowerCase().includes(lower))
        .map(n => n.id)
    );
    setHighlightNodes(matched);
    // Zoom to first match
    if (matched.size > 0) {
      const first = graphData.nodes.find(n => matched.has(n.id)) as any;
      if (first?.x !== undefined) {
        graphRef.current?.centerAt(first.x, first.y, 600);
        graphRef.current?.zoom(5, 600);
      }
    }
  }, [data, graphData.nodes]);

  const toggleType = (type: string) => {
    setActiveTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        if (next.size > 1) next.delete(type); // keep at least 1
      } else {
        next.add(type);
      }
      return next;
    });
  };

  // Custom node renderer
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(node.id);
    const isSelected = selectedNode?.id === node.id;
    const size = 3 + (node.val || 1) * 1.5;
    const color = nodeColor(node.type);
    const alpha = isHighlighted ? 1 : 0.15;

    ctx.globalAlpha = alpha;
    drawDiamond(
      ctx, node.x, node.y, size,
      isSelected ? color : `${color}99`,
      isSelected ? '#ffeebb' : color,
      isSelected ? 1.5 : 0.8
    );
    ctx.globalAlpha = 1;

    // Label for selected or highlighted solo
    if (isSelected || (highlightNodes.size === 1 && highlightNodes.has(node.id))) {
      ctx.font = `${Math.max(3, size * 0.9)}px Space Grotesk, sans-serif`;
      ctx.fillStyle = isSelected ? '#ffeebb' : color;
      ctx.textAlign = 'center';
      ctx.fillText(node.name, node.x, node.y + size + 4);
    }
  }, [highlightNodes, selectedNode]);

return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex flex-col bg-navy-deep"
    >
      {/* Top accent line */}
      <div className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent" />

      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-primary/20 bg-navy-deep/95 backdrop-blur-sm shrink-0">
        {/* Title */}
        <div className="flex items-center gap-2 mr-2 shrink-0">
          <span className="w-6 h-6 bg-primary/20 rounded rotate-45 flex items-center justify-center border border-primary/30">
            <Sparkles className="w-3 h-3 text-primary -rotate-45" />
          </span>
          <span className="text-sm font-bold text-primary tracking-widest uppercase">
            Knowledge Graph
          </span>
        </div>

        {/* Stats */}
        {data && (
          <span className="text-[10px] font-mono text-primary/60 bg-black/30 px-2 py-0.5 rounded border border-primary/20 shrink-0">
            {graphData.nodes.filter(n => activeTypes.has((n as any).type)).length} nodes
            {' · '}
            {graphData.links.filter(l => {
              const st = typeof l.source === 'object' ? (l.source as any).type : data.nodes.find(n => n.id === l.source)?.type;
              const tt = typeof l.target === 'object' ? (l.target as any).type : data.nodes.find(n => n.id === l.target)?.type;
              return activeTypes.has(st ?? '') && activeTypes.has(tt ?? '');
            }).length} edges
          </span>
        )}

        {/* Type filters */}
        <div className="flex items-center gap-1.5 flex-wrap flex-1">
          {ALL_TYPES.map(type => (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider border transition-all"
              style={{
                borderColor: activeTypes.has(type) ? nodeColor(type) : 'rgba(255,255,255,0.1)',
                backgroundColor: activeTypes.has(type) ? `${nodeColor(type)}20` : 'transparent',
                color: activeTypes.has(type) ? nodeColor(type) : '#555e78',
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-sm rotate-45 inline-block shrink-0"
                style={{ backgroundColor: nodeColor(type) }}
              />
              {type}
              {data && (
                <span className="opacity-60">
                  {data.stats.by_type[type] || 0}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative shrink-0">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-primary/40" />
          <input
            type="text"
            placeholder="Search entity..."
            value={search}
            onChange={e => handleSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 rounded-lg bg-black/40 border border-primary/20 text-xs text-gray-200 placeholder-gray-600 focus:border-primary/50 focus:outline-none w-44"
          />
        </div>

        {/* Close */}
        <button
          type="button"
          title="Close"
          onClick={onClose}
          className="p-2 rounded-lg bg-black/30 border border-primary/20 text-primary/60 hover:text-primary hover:border-primary/50 transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Graph area + info panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* Canvas */}
        <div ref={containerRef} className="flex-1 relative overflow-hidden">
          {isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                className="w-12 h-12 bg-primary/10 rounded border border-primary/30 rotate-45 flex items-center justify-center"
              >
                <Sparkles className="w-6 h-6 text-primary -rotate-45" />
              </motion.div>
              <p className="text-sm text-primary/60 font-mono tracking-widest uppercase">
                Loading graph...
              </p>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="text-center">
                <p className="text-red-400 text-sm mb-2">Failed to load graph</p>
                <p className="text-gray-500 text-xs">{error}</p>
              </div>
            </div>
          )}

          {!isLoading && !error && graphData.nodes.length > 0 && (
            <ForceGraph2D
              ref={graphRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData}
              backgroundColor="#0B1120"
              nodeVisibility={nodeVisible}
              linkVisibility={linkVisible}
              nodeCanvasObject={paintNode}
              nodeCanvasObjectMode={() => 'replace'}
              linkColor={(link: any) => {
                const s = linkSourceId(link);
                const t = linkTargetId(link);
                const key = `${s}__${t}`;
                const isHighlighted = highlightLinks.size === 0 || highlightLinks.has(key);
                const c = relColor(link.relation);
                return isHighlighted ? c : `${c}22`;
              }}
              linkWidth={(link: any) => {
                const s = linkSourceId(link);
                const t = linkTargetId(link);
                return highlightLinks.has(`${s}__${t}`) ? 1.5 : 0.5;
              }}
              onNodeClick={handleNodeClick}
              onBackgroundClick={() => {
                setSelectedNode(null);
                setHighlightNodes(new Set());
                setHighlightLinks(new Set());
              }}
              nodeLabel={(node: any) => `${node.name} (${node.type})`}
              cooldownTicks={200}
              d3AlphaDecay={0.01}
              d3VelocityDecay={0.3}
            />
          )}
        </div>

        {/* Info Panel */}
        <AnimatePresence>
          {selectedNode && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="shrink-0 border-l border-primary/20 bg-navy-deep/95 backdrop-blur-sm overflow-hidden"
            >
              <div className="w-[280px] h-full flex flex-col overflow-hidden">
                {/* Node header */}
                <div
                  className="p-4 border-b border-primary/20 shrink-0"
                  style={{ background: `linear-gradient(135deg, ${nodeColor(selectedNode.type)}15, transparent)` }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-bold text-primary leading-tight">{selectedNode.name}</h3>
                      <span
                        className="text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded mt-1 inline-block"
                        style={{
                          backgroundColor: `${nodeColor(selectedNode.type)}25`,
                          color: nodeColor(selectedNode.type),
                        }}
                      >
                        {selectedNode.type}
                      </span>
                    </div>
                    <button
                      type="button"
                      title="Deselect node"
                      onClick={() => {
                        setSelectedNode(null);
                        setHighlightNodes(new Set());
                        setHighlightLinks(new Set());
                      }}
                      className="p-1 text-primary/40 hover:text-primary transition-colors shrink-0"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-[10px] text-primary/50 mt-1 font-mono">
                    {selectedNodeLinks.length} relationship{selectedNodeLinks.length !== 1 ? 's' : ''}
                  </p>
                </div>

                {/* Relationships list */}
                <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
                  {selectedNodeLinks.slice(0, 50).map((link, i) => {
                    const s = linkSourceId(link);
                    const t = linkTargetId(link);
                    const isOutgoing = s === selectedNode.id;
                    const other = isOutgoing ? t : s;
                    const otherNode = data?.nodes.find(n => n.id === other);
                    return (
                      <button
                        key={i}
                        type="button"
                        onClick={() => {
                          const node = graphData.nodes.find(n => n.id === other) as any;
                          if (node) handleNodeClick(node);
                        }}
                        className="w-full flex items-center gap-2 p-2 rounded-lg bg-black/20 hover:bg-black/40 border border-primary/5 hover:border-primary/20 transition-all text-left group"
                      >
                        <span
                          className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0"
                          style={{
                            backgroundColor: `${relColor(link.relation)}20`,
                            color: relColor(link.relation),
                          }}
                        >
                          {link.relation.replace(/_/g, ' ')}
                        </span>
                        <span className="text-[11px] text-gray-300 truncate flex-1 group-hover:text-gray-100">
                          {isOutgoing ? '→' : '←'} {other as string}
                        </span>
                        {otherNode && (
                          <span
                            className="w-2 h-2 rounded-sm rotate-45 shrink-0"
                            style={{ backgroundColor: nodeColor(otherNode.type) }}
                          />
                        )}
                        <ChevronRight className="w-3 h-3 text-primary/30 group-hover:text-primary/60 shrink-0" />
                      </button>
                    );
                  })}
                  {selectedNodeLinks.length > 50 && (
                    <p className="text-[10px] text-gray-500 text-center py-2">
                      +{selectedNodeLinks.length - 50} more
                    </p>
                  )}
                </div>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {/* Legend — bottom bar */}
      <div className="shrink-0 px-4 py-2 border-t border-primary/10 bg-navy-deep/80 flex items-center gap-4 overflow-x-auto">
        <span className="text-[9px] uppercase tracking-widest text-primary/40 shrink-0">Relations</span>
        {Object.entries(RELATION_COLORS)
          .filter(([k]) => k !== 'default')
          .slice(0, 10)
          .map(([rel, color]) => (
            <span key={rel} className="flex items-center gap-1 shrink-0">
              <span className="w-4 h-0.5 inline-block rounded" style={{ backgroundColor: color }} />
              <span className="text-[9px] uppercase tracking-wider" style={{ color: `${color}cc` }}>
                {rel.replace(/_/g, ' ')}
              </span>
            </span>
          ))}
      </div>
    </motion.div>
  );
}

export function GraphExplorerPortal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  return createPortal(
    <AnimatePresence>
      {isOpen && <GraphExplorer onClose={onClose} />}
    </AnimatePresence>,
    document.body
  );
}
