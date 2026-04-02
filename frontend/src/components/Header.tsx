import { motion } from 'framer-motion';
import { BookOpen, Settings } from 'lucide-react';
import { CONFIGS } from '../types';

interface HeaderProps {
  config: string;
  onConfigChange: (config: string) => void;
  showConfigPanel: boolean;
  onToggleConfig: () => void;
}

export function Header({ config, onConfigChange, showConfigPanel, onToggleConfig }: HeaderProps) {
  const currentConfig = CONFIGS.find(c => c.name === config) || CONFIGS[0];

  return (
    <motion.header
      initial={{ y: -50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed top-0 left-0 right-0 z-50 glass border-b border-genshin-gold/20"
    >
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Logo */}
        <motion.div
          className="flex items-center gap-3"
          whileHover={{ scale: 1.02 }}
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-genshin-gold to-genshin-gold-dark flex items-center justify-center shadow-lg">
            <BookOpen className="w-6 h-6 text-genshin-dark" />
          </div>
          <div>
            <h1 className="text-xl font-genshin text-genshin-gold text-glow">
              LoreMaster-AI
            </h1>
            <p className="text-xs text-genshin-text-dim">Genshin Impact Lore Expert</p>
          </div>
        </motion.div>

        {/* Config Button */}
        <div className="relative">
          <motion.button
            onClick={onToggleConfig}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center gap-2 px-4 py-2 glass-light rounded-xl hover:border-genshin-gold/50 transition-colors"
          >
            <span className="text-lg">{currentConfig.icon}</span>
            <span className="text-sm text-genshin-text">{currentConfig.description}</span>
            <Settings className="w-4 h-4 text-genshin-text-dim" />
          </motion.button>

          {/* Config Panel */}
          {showConfigPanel && (
            <motion.div
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              className="absolute right-0 mt-2 w-64 glass rounded-xl overflow-hidden shadow-2xl"
            >
              {CONFIGS.map((c) => (
                <motion.button
                  key={c.name}
                  onClick={() => {
                    onConfigChange(c.name);
                    onToggleConfig();
                  }}
                  whileHover={{ backgroundColor: 'rgba(212, 160, 83, 0.1)' }}
                  className={`w-full px-4 py-3 flex items-center gap-3 text-left transition-colors ${
                    config === c.name ? 'bg-genshin-gold/10 border-l-2 border-genshin-gold' : ''
                  }`}
                >
                  <span className="text-xl">{c.icon}</span>
                  <div>
                    <div className="text-sm text-genshin-text">{c.description}</div>
                    <div className="text-xs text-genshin-text-dim">{c.name}</div>
                  </div>
                </motion.button>
              ))}
            </motion.div>
          )}
        </div>
      </div>
    </motion.header>
  );
}
