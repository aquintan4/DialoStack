import { Check, Copy, Download } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { downloadFile } from '../../lib/download'

/**
 * Bidirectional JSON editor for ONE goal field.
 *
 * - Mirrors the state built on the left (slots / questions / resources).
 * - If the user types/pastes valid JSON here, it is applied to the editor
 *   (while editing, the text is not reformatted to avoid interfering).
 * - Exports the JSON to a file with a name chosen by the user.
 *
 * `field.parse(text)` returns the editable items or null if the JSON does not fit.
 */
function FieldEditor({ field }) {
  const { json, field: goalField, parse, onApply } = field
  const [draft, setDraft] = useState(json)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [filename, setFilename] = useState(`${goalField.replace(/_json$/, '')}.json`)
  const editingRef = useRef(false)

  // Changes from the left side: refresh the text (unless editing here).
  useEffect(() => {
    if (!editingRef.current) {
      setDraft(json)
      setError(null)
    }
  }, [json])

  function handleChange(text) {
    setDraft(text)
    const items = parse(text)
    if (items) {
      setError(null)
      onApply(items)
    } else {
      setError('Invalid JSON - the editor will update once it is valid')
    }
  }

  function handleBlur() {
    editingRef.current = false
    setDraft((prev) => {
      try { return JSON.stringify(JSON.parse(prev), null, 2) } catch { return prev }
    })
  }

  function copy() {
    navigator.clipboard.writeText(draft)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function download() {
    let name = filename.trim() || `${goalField}.json`
    if (!name.endsWith('.json')) name += '.json'
    downloadFile(name, json, 'application/json')
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-app-border flex-shrink-0">
        <span className="text-xs font-medium text-slate-500">
          <span className="font-mono text-brand-500/80">{goalField}</span>
          <span className="ml-2 text-slate-600">(you can paste JSON here)</span>
        </span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300
            px-2 py-1 rounded-md hover:bg-app-700 transition-all"
        >
          {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      <textarea
        value={draft}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => { editingRef.current = true }}
        onBlur={handleBlur}
        spellCheck={false}
        className={`flex-1 w-full resize-none bg-transparent p-4 font-mono text-xs
          leading-relaxed focus:outline-none transition-colors ${
            error ? 'text-red-300/90' : 'text-slate-300'
          }`}
      />

      {error && (
        <p className="px-4 py-2 text-xs text-red-400 border-t border-red-700/40 bg-red-900/10 flex-shrink-0">
          {error}
        </p>
      )}

      <div className="flex items-center gap-2 px-4 py-3 border-t border-app-border flex-shrink-0">
        <input
          type="text"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          className="flex-1 bg-app-800 border border-app-border rounded-lg px-3 py-1.5
            text-xs text-slate-300 font-mono placeholder-slate-600 focus:outline-none
            focus:border-brand-600 transition-colors"
        />
        <button
          onClick={download}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-brand-600
            hover:bg-brand-700 text-white text-xs font-medium transition-colors"
        >
          <Download size={13} />
          Export
        </button>
      </div>
    </div>
  )
}

/**
 * Builder JSON panel. Receives the goal fields of the active mode and shows a
 * bidirectional editor per field, with tabs when there is more than one (e.g.
 * slot_filling: frame_schema_json + resources_json).
 */
export function JsonEditor({ fields }) {
  const [activeIdx, setActiveIdx] = useState(0)
  if (!fields.length) return <div className="flex-1" />
  const idx = Math.min(activeIdx, fields.length - 1)
  const active = fields[idx]

  return (
    <div className="flex flex-col h-full min-h-0">
      {fields.length > 1 && (
        <div className="flex gap-1 px-3 pt-3 flex-shrink-0">
          {fields.map((f, i) => (
            <button
              key={f.field}
              onClick={() => setActiveIdx(i)}
              className={`px-3 py-1.5 rounded-t-lg text-xs font-medium transition-colors ${
                i === idx
                  ? 'bg-app-900 text-brand-300 border-x border-t border-app-border'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-app-800'
              }`}
            >
              {f.label}
              <span className="ml-1.5 text-[10px] font-mono text-slate-600">{f.field}</span>
            </button>
          ))}
        </div>
      )}
      {/* key per field: remounts the editor on tab change (clean draft) */}
      <FieldEditor key={active.field} field={active} />
    </div>
  )
}
