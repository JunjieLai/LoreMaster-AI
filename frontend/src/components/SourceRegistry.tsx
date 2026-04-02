import { useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ExternalLink, Sparkles, MapPin, ChevronDown, X, BookOpen } from 'lucide-react';
import { Source, ENTITY_COLORS } from '../types';
import { useThumbnail } from '../hooks/useThumbnail';
import { useTheme } from '../App';

interface SourceRegistryProps {
  sources: Source[];
}

// Get relevance badge color based on score - unified color scale
function getRelevanceBadgeStyle(relevance: number): string {
  if (relevance >= 95) {
    return 'bg-emerald-900/60 text-emerald-300 border-emerald-500/50';
  } else if (relevance >= 90) {
    return 'bg-green-900/50 text-green-400 border-green-500/40';
  } else if (relevance >= 85) {
    return 'bg-primary/25 text-primary border-primary/50';
  } else if (relevance >= 80) {
    return 'bg-primary/15 text-primary/90 border-primary/40';
  } else if (relevance >= 75) {
    return 'bg-amber-900/40 text-amber-400 border-amber-500/40';
  } else if (relevance >= 70) {
    return 'bg-orange-900/40 text-orange-400 border-orange-500/40';
  } else {
    return 'bg-gray-800/50 text-gray-400 border-gray-600/40';
  }
}

// Full text modal component
function TextModal({
  source,
  onClose
}: {
  source: Source;
  onClose: () => void;
}) {
  const { thumbnailUrl } = useThumbnail(source.title);
  const color = ENTITY_COLORS[source.entity_type] || ENTITY_COLORS.default;
  const relevance = Math.round(source.score * 100);
  const badgeStyle = getRelevanceBadgeStyle(relevance);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        onClick={(e) => e.stopPropagation()}
        className="relative max-w-2xl w-full max-h-[80vh] overflow-hidden rounded-xl border border-primary/40 bg-navy-deep shadow-[0_0_50px_rgba(0,0,0,0.5),0_0_30px_rgba(212,161,84,0.15)]"
      >
        {/* Top accent line */}
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary/60 via-primary to-primary/60"></div>

        {/* Close button */}
        <button
          type="button"
          title="Close"
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-2 rounded-lg bg-black/40 border border-primary/30 text-primary/70 hover:text-primary hover:border-primary/60 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Header */}
        <div className="p-5 pb-4 border-b border-primary/20 bg-gradient-to-r from-primary/10 to-transparent">
          <div className="flex gap-4 items-start pr-10">
            {/* Thumbnail */}
            <div
              className="w-16 h-20 rounded-lg overflow-hidden shrink-0 border-2 shadow-lg"
              style={{ borderColor: `${color}60` }}
            >
              {thumbnailUrl ? (
                <img
                  src={thumbnailUrl}
                  alt={source.title}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-navy-light flex items-center justify-center">
                  <BookOpen className="w-6 h-6 text-primary/40" />
                </div>
              )}
            </div>

            {/* Title and meta */}
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-bold text-primary mb-2 flex items-center gap-2">
                <Sparkles className="w-4 h-4 shrink-0" />
                {source.title}
              </h3>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded"
                  style={{ backgroundColor: `${color}25`, color: color }}
                >
                  {source.entity_type}
                </span>
                {source.section && (
                  <span className="text-[10px] text-gray-400">• {source.section}</span>
                )}
                {source.region && (
                  <span className="text-[10px] text-gray-400 flex items-center gap-1">
                    <MapPin className="w-2.5 h-2.5" />
                    {source.region}
                  </span>
                )}
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeStyle}`}>
                  {relevance}% Match
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Content - scrollable */}
        <div className="p-5 overflow-y-auto max-h-[50vh]">
          <div className="bg-black/30 rounded-lg p-4 border border-primary/10">
            <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">
              {source.text || "No text content available."}
            </p>
          </div>
        </div>

        {/* Footer */}
        {source.source_url && (
          <div className="px-5 py-3 border-t border-primary/20 bg-black/30">
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-primary hover:text-primary-glow transition-colors group"
            >
              <ExternalLink className="w-4 h-4 group-hover:scale-110 transition-transform" />
              View Full Article on Wiki
            </a>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

function SourceCard({
  source,
  index,
  onTextClick
}: {
  source: Source;
  index: number;
  onTextClick: (source: Source) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { thumbnailUrl, isLoading } = useThumbnail(source.title);
  const { hoveredEntity } = useTheme();
  const isHighlighted = hoveredEntity === source.title;
  const isFirst = index === 0;

  const color = ENTITY_COLORS[source.entity_type] || ENTITY_COLORS.default;
  const relevance = Math.round(source.score * 100);
  const badgeStyle = getRelevanceBadgeStyle(relevance);

  const handleCardClick = () => {
    setIsExpanded(!isExpanded);
  };

  const handleTextClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onTextClick(source);
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1 }}
      onClick={handleCardClick}
      className={`group relative rounded-lg p-3 cursor-pointer overflow-hidden transition-all duration-300 ${
        isFirst
          ? 'bg-navy-light border border-primary/50 shadow-[0_0_20px_rgba(0,0,0,0.3)] ring-1 ring-primary/20'
          : 'bg-navy-light/40 border border-primary/10 hover:bg-navy-light hover:border-primary/40'
      } ${isHighlighted ? 'ring-2 ring-primary/60' : ''}`}
    >
      {/* Left accent bar for primary source */}
      {isFirst && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary"></div>}

      {/* Relevance badge - always visible at top right with unified color scale */}
      <div className={`absolute top-2 right-2 flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${badgeStyle}`}>
        <Sparkles className="w-2.5 h-2.5" />
        {relevance}%
      </div>

      <div className="flex gap-3 items-start">
        {/* Thumbnail - Fixed size for all cards */}
        <div
          className="w-12 h-14 rounded overflow-hidden shrink-0 border shadow-md relative group-hover:scale-105 transition-transform"
          style={{ borderColor: `${color}40` }}
        >
          {isLoading ? (
            <div className="w-full h-full bg-navy-deep flex items-center justify-center">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                className="w-3 h-3 border-2 border-primary/30 border-t-primary rounded-full"
              />
            </div>
          ) : thumbnailUrl ? (
            <img
              src={thumbnailUrl}
              alt={source.title}
              className="w-full h-full object-cover opacity-90"
            />
          ) : (
            <div className="w-full h-full bg-navy-deep flex items-center justify-center">
              <span className="text-lg opacity-50">📜</span>
            </div>
          )}
          <div className="absolute inset-0 bg-primary/10"></div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 pt-0.5 pr-14">
          <div className="flex items-center gap-2 mb-1">
            <h4 className={`text-sm font-semibold truncate transition-colors ${
              isFirst ? 'text-primary' : 'text-primary/90 group-hover:text-primary'
            }`}>
              {source.title}
            </h4>
            <ChevronDown
              className={`w-3 h-3 text-primary/50 shrink-0 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            />
          </div>

          <div className="flex items-center gap-2 mb-1.5">
            <span
              className="text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded"
              style={{ backgroundColor: `${color}20`, color: color }}
            >
              {source.entity_type}
            </span>
            {source.section && (
              <span className="text-[9px] text-gray-500">• {source.section}</span>
            )}
            {source.region && (
              <span className="text-[9px] text-gray-500 flex items-center gap-0.5">
                <MapPin className="w-2 h-2" />
                {source.region}
              </span>
            )}
          </div>

          {isExpanded ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div
                onClick={handleTextClick}
                className="bg-black/30 p-2 rounded border border-primary/10 mb-2 cursor-pointer hover:bg-black/50 hover:border-primary/30 transition-colors group/text"
              >
                <p className="text-xs text-gray-300 leading-relaxed italic line-clamp-3 group-hover/text:text-gray-200">
                  "{source.text}"
                </p>
                <span className="text-[9px] text-primary/60 group-hover/text:text-primary mt-1 inline-block">
                  Click to view full text
                </span>
              </div>
              {source.source_url && (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-[10px] text-primary hover:text-primary-glow hover:underline inline-flex items-center gap-1"
                >
                  <ExternalLink className="w-3 h-3" />
                  View on Wiki
                </a>
              )}
            </motion.div>
          ) : (
            <p className="text-[11px] text-gray-400 line-clamp-1 leading-relaxed">
              {source.text}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export function SourceRegistry({ sources }: SourceRegistryProps) {
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);

  return (
    <>
      <div className="space-y-2">
        {sources.map((source, index) => (
          <SourceCard
            key={source.title}
            source={source}
            index={index}
            onTextClick={setSelectedSource}
          />
        ))}
      </div>

      {/* Full text modal - rendered via portal to body */}
      {createPortal(
        <AnimatePresence>
          {selectedSource && (
            <TextModal
              source={selectedSource}
              onClose={() => setSelectedSource(null)}
            />
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
}
