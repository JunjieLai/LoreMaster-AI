import { useState, useEffect, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Search, Sparkles, Clock, MessageSquare, Database, GripVertical } from 'lucide-react';
import { ConstellationGraph } from './ConstellationGraph';
import { SourceRegistry } from './SourceRegistry';
import { ChatMessage } from './ChatMessage';
import { ENTITY_COLORS } from '../types';
import type { PathData, GraphResult, Message } from '../types';
import { API_BASE } from '../config';

// ── Constants ─────────────────────────────────────────────────────────────────

const COMPACT_WIDTH  = 48;
const WIDE_WIDTH     = 280;
const SNAP_THRESHOLD = 160;
const MAX_RAIL_WIDTH = 400;

// ── Local types ───────────────────────────────────────────────────────────────

// One cached Q&A entry (Cache tab)
interface HistoryEntry {
  question: string;
  answer: string;
  entities: string[];
  timestamp: number;
  query_type: string;
  sources: Message['sources'];
  path?: PathData;
  graph_results?: GraphResult[];
  _msgId?: string;
}

// One full session (Conversations tab) — mirrors App.tsx StoredConversation
interface StoredConversation {
  sessionId: string;
  startedAt: number;
  messages: Message[];
}

// One turn inside a conversation
interface ConvTurn {
  question: string;
  assistantMsg: Message;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(ts: number): string {
  if (!ts) return 'Today';
  const d = new Date(ts * 1000);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return 'Today';
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatTimestamp(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function queryTypeMeta(qt: string): { bg: string; text: string; label: string } {
  switch (qt) {
    case 'RELATIONSHIP': return { bg: 'rgba(176,123,204,0.2)', text: '#B07BCC', label: 'Relation' };
    case 'MULTI_HOP':    return { bg: 'rgba(123,200,108,0.2)', text: '#7BC86C', label: 'Multi-hop' };
    case 'FACTUAL':      return { bg: 'rgba(239,122,53,0.2)',  text: '#EF7A35', label: 'Factual' };
    default:             return { bg: 'rgba(212,160,83,0.15)', text: '#D4A053', label: qt || 'Query' };
  }
}

// ── Cache tab helpers ─────────────────────────────────────────────────────────

function groupByDate(entries: HistoryEntry[]): { label: string; items: HistoryEntry[] }[] {
  const groups: Record<string, HistoryEntry[]> = {};
  for (const e of entries) {
    const label = formatDate(e.timestamp);
    if (!groups[label]) groups[label] = [];
    groups[label].push(e);
  }
  return Object.entries(groups).map(([label, items]) => ({ label, items }));
}

function getKey(e: HistoryEntry): string {
  return e._msgId ?? `${e.timestamp}-${e.question.slice(0, 20)}`;
}

function entryToMessage(entry: HistoryEntry, id: string): Message {
  return {
    id,
    role: 'assistant',
    content: entry.answer,
    sources: entry.sources,
    path: entry.path,
    graphResults: entry.graph_results,
    entities: entry.entities,
    queryType: entry.query_type,
  };
}

// ── Conversation helpers ──────────────────────────────────────────────────────

function convKey(conv: StoredConversation): string {
  return conv.sessionId || 'current';
}

function convTurns(conv: StoredConversation): ConvTurn[] {
  const turns: ConvTurn[] = [];
  const msgs = conv.messages;
  for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i];
    if (msg.role !== 'assistant' || msg.streaming) continue;
    const userMsg = i > 0 && msgs[i - 1].role === 'user' ? msgs[i - 1] : null;
    turns.push({ question: userMsg?.content ?? '(unknown)', assistantMsg: msg });
  }
  return turns;
}

function convLastQueryType(conv: StoredConversation): string {
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    const m = conv.messages[i];
    if (m.role === 'assistant' && !m.streaming && m.queryType) return m.queryType;
  }
  return 'FACTUAL';
}

function convFirstQuestion(conv: StoredConversation): string {
  for (const m of conv.messages) {
    if (m.role === 'user') return m.content;
  }
  return '(empty conversation)';
}

function groupConvsByDate(convs: StoredConversation[]): { label: string; items: StoredConversation[] }[] {
  const groups: Record<string, StoredConversation[]> = {};
  for (const c of convs) {
    const label = formatDate(c.startedAt);
    if (!groups[label]) groups[label] = [];
    groups[label].push(c);
  }
  return Object.entries(groups).map(([label, items]) => ({ label, items }));
}

// ── HistoryCard (Cache tab) ───────────────────────────────────────────────────

function HistoryCard({
  entry,
  isSelected,
  badge,
  onClick,
}: {
  entry: HistoryEntry;
  isSelected: boolean;
  badge?: string;
  onClick: () => void;
}) {
  const qt = queryTypeMeta(entry.query_type);
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-200 group relative overflow-hidden
        ${isSelected
          ? 'border-primary/60 bg-primary/8 shadow-[0_0_20px_rgba(212,161,84,0.1)]'
          : 'border-primary/15 bg-navy-light/20 hover:border-primary/35 hover:bg-navy-light/40'
        }`}
    >
      {isSelected && (
        <div className="absolute left-0 top-3 bottom-3 w-[3px] bg-primary rounded-full" />
      )}
      <div className="flex items-start gap-3 pl-1">
        <div
          className="w-3.5 h-3.5 rounded-sm rotate-45 shrink-0 mt-1"
          style={{
            backgroundColor: isSelected ? '#D4A053' : qt.text,
            opacity: isSelected ? 1 : 0.4,
            boxShadow: isSelected ? '0 0 10px #D4A05380' : 'none',
            transition: 'opacity 0.15s, box-shadow 0.15s',
          }}
        />
        <p className="text-sm font-medium text-gray-200 leading-snug line-clamp-1 flex-1 group-hover:text-primary/90 transition-colors">
          {entry.question}
        </p>
      </div>
      <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 mt-2 pl-6">
        {entry.answer.replace(/#+\s/g, '').replace(/\*\*/g, '').slice(0, 160)}
      </p>
      <div className="flex items-center gap-1.5 mt-3 pl-6 flex-wrap">
        {entry.entities.slice(0, 2).map(e => (
          <span key={e} className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/8 border border-primary/20 text-primary/50">
            {e}
          </span>
        ))}
        <span
          className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded font-semibold"
          style={{ backgroundColor: qt.bg, color: qt.text }}
        >
          {qt.label}
        </span>
        {badge && (
          <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-sky-900/30 text-sky-400 border border-sky-500/20 font-semibold">
            {badge}
          </span>
        )}
        {entry.timestamp > 0 && (
          <span className="ml-auto text-[9px] text-gray-600 shrink-0">{formatTimestamp(entry.timestamp)}</span>
        )}
      </div>
    </motion.button>
  );
}

// ── ConversationCard (Conversations tab) ──────────────────────────────────────

function ConversationCard({
  conv,
  isSelected,
  isActive,
  onClick,
}: {
  conv: StoredConversation;
  isSelected: boolean;
  isActive?: boolean;
  onClick: () => void;
}) {
  const qt = queryTypeMeta(convLastQueryType(conv));
  const turns = convTurns(conv);
  const firstQ = convFirstQuestion(conv);
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-200 group relative overflow-hidden
        ${isSelected
          ? 'border-primary/60 bg-primary/8 shadow-[0_0_20px_rgba(212,161,84,0.1)]'
          : 'border-primary/15 bg-navy-light/20 hover:border-primary/35 hover:bg-navy-light/40'
        }`}
    >
      {isSelected && (
        <div className="absolute left-0 top-3 bottom-3 w-[3px] bg-primary rounded-full" />
      )}
      <div className="flex items-start gap-3 pl-1">
        <div
          className="w-3.5 h-3.5 rounded-sm rotate-45 shrink-0 mt-1"
          style={{
            backgroundColor: isSelected ? '#D4A053' : qt.text,
            opacity: isSelected ? 1 : 0.4,
            boxShadow: isSelected ? '0 0 10px #D4A05380' : 'none',
            transition: 'opacity 0.15s, box-shadow 0.15s',
          }}
        />
        <p className="text-sm font-medium text-gray-200 leading-snug line-clamp-1 flex-1 group-hover:text-primary/90 transition-colors">
          {firstQ}
        </p>
      </div>
      <div className="flex items-center gap-1.5 mt-3 pl-6 flex-wrap">
        <span className="text-[9px] font-mono text-gray-600">
          {turns.length} {turns.length === 1 ? 'turn' : 'turns'}
        </span>
        {isActive && (
          <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-green-900/30 text-green-400 border border-green-500/20 font-semibold">
            Active
          </span>
        )}
        <span
          className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded font-semibold"
          style={{ backgroundColor: qt.bg, color: qt.text }}
        >
          {qt.label}
        </span>
        {conv.startedAt > 0 && (
          <span className="ml-auto text-[9px] text-gray-600 shrink-0">{formatTimestamp(conv.startedAt)}</span>
        )}
      </div>
    </motion.button>
  );
}

// ── DiamondItem ───────────────────────────────────────────────────────────────

function DiamondItem({
  queryType,
  title,
  isSelected,
  onClick,
}: {
  queryType: string;
  title: string;
  isSelected: boolean;
  onClick: () => void;
}) {
  const qt = queryTypeMeta(queryType);
  const color = isSelected ? '#D4A053' : qt.text;
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="w-full flex items-center justify-center rounded hover:bg-primary/8 transition-colors"
      style={{ height: 40 }}
    >
      <div
        style={{
          width: 13,
          height: 13,
          transform: 'rotate(45deg)',
          borderRadius: 2,
          backgroundColor: color,
          opacity: isSelected ? 1 : 0.4,
          boxShadow: isSelected ? `0 0 10px ${color}80` : 'none',
          transition: 'opacity 0.15s, box-shadow 0.15s',
        }}
      />
    </button>
  );
}

// ── AnswerSidebarLayout (single turn detail) ──────────────────────────────────

function AnswerSidebarLayout({ entry }: { entry: HistoryEntry }) {
  const msgId = entry._msgId ?? `hist-${entry.timestamp}-${entry.question.slice(0, 8)}`;
  const message = entryToMessage(entry, msgId);
  const hasGraph = !!(entry.path || (entry.graph_results && entry.graph_results.length > 0));
  const hasSources = !!(entry.sources && entry.sources.length > 0);

  return (
    <motion.div
      key={msgId}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="flex flex-1 h-full overflow-hidden"
    >
      {/* Answer */}
      <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
        <ChatMessage message={message} isSelected={false} />
        <div className="h-32" />
      </div>

      {/* Graph + Sources sidebar */}
      <aside
        className="shrink-0 flex flex-col border-l border-primary/20 bg-navy-deep overflow-hidden"
        style={{ width: '40%' }}
      >
        <div
          className="relative border-b border-primary/20 bg-navy-deep/50 overflow-hidden"
          style={{ height: hasGraph ? '55%' : 0 }}
        >
          {hasGraph && (
            <>
              <div className="absolute top-3 left-4 right-4 z-10 flex items-center gap-2">
                <span className="w-5 h-5 bg-primary/20 rounded rotate-45 flex items-center justify-center border border-primary/30 shrink-0">
                  <Sparkles className="w-3 h-3 text-primary -rotate-45" />
                </span>
                <h2 className="text-sm font-bold text-primary tracking-widest uppercase drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
                  Constellation Map
                </h2>
              </div>
              <ConstellationGraph
                key={`hist-graph-${msgId}`}
                pathData={entry.path}
                graphResults={entry.graph_results}
              />
            </>
          )}
        </div>
        <div
          className="flex flex-col min-h-0 bg-navy-deep/95 backdrop-blur-md"
          style={{ height: hasGraph ? '45%' : '100%' }}
        >
          <div className="px-5 py-3 border-b border-primary/10 flex items-center justify-between bg-gradient-to-r from-primary/10 to-transparent shrink-0">
            <h2 className="text-sm font-bold text-primary tracking-widest uppercase flex items-center gap-2">
              <span className="w-5 h-5 bg-primary/20 rounded rotate-45 flex items-center justify-center border border-primary/30">
                <Sparkles className="w-3 h-3 text-primary -rotate-45" />
              </span>
              Source Registry
            </h2>
            {hasSources && (
              <span className="text-[10px] font-mono text-primary/80 bg-black/40 px-2 py-0.5 rounded border border-primary/30">
                {entry.sources!.length} Sources
              </span>
            )}
          </div>
          <div className="overflow-y-auto p-4 flex-1">
            {hasSources ? (
              <SourceRegistry key={`hist-src-${msgId}`} sources={entry.sources!} />
            ) : (
              <div className="text-center text-gray-500 py-8 text-sm">No sources available</div>
            )}
          </div>
        </div>
      </aside>
    </motion.div>
  );
}

// ── ConversationDetailLayout (multi-turn) ─────────────────────────────────────

function ConversationDetailLayout({
  conv,
  selectedTurnIndex,
  onSelectTurn,
}: {
  conv: StoredConversation;
  selectedTurnIndex: number;
  onSelectTurn: (i: number) => void;
}) {
  const turns = convTurns(conv);
  if (turns.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
        No completed turns in this conversation.
      </div>
    );
  }

  const safeIndex = Math.min(selectedTurnIndex, turns.length - 1);
  const turn = turns[safeIndex];

  // Convert the selected turn's assistant message to HistoryEntry for AnswerSidebarLayout
  const entry: HistoryEntry = {
    question: turn.question,
    answer: turn.assistantMsg.content,
    entities: turn.assistantMsg.entities ?? [],
    timestamp: 0,
    query_type: turn.assistantMsg.queryType ?? 'FACTUAL',
    sources: turn.assistantMsg.sources ?? [],
    path: turn.assistantMsg.path,
    graph_results: turn.assistantMsg.graphResults,
    _msgId: turn.assistantMsg.id,
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Turn selector strip */}
      {turns.length > 1 && (
        <div className="shrink-0 flex items-center gap-1.5 px-4 py-2 border-b border-primary/15 bg-navy-deep/80 overflow-x-auto">
          <span className="text-[9px] uppercase tracking-widest text-gray-600 shrink-0 mr-1">Turn</span>
          {turns.map((t, i) => {
            const qt = queryTypeMeta(t.assistantMsg.queryType ?? 'FACTUAL');
            const isActive = i === safeIndex;
            return (
              <button
                key={t.assistantMsg.id}
                type="button"
                title={t.question}
                onClick={() => onSelectTurn(i)}
                className={`shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-semibold border transition-all ${
                  isActive
                    ? 'bg-primary/20 border-primary/40 text-primary'
                    : 'border-primary/15 text-gray-500 hover:text-gray-300 hover:border-primary/25'
                }`}
              >
                <div
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 1,
                    transform: 'rotate(45deg)',
                    backgroundColor: isActive ? '#D4A053' : qt.text,
                    opacity: isActive ? 1 : 0.5,
                  }}
                />
                {i + 1}
              </button>
            );
          })}
        </div>
      )}

      {/* Reuse AnswerSidebarLayout for the selected turn */}
      <div className="flex flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <AnswerSidebarLayout key={entry._msgId} entry={entry} />
        </AnimatePresence>
      </div>
    </div>
  );
}

// ── HistoryExplorer ───────────────────────────────────────────────────────────

interface HistoryExplorerProps {
  onClose: () => void;
  messages: Message[];
  storedConversations: StoredConversation[];
}

export function HistoryExplorer({ onClose, messages, storedConversations }: HistoryExplorerProps) {
  type Tab = 'conversations' | 'cache';
  const [tab, setTab] = useState<Tab>('conversations');
  const [search, setSearch] = useState('');

  // Conversations tab: selectedConvKey = sessionId or 'current'
  const [selectedConvKey, setSelectedConvKey] = useState<string | null>(null);
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number>(0);

  // Cache tab: selectedCacheKey = HistoryEntry key
  const [selectedCacheKey, setSelectedCacheKey] = useState<string | null>(null);

  const [cacheEntries, setCacheEntries] = useState<HistoryEntry[]>([]);
  const [cacheLoading, setCacheLoading] = useState(true);
  const [cacheError, setCacheError] = useState<string | null>(null);

  // Rail resize state
  const [railWidth, setRailWidth] = useState(WIDE_WIDTH);
  const [isResizingRail, setIsResizingRail] = useState(false);
  const isCompact = railWidth < SNAP_THRESHOLD;

  // Drag handlers
  const handleRailMouseMove = useCallback((e: MouseEvent) => {
    const newWidth = Math.min(Math.max(e.clientX, COMPACT_WIDTH), MAX_RAIL_WIDTH);
    setRailWidth(newWidth);
  }, []);

  const handleRailMouseUp = useCallback(() => {
    setIsResizingRail(false);
    setRailWidth(prev => prev < SNAP_THRESHOLD ? COMPACT_WIDTH : WIDE_WIDTH);
  }, []);

  useEffect(() => {
    if (!isResizingRail) return;
    document.addEventListener('mousemove', handleRailMouseMove);
    document.addEventListener('mouseup', handleRailMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.removeEventListener('mousemove', handleRailMouseMove);
      document.removeEventListener('mouseup', handleRailMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizingRail, handleRailMouseMove, handleRailMouseUp]);

  // ESC to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  // Fetch cache on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/cache/history`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(d => {
        setCacheEntries((d.entries ?? []).map((e: any) => ({
          question: e.question,
          answer: e.answer,
          entities: e.entities ?? [],
          timestamp: e.timestamp ?? 0,
          query_type: e.query_type ?? 'FACTUAL',
          sources: e.sources ?? [],
          path: e.path,
          graph_results: e.graph_results,
        })));
      })
      .catch(() => setCacheError('Failed to load cache'))
      .finally(() => setCacheLoading(false));
  }, []);

  // Build the conversation list:
  // current session (if has messages) + storedConversations
  const allConvs = useMemo<StoredConversation[]>(() => {
    const stableMessages = messages.filter(m => !m.streaming);
    const hasCurrentSession = stableMessages.some(m => m.role === 'assistant');
    const currentConv: StoredConversation[] = hasCurrentSession
      ? [{ sessionId: 'current', startedAt: 0, messages: stableMessages }]
      : [];
    return [...currentConv, ...storedConversations];
  }, [messages, storedConversations]);

  // Filtered conversations
  const activeConvs = useMemo<StoredConversation[]>(() => {
    if (!search.trim()) return allConvs;
    const q = search.toLowerCase();
    return allConvs.filter(c =>
      c.messages.some(m => m.content.toLowerCase().includes(q))
    );
  }, [allConvs, search]);

  // Filtered cache entries
  const activeCacheEntries = useMemo<HistoryEntry[]>(() => {
    if (!search.trim()) return cacheEntries;
    const q = search.toLowerCase();
    return cacheEntries.filter(e =>
      e.question.toLowerCase().includes(q) ||
      e.answer.slice(0, 400).toLowerCase().includes(q)
    );
  }, [cacheEntries, search]);

  const groupedConvs = useMemo(() => groupConvsByDate(activeConvs), [activeConvs]);
  const groupedCache = useMemo(() => groupByDate(activeCacheEntries), [activeCacheEntries]);

  const selectedConv = useMemo<StoredConversation | null>(() => {
    if (!selectedConvKey) return null;
    return activeConvs.find(c => convKey(c) === selectedConvKey) ?? null;
  }, [selectedConvKey, activeConvs]);

  const selectedCacheEntry = useMemo<HistoryEntry | null>(() => {
    if (!selectedCacheKey) return null;
    return activeCacheEntries.find(e => getKey(e) === selectedCacheKey) ?? null;
  }, [selectedCacheKey, activeCacheEntries]);

  const isLoading = tab === 'cache' && cacheLoading;
  const error = tab === 'cache' ? cacheError : null;

  const handleTabSwitch = (t: Tab) => {
    setTab(t);
    setSearch('');
    // Clear selections when switching tabs
    setSelectedConvKey(null);
    setSelectedCacheKey(null);
  };

  const handleSelectConv = (key: string, conv: StoredConversation) => {
    if (selectedConvKey === key) {
      setSelectedConvKey(null);
    } else {
      setSelectedConvKey(key);
      // Default to last turn
      const turns = convTurns(conv);
      setSelectedTurnIndex(Math.max(0, turns.length - 1));
    }
  };

  const handleSelectCache = (key: string) => {
    setSelectedCacheKey(prev => prev === key ? null : key);
  };

  // Content area: what to render on the right
  const contentArea = tab === 'conversations'
    ? (selectedConv
        ? <ConversationDetailLayout
            key={convKey(selectedConv)}
            conv={selectedConv}
            selectedTurnIndex={selectedTurnIndex}
            onSelectTurn={setSelectedTurnIndex}
          />
        : null)
    : (selectedCacheEntry
        ? <AnswerSidebarLayout key={getKey(selectedCacheEntry)} entry={selectedCacheEntry} />
        : null);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex flex-col bg-navy-deep"
    >
      <div className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent" />

      {/* Header */}
      <div className="shrink-0 flex items-center gap-3 px-6 py-4 border-b border-primary/20 bg-navy-deep/95 backdrop-blur-sm relative z-40 shadow-[0_2px_15px_rgba(0,0,0,0.5)]">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 bg-primary/20 rounded rotate-45 flex items-center justify-center border border-primary/30">
            <Clock className="w-3 h-3 text-primary -rotate-45" />
          </span>
          <span className="text-sm font-bold text-primary tracking-widest uppercase">History</span>
        </div>
        <div className="flex-1" />
        <button
          type="button"
          title="Close"
          onClick={onClose}
          className="p-2 rounded-lg bg-black/30 border border-primary/20 text-primary/60 hover:text-primary hover:border-primary/50 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Rail ── */}
        <div
          className="shrink-0 flex flex-col border-r border-primary/15 bg-navy-deep/60 overflow-hidden"
          style={{
            width: railWidth,
            transition: isResizingRail ? 'none' : 'width 0.2s cubic-bezier(0.25,0.46,0.45,0.94)',
          }}
        >
          {isCompact ? (
            // ── Compact: diamond list ──────────────────────────────────────
            <div className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
              {tab === 'conversations' ? (
                activeConvs.length === 0 ? (
                  <div className="flex items-center justify-center pt-8">
                    <div className="w-3 h-3 rounded-sm rotate-45" style={{ backgroundColor: ENTITY_COLORS.default, opacity: 0.15 }} />
                  </div>
                ) : (
                  activeConvs.map(conv => (
                    <DiamondItem
                      key={convKey(conv)}
                      queryType={convLastQueryType(conv)}
                      title={convFirstQuestion(conv)}
                      isSelected={selectedConvKey === convKey(conv)}
                      onClick={() => handleSelectConv(convKey(conv), conv)}
                    />
                  ))
                )
              ) : (
                activeCacheEntries.length === 0 ? (
                  <div className="flex items-center justify-center pt-8">
                    <div className="w-3 h-3 rounded-sm rotate-45" style={{ backgroundColor: ENTITY_COLORS.default, opacity: 0.15 }} />
                  </div>
                ) : (
                  activeCacheEntries.map(entry => (
                    <DiamondItem
                      key={getKey(entry)}
                      queryType={entry.query_type}
                      title={entry.question}
                      isSelected={selectedCacheKey === getKey(entry)}
                      onClick={() => handleSelectCache(getKey(entry))}
                    />
                  ))
                )
              )}
            </div>
          ) : (
            // ── Wide: search + tabs + cards ────────────────────────────────
            <div className="flex flex-col h-full">
              {/* Search + Tabs */}
              <div className="px-3 pt-4 pb-3 shrink-0 space-y-2.5">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-primary/40" />
                  <input
                    type="text"
                    placeholder="Search..."
                    value={search}
                    onChange={e => {
                      setSearch(e.target.value);
                      setSelectedConvKey(null);
                      setSelectedCacheKey(null);
                    }}
                    className="w-full pl-8 pr-3 py-2 rounded-xl bg-black/40 border border-primary/20 text-xs text-gray-200 placeholder-gray-600 focus:border-primary/50 focus:outline-none transition-colors"
                  />
                </div>
                <div className="flex gap-1 p-1 bg-black/30 rounded-xl border border-primary/10">
                  {([
                    ['conversations', 'Conv', allConvs.length, MessageSquare],
                    ['cache', 'Cache', cacheEntries.length, Database],
                  ] as const).map(([key, label, count, Icon]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => handleTabSwitch(key)}
                      className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-semibold tracking-wide uppercase transition-all ${
                        tab === key
                          ? 'bg-primary/20 text-primary border border-primary/30'
                          : 'text-gray-500 hover:text-gray-300'
                      }`}
                    >
                      <Icon className="w-3 h-3 shrink-0" />
                      {label}
                      {count > 0 && (
                        <span className="text-[9px] font-mono bg-black/40 px-1 py-0.5 rounded-full">{count}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Card list */}
              <div className="flex-1 overflow-y-auto px-3 pb-4">
                {isLoading && (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                      className="w-8 h-8 border border-primary/30 rounded rotate-45 bg-primary/10 flex items-center justify-center"
                    >
                      <Sparkles className="w-4 h-4 text-primary -rotate-45" />
                    </motion.div>
                    <p className="text-[10px] text-primary/50 font-mono uppercase tracking-widest">Loading...</p>
                  </div>
                )}
                {!isLoading && error && (
                  <div className="text-center py-12">
                    <p className="text-red-400 text-xs">{error}</p>
                  </div>
                )}

                {/* Conversations tab */}
                {tab === 'conversations' && !isLoading && (
                  activeConvs.length === 0 ? (
                    <div className="text-center py-12">
                      <div className="w-10 h-10 mx-auto mb-3 border border-primary/20 rounded-lg rotate-45 flex items-center justify-center">
                        <MessageSquare className="w-5 h-5 text-primary/25 -rotate-45" />
                      </div>
                      <p className="text-xs text-gray-500">
                        {search ? 'No results' : 'No history yet'}
                      </p>
                    </div>
                  ) : (
                    groupedConvs.map(group => (
                      <div key={group.label} className="mb-2">
                        <div className="flex items-center gap-2 py-2">
                          <span className="text-[9px] font-semibold uppercase tracking-widest text-gray-600">{group.label}</span>
                          <div className="flex-1 h-px bg-primary/8" />
                        </div>
                        <div className="space-y-1.5">
                          {group.items.map(conv => (
                            <ConversationCard
                              key={convKey(conv)}
                              conv={conv}
                              isSelected={selectedConvKey === convKey(conv)}
                              isActive={conv.sessionId === 'current'}
                              onClick={() => handleSelectConv(convKey(conv), conv)}
                            />
                          ))}
                        </div>
                      </div>
                    ))
                  )
                )}

                {/* Cache tab */}
                {tab === 'cache' && !isLoading && !error && (
                  activeCacheEntries.length === 0 ? (
                    <div className="text-center py-12">
                      <div className="w-10 h-10 mx-auto mb-3 border border-primary/20 rounded-lg rotate-45 flex items-center justify-center">
                        <Database className="w-5 h-5 text-primary/25 -rotate-45" />
                      </div>
                      <p className="text-xs text-gray-500">
                        {search ? 'No results' : 'No cached answers'}
                      </p>
                    </div>
                  ) : (
                    groupedCache.map(group => (
                      <div key={group.label} className="mb-2">
                        <div className="flex items-center gap-2 py-2">
                          <span className="text-[9px] font-semibold uppercase tracking-widest text-gray-600">{group.label}</span>
                          <div className="flex-1 h-px bg-primary/8" />
                        </div>
                        <div className="space-y-1.5">
                          {group.items.map(entry => (
                            <HistoryCard
                              key={getKey(entry)}
                              entry={entry}
                              isSelected={selectedCacheKey === getKey(entry)}
                              badge="CACHED"
                              onClick={() => handleSelectCache(getKey(entry))}
                            />
                          ))}
                        </div>
                      </div>
                    ))
                  )
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Drag handle ── */}
        <div
          className="w-2 shrink-0 cursor-col-resize flex items-center justify-center hover:bg-primary/20 transition-colors group z-10"
          onMouseDown={(e) => { e.preventDefault(); setIsResizingRail(true); }}
        >
          <div className="w-1 h-12 rounded-full bg-primary/30 group-hover:bg-primary/60 transition-colors flex items-center justify-center">
            <GripVertical className="w-3 h-3 text-primary/50 group-hover:text-primary" />
          </div>
        </div>

        {/* ── Content area ── */}
        <div className="flex-1 overflow-hidden flex">
          <AnimatePresence mode="wait">
            {contentArea ?? (
              <motion.div
                key="placeholder"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="flex-1 flex items-center justify-center"
              >
                <div className="text-center text-gray-600">
                  <div className="w-14 h-14 mx-auto mb-4 border border-primary/10 rounded-lg rotate-45 flex items-center justify-center">
                    <Sparkles className="w-7 h-7 text-primary/15 -rotate-45" />
                  </div>
                  <p className="text-sm">Select a record to view</p>
                  {isCompact && (
                    <p className="text-xs text-gray-700 mt-1">Drag the handle to expand the panel</p>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

// ── Portal wrapper ────────────────────────────────────────────────────────────

export function HistoryExplorerPortal({
  isOpen,
  onClose,
  messages,
  storedConversations,
}: {
  isOpen: boolean;
  onClose: () => void;
  messages: Message[];
  storedConversations: StoredConversation[];
}) {
  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <HistoryExplorer
          onClose={onClose}
          messages={messages}
          storedConversations={storedConversations}
        />
      )}
    </AnimatePresence>,
    document.body
  );
}
