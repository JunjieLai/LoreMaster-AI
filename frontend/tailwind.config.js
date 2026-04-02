/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Primary theme colors
        primary: '#d4a154',
        'primary-glow': '#ffeebb',
        'navy-deep': '#0B1120',
        'navy-light': '#1A2332',
        'glass-border': 'rgba(212, 161, 84, 0.3)',
        'glass-bg': 'rgba(11, 17, 32, 0.75)',
        // Legacy genshin colors for compatibility
        genshin: {
          gold: '#D4A053',
          'gold-light': '#E8C87A',
          'gold-dark': '#B8863A',
          dark: '#0D0F1A',
          panel: '#1A1D2E',
          'panel-light': '#252A3D',
          text: '#E8E4DC',
          'text-dim': '#8A8A8A',
          accent: '#6BB5FF',
          pyro: '#EF7A35',
          hydro: '#4CC2FF',
          anemo: '#74C2A8',
          electro: '#B07BCC',
          dendro: '#7BC86C',
          cryo: '#99D6EB',
          geo: '#F0B232',
        }
      },
      fontFamily: {
        'display': ['Space Grotesk', 'Noto Sans SC', 'sans-serif'],
        'genshin': ['"HYWenHei"', '"Noto Serif SC"', 'serif'],
        'sans': ['"Noto Sans SC"', 'system-ui', 'sans-serif'],
      },
      animation: {
        'glow': 'glow 2s ease-in-out infinite alternate',
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'float-up': 'float-up 10s linear infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px #d4a154' },
          '100%': { boxShadow: '0 0 20px #d4a154, 0 0 10px #ffeebb' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'float-up': {
          '0%': { transform: 'translateY(0) rotate(0deg)', opacity: '0' },
          '50%': { opacity: '1' },
          '100%': { transform: 'translateY(-100px) rotate(360deg)', opacity: '0' },
        }
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'genshin-gradient': 'linear-gradient(135deg, #1A1D2E 0%, #0D0F1A 100%)',
        'star-pattern': "radial-gradient(white, rgba(255,255,255,.2) 2px, transparent 3px), radial-gradient(white, rgba(255,255,255,.15) 1px, transparent 2px)",
      },
      backdropBlur: {
        xs: '2px',
      }
    },
  },
  plugins: [],
}
