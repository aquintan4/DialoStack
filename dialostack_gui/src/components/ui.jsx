import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, ChevronUp, Info } from 'lucide-react'

/**
 * Form atoms and status pieces shared across the whole GUI.
 * Any new page should be built from these pieces, not redefine them.
 * All controls replace the browser's native widgets to keep a
 * consistent look with the dark theme.
 */

export const inputCls = `w-full bg-app-800 border border-app-border rounded-lg px-3 py-2
  text-sm text-slate-200 placeholder-slate-600 focus:outline-none
  focus:border-brand-600 focus:ring-1 focus:ring-brand-600/30 transition-colors`

export const selectCls = `${inputCls} cursor-pointer`

/**
 * Info icon with a hover tooltip. Keeps labels clean: long
 * explanations go here, not in the label text.
 *
 * The tooltip renders in a portal over <body> with fixed position,
 * so overflow containers (cards, drawers) never clip it and it
 * snaps to the window edges on its own.
 */
export function Hint({ text }) {
  const [pos, setPos] = useState(null)   // { anchor, x, y, ready }
  const iconRef = useRef(null)
  const tipRef = useRef(null)

  useLayoutEffect(() => {
    if (!pos?.anchor || pos.ready || !tipRef.current) return
    const { width, height } = tipRef.current.getBoundingClientRect()
    const a = pos.anchor
    const margin = 8
    let x = a.left + a.width / 2 - width / 2
    x = Math.max(margin, Math.min(x, window.innerWidth - width - margin))
    let y = a.top - height - 8
    if (y < margin) y = a.bottom + 8   // no room above, place below
    setPos({ anchor: a, x, y, ready: true })
  }, [pos])

  if (!text) return null
  return (
    <span
      ref={iconRef}
      className="inline-flex items-center align-middle ml-1.5"
      onMouseEnter={() => setPos({ anchor: iconRef.current.getBoundingClientRect() })}
      onMouseLeave={() => setPos(null)}
    >
      <Info size={12} className={`transition-colors cursor-help ${pos ? 'text-brand-400' : 'text-slate-600'}`} />
      {pos && createPortal(
        <span
          ref={tipRef}
          style={{
            position: 'fixed',
            left: pos.x ?? -9999,
            top: pos.y ?? -9999,
            visibility: pos.ready ? 'visible' : 'hidden',
          }}
          className="pointer-events-none z-50 block w-max max-w-[240px] px-2.5 py-1.5
            rounded-lg bg-app-700 border border-app-border text-[11px] leading-snug
            text-slate-300 normal-case font-normal tracking-normal shadow-xl shadow-black/50"
        >
          {text}
        </span>,
        document.body
      )}
    </span>
  )
}

export function Field({ label, hint, children }) {
  return (
    <div>
      <label className="flex items-center text-xs text-slate-500 mb-1.5">
        {label}
        <Hint text={hint} />
      </label>
      {children}
    </div>
  )
}

/**
 * Styled select: hides the native arrow and draws a custom chevron.
 * `className` allows compact variants (e.g. SlotCard).
 */
export function Select({ value, onChange, children, className = selectCls, wrapClassName = '' }) {
  return (
    <div className={`relative ${wrapClassName}`}>
      <select value={value} onChange={onChange} className={`${className} appearance-none pr-8`}>
        {children}
      </select>
      <ChevronDown
        size={13}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
      />
    </div>
  )
}

/**
 * Robust numeric input with custom steppers (no native spinners).
 * While editing it accepts free text; on commit (blur/Enter), if it is
 * not a valid number it reverts to the previous one and out-of-range
 * values are clamped. `unit` paints a subtle suffix inside the field
 * (s, MB, Hz...).
 */
export function NumberField({ label, hint, unit, value, onChange, min, max, step = 1 }) {
  const [draft, setDraft] = useState(null)
  const isInt = Number.isInteger(step)
  // step decimals to avoid floating-point remainders (0.1+0.2...)
  const decimals = isInt ? 0 : (String(step).split('.')[1] || '').length

  function clamp(n) {
    if (min != null && n < min) n = min
    if (max != null && n > max) n = max
    return Number(n.toFixed(decimals))
  }

  function commit() {
    if (draft === null) return
    const n = isInt ? parseInt(draft, 10) : parseFloat(draft)
    if (Number.isFinite(n)) onChange(clamp(n))
    setDraft(null)
  }

  function nudge(direction) {
    const current = draft !== null ? parseFloat(draft) : value
    const base = Number.isFinite(current) ? current : (min ?? 0)
    onChange(clamp(base + direction * step))
    setDraft(null)
  }

  const stepBtnCls = `flex-1 flex items-center justify-center text-slate-600
    hover:text-slate-300 hover:bg-app-700 transition-colors`

  return (
    <Field label={label} hint={hint}>
      <div className="relative">
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={draft ?? value}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
          className={`${inputCls} no-spinner ${unit ? 'pr-16' : 'pr-9'}`}
        />
        {unit && (
          <span className="absolute right-9 top-1/2 -translate-y-1/2 text-xs text-slate-600 pointer-events-none">
            {unit}
          </span>
        )}
        <div className="absolute right-1.5 top-1.5 bottom-1.5 w-6 flex flex-col
          rounded-md overflow-hidden border border-app-border bg-app-800">
          <button type="button" tabIndex={-1} onClick={() => nudge(+1)} className={stepBtnCls}>
            <ChevronUp size={11} />
          </button>
          <button type="button" tabIndex={-1} onClick={() => nudge(-1)} className={stepBtnCls}>
            <ChevronDown size={11} />
          </button>
        </div>
      </div>
    </Field>
  )
}

export function Toggle({ value, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      className={`relative flex-shrink-0 w-9 h-5 rounded-full border transition-colors ${
        value ? 'bg-brand-600 border-brand-600' : 'bg-app-600 border-app-border'
      }`}
    >
      {/* left-0 is essential: without it the knob inherits the <button>
          text centering and slides off the track when activated */}
      <span
        className={`absolute left-0 top-1/2 -translate-y-1/2 w-3.5 h-3.5 bg-white rounded-full
          shadow-sm transition-transform ${value ? 'translate-x-[18px]' : 'translate-x-[3px]'}`}
      />
    </button>
  )
}

export function ToggleField({ label, hint, value, onChange }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="flex items-center text-sm text-slate-300">
        {label}
        <Hint text={hint} />
      </span>
      <Toggle value={value} onChange={onChange} />
    </div>
  )
}

export function SliderField({ label, hint, value, onChange, min, max, step = 1 }) {
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0
  return (
    <Field label={label} hint={hint}>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(step < 1 ? parseFloat(e.target.value) : Number(e.target.value))}
          className="slider flex-1"
          style={{ '--fill': `${pct}%` }}
        />
        <span className="text-sm text-slate-300 font-mono w-12 text-right shrink-0">{value}</span>
      </div>
    </Field>
  )
}

/**
 * Section card with a header (icon + title + description).
 * It is the basic building block of the configuration pages.
 */
export function SectionCard({ icon: Icon, title, description, children }) {
  return (
    <section className="bg-app-900/80 border border-app-border rounded-xl">
      <header className="flex items-center gap-3 px-5 py-3.5 border-b border-app-border/70 bg-app-900 rounded-t-xl">
        {Icon && (
          <div className="w-7 h-7 rounded-lg bg-brand-glow border border-brand-600/30
            flex items-center justify-center flex-shrink-0">
            <Icon size={14} className="text-brand-400" />
          </div>
        )}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-200 leading-none">{title}</h3>
          {description && <p className="text-xs text-slate-600 mt-1 truncate">{description}</p>}
        </div>
      </header>
      <div className="p-5 space-y-4">{children}</div>
    </section>
  )
}

/** Status pill (colored dot + label) used in the sidebar. */
export function StatusBadge({ dot, text, label }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-app-800 border border-app-border">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
      <span className={`text-xs font-medium ${text}`}>{label}</span>
    </div>
  )
}
