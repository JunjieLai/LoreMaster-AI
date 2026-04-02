import { useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, Coins, ThumbsUp, Copy, Sparkles, X, ExternalLink, MapPin, BookOpen } from 'lucide-react';
import { Message, Source, ENTITY_COLORS } from '../types';
import { useTheme } from '../App';
import { useThumbnail } from '../hooks/useThumbnail';

interface ChatMessageProps {
  message: Message;
}

// Source Modal Component
function SourceModal({
  source,
  onClose
}: {
  source: Source;
  onClose: () => void;
}) {
  const { thumbnailUrl } = useThumbnail(source.title);
  const color = ENTITY_COLORS[source.entity_type] || ENTITY_COLORS.default;
  const relevance = Math.round(source.score * 100);

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
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-primary/15 text-primary border-primary/40">
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

// Parse content and highlight entities with gold theme
function parseContent(content: string, entities: string[] | undefined): string {
  let result = content;

  // First, handle markdown headings (must be done before \n -> <br/> conversion)
  // ## Heading -> styled h3 (mt-3 for spacing from previous paragraph)
  result = result.replace(/^## (.+)$/gm, '<h3 class="text-lg font-bold text-primary mt-3">$1</h3>');
  // ### Heading -> styled h4
  result = result.replace(/^### (.+)$/gm, '<h4 class="text-base font-semibold text-primary mt-3">$1</h4>');
  // # Heading -> styled h2
  result = result.replace(/^# (.+)$/gm, '<h2 class="text-xl font-bold text-primary mt-3">$1</h2>');

  // Remove all newlines around heading tags (spacing handled by margin-top)
  result = result.replace(/(<\/h[234]>)\n+/g, '$1');
  result = result.replace(/\n+(<h[234] )/g, '$1');

  // Handle [Source: xxx] - capture preceding sentence and make it clickable with gold dashed underline
  // Pattern: capture text up to previous period/newline, then [Source: xxx]
  result = result.replace(
    /([^.。\n]+?)(\s*)\[Source:\s*([^\]]+)\]/g,
    '<span class="source-cite cursor-pointer border-b-2 border-dashed border-primary/60 hover:border-primary hover:text-primary transition-colors" data-source="$3">$1</span>$2'
  );

  if (entities && entities.length > 0) {
    // Sort entities by length (longest first) to avoid partial matches
    const sortedEntities = [...entities].sort((a, b) => b.length - a.length);

    // Replace entities with special markers
    sortedEntities.forEach((entity, idx) => {
      const regex = new RegExp(`\\*\\*${entity}\\*\\*`, 'g');
      result = result.replace(regex, `__ENTITY_${idx}__`);
    });

    // Format other markdown - use gold colors for emphasis
    result = result
      .replace(/\*\*(.*?)\*\*/g, '<strong class="text-primary font-bold">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em class="text-primary/80 italic">$1</em>')
      .replace(/\[Relation: (.*?)\]/g, '')
      .replace(/(\d+)\.\s\*\*/g, '<span class="text-primary font-bold">$1.</span> **')
      .replace(/\n/g, '<br/>');

    // Replace markers with highlighted spans
    sortedEntities.forEach((entity, idx) => {
      const marker = `__ENTITY_${idx}__`;
      const replacement = `<strong class="entity-keyword text-primary font-bold" data-entity="${entity}">${entity}</strong>`;
      result = result.split(marker).join(replacement);
    });
  } else {
    result = result
      .replace(/\*\*(.*?)\*\*/g, '<strong class="text-primary font-bold">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em class="text-primary/80 italic">$1</em>')
      .replace(/\[Relation: (.*?)\]/g, '')
      .replace(/(\d+)\.\s\*\*/g, '<span class="text-primary font-bold">$1.</span> **')
      .replace(/\n/g, '<br/>');
  }

  return result;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { setHoveredEntity } = useTheme();
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const isUser = message.role === 'user';

  const handleMouseOver = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('entity-keyword')) {
      const entity = target.getAttribute('data-entity');
      setHoveredEntity(entity);
    }
  };

  const handleMouseOut = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('entity-keyword')) {
      setHoveredEntity(null);
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('source-cite')) {
      const sourceName = target.getAttribute('data-source');
      if (sourceName && message.sources) {
        // Find the source that matches the name (partial match)
        const source = message.sources.find(s =>
          s.title.toLowerCase().includes(sourceName.toLowerCase()) ||
          sourceName.toLowerCase().includes(s.title.toLowerCase())
        );
        if (source) {
          setSelectedSource(source);
        }
      }
    }
  };

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-row-reverse gap-4 max-w-3xl mx-auto group"
      >
        {/* User Avatar */}
        <div className="w-10 h-10 rounded-full overflow-hidden border-2 border-primary/40 shrink-0 shadow-[0_0_15px_rgba(212,161,84,0.15)] group-hover:border-primary/80 transition-colors bg-navy-light flex items-center justify-center">
          <span className="text-primary text-sm font-bold">T</span>
        </div>

        {/* Message */}
        <div className="flex flex-col items-end gap-1 max-w-[80%]">
          <div className="bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/30 rounded-2xl rounded-tr-sm px-6 py-4 text-gray-100 shadow-lg backdrop-blur-sm group-hover:shadow-[0_4px_20px_rgba(212,161,84,0.1)] transition-all">
            <p className="leading-relaxed font-light">{message.content}</p>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-2">Traveler</span>
        </div>
      </motion.div>
    );
  }

  // Assistant message
  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex gap-5 max-w-3xl mx-auto relative group/chat"
      >
        {/* AI Avatar */}
        <div className="w-10 h-10 relative shrink-0">
          <div className="absolute inset-0 bg-primary/20 rounded rotate-45 animate-pulse-slow"></div>
          <div className="absolute inset-0 border border-primary bg-navy-deep rounded rotate-45 flex items-center justify-center shadow-[0_0_15px_rgba(212,161,84,0.3)] z-10">
            <Sparkles className="w-4 h-4 text-primary transform -rotate-45" />
          </div>
        </div>

        {/* Message Content */}
        <div className="flex flex-col gap-2 max-w-[90%] w-full">
          <div className="glass-panel rounded-2xl rounded-tl-sm px-6 py-5 text-gray-200 shadow-xl relative overflow-hidden">
            {/* Top accent line */}
            <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent"></div>

            {/* Title if present */}
            {message.queryType && (
              <h3 className="text-lg font-bold text-primary mb-4 flex items-center gap-2 pb-2 border-b border-primary/10">
                <Sparkles className="w-4 h-4" />
                {message.queryType === 'RELATIONSHIP' ? 'Relationship Analysis' :
                 message.queryType === 'FACTUAL' ? 'Factual Query' :
                 message.queryType}
              </h3>
            )}

            {/* Content with entity highlighting and source citations */}
            <div
              className="prose prose-invert prose-p:text-gray-300 prose-headings:text-primary prose-strong:text-primary/90 max-w-none relative z-10 text-sm leading-relaxed"
              dangerouslySetInnerHTML={{
                __html: parseContent(message.content, message.entities)
              }}
              onMouseOver={handleMouseOver}
              onMouseOut={handleMouseOut}
              onClick={handleClick}
            />

            {/* Tags */}
            {message.entities && message.entities.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-primary/10">
                {message.entities.slice(0, 5).map((entity) => (
                  <span
                    key={entity}
                    className="text-[10px] uppercase tracking-wider px-2 py-1 rounded bg-primary/5 border border-primary/20 text-primary/70 hover:bg-primary/20 hover:text-primary cursor-pointer transition-colors"
                    onMouseEnter={() => setHoveredEntity(entity)}
                    onMouseLeave={() => setHoveredEntity(null)}
                  >
                    #{entity.toLowerCase().replace(/\s+/g, '-')}
                  </span>
                ))}
              </div>
            )}

            {/* Metadata Badges */}
            {(message.timing || message.cost) && (
              <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-primary/10">
                {message.timing && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-genshin-accent/15 text-genshin-accent text-xs">
                    <Clock className="w-3 h-3" />
                    {message.timing.total.toFixed(2)}s
                  </span>
                )}
                {message.cost !== undefined && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-genshin-pyro/15 text-genshin-pyro text-xs">
                    <Coins className="w-3 h-3" />
                    ${message.cost.toFixed(4)}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-between px-2 mt-1">
            <span className="text-[10px] uppercase tracking-wider text-gray-500">LoreMaster</span>
            <div className="flex gap-2">
              <button type="button" title="Like" className="text-gray-500 hover:text-primary transition-colors p-1 rounded hover:bg-primary/10">
                <ThumbsUp className="w-4 h-4" />
              </button>
              <button type="button" title="Copy" className="text-gray-500 hover:text-primary transition-colors p-1 rounded hover:bg-primary/10">
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Source Modal - rendered via portal */}
      {createPortal(
        <AnimatePresence>
          {selectedSource && (
            <SourceModal
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
