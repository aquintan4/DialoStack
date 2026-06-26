/** Menu to copy the current task as a ros2 command or as the goal JSON. */
import { useState } from 'react'
import { Braces, Check, Copy, Terminal } from 'lucide-react'
import { usePopover } from '../../../hooks/usePopover'
import { PopoverPanel } from '../../../components/ui'
import { ros2Command } from './goal'

/**
 * Menu to copy the current task in two formats: the ros2 command (to launch it
 * from another terminal) or the goal JSON (to hardcode it in an app).
 */
export function CopyTaskMenu({ goal, disabled }) {
  const { open, setOpen, ref } = usePopover()
  const [copied, setCopied] = useState(null)   // 'cmd' | 'json' | null

  function copy(kind) {
    const text = kind === 'cmd' ? ros2Command(goal) : JSON.stringify(goal, null, 2)
    navigator.clipboard.writeText(text)
    setCopied(kind)
    setTimeout(() => setCopied(null), 1500)
  }

  const rowCls = `w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs
    text-slate-300 hover:bg-app-700 transition-colors text-left`

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        title={disabled ? 'Describe the task to be able to copy it' : 'Copy the task (ros2 command or JSON)'}
        className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg text-slate-500
          hover:text-slate-300 hover:bg-app-700 border border-transparent hover:border-app-border
          text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Copy size={14} />
      </button>

      {open && (
        <PopoverPanel placement="top" width="w-60">
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] text-slate-600 uppercase tracking-wide">
            Copy task
          </p>
          <button onClick={() => copy('cmd')} className={rowCls}>
            {copied === 'cmd' ? <Check size={13} className="text-green-400" /> : <Terminal size={13} className="text-slate-500" />}
            <span className="min-w-0">
              <span className="block text-slate-200">ros2 command</span>
              <span className="block text-[10px] text-slate-600">launch from another terminal</span>
            </span>
          </button>
          <button onClick={() => copy('json')} className={rowCls}>
            {copied === 'json' ? <Check size={13} className="text-green-400" /> : <Braces size={13} className="text-slate-500" />}
            <span className="min-w-0">
              <span className="block text-slate-200">goal JSON</span>
              <span className="block text-[10px] text-slate-600">hardcode in an app</span>
            </span>
          </button>
        </PopoverPanel>
      )}
    </div>
  )
}
