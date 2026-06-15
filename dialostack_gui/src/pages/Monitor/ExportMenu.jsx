/** Export menu for the Monitor: serializes the on-screen session timeline to CSV, JSON or Markdown. */
import { Braces, Download, FileText, Sheet } from 'lucide-react'
import { buildExport } from '../../lib/sessionExport'
import { downloadFile } from '../../lib/download'
import { usePopover } from '../../hooks/usePopover'

const FORMATS = [
  { key: 'csv',  ext: 'csv', mime: 'text/csv',         icon: Sheet,    label: 'CSV',      hint: 'one row per turn (Excel/pandas)' },
  { key: 'json', ext: 'json', mime: 'application/json', icon: Braces,   label: 'JSON',     hint: 'events + summary, full fidelity' },
  { key: 'md',   ext: 'md',  mime: 'text/markdown',     icon: FileText, label: 'Markdown', hint: 'readable transcription' },
]

/**
 * Exports the current Monitor session (the on-screen timeline) to CSV, JSON or
 * Markdown, segmented by task and with metrics. It captures nothing: it
 * serializes what is already in memory.
 */
export function ExportMenu({ events }) {
  const { open, setOpen, ref } = usePopover()
  const disabled = events.length === 0

  function doExport(fmt) {
    const ex = buildExport(events, new Date())
    const text = fmt.key === 'csv' ? ex.csv : fmt.key === 'json' ? ex.json : ex.markdown
    downloadFile(`${ex.filenameBase}.${fmt.ext}`, text, fmt.mime)
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        title={disabled ? 'No activity to export' : 'Export the session (CSV / JSON / Markdown)'}
        className={`flex items-center gap-1.5 text-xs px-2.5 py-2 rounded-lg border transition-all ${
          open
            ? 'text-brand-400 bg-brand-glow border-brand-600/40'
            : 'text-slate-500 hover:text-slate-300 hover:bg-app-700 border-transparent hover:border-app-border'
        } disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent`}
      >
        <Download size={13} />
        Export
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 z-50 p-1.5 rounded-xl
          bg-app-800 border border-app-border shadow-xl shadow-black/50 animate-fade-in">
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] text-slate-600 uppercase tracking-wide">
            Export session
          </p>
          {FORMATS.map((f) => (
            <button
              key={f.key}
              onClick={() => doExport(f)}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg hover:bg-app-700 transition-colors text-left"
            >
              <f.icon size={14} className="text-slate-500 flex-shrink-0" />
              <span className="min-w-0">
                <span className="block text-xs text-slate-200">{f.label}</span>
                <span className="block text-[10px] text-slate-600 truncate">{f.hint}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
