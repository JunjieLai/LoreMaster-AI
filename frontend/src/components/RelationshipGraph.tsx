import { useRef, useEffect, useCallback, useState } from 'react';
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import { motion } from 'framer-motion';
import { Maximize2, RotateCcw } from 'lucide-react';
import { PathData, GraphData, GraphNode, GraphLink, ENTITY_COLORS } from '../types';

interface RelationshipGraphProps {
  pathData: PathData;
}

function buildGraphData(pathData: PathData): GraphData {
  const nodesMap = new Map<string, GraphNode>();
  const links: GraphLink[] = [];

  // Add nodes from main path
  pathData.nodes.forEach((name, index) => {
    nodesMap.set(name, {
      id: name,
      name,
      val: index === 0 || index === pathData.nodes.length - 1 ? 20 : 12,
      isMain: true,
      color: index === 0 ? ENTITY_COLORS.Character :
             index === pathData.nodes.length - 1 ? ENTITY_COLORS.Lore :
             ENTITY_COLORS.default,
    });
  });

  // Add links from main path
  for (let i = 0; i < pathData.relations.length; i++) {
    links.push({
      source: pathData.nodes[i],
      target: pathData.nodes[i + 1],
      relation: pathData.relations[i],
      isAlternative: false,
    });
  }

  // Add alternative paths
  pathData.alternative_paths?.forEach((altPath) => {
    altPath.nodes.forEach((name) => {
      if (!nodesMap.has(name)) {
        nodesMap.set(name, {
          id: name,
          name,
          val: 8,
          isMain: false,
          color: '#4A5568',
        });
      }
    });

    for (let i = 0; i < altPath.relations.length; i++) {
      const source = altPath.nodes[i];
      const target = altPath.nodes[i + 1];
      // Avoid duplicate links
      const exists = links.some(
        l => (l.source === source && l.target === target) ||
             (l.source === target && l.target === source)
      );
      if (!exists) {
        links.push({
          source,
          target,
          relation: altPath.relations[i],
          isAlternative: true,
        });
      }
    }
  });

  return {
    nodes: Array.from(nodesMap.values()),
    links,
  };
}

export function RelationshipGraph({ pathData }: RelationshipGraphProps) {
  const graphRef = useRef<ForceGraphMethods>();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 350 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const graphData = buildGraphData(pathData);

  // Handle resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: 350,
        });
      }
    };
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Center graph on load
  useEffect(() => {
    setTimeout(() => {
      graphRef.current?.zoomToFit(400, 50);
    }, 500);
  }, [pathData]);

  const handleNodeHover = useCallback((node: NodeObject | null) => {
    setHoveredNode(node ? (node as GraphNode).id : null);
  }, []);

  const nodeCanvasObject = useCallback((node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const graphNode = node as GraphNode & { x?: number; y?: number };

    // Skip if coordinates not ready
    if (graphNode.x === undefined || graphNode.y === undefined) return;

    const label = graphNode.name;
    const fontSize = 12 / globalScale;
    const nodeSize = (graphNode.val || 10) / globalScale;
    const isHovered = hoveredNode === graphNode.id;

    // Draw glow effect for main nodes
    if (graphNode.isMain || isHovered) {
      const gradient = ctx.createRadialGradient(
        graphNode.x, graphNode.y, nodeSize * 0.5,
        graphNode.x, graphNode.y, nodeSize * 2
      );
      gradient.addColorStop(0, `${graphNode.color}60`);
      gradient.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(graphNode.x, graphNode.y, nodeSize * 2, 0, 2 * Math.PI);
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    // Draw node circle
    ctx.beginPath();
    ctx.arc(graphNode.x, graphNode.y, nodeSize, 0, 2 * Math.PI);
    ctx.fillStyle = graphNode.color || '#D4A053';
    ctx.fill();

    // Draw border
    ctx.strokeStyle = isHovered ? '#fff' : 'rgba(255,255,255,0.3)';
    ctx.lineWidth = isHovered ? 2 / globalScale : 1 / globalScale;
    ctx.stroke();

    // Draw label
    ctx.font = `${fontSize}px "Noto Sans SC", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#E8E4DC';
    ctx.fillText(label, graphNode.x, graphNode.y + nodeSize + 4 / globalScale);
  }, [hoveredNode]);

  const linkCanvasObject = useCallback((link: LinkObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const graphLink = link as GraphLink & {
      source: GraphNode & { x?: number; y?: number };
      target: GraphNode & { x?: number; y?: number };
    };

    const start = graphLink.source;
    const end = graphLink.target;

    // Skip if coordinates not ready
    if (start.x === undefined || start.y === undefined || end.x === undefined || end.y === undefined) return;

    // Draw link line
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);

    if (graphLink.isAlternative) {
      ctx.setLineDash([4 / globalScale, 4 / globalScale]);
      ctx.strokeStyle = 'rgba(107, 181, 255, 0.4)';
    } else {
      ctx.setLineDash([]);
      ctx.strokeStyle = 'rgba(212, 160, 83, 0.6)';
    }

    ctx.lineWidth = graphLink.isAlternative ? 1 / globalScale : 2 / globalScale;
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw relation label
    const midX = (start.x + end.x) / 2;
    const midY = (start.y + end.y) / 2;
    const fontSize = 9 / globalScale;

    ctx.font = `${fontSize}px "Noto Sans SC", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Background for label
    const labelWidth = ctx.measureText(graphLink.relation).width + 8 / globalScale;
    ctx.fillStyle = 'rgba(13, 15, 26, 0.8)';
    ctx.fillRect(midX - labelWidth / 2, midY - fontSize / 2 - 2 / globalScale, labelWidth, fontSize + 4 / globalScale);

    // Label text
    ctx.fillStyle = graphLink.isAlternative ? '#6BB5FF' : '#D4A053';
    ctx.fillText(graphLink.relation, midX, midY);
  }, []);

  const resetView = () => {
    graphRef.current?.zoomToFit(400, 50);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-6"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-genshin-gold font-medium flex items-center gap-2">
          <span className="text-xl">🕸️</span>
          实体关系图
        </h3>
        <div className="flex gap-2">
          <motion.button
            onClick={resetView}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            className="p-2 glass-light rounded-lg text-genshin-text-dim hover:text-genshin-gold transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            className="p-2 glass-light rounded-lg text-genshin-text-dim hover:text-genshin-gold transition-colors"
          >
            <Maximize2 className="w-4 h-4" />
          </motion.button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="glass rounded-xl overflow-hidden border border-genshin-gold/20"
        style={{ height: 350 }}
      >
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="transparent"
          nodeCanvasObject={nodeCanvasObject}
          linkCanvasObject={linkCanvasObject}
          onNodeHover={handleNodeHover}
          nodeRelSize={6}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.9}
          cooldownTicks={100}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
        />
      </div>

      {/* Evidence Section */}
      {pathData.evidences && pathData.evidences.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="mt-4 p-4 glass-light rounded-xl"
        >
          <h4 className="text-sm text-genshin-gold mb-2">📝 关系证据</h4>
          {pathData.evidences.map((evidence, i) => (
            <p key={i} className="text-sm text-genshin-text-dim italic">
              "{evidence}"
            </p>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
