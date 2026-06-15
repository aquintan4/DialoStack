/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        app: {
          950: '#07091a',
          900: '#0b0f23',
          800: '#0f1530',
          700: '#14203f',
          600: '#1a2850',
          500: '#203060',
          border: '#1e2d47',
        },
        // Derivada del cian del logo de DialoStack (#0FA5CA)
        brand: {
          300: '#7dd8ef',
          400: '#3cc1e3',
          500: '#0fa5ca',
          600: '#0d8cab',
          700: '#0b7390',
          glow: 'rgba(15,165,202,0.15)',
        },
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.2s ease-out',
        'pop-in': 'popIn 0.25s cubic-bezier(0.16,1,0.3,1)',
        'slide-in-right': 'slideInRight 0.25s cubic-bezier(0.16,1,0.3,1)',
      },
      keyframes: {
        slideInRight: { from: { transform: 'translateX(40px)', opacity: 0 }, to: { transform: 'translateX(0)', opacity: 1 } },
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        popIn: { from: { opacity: 0, transform: 'translateY(12px) scale(0.97)' }, to: { opacity: 1, transform: 'translateY(0) scale(1)' } },
      },
    },
  },
  plugins: [],
}
