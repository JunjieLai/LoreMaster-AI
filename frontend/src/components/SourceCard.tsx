import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ExternalLink, MapPin, FileText } from 'lucide-react';
import { Source, ENTITY_ICONS, ENTITY_COLORS } from '../types';
import { useThumbnail } from '../hooks/useThumbnail';

interface SourceCardProps {
  source: Source;
  index: number;
}

export function SourceCard({ source, index }: SourceCardProps) {
  const [isExpanded, setIsExpanded] = useState(index === 0);
  const [imageError, setImageError] = useState(false);
  const { thumbnailUrl, isLoading } = useThumbnail(source.title);

  const icon = ENTITY_ICONS[source.entity_type] || ENTITY_ICONS.default;
  const color = ENTITY_COLORS[source.entity_type] || ENTITY_COLORS.default;
  const relevance = Math.round(source.score * 100);

  const showImage = thumbnailUrl && !imageError;

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1 }}
      className="group"
    >
      <motion.div
        className="glass-light rounded-xl overflow-hidden transition-all duration-300 hover:border-genshin-gold/40"
        style={{ borderColor: isExpanded ? `${color}40` : undefined }}
        whileHover={{ scale: 1.01 }}
      >
        {/* Card Header */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full p-4 flex items-center gap-4 text-left"
        >
          {/* Entity Icon/Thumbnail */}
          <motion.div
            className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl overflow-hidden relative"
            style={{ backgroundColor: `${color}20` }}
            whileHover={{ scale: 1.1, rotate: showImage ? 0 : 5 }}
          >
            {isLoading ? (
              <motion.div
                className="w-6 h-6 border-2 border-t-transparent rounded-full"
                style={{ borderColor: `${color}80`, borderTopColor: 'transparent' }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
            ) : showImage ? (
              <img
                src={thumbnailUrl}
                alt={source.title}
                className="w-full h-full object-cover"
                onError={() => setImageError(true)}
              />
            ) : (
              icon
            )}
          </motion.div>

          {/* Title & Meta */}
          <div className="flex-1 min-w-0">
            <h4 className="text-genshin-gold-light font-medium truncate">
              {source.title}
            </h4>
            <div className="flex items-center gap-2 text-xs text-genshin-text-dim mt-1">
              <span className="px-2 py-0.5 rounded-full" style={{ backgroundColor: `${color}20`, color }}>
                {source.entity_type}
              </span>
              {source.region && (
                <span className="flex items-center gap-1">
                  <MapPin className="w-3 h-3" />
                  {source.region}
                </span>
              )}
              {source.section && (
                <span className="flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  {source.section}
                </span>
              )}
            </div>
          </div>

          {/* Relevance Badge */}
          <div className="flex items-center gap-3">
            <div
              className="px-3 py-1 rounded-full text-sm font-medium"
              style={{
                backgroundColor: relevance > 85 ? 'rgba(123, 200, 108, 0.2)' : 'rgba(107, 181, 255, 0.2)',
                color: relevance > 85 ? '#7BC86C' : '#6BB5FF'
              }}
            >
              {relevance}%
            </div>
            <motion.div
              animate={{ rotate: isExpanded ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown className="w-5 h-5 text-genshin-text-dim" />
            </motion.div>
          </div>
        </button>

        {/* Expanded Content */}
        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 border-t border-white/5">
                {/* Text Content */}
                <p className="text-genshin-text text-sm leading-relaxed mt-4">
                  {source.text}
                </p>

                {/* Wiki Link */}
                {source.source_url && (
                  <motion.a
                    href={source.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-lg bg-genshin-accent/10 text-genshin-accent text-sm hover:bg-genshin-accent/20 transition-colors"
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <ExternalLink className="w-4 h-4" />
                    View on Wiki
                  </motion.a>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}
