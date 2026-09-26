import colors from 'tailwindcss/colors'
import plugin from 'tailwindcss/plugin'

// ==== THEMES ====
// Every color the GUI uses is a CSS variable, so switching theme is one
// attribute on <html> (data-theme="light" | "dark"), not a second set of
// classes. Components keep writing bg-app-900, text-slate-300, text-red-400...
// and the variables below decide what those mean in each theme.

const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]

// Stock Tailwind scales. In light mode each scale is mirrored (50<->950,
// 100<->900...): text-red-400 becomes a readable red-600 on white and a
// bg-red-900/30 tint becomes a pale red-100/30. slate is zinc on purpose:
// slate carries a blue cast, zinc is neutral.
const MIRRORED = {
  slate: colors.zinc,
  red: colors.red,
  green: colors.green,
  yellow: colors.yellow,
  amber: colors.amber,
  orange: colors.orange,
  emerald: colors.emerald,
  blue: colors.blue,
}

// Surfaces, darkest to lightest in dark mode. In light mode 950 is the
// white page/input background and the higher steps are progressively
// darker grays for panels, hover and active states.
const APP = {
  dark: {
    950: '#0f1012', 900: '#141518', 800: '#1a1b1f', 700: '#222328',
    600: '#2b2d32', 500: '#383a40', border: '#2a2c31',
  },
  light: {
    950: '#ffffff', 900: '#f7f7f8', 800: '#f0f0f2', 700: '#e8e8eb',
    600: '#dddde1', 500: '#c9c9cf', border: '#dcdce0',
  },
}

// Muted take on the DialoStack cyan (#0FA5CA): only for focus, selection and
// the active state, never as a large fill. Light mode darkens the text steps
// (300/400) so accent text stays readable on white.
const BRAND = {
  dark: { 300: '#a3cfda', 400: '#78b6c6', 500: '#4f9aad', 600: '#3d8193', 700: '#316877' },
  light: { 300: '#28596a', 400: '#2f6a7a', 500: '#3d8193', 600: '#3d8193', 700: '#316877' },
}

const channels = (hex) => {
  const n = parseInt(hex.slice(1), 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}
const ref = (name, step) => `rgb(var(--c-${name}-${step}) / <alpha-value>)`
const refScale = (name, steps) => Object.fromEntries(steps.map((s) => [s, ref(name, s)]))

function themeVars(mode) {
  const vars = {}
  for (const [name, scale] of Object.entries(MIRRORED)) {
    SHADES.forEach((s, i) => {
      const src = mode === 'light' ? SHADES[SHADES.length - 1 - i] : s
      vars[`--c-${name}-${s}`] = channels(scale[src])
    })
  }
  for (const [k, v] of Object.entries(APP[mode])) vars[`--c-app-${k}`] = channels(v)
  for (const [k, v] of Object.entries(BRAND[mode])) vars[`--c-brand-${k}`] = channels(v)
  return vars
}

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        ...Object.fromEntries(Object.keys(MIRRORED).map((n) => [n, refScale(n, SHADES)])),
        app: refScale('app', Object.keys(APP.dark)),
        brand: {
          ...refScale('brand', Object.keys(BRAND.dark)),
          glow: 'rgb(var(--c-brand-500) / 0.10)',
        },
      },
      // Tight radii: a tool, not a landing page
      borderRadius: {
        sm: '2px',
        DEFAULT: '3px',
        md: '3px',
        lg: '4px',
        xl: '5px',
        '2xl': '6px',
      },
      // Motion kept to plain, short fades
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in': 'fadeIn 0.12s ease-out',
        'slide-up': 'fadeIn 0.12s ease-out',
        'pop-in': 'fadeIn 0.12s ease-out',
        'slide-in-right': 'slideInRight 0.15s ease-out',
      },
      keyframes: {
        slideInRight: { from: { transform: 'translateX(16px)', opacity: 0 }, to: { transform: 'translateX(0)', opacity: 1 } },
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
      },
    },
  },
  plugins: [
    plugin(({ addBase, addVariant }) => {
      // Per-theme tweaks where a CSS variable is not enough (e.g. swapping an
      // image): `light:hidden` hides in light mode, `hidden light:block` shows
      // only in light mode. (Tailwind's own `dark:` variant is media-based and
      // does not follow data-theme, so it is not used.)
      addVariant('light', '[data-theme="light"] &')
      addBase({
        ':root, [data-theme="dark"]': { ...themeVars('dark'), colorScheme: 'dark' },
        '[data-theme="light"]': { ...themeVars('light'), colorScheme: 'light' },
      })
    }),
  ],
}
