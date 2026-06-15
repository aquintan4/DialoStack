import { useRef, useState } from 'react'
import {
  Bookmark, BookmarkPlus, Braces, Download, FileCode, FileText,
  FolderOpen, Trash2, Upload,
} from 'lucide-react'
import { usePopover } from '../../hooks/usePopover'

const iconBtn = (active) =>
  `flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
    active
      ? 'text-brand-400 bg-brand-glow border-brand-600/40'
      : 'text-slate-500 hover:text-slate-300 hover:bg-app-700 border-transparent hover:border-app-border'
  }`

function ProfilesMenu({ profiles, count, onSave, onLoad, onDelete }) {
  const { open, setOpen, ref } = usePopover()
  const [name, setName] = useState('')

  function save() {
    onSave(name.trim() || 'Untitled profile')
    setName('')
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className={iconBtn(open || profiles.length > 0)} title="Prompt profiles">
        <Bookmark size={13} />
        Profiles
        {profiles.length > 0 && <span className="text-slate-600">({profiles.length})</span>}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-64 z-50 p-1.5 rounded-xl
          bg-app-800 border border-app-border shadow-xl shadow-black/50 animate-fade-in">
          <div className="flex gap-2 p-1.5">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && save()}
              placeholder={count > 0 ? `Save (${count} prompts)` : 'No overrides to save'}
              className="flex-1 bg-app-700 border border-app-border rounded-lg px-2.5 py-1.5
                text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
            />
            <button
              onClick={save}
              disabled={count === 0}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700
                text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <BookmarkPlus size={12} />
            </button>
          </div>

          {profiles.length > 0 ? (
            <div className="max-h-52 overflow-y-auto border-t border-app-border/60 mt-1">
              {profiles.map((p) => (
                <div key={p.id} className="group flex items-center gap-2 px-2.5 py-2 hover:bg-app-700/50 transition-colors">
                  <button onClick={() => onLoad(p)} title="Load profile" className="flex-1 flex items-center gap-2 text-left min-w-0">
                    <FolderOpen size={13} className="text-slate-600 group-hover:text-brand-400 flex-shrink-0" />
                    <span className="text-xs text-slate-300 truncate">{p.name}</span>
                    <span className="text-[10px] text-slate-600 flex-shrink-0">
                      {Object.keys(p.overrides || {}).length}
                    </span>
                  </button>
                  <button
                    onClick={() => onDelete(p.id)}
                    title="Delete"
                    className="p-1 rounded text-slate-700 hover:text-red-400 hover:bg-red-900/20
                      transition-colors flex-shrink-0 opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="px-2.5 pb-2 pt-1 text-[11px] text-slate-600 leading-snug">
              Save the set of modified prompts under a name to reuse it.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ExportMenu({ count, onExportJson, onExportYaml }) {
  const { open, setOpen, ref } = usePopover()

  const row = `w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-left transition-colors`

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className={iconBtn(open)} title="Export prompts">
        <Download size={13} />
        Export
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-64 z-50 p-1.5 rounded-xl
          bg-app-800 border border-app-border shadow-xl shadow-black/50 animate-fade-in">
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] text-slate-600 uppercase tracking-wide">Export</p>
          <button onClick={() => { onExportYaml('full'); setOpen(false) }} className={`${row} text-slate-200 hover:bg-app-700`}>
            <FileCode size={14} className="text-slate-500 flex-shrink-0" />
            <span className="min-w-0">
              <span className="block">prompts.yaml (full)</span>
              <span className="block text-[10px] text-slate-600">deployable: replaces the engine's</span>
            </span>
          </button>
          <button onClick={() => { onExportYaml('overrides'); setOpen(false) }} disabled={count === 0} className={`${row} text-slate-200 hover:bg-app-700 disabled:opacity-40 disabled:cursor-not-allowed`}>
            <FileText size={14} className="text-slate-500 flex-shrink-0" />
            <span className="min-w-0">
              <span className="block">params (overrides only)</span>
              <span className="block text-[10px] text-slate-600">extra layer after prompts.yaml</span>
            </span>
          </button>
          <button onClick={() => { onExportJson(); setOpen(false) }} disabled={count === 0} className={`${row} text-slate-200 hover:bg-app-700 disabled:opacity-40 disabled:cursor-not-allowed`}>
            <Braces size={14} className="text-slate-500 flex-shrink-0" />
            <span className="min-w-0">
              <span className="block">overrides JSON</span>
              <span className="block text-[10px] text-slate-600">backup / share / import</span>
            </span>
          </button>
        </div>
      )}
    </div>
  )
}

/** Standalone import button: opens the file picker directly. */
function ImportButton({ onImportFile }) {
  const fileRef = useRef(null)
  return (
    <>
      <button onClick={() => fileRef.current?.click()} className={iconBtn(false)} title="Import overrides from a JSON">
        <Upload size={13} />
        Import
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onImportFile(f)
          e.target.value = ''
        }}
      />
    </>
  )
}

/**
 * Profiles + export + import bar for the prompts editor: profiles menu
 * (save/load/delete), export menu (YAML full/overrides, JSON) and import button.
 */
export function PromptsToolbar(props) {
  return (
    <div className="flex items-center gap-1.5">
      <ProfilesMenu
        profiles={props.profiles}
        count={props.count}
        onSave={props.onSaveProfile}
        onLoad={props.onLoadProfile}
        onDelete={props.onDeleteProfile}
      />
      <ExportMenu
        count={props.count}
        onExportJson={props.onExportJson}
        onExportYaml={props.onExportYaml}
      />
      <ImportButton onImportFile={props.onImportFile} />
    </div>
  )
}
