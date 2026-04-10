import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PathData, GraphResult, ENTITY_COLORS } from '../types';
import { useTheme } from '../App';
import { useThumbnail } from '../hooks/useThumbnail';

interface ConstellationGraphProps {
  pathData?: PathData | null;
  graphResults?: GraphResult[];
}

/** Convert entity neighborhood data into a PathData-compatible structure for rendering. */
function buildFallbackPathData(graphResults: GraphResult[]): PathData {
  const nodes = graphResults.map(r => r.entity.name);
  // Only draw edges between entities that are both present in graphResults,
  // to prevent external neighbors from bleeding in from a previous graph.
  const entitySet = new Set(nodes);
  const altPaths: { nodes: string[]; relations: string[] }[] = [];
  const seen = new Set<string>();

  graphResults.forEach(r => {
    r.relationships.slice(0, 5).forEach(rel => {
      const from = rel.direction === 'outgoing' ? r.entity.name : (rel.source ?? '');
      const to   = rel.direction === 'outgoing' ? (rel.target ?? '') : r.entity.name;
      const key  = `${from}__${rel.relation}__${to}`;
      if (from && to && from !== to && !seen.has(key) && entitySet.has(from) && entitySet.has(to)) {
        seen.add(key);
        altPaths.push({ nodes: [from, to], relations: [rel.relation] });
      }
    });
  });

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

// Minimum center-to-center distance so labels never overlap, with extra room for dashed lines
function safeSpacing(a: string, b: string): number {
  return labelPx(a) / 2 + labelPx(b) / 2 + 120;
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
  const altNodesToPosition: { name: string; pathIndex: number }[] = [];
  const altNodesSeen = new Set<string>();
  pathData.alternative_paths?.forEach((altPath, pathIndex) => {
    altPath.nodes.forEach((name) => {
      if (!nodeMap.has(name) && !altNodesSeen.has(name)) {
        altNodesToPosition.push({ name, pathIndex });
        altNodesSeen.add(name);
      }
    });
  });

  if (altNodesToPosition.length > 0) {
    // Greedily pack alt nodes into rows left-to-right
    const rows: string[][] = [];
    let currentRow: string[] = [];
    let currentRowWidth = 0;

    for (const { name } of altNodesToPosition) {
      const gap = currentRow.length > 0 ? 60 : 0;
      const contrib = labelPx(name) + gap;
      if (currentRow.length > 0 && currentRowWidth + contrib > maxUsableWidth) {
        rows.push(currentRow);
        currentRow = [name];
        currentRowWidth = labelPx(name);
      } else {
        currentRow.push(name);
        currentRowWidth += contrib;
      }
    }
    if (currentRow.length > 0) rows.push(currentRow);

    // Place rows above the main axis (row 0 = closest to main row)
    const firstRowY = centerY - 120;
    const rowGap = 110;

    rows.forEach((row, rowIndex) => {
      const y = firstRowY - rowIndex * rowGap;

      if (row.length === 1) {
        const node: NodePosition = {
          id: row[0],
          x: centerX,
          y,
          isMain: true,
          color: ENTITY_COLORS.Character,
          labelBelow: false,
        };
        nodes.push(node);
        nodeMap.set(row[0], node);
      } else {
        const rowPositions: number[] = [0];
        for (let i = 1; i < row.length; i++) {
          rowPositions.push(rowPositions[i - 1] + safeSpacing(row[i - 1], row[i]));
        }
        const rowSpan = rowPositions[row.length - 1];
        const rowOffsetX = centerX - rowSpan / 2;

        row.forEach((name, i) => {
          const node: NodePosition = {
            id: name,
            x: rowOffsetX + rowPositions[i],
            y,
            isMain: true,
            color: ENTITY_COLORS.Character,
            labelBelow: false,
          };
          nodes.push(node);
          nodeMap.set(name, node);
        });
      }
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

// Connection line with animation - blue color
function ConnectionLine({
  source,
  target,
  relation,
  isAlternative: _isAlternative,
  nodeMap,
  isHighlighted,
}: {
  source: string;
  target: string;
  relation: string;
  isAlternative: boolean;
  nodeMap: Map<string, NodePosition>;
  isHighlighted: boolean;
}) {
  const sourceNode = nodeMap.get(source);
  const targetNode = nodeMap.get(target);

  if (!sourceNode || !targetNode) return null;

  const midX = (sourceNode.x + targetNode.x) / 2;
  const midY = (sourceNode.y + targetNode.y) / 2;

  // Blue color for relationship lines
  const color = '#6BB5FF';

  return (
    <g>
      {/* Connection line - all lines use consistent dashed style */}
      <line
        x1={sourceNode.x}
        y1={sourceNode.y}
        x2={targetNode.x}
        y2={targetNode.y}
        stroke={color}
        strokeWidth={isHighlighted ? 3 : 2}
        strokeDasharray="8,4"
        opacity={isHighlighted ? 1 : 0.8}
        strokeLinecap="round"
      />

      {/* Flowing particle */}
      <circle r="4" fill={color} opacity="0.9">
        <animateMotion
          dur="2.5s"
          repeatCount="indefinite"
          path={`M${sourceNode.x},${sourceNode.y} L${targetNode.x},${targetNode.y}`}
        />
      </circle>

      {/* Relation label */}
      <g>
        <rect
          x={midX - relation.length * 3.5 - 12}
          y={midY - 11}
          width={relation.length * 7 + 24}
          height={22}
          rx={11}
          fill="rgba(11, 17, 32, 0.95)"
          stroke={color}
          strokeWidth={1.5}
        />
        <text
          x={midX}
          y={midY + 4}
          textAnchor="middle"
          fill={color}
          fontSize={10}
          fontFamily="'Space Grotesk', sans-serif"
          fontWeight={600}
        >
          {relation}
        </text>
      </g>
    </g>
  );
}

export function ConstellationGraph({ pathData, graphResults }: ConstellationGraphProps) {
  const { hoveredEntity, setHoveredEntity, selectedEntity, setSelectedEntity } = useTheme();
  const [localHovered, setLocalHovered] = useState<string | null>(null);

  // Use pathData if available, otherwise build fallback from entity neighborhoods.
  // Cap alternative_paths to 2 to prevent distant graph traversals from including
  // unrelated nodes (e.g. entities from a previous question's graph).
  const effectivePathData = useMemo(() => {
    if (pathData) {
      return {
        ...pathData,
        alternative_paths: (pathData.alternative_paths ?? []).slice(0, 2),
      };
    }
    if (graphResults && graphResults.length > 0) return buildFallbackPathData(graphResults);
    return null;
  }, [pathData, graphResults]);

  const dimensions = useMemo(() => {
    if (!effectivePathData) return { width: 700, height: 320 };
    const mainNodeSet = new Set(effectivePathData.nodes);
    const altNodes = new Set<string>();
    effectivePathData.alternative_paths?.forEach(ap => {
      ap.nodes.forEach(n => { if (!mainNodeSet.has(n)) altNodes.add(n); });
    });
    const altCount = altNodes.size;
    if (altCount === 0) return { width: 700, height: 320 };
    const estimatedRows = Math.max(1, Math.ceil(altCount / 3));
    return { width: 700, height: 390 + Math.max(0, estimatedRows - 1) * 110 };
  }, [effectivePathData]);

  const { nodes, links, nodeMap } = useMemo(
    () => effectivePathData ? calculateLayout(effectivePathData, dimensions.width, dimensions.height) : { nodes: [], links: [], nodeMap: new Map() },
    [effectivePathData, dimensions]
  );

  const handleNodeHover = (nodeId: string, hovered: boolean) => {
    setLocalHovered(hovered ? nodeId : null);
    setHoveredEntity(hovered ? nodeId : null);
  };

  return (
    <div className="w-full h-full flex items-center justify-center p-4">
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
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

        {/* Links - render first so they appear behind nodes */}
        <g>
          {links.map((link, i) => (
            <ConnectionLine
              key={`${link.source}-${link.target}-${i}`}
              {...link}
              nodeMap={nodeMap}
              isHighlighted={
                localHovered === link.source ||
                localHovered === link.target ||
                hoveredEntity === link.source ||
                hoveredEntity === link.target ||
                selectedEntity === link.source ||
                selectedEntity === link.target
              }
            />
          ))}
        </g>

        {/* Nodes */}
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

      {/* Evidence Section */}
      <AnimatePresence>
        {effectivePathData?.evidences && effectivePathData.evidences.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute bottom-4 left-4 right-4 p-3 glass-panel rounded-lg"
          >
            <p className="text-[10px] text-primary/60 uppercase tracking-wider mb-1">Evidence</p>
            <p className="text-xs text-gray-400 italic line-clamp-2">
              "{effectivePathData!.evidences![0]}"
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
