import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Sparkles } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

const EXAMPLE_QUESTIONS = [
  'What is the relationship between King Deshret and Nabu Malikata?',
  'Why did the Wanderer erase himself from Irminsul?',
  'How was the ancient desert civilization destroyed?',
  'What is the connection between Fatui and the Tsaritsa?',
];

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    if (input.trim() && !isLoading) {
      onSend(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleExampleClick = (question: string) => {
    setInput(question);
    textareaRef.current?.focus();
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  return (
    <div className="space-y-3">
      {/* Input Area */}
      <motion.div
        className={`relative glass rounded-2xl overflow-hidden transition-all duration-300 ${
          isFocused ? 'border-genshin-gold/50 shadow-lg shadow-genshin-gold/10' : ''
        }`}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setTimeout(() => setIsFocused(false), 200)}
          placeholder="Ask anything about Teyvat's lore..."
          disabled={isLoading}
          rows={1}
          className="w-full bg-transparent text-genshin-text placeholder-genshin-text-dim px-5 py-4 pr-14 resize-none focus:outline-none disabled:opacity-50"
          style={{ minHeight: '56px' }}
        />

        {/* Send Button */}
        <motion.button
          onClick={handleSubmit}
          disabled={!input.trim() || isLoading}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          className={`absolute right-3 bottom-3 w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
            input.trim() && !isLoading
              ? 'bg-gradient-to-r from-genshin-gold to-genshin-gold-dark text-genshin-dark shadow-lg'
              : 'bg-genshin-panel-light text-genshin-text-dim'
          }`}
        >
          {isLoading ? (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            >
              <Sparkles className="w-5 h-5" />
            </motion.div>
          ) : (
            <Send className="w-5 h-5" />
          )}
        </motion.button>
      </motion.div>

      {/* Example Questions - Show only when focused and input is empty */}
      <AnimatePresence>
        {isFocused && !input && (
          <motion.div
            initial={{ opacity: 0, y: -10, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            exit={{ opacity: 0, y: -10, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_QUESTIONS.map((q, i) => (
                <motion.button
                  key={i}
                  onClick={() => handleExampleClick(q)}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  className="px-3 py-1.5 glass-light rounded-lg text-xs text-genshin-text-dim hover:text-genshin-text hover:border-genshin-gold/30 transition-all"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <Sparkles className="w-3 h-3 inline mr-1.5 text-genshin-gold" />
                  {q.length > 45 ? q.substring(0, 45) + '...' : q}
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Hint */}
      <p className="text-center text-xs text-genshin-text-dim">
        Press Enter to send · Shift + Enter for new line
      </p>
    </div>
  );
}
