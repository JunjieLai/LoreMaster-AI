import { useState, useRef, useEffect, useMemo, createContext, useContext, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Send, RotateCcw, GripVertical, GripHorizontal, Network, ChevronLeft, ChevronRight, Clock } from 'lucide-react';
import { ChatMessage } from './components/ChatMessage';
import { ConstellationGraph } from './components/ConstellationGraph';
import { SourceRegistry } from './components/SourceRegistry';
import { GraphExplorerPortal } from './components/GraphExplorer';
import { HistoryExplorerPortal } from './components/HistoryExplorer';
import { Message } from './types';
import { API_BASE } from './config';

// Theme Context
interface ThemeContextType {
  hoveredEntity: string | null;
  setHoveredEntity: (entity: string | null) => void;
  selectedEntity: string | null;
  setSelectedEntity: (entity: string | null) => void;
}

export const ThemeContext = createContext<ThemeContextType>({
  hoveredEntity: null,
  setHoveredEntity: () => {},
  selectedEntity: null,
  setSelectedEntity: () => {},
});

export const useTheme = () => useContext(ThemeContext);


const SESSION_STORAGE_KEY = 'loremaster_session_id';
const MESSAGES_STORAGE_KEY = 'loremaster_messages';
const CONVERSATIONS_STORAGE_KEY = 'loremaster_conversations';
const MAX_STORED_CONVERSATIONS = 20;

interface StoredConversation {
  sessionId: string;
  startedAt: number;
  messages: Message[];
}

// Default questions for the welcome screen (5 test questions)
const DEFAULT_QUESTIONS = [
  "What is the relationship between King Deshret and Nabu Malikata?",
  "Who is Nahida and what is her connection to Greater Lord Rukkhadevata?",
  "What is the relationship between Scaramouche and Raiden Shogun?",
  "How did the forbidden knowledge from King Deshret affect the fall of the desert civilization and what role did the Goddess of Flowers play in containing it?",
  "Tell me about the Archon War and its consequences for Teyvat",
];

function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = localStorage.getItem(MESSAGES_STORAGE_KEY);
      if (!saved) return [];
      return (JSON.parse(saved) as Message[]).filter(m => !m.streaming);
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [hoveredEntity, setHoveredEntity] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Session ID persisted in localStorage for multi-turn memory
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem(SESSION_STORAGE_KEY)
  );

  const [storedConversations, setStoredConversations] = useState<StoredConversation[]>(() => {
    try {
      const saved = localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });

  const [showGraphExplorer, setShowGraphExplorer] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Resizable panel states
  const [mainSplitPercent, setMainSplitPercent] = useState(60); // Chat vs Sidebar
  const [sidebarSplitPercent, setSidebarSplitPercent] = useState(55); // Map vs Sources
  const [isResizingMain, setIsResizingMain] = useState(false);
  const [isResizingSidebar, setIsResizingSidebar] = useState(false);

  // Selected message: right panels follow this message's graph/sources.
  // null = auto-follow latest assistant message.
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const selectedMessage = selectedMessageId
    ? messages.find(m => m.id === selectedMessageId)
    : [...messages].reverse().find(m => m.role === 'assistant');

  // Flat list of completed (non-streaming) assistant messages — shared by turn numbers, session bar, and nav buttons
  const assistantMessages = useMemo(
    () => messages.filter(m => m.role === 'assistant' && !m.streaming),
    [messages]
  );

  // Navigation index within assistantMessages
  const currentNavIndex = useMemo(() => {
    if (!selectedMessage) return assistantMessages.length - 1;
    const idx = assistantMessages.findIndex(m => m.id === selectedMessage.id);
    return idx >= 0 ? idx : assistantMessages.length - 1;
  }, [assistantMessages, selectedMessageId]);
  const hasPrev = currentNavIndex > 0;
  const hasNext = currentNavIndex < assistantMessages.length - 1;

  // Clear stale entity selection/hover when switching to a different message's graph
  useEffect(() => {
    setSelectedEntity(null);
    setHoveredEntity(null);
  }, [selectedMessageId]);

  // Persist messages to localStorage (skip streaming placeholders)
  useEffect(() => {
    const stable = messages.filter(m => !m.streaming);
    if (stable.length > 0) {
      localStorage.setItem(MESSAGES_STORAGE_KEY, JSON.stringify(stable));
    }
  }, [messages]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle main split resize — stable callback (no guard needed; only registered while dragging)
  const handleMainMouseMove = useCallback((e: MouseEvent) => {
    const container = document.getElementById('main-container');
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const newPercent = ((e.clientX - rect.left) / rect.width) * 100;
    setMainSplitPercent(Math.min(Math.max(newPercent, 30), 80));
  }, []);

  // Handle sidebar split resize — stable callback
  const handleSidebarMouseMove = useCallback((e: MouseEvent) => {
    const container = document.getElementById('sidebar-container');
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const newPercent = ((e.clientY - rect.top) / rect.height) * 100;
    setSidebarSplitPercent(Math.min(Math.max(newPercent, 25), 75));
  }, []);

  const handleMouseUp = useCallback(() => {
    setIsResizingMain(false);
    setIsResizingSidebar(false);
  }, []);

  useEffect(() => {
    if (isResizingMain || isResizingSidebar) {
      document.addEventListener('mousemove', isResizingMain ? handleMainMouseMove : handleSidebarMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = isResizingMain ? 'col-resize' : 'row-resize';
      document.body.style.userSelect = 'none';
    }
    return () => {
      document.removeEventListener('mousemove', handleMainMouseMove);
      document.removeEventListener('mousemove', handleSidebarMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizingMain, isResizingSidebar, handleMainMouseMove, handleSidebarMouseMove, handleMouseUp]);

  const handleSend = async (customInput?: string) => {
    const messageContent = customInput || input;
    if (!messageContent.trim() || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: messageContent.trim(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Placeholder assistant message that gets updated as tokens stream in
    const assistantId = generateId();
    setMessages((prev) => [...prev, {
      id: assistantId,
      role: 'assistant',
      content: '',
      streaming: true,
    }]);

    try {
      const response = await fetch(`${API_BASE}/api/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: messageContent.trim(), session_id: sessionId }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalMetadata: Record<string, unknown> | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event: Record<string, unknown>;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue; // skip malformed SSE lines
          }
          if (event.type === 'token') {
            setMessages((prev) => prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + (event.content as string) }
                : m
            ));
          } else if (event.type === 'metadata') {
            finalMetadata = event;
            // Persist session_id
            if (event.session_id) {
              setSessionId(event.session_id as string);
              localStorage.setItem(SESSION_STORAGE_KEY, event.session_id as string);
            }
          } else if (event.type === 'error') {
            throw new Error(event.message as string);
          }
        }
      }

      // Enrich the assistant message with metadata once streaming is done
      if (finalMetadata) {
        const meta = finalMetadata;
        setMessages((prev) => prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                streaming: false,
                sources: meta.sources as Message['sources'],
                path: meta.path as Message['path'],
                graphResults: meta.graph_results as Message['graphResults'],
                entities: meta.entities as string[],
                queryType: meta.query_type as string,
                cacheHit: meta.cache_hit as boolean,
              }
            : m
        ));
      } else {
        setMessages((prev) => prev.map((m) =>
          m.id === assistantId ? { ...m, streaming: false } : m
        ));
      }
      // Auto-select the new answer so right panels update immediately
      setSelectedMessageId(assistantId);
    } catch (err) {
      console.error('API Error:', err);
      const errorMessage = err instanceof Error ? err.message : 'An unexpected error occurred';
      setMessages((prev) => prev.map((m) =>
        m.id === assistantId
          ? {
              ...m,
              streaming: false,
              content: `I apologize, but I encountered an error: ${errorMessage}\n\nPlease make sure the backend server is running and try again.`,
            }
          : m
      ));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuestionClick = (question: string) => {
    handleSend(question);
  };

  return (
    <ThemeContext.Provider value={{ hoveredEntity, setHoveredEntity, selectedEntity, setSelectedEntity }}>
      <div className="h-screen overflow-hidden flex flex-col bg-navy-deep font-display text-gray-100">
        {/* Header */}
        <header className="h-16 flex items-center justify-between px-6 border-b border-primary/30 bg-navy-deep/95 backdrop-blur-sm relative z-40 shadow-[0_2px_15px_rgba(0,0,0,0.5)]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-gradient-to-br from-primary to-yellow-700 flex items-center justify-center transform rotate-45 border-2 border-primary shadow-[0_0_15px_rgba(212,161,84,0.6)]">
              <Sparkles className="w-4 h-4 text-navy-deep transform -rotate-45" />
            </div>
            <h1 className="text-xl font-bold tracking-widest text-primary uppercase drop-shadow-md">
              LoreMaster
              <span className="text-primary/60 text-base font-normal normal-case ml-2 tracking-normal">AI Archive</span>
            </h1>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-primary/90 shadow-[inset_0_0_10px_rgba(212,161,84,0.1)]">
              <span className="w-2 h-2 rounded-full bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.8)] animate-pulse"></span>
              <span className="text-xs uppercase tracking-wide font-medium">System Online</span>
            </div>
            <button
              type="button"
              title="History"
              onClick={() => setShowHistory(true)}
              className="p-2 rounded-full hover:bg-primary/10 text-primary/70 hover:text-primary transition-all duration-300"
            >
              <Clock className="w-5 h-5" />
            </button>
            <button
              type="button"
              title="Knowledge Graph Explorer"
              onClick={() => setShowGraphExplorer(true)}
              className="p-2 rounded-full hover:bg-primary/10 text-primary/70 hover:text-primary transition-all duration-300"
            >
              <Network className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Main Content - Split Pane */}
        <main id="main-container" className="flex-1 flex overflow-hidden relative">
          {/* Stars Background */}
          <div className="absolute inset-0 z-0 stars-bg pointer-events-none"></div>

          {/* Left Pane - Chat */}
          <section
            className="flex flex-col relative z-10 border-r border-primary/20 h-full bg-gradient-to-b from-transparent to-black/20"
            style={{ width: `${mainSplitPercent}%` }}
          >
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 scroll-smooth relative">
              {/* Empty State */}
              {messages.length === 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center py-12"
                >
                  <motion.div
                    animate={{ y: [0, -10, 0] }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                    className="inline-block mb-6"
                  >
                    <div className="w-20 h-20 mx-auto bg-primary/10 rounded-lg rotate-45 flex items-center justify-center border border-primary/30">
                      <Sparkles className="w-10 h-10 text-primary -rotate-45" />
                    </div>
                  </motion.div>
                  <h2 className="text-2xl font-bold text-primary tracking-wide mb-3">
                    Welcome, Traveler
                  </h2>
                  <p className="text-gray-400 max-w-md mx-auto text-sm mb-8">
                    Explore Sumeru's lore — ask about characters, ancient history, entity relationships, or the secrets hidden within Irminsul.
                  </p>

                  {/* Default Questions */}
                  <div className="max-w-2xl mx-auto grid gap-3">
                    {DEFAULT_QUESTIONS.map((question, index) => (
                      <motion.button
                        key={index}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 + index * 0.1 }}
                        onClick={() => handleQuestionClick(question)}
                        className="group relative px-5 py-3 text-left rounded-lg border border-primary/30 bg-navy-light/30 hover:bg-navy-light/60 hover:border-primary/50 transition-all duration-300 overflow-hidden"
                      >
                        {/* Hover gradient effect */}
                        <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

                        {/* Diamond icon */}
                        <div className="flex items-center gap-3">
                          <span className="w-6 h-6 bg-primary/10 rounded rotate-45 flex items-center justify-center border border-primary/20 shrink-0 group-hover:bg-primary/20 transition-colors">
                            <Sparkles className="w-3 h-3 text-primary -rotate-45" />
                          </span>
                          <span className="text-primary/90 text-sm font-medium group-hover:text-primary transition-colors">
                            {question}
                          </span>
                        </div>
                      </motion.button>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Session status bar — visible once at least one answer exists */}
              {sessionId && assistantMessages.length > 0 && (
                <div className="flex items-center gap-2.5 text-[10px] font-mono text-gray-600 pb-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400/50 shrink-0" />
                  <span>SESSION {sessionId.slice(0, 8).toUpperCase()}</span>
                  <span className="text-gray-700">·</span>
                  <span>{assistantMessages.length} {assistantMessages.length === 1 ? 'turn' : 'turns'}</span>
                </div>
              )}

              {/* Messages */}
              <AnimatePresence mode="popLayout">
                {(() => {
                  let turnCount = 0;
                  return messages.map((message) => {
                    if (message.role === 'assistant') turnCount++;
                    return (
                      <ChatMessage
                        key={message.id}
                        message={message}
                        isSelected={message.role === 'assistant' && message.id === selectedMessage?.id}
                        onSelect={message.role === 'assistant' ? () => setSelectedMessageId(message.id) : undefined}
                        turnNumber={message.role === 'assistant' ? turnCount : undefined}
                      />
                    );
                  });
                })()}

                {/* Loading Indicator */}
                {isLoading && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex gap-5 max-w-3xl mx-auto opacity-70"
                  >
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 border border-primary/20">
                      <motion.div
                        animate={{ rotate: 360 }}
                        transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                      >
                        <Sparkles className="w-4 h-4 text-primary/60" />
                      </motion.div>
                    </div>
                    <div className="flex items-center gap-1 pt-2">
                      {[0, 1, 2].map((i) => (
                        <motion.span
                          key={i}
                          className="w-1.5 h-1.5 bg-primary/60 rounded-full"
                          animate={{ y: [0, -5, 0] }}
                          transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.1 }}
                        />
                      ))}
                      <span className="text-xs text-primary/60 ml-2 font-mono uppercase tracking-widest">Processing</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div ref={messagesEndRef} className="h-32" />
            </div>

            {/* Input Area */}
            <div className="absolute bottom-0 left-0 w-full p-6 bg-gradient-to-t from-navy-deep via-navy-deep/95 to-transparent z-20">
              <div className="max-w-4xl mx-auto relative group">
                <div className="glass-panel rounded-xl p-1.5 flex items-end gap-2 shadow-[0_4px_20px_rgba(0,0,0,0.5)] border-primary/30 transition-colors group-hover:border-primary/50">
                  <button
                    type="button"
                    title="New conversation"
                    onClick={() => {
                      // Archive current session before clearing
                      const stableMessages = messages.filter(m => !m.streaming);
                      if (stableMessages.length > 0 && sessionId) {
                        const archived: StoredConversation = {
                          sessionId,
                          startedAt: Date.now() / 1000,
                          messages: stableMessages,
                        };
                        const updated = [archived, ...storedConversations].slice(0, MAX_STORED_CONVERSATIONS);
                        setStoredConversations(updated);
                        localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(updated));
                      }
                      setMessages([]);
                      setSessionId(null);
                      setSelectedMessageId(null);
                      localStorage.removeItem(SESSION_STORAGE_KEY);
                      localStorage.removeItem(MESSAGES_STORAGE_KEY);
                    }}
                    className="p-3 text-primary/60 hover:text-primary transition-colors rounded-lg hover:bg-primary/5 shrink-0"
                  >
                    <RotateCcw className="w-5 h-5" />
                  </button>
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="w-full bg-transparent border-none focus:ring-0 text-gray-200 placeholder-gray-500 resize-none py-3 max-h-32 text-sm leading-relaxed font-light"
                    placeholder="Ask Irminsul about Teyvat..."
                    rows={1}
                  />
                  <button
                    type="button"
                    title="Send message"
                    onClick={() => handleSend()}
                    disabled={!input.trim() || isLoading}
                    className="m-1 p-3 bg-gradient-to-br from-primary to-yellow-600 hover:from-primary hover:to-yellow-500 text-navy-deep rounded-lg transition-all shadow-[0_0_15px_rgba(212,161,84,0.3)] shrink-0 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-center mt-2 text-[10px] text-gray-500">
                  LoreMaster-AI can make mistakes. Verify important information.
                </p>
              </div>
            </div>
          </section>

          {/* Main Resize Handle */}
          <div
            className="hidden lg:flex w-2 cursor-col-resize items-center justify-center z-30 hover:bg-primary/20 transition-colors group"
            onMouseDown={(e) => { e.preventDefault(); setIsResizingMain(true); }}
          >
            <div className="w-1 h-12 rounded-full bg-primary/30 group-hover:bg-primary/60 transition-colors flex items-center justify-center">
              <GripVertical className="w-3 h-3 text-primary/50 group-hover:text-primary" />
            </div>
          </div>

          {/* Right Pane - Astro Registry (Desktop Only) */}
          <aside
            id="sidebar-container"
            className="hidden lg:flex flex-col bg-navy-deep border-l border-primary/20 relative overflow-hidden shadow-2xl z-20"
            style={{ width: `${100 - mainSplitPercent - 0.5}%` }}
          >
            {/* Floating Particles */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
              {[...Array(4)].map((_, i) => (
                <div
                  key={i}
                  className="floating-particle"
                  style={{
                    width: `${4 + i * 2}px`,
                    height: `${4 + i * 2}px`,
                    top: `${70 + i * 5}%`,
                    left: `${10 + i * 20}%`,
                    animationDuration: `${12 + i * 3}s`,
                    animationDelay: `${i * 2}s`,
                    opacity: 0.3 - i * 0.05,
                  }}
                />
              ))}
            </div>

            {/* Constellation Graph */}
            <div
              className="relative w-full bg-navy-deep/50 overflow-hidden border-b border-primary/20"
              style={{ height: `${sidebarSplitPercent}%` }}
            >
              <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between">
                <h2 className="text-sm font-bold text-primary tracking-widest uppercase flex items-center gap-2 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
                  <span className="w-5 h-5 bg-primary/20 rounded rotate-45 flex items-center justify-center border border-primary/30">
                    <Sparkles className="w-3 h-3 text-primary -rotate-45" />
                  </span>
                  Constellation Map
                </h2>
                {/* History navigation — shown when 2+ answers exist */}
                {assistantMessages.length >= 2 && (
                  <div className="flex items-center gap-0.5">
                    <button
                      type="button"
                      title="Previous answer"
                      disabled={!hasPrev}
                      onClick={() => setSelectedMessageId(assistantMessages[currentNavIndex - 1].id)}
                      className="p-1 rounded text-primary/50 hover:text-primary hover:bg-primary/10 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
                    >
                      <ChevronLeft className="w-3.5 h-3.5" />
                    </button>
                    <span className="text-[10px] font-mono text-primary/40 select-none w-8 text-center">
                      {currentNavIndex + 1}/{assistantMessages.length}
                    </span>
                    <button
                      type="button"
                      title="Next answer"
                      disabled={!hasNext}
                      onClick={() => setSelectedMessageId(assistantMessages[currentNavIndex + 1].id)}
                      className="p-1 rounded text-primary/50 hover:text-primary hover:bg-primary/10 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
                    >
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>

              {(selectedMessage?.path || selectedMessage?.graphResults?.length) ? (
                <ConstellationGraph
                  key={selectedMessage.id}
                  pathData={selectedMessage.path}
                  graphResults={selectedMessage.graphResults}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <div className="text-center text-gray-500">
                    <div className="w-16 h-16 mx-auto mb-4 border border-primary/20 rounded-lg rotate-45 flex items-center justify-center">
                      <Sparkles className="w-8 h-8 text-primary/30 -rotate-45" />
                    </div>
                    {messages.some(m => m.role === 'assistant') ? (
                      <>
                        <p className="text-sm">Click an answer to view its map</p>
                        <p className="text-xs text-gray-600 mt-1">Each answer has its own relationship graph</p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm">No constellation data yet</p>
                        <p className="text-xs text-gray-600 mt-1">Ask a question to see entity relationships</p>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Sidebar Resize Handle */}
            <div
              className="h-2 cursor-row-resize flex items-center justify-center z-30 hover:bg-primary/20 transition-colors group"
              onMouseDown={(e) => { e.preventDefault(); setIsResizingSidebar(true); }}
            >
              <div className="h-1 w-12 rounded-full bg-primary/30 group-hover:bg-primary/60 transition-colors flex items-center justify-center">
                <GripHorizontal className="w-3 h-3 text-primary/50 group-hover:text-primary" />
              </div>
            </div>

            {/* Source Registry */}
            <div
              className="bg-navy-deep/95 backdrop-blur-md flex flex-col min-h-0 relative z-20"
              style={{ height: `${100 - sidebarSplitPercent - 0.5}%` }}
            >
              <div className="px-5 py-3 border-b border-primary/10 flex justify-between items-center bg-gradient-to-r from-primary/10 to-transparent shrink-0">
                <h2 className="text-sm font-bold text-primary tracking-widest uppercase flex items-center gap-2">
                  <span className="w-5 h-5 bg-primary/20 rounded rotate-45 flex items-center justify-center border border-primary/30">
                    <Sparkles className="w-3 h-3 text-primary -rotate-45" />
                  </span>
                  Source Registry
                </h2>
                {selectedMessage?.sources && (
                  <span className="text-[10px] font-mono text-primary/80 bg-black/40 px-2 py-0.5 rounded border border-primary/30">
                    {selectedMessage.sources.length} Relevant Sources
                  </span>
                )}
              </div>
              <div className="overflow-y-auto p-4 space-y-3 flex-1">
                {selectedMessage?.sources ? (
                  <SourceRegistry key={selectedMessage.id} sources={selectedMessage.sources} />
                ) : (
                  <div className="text-center text-gray-500 py-8">
                    <p className="text-sm">No sources available</p>
                    <p className="text-xs text-gray-600 mt-1">Sources will appear after asking a question</p>
                  </div>
                )}
              </div>
            </div>
          </aside>
        </main>

        {/* Gradient Overlay */}
        <div className="fixed inset-0 pointer-events-none z-50 bg-gradient-to-b from-transparent via-transparent to-primary/5"></div>
      </div>

      {/* Knowledge Graph Explorer */}
      <GraphExplorerPortal
        isOpen={showGraphExplorer}
        onClose={() => setShowGraphExplorer(false)}
      />

      {/* History Explorer */}
      <HistoryExplorerPortal
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        messages={messages}
        storedConversations={storedConversations}
      />
    </ThemeContext.Provider>
  );
}
