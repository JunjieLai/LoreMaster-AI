import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { PathData, GraphResult, ENTITY_COLORS } from '../types';
import { useTheme } from '../App';
import { useThumbnail } from '../hooks/useThumbnail';

interface ConstellationGraphProps {
  pathData?: PathData | null;
  graphResults?: GraphResult[];
}

/** Convert entity neighborhood data into a PathData-compatible structure for rendering.
 *  Returns null if no edges can be found between the retrieved entities —
 *  callers should suppress the graph in that case rather than show isolated nodes. */
function buildFallbackPathData(graphResults: GraphResult[]): PathData | null {
  const nodes = graphResults.map(r => r.entity.name);
  // Only draw edges between entities that are both present in graphResults,
  // to prevent external neighbors from bleeding in from a previous graph.
  const entitySet = new Set(nodes);
  const altPaths: { nodes: string[]; relations: string[] }[] = [];
  const seen = new Set<string>();

  graphResults.forEach(r => {
    r.relationships.slice(0, 15).forEach(rel => {
      const from = rel.direction === 'outgoing' ? r.entity.name : (rel.source ?? '');
      const to   = rel.direction === 'outgoing' ? (rel.target ?? '') : r.entity.name;
      const key  = `${from}__${rel.relation}__${to}`;
      if (from && to && from !== to && !seen.has(key) && entitySet.has(from) && entitySet.has(to)) {
        seen.add(key);
        altPaths.push({ nodes: [from, to], relations: [rel.relation] });
      }
    });
  });

  // If no edges found, return null so the caller can hide the graph entirely
  if (altPaths.length === 0) return null;

  return { nodes, relations: [], evidences: [], alternative_paths: altPaths };
}

interface NodePosition {
  id: string;
  x: number;
  y: number;
  isMain: boolean;
  color: string;
  labelBelow: boolean;
}

interface LinkData {
  source: string;
  target: string;
  relation: string;
  isAlternative: boolean;
}

// Estimate label pixel width based on character count
function labelPx(name: string): number {
  return name.length * 7 + 24;
}

// Minimum center-to-center distance so labels never overlap.
// `gap` controls the extra room: main row needs space for edge labels, alt row needs less.
function safeSpacing(a: string, b: string, gap = 140): number {
  return labelPx(a) / 2 + labelPx(b) / 2 + gap;
}

// Calculate positions with label-aware spacing
function calculateLayout(pathData: PathData, width: number, height: number) {
  const nodes: NodePosition[] = [];
  const links: LinkData[] = [];
  const nodeMap = new Map<string, NodePosition>();

  const centerX = width / 2;
  const centerY = height / 2 + 20;
  const maxUsableWidth = width - 80; // 40px padding each side

  const mainNodes = pathData.nodes;
  const mainCount = mainNodes.length;

  if (mainCount === 0) return { nodes, links, nodeMap };

  // Position main path nodes on a horizontal axis with label-aware spacing
  if (mainCount === 1) {
    const node: NodePosition = {
      id: mainNodes[0],
      x: centerX,
      y: centerY,
      isMain: true,
      color: ENTITY_COLORS.Character,
      labelBelow: true,
    };
    nodes.push(node);
    nodeMap.set(mainNodes[0], node);
  } else {
    // Cumulative center-to-center distances
    const positions: number[] = [0];
    for (let i = 1; i < mainCount; i++) {
      positions.push(positions[i - 1] + safeSpacing(mainNodes[i - 1], mainNodes[i]));
    }
    const totalSpan = positions[mainCount - 1];

    // Scale down proportionally if the path is too wide
    const scale = totalSpan > maxUsableWidth ? maxUsableWidth / totalSpan : 1;
    const offsetX = centerX - (totalSpan * scale) / 2;

    mainNodes.forEach((name, i) => {
      const color = i === 0 ? ENTITY_COLORS.Character :
                    i === mainCount - 1 ? ENTITY_COLORS.Lore :
                    ENTITY_COLORS.default;
      const node: NodePosition = {
        id: name,
        x: offsetX + positions[i] * scale,
        y: centerY,
        isMain: true,
        color,
        labelBelow: true,
      };
      nodes.push(node);
      nodeMap.set(name, node);
    });
  }

  // Main path links
  for (let i = 0; i < pathData.relations.length; i++) {
    links.push({
      source: pathData.nodes[i],
      target: pathData.nodes[i + 1],
      relation: pathData.relations[i],
      isAlternative: false,
    });
  }

  // Collect unique alt-only nodes (not already placed on the main path)
  const altNodesToPosition: string[] = [];
  const altNodesSeen = new Set<string>();
  pathData.alternative_paths?.forEach((altPath) => {
    altPath.nodes.forEach((name) => {
      if (!nodeMap.has(name) && !altNodesSeen.has(name)) {
        altNodesToPosition.push(name);
        altNodesSeen.add(name);
      }
    });
  });

  if (altNodesToPosition.length > 0) {
    // ── Sugiyama barycenter heuristic: position each alt node at the
    //    average x of its main-row neighbours → minimises edge crossings
    //    between the two layers. ──────────────────────────────────────────
    const barycenters = new Map<string, number>();
    for (const name of altNodesToPosition) {
      const xs: number[] = [];
      pathData.alternative_paths?.forEach(ap => {
        for (let i = 0; i < ap.nodes.length; i++) {
          if (ap.nodes[i] !== name) continue;
          if (i > 0 && nodeMap.has(ap.nodes[i - 1]))
            xs.push(nodeMap.get(ap.nodes[i - 1])!.x);
          if (i < ap.nodes.length - 1 && nodeMap.has(ap.nodes[i + 1]))
            xs.push(nodeMap.get(ap.nodes[i + 1])!.x);
        }
      });
      barycenters.set(name,
        xs.length > 0 ? xs.reduce((a, b) => a + b, 0) / xs.length : centerX);
    }

    // Sort left → right by barycenter (crossing minimisation)
    altNodesToPosition.sort((a, b) => (barycenters.get(a) || 0) - (barycenters.get(b) || 0));

    // Greedy placement: try barycenter x, enforce minimum spacing.
    // Alt row uses smaller gap (60) — no edge labels sit between adjacent alt nodes.
    const y = centerY - 120;
    const placed: { name: string; x: number }[] = [];
    for (const name of altNodesToPosition) {
      let x = barycenters.get(name) || centerX;
      if (placed.length > 0) {
        const prev = placed[placed.length - 1];
        x = Math.max(x, prev.x + safeSpacing(prev.name, name, 60));
      }
      placed.push({ name, x });
    }

    // ── Sugiyama Phase 3: re-center the alt row so its centroid aligns
    //    with the weighted centroid of its connected main-row nodes.
    //    This prevents the greedy left-to-right push from drifting the
    //    entire row away from the graph's visual centre. ──────────────
    if (placed.length > 0) {
      const altCentroid = placed.reduce((s, p) => s + p.x, 0) / placed.length;
      const targetCentroid = placed.reduce((s, p) =>
        s + (barycenters.get(p.name) || centerX), 0) / placed.length;
      const shift = targetCentroid - altCentroid;
      for (const p of placed) p.x += shift;
    }

    placed.forEach(({ name, x }) => {
      const node: NodePosition = {
        id: name, x, y,
        isMain: true,
        color: ENTITY_COLORS.Character,
        labelBelow: false,
      };
      nodes.push(node);
      nodeMap.set(name, node);
    });
  }

  // Alternative path links
  pathData.alternative_paths?.forEach((altPath) => {
    for (let i = 0; i < altPath.relations.length; i++) {
      const exists = links.some(
        l => (l.source === altPath.nodes[i] && l.target === altPath.nodes[i + 1]) ||
             (l.source === altPath.nodes[i + 1] && l.target === altPath.nodes[i])
      );
      if (!exists) {
        links.push({
          source: altPath.nodes[i],
          target: altPath.nodes[i + 1],
          relation: altPath.relations[i],
          isAlternative: true,
        });
      }
    }
  });

  return { nodes, links, nodeMap };
}

// Diamond Node with thumbnail - uniform size
function DiamondNode({
  node,
  isHovered,
  isSelected,
  onClick,
  onHover
}: {
  node: NodePosition;
  isHovered: boolean;
  isSelected: boolean;
  onClick: () => void;
  onHover: (hovered: boolean) => void;
}) {
  const { thumbnailUrl } = useThumbnail(node.id);
  const size = 50; // Uniform size for all nodes
  const innerSize = size - 8;
  const isActive = isHovered || isSelected;

  // Calculate label position - more distance from diamond
  const labelOffset = node.labelBelow ? (size / 2 + 28) : -(size / 2 + 20);
  const labelBgOffset = node.labelBelow ? (size / 2 + 16) : -(size / 2 + 32);

  return (
    <g
      transform={`translate(${node.x}, ${node.y})`}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onClick={onClick}
      style={{ cursor: 'pointer' }}
    >
      {/* Outer glow */}
      <motion.rect
        x={-size / 2 - 4}
        y={-size / 2 - 4}
        width={size + 8}
        height={size + 8}
        rx={4}
        fill="#d4a154"
        opacity={0.15}
        transform="rotate(45)"
        animate={{
          opacity: isActive ? 0.35 : 0.15,
          scale: isActive ? 1.1 : 1,
        }}
        transition={{ duration: 0.3 }}
        className="animate-pulse-slow"
      />

      {/* Diamond shape */}
      <motion.rect
        x={-size / 2}
        y={-size / 2}
        width={size}
        height={size}
        rx={4}
        fill="#1A2332"
        stroke={isActive ? '#ffeebb' : '#d4a154'}
        strokeWidth={isActive ? 2.5 : 1.5}
        transform="rotate(45)"
        animate={{
          scale: isActive ? 1.08 : 1,
        }}
        transition={{ duration: 0.2 }}
        className={isActive ? 'active-node-glow' : 'node-glow'}
      />

      {/* Inner content area */}
      <clipPath id={`clip-${node.id.replace(/\s/g, '-')}`}>
        <rect
          x={-innerSize / 2}
          y={-innerSize / 2}
          width={innerSize}
          height={innerSize}
          rx={2}
          transform="rotate(45)"
        />
      </clipPath>

      {/* Thumbnail or placeholder */}
      <g clipPath={`url(#clip-${node.id.replace(/\s/g, '-')})`}>
        {thumbnailUrl ? (
          <image
            href={thumbnailUrl}
            x={-innerSize / 2 - 10}
            y={-innerSize / 2 - 10}
            width={innerSize + 20}
            height={innerSize + 20}
            preserveAspectRatio="xMidYMid slice"
          />
        ) : (
          <>
            <rect
              x={-innerSize / 2}
              y={-innerSize / 2}
              width={innerSize}
              height={innerSize}
              fill="rgba(212, 161, 84, 0.15)"
              transform="rotate(45)"
            />
            {/* Sparkles icon as placeholder - matches the title icon style */}
            <g transform="scale(1.6)" opacity={0.6}>
              <path
                d="m0 -9-1.912 5.813a2 2 0 0 1-1.275 1.275L-9 0l5.813 1.912a2 2 0 0 1 1.275 1.275L0 9l1.912-5.813a2 2 0 0 1 1.275-1.275L9 0l-5.813-1.912a2 2 0 0 1-1.275-1.275L0-9Z"
                fill="none"
                stroke="#d4a154"
                strokeWidth={1.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <line x1={-7} y1={-9} x2={-7} y2={-5} stroke="#d4a154" strokeWidth={1.5} strokeLinecap="round" />
              <line x1={-9} y1={-7} x2={-5} y2={-7} stroke="#d4a154" strokeWidth={1.5} strokeLinecap="round" />
              <line x1={7} y1={5} x2={7} y2={9} stroke="#d4a154" strokeWidth={1.5} strokeLinecap="round" />
              <line x1={5} y1={7} x2={9} y2={7} stroke="#d4a154" strokeWidth={1.5} strokeLinecap="round" />
            </g>
          </>
        )}
      </g>

      {/* Background for label */}
      <rect
        x={-node.id.length * 3.5 - 10}
        y={labelBgOffset}
        width={node.id.length * 7 + 20}
        height={22}
        rx={4}
        fill="rgba(11, 17, 32, 0.95)"
        stroke={isActive ? 'rgba(212, 161, 84, 0.8)' : 'rgba(212, 161, 84, 0.3)'}
        strokeWidth={1}
      />

      {/* Label text */}
      <text
        y={labelOffset}
        textAnchor="middle"
        fill={isActive ? '#ffeebb' : '#d4a154'}
        fontSize={11}
        fontWeight={600}
        fontFamily="'Space Grotesk', sans-serif"
      >
        {node.id}
      </text>
    </g>
  );
}

const NODE_R = 42;      // offset from node centre to line start/end (clears diamond tip + glow)
const LABEL_H = 22;     // label pill height
const ARC_X_MIN = 250;  // x-span threshold above which same-row edges become arcs

/**
 * Compute all drawing geometry for one edge.
 *
 * Same-row, non-adjacent edges (|dy|<15 && |dx|>ARC_X_MIN) are routed as a
 * downward quadratic bezier arc so they never pass through intermediate nodes.
 * All other edges are straight lines with a gap cut at the label centre.
 *
 * Returns null when source === target or distance is negligible.
 */
function edgeGeometry(sourceNode: NodePosition, targetNode: NodePosition, relation: string) {
  const dx = targetNode.x - sourceNode.x;
  const dy = targetNode.y - sourceNode.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist < 1) return null;

  const ux = dx / dist;
  const uy = dy / dist;

  // Label pill width — generous estimate so long names (ORIGINATED_FROM etc.) fit.
  const labelW = Math.max(relation.length * 8 + 24, 56);

  // Line start/end offset from node centres (clear the diamond tip)
  const x1 = sourceNode.x + ux * NODE_R;
  const y1 = sourceNode.y + uy * NODE_R;
  const x2 = targetNode.x - ux * NODE_R;
  const y2 = targetNode.y - uy * NODE_R;

  const sameRow = Math.abs(dy) < 15;
  const useArc  = sameRow && Math.abs(dx) > ARC_X_MIN;

  if (useArc) {
    // Arc bows DOWNWARD (positive y = down in SVG) so it stays clear of nodes
    // and alt-nodes which live above the main row.
    const arcH = Math.min(Math.abs(dx) * 0.28 + 30, 180);
    const cx   = (sourceNode.x + targetNode.x) / 2;
    const cy   = sourceNode.y + arcH;          // control point below the row
    // Bezier midpoint (t = 0.5): P = 0.25*P0 + 0.5*CP + 0.25*P1
    const labelX = 0.25 * x1 + 0.5 * cx + 0.25 * x2;
    const labelY = 0.25 * y1 + 0.5 * cy + 0.25 * y2;
    return {
      useArc: true,
      x1, y1, x2, y2, cx, cy,
      pathD: `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`,
      labelX, labelY, labelW,
    };
  }

  // ── Straight line with gap at label centre ──────────────────────────────
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const lineLen = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
  // Cap label width so it never extends past node edges
  const cappedLabelW = Math.min(labelW, Math.max(lineLen - 8, 56));
  // Half-extent of label projected onto line direction
  const halfAlong = Math.abs(ux) * cappedLabelW / 2 + Math.abs(uy) * LABEL_H / 2 + 4;
  const hasGap    = lineLen > halfAlong * 2 + 10;

  return {
    useArc: false,
    x1, y1, x2, y2, cx: midX, cy: midY,
    pathD: `M${x1},${y1} L${x2},${y2}`,
    labelX: midX, labelY: midY, labelW: cappedLabelW,
    // straight-only fields
    gx1: midX - ux * halfAlong, gy1: midY - uy * halfAlong,
    gx2: midX + ux * halfAlong, gy2: midY + uy * halfAlong,
    hasGap,
  };
}

// ── Pass 1: edge lines only (rendered below labels and nodes) ─────────────
function ConnectionEdge({ geo, isHighlighted }: {
  geo: NonNullable<ReturnType<typeof edgeGeometry>>; isHighlighted: boolean;
}) {
  const color = '#6BB5FF';
  const sw = isHighlighted ? 3 : 2;
  const op = isHighlighted ? 1 : 0.8;
  const da = '8,4';

  if (geo.useArc) {
    return (
      <g>
        <path d={geo.pathD} stroke={color} strokeWidth={sw} strokeDasharray={da}
          opacity={op} strokeLinecap="round" fill="none" />
        <circle r="3.5" fill={color} opacity="0.85">
          <animateMotion dur="3s" repeatCount="indefinite" path={geo.pathD} />
        </circle>
      </g>
    );
  }

  const { x1, y1, x2, y2 } = geo;
  const straight = geo as ReturnType<typeof edgeGeometry> & { hasGap: boolean; gx1: number; gy1: number; gx2: number; gy2: number };
  return (
    <g>
      {straight.hasGap ? (
        <>
          <line x1={x1} y1={y1} x2={straight.gx1} y2={straight.gy1}
            stroke={color} strokeWidth={sw} strokeDasharray={da} opacity={op} strokeLinecap="round" />
          <line x1={straight.gx2} y1={straight.gy2} x2={x2} y2={y2}
            stroke={color} strokeWidth={sw} strokeDasharray={da} opacity={op} strokeLinecap="round" />
        </>
      ) : (
        <line x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={color} strokeWidth={sw} strokeDasharray={da} opacity={op} strokeLinecap="round" />
      )}
      <circle r="3.5" fill={color} opacity="0.85">
        <animateMotion dur="2.5s" repeatCount="indefinite"
          path={`M${x1},${y1} L${x2},${y2}`} />
      </circle>
    </g>
  );
}

// ── Pass 2: labels only (rendered above lines, below nodes) ──────────────
function ConnectionLabel({ geo, relation, isHighlighted }: {
  geo: NonNullable<ReturnType<typeof edgeGeometry>>; relation: string; isHighlighted: boolean;
}) {
  const { labelX, labelY, labelW } = geo;
  const color = '#6BB5FF';

  // Truncate relation name if the capped pill is too narrow for the full text
  const maxChars = Math.floor((labelW - 16) / 7);
  const displayRelation = relation.length > maxChars
    ? relation.slice(0, Math.max(maxChars - 1, 2)) + '…'
    : relation;

  return (
    <g>
      <rect x={labelX - labelW / 2} y={labelY - LABEL_H / 2}
        width={labelW} height={LABEL_H} rx={11}
        fill="rgba(11, 17, 32, 0.98)"
        stroke={isHighlighted ? color : `${color}99`}
        strokeWidth={isHighlighted ? 1.5 : 1}
      />
      <text x={labelX} y={labelY + 4} textAnchor="middle"
        fill={isHighlighted ? color : `${color}cc`}
        fontSize={10} fontFamily="'Space Grotesk', sans-serif" fontWeight={600}
      >
        {displayRelation}
      </text>
    </g>
  );
}

export function ConstellationGraph({ pathData, graphResults }: ConstellationGraphProps) {
  const { hoveredEntity, setHoveredEntity, selectedEntity, setSelectedEntity } = useTheme();
  const [localHovered, setLocalHovered] = useState<string | null>(null);

  // Use pathData if available, otherwise build fallback from entity neighborhoods.
  const effectivePathData = useMemo(() => {
    if (pathData) {
      // Cap alt paths to 2 to prevent distant traversals from adding unrelated nodes.
      // Alt path nodes that aren't in the main path are placed above it, forming
      // the constellation/triangle shape naturally.
      return {
        ...pathData,
        alternative_paths: (pathData.alternative_paths ?? []).slice(0, 2),
      };
    }
    if (graphResults && graphResults.length > 0) return buildFallbackPathData(graphResults); // may return null
    return null;
  }, [pathData, graphResults]);

  // Layout in a generous coordinate space — actual viewBox is computed afterwards
  // from the real positions of nodes and edge labels.
  const CANVAS = { width: 1600, height: 600 };

  const { nodes, links, nodeMap } = useMemo(
    () => effectivePathData ? calculateLayout(effectivePathData, CANVAS.width, CANVAS.height) : { nodes: [], links: [], nodeMap: new Map() },
    [effectivePathData]
  );

  // ── Pre-compute all edge geometries + label anti-collision ────────────
  const edgeGeos = useMemo(() => {
    const geos = links.map(link => {
      const sn = nodeMap.get(link.source);
      const tn = nodeMap.get(link.target);
      if (!sn || !tn) return null;
      return edgeGeometry(sn, tn, link.relation);
    });

    // Gather non-null entries sorted by y then x
    const valid = geos
      .map((g, i) => g ? { i, g } : null)
      .filter((x): x is { i: number; g: NonNullable<typeof geos[0]> } => x !== null);
    valid.sort((a, b) => a.g.labelY - b.g.labelY || a.g.labelX - b.g.labelX);

    // Push overlapping labels apart vertically (greedy sweep)
    for (let a = 0; a < valid.length; a++) {
      for (let b = a + 1; b < valid.length; b++) {
        const ga = valid[a].g, gb = valid[b].g;
        const ox = (ga.labelW + gb.labelW) / 2 + 6 - Math.abs(ga.labelX - gb.labelX);
        const oy = LABEL_H + 6 - Math.abs(ga.labelY - gb.labelY);
        if (ox > 0 && oy > 0) {
          // Push the lower-priority label downward
          gb.labelY = ga.labelY + LABEL_H + 8;
        }
      }
    }

    return geos;
  }, [links, nodeMap]);

  // ── Tight viewBox from actual positions (layout-first, viewBox-second) ──
  const viewBox = useMemo(() => {
    if (nodes.length === 0) return '0 0 700 320';
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    // Node bounds: diamond tip ≈ 42px, label extends labelPx/2 horizontally
    for (const n of nodes) {
      const hw = Math.max(labelPx(n.id) / 2 + 12, 50);
      minX = Math.min(minX, n.x - hw);
      maxX = Math.max(maxX, n.x + hw);
      minY = Math.min(minY, n.y - 80);  // diamond + label above
      maxY = Math.max(maxY, n.y + 80);  // diamond + label below
    }
    // Edge label bounds (including arc labels that bow downward)
    for (const geo of edgeGeos) {
      if (!geo) continue;
      minX = Math.min(minX, geo.labelX - geo.labelW / 2 - 4);
      maxX = Math.max(maxX, geo.labelX + geo.labelW / 2 + 4);
      minY = Math.min(minY, geo.labelY - LABEL_H / 2 - 4);
      maxY = Math.max(maxY, geo.labelY + LABEL_H / 2 + 4);
    }
    const pad = 24;
    const w = Math.max(500, maxX - minX + pad * 2);
    const h = Math.max(250, maxY - minY + pad * 2);
    return `${minX - pad} ${minY - pad} ${w} ${h}`;
  }, [nodes, edgeGeos]);

  // No renderable graph — suppress entirely rather than show isolated nodes
  if (!effectivePathData) return null;

  const handleNodeHover = (nodeId: string, hovered: boolean) => {
    setLocalHovered(hovered ? nodeId : null);
    setHoveredEntity(hovered ? nodeId : null);
  };

  const isEdgeHighlighted = (link: LinkData) =>
    localHovered === link.source || localHovered === link.target ||
    hoveredEntity === link.source || hoveredEntity === link.target ||
    selectedEntity === link.source || selectedEntity === link.target;

  return (
    <div className="w-full h-full flex items-center justify-center p-4">
      <svg
        width="100%"
        height="100%"
        viewBox={viewBox}
        className="overflow-visible"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Layer 1 — edge lines (behind everything) */}
        <g>
          {links.map((link, i) => {
            const geo = edgeGeos[i];
            return geo ? (
              <ConnectionEdge
                key={`edge-${link.source}-${link.target}-${i}`}
                geo={geo}
                isHighlighted={isEdgeHighlighted(link)}
              />
            ) : null;
          })}
        </g>

        {/* Layer 2 — relationship labels (above lines, below nodes) */}
        <g>
          {links.map((link, i) => {
            const geo = edgeGeos[i];
            return geo ? (
              <ConnectionLabel
                key={`label-${link.source}-${link.target}-${i}`}
                geo={geo}
                relation={link.relation}
                isHighlighted={isEdgeHighlighted(link)}
              />
            ) : null;
          })}
        </g>

        {/* Layer 3 — nodes (topmost layer) */}
        {nodes.map((node) => (
          <DiamondNode
            key={node.id}
            node={node}
            isHovered={localHovered === node.id || hoveredEntity === node.id}
            isSelected={selectedEntity === node.id}
            onClick={() => setSelectedEntity(selectedEntity === node.id ? null : node.id)}
            onHover={(hovered) => handleNodeHover(node.id, hovered)}
          />
        ))}
      </svg>
    </div>
  );
}
