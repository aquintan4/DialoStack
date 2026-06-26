/** Menu to import a task: paste a goal (JSON, YAML or a ros2 command) or a file. */
import { useState } from 'react'
import { Check, Upload } from 'lucide-react'
import { usePopover } from '../../../hooks/usePopover'
import { PopoverPanel } from '../../../components/ui'
import { FileImportButton } from '../../../components/FileImportButton'

/**
 * Inverse of CopyTaskMenu. `onImport(text)` parses the text into a goal and
 * fills the launch form. It returns true on success, false otherwise.
 */
export function ImportTaskMenu({ onImport }) {
  const { open, setOpen, ref } = usePopover()
  const [text, setText] = useState('')
  const [error, setError] = useState(false)

  async function run(value) {
    const ok = await onImport(value)
    if (ok) {
      setText('')
      setError(false)
      setOpen(false)
    } else {
      setError(true)
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Import a task (paste the goal JSON or a ros2 command, or load a file)"
        className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg text-slate-500
          hover:text-slate-300 hover:bg-app-700 border border-transparent hover:border-app-border
          text-sm transition-all"
      >
        <Upload size={14} />
      </button>

      {open && (
        <PopoverPanel placement="top" width="w-80">
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] text-slate-600 uppercase tracking-wide">
            Import task
          </p>
          <textarea
            value={text}
            onChange={(e) => { setText(e.target.value); setError(false) }}
            rows={5}
            spellCheck={false}
            placeholder={'Paste the goal JSON, or a "ros2 action send_goal ..." command'}
            className="w-full bg-app-700 border border-app-border rounded-lg px-2.5 py-2 text-xs
              font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 resize-none"
          />
          {error && (
            <p className="px-1 pt-1 text-[11px] text-red-400">Could not read a task from that text.</p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <button
              onClick={() => run(text)}
              disabled={!text.trim()}
              className="flex-1 flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg
                bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium transition-colors
                disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Check size={12} /> Import
            </button>
            <FileImportButton
              accept=".json,.txt,.yaml,.yml"
              onFile={async (f) => run(await f.text())}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200
                hover:bg-app-700 border border-app-border"
            >
              From file
            </FileImportButton>
          </div>
        </PopoverPanel>
      )}
    </div>
  )
}
