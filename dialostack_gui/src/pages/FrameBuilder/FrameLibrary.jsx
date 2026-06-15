import { useState } from 'react'
import { Bookmark, BookmarkPlus, FolderOpen, Trash2 } from 'lucide-react'
import { kindMeta } from '../../lib/frames'

/**
 * Library of saved frames - same pattern as the LaunchDrawer's saved tasks.
 * Stores the editable state (round-trip) under a name and reloads it with one
 * click. The state is governed by the Builder (persisted).
 */
export function FrameLibrary({ library, onSave, onLoad, onDelete, suggestedName }) {
  const [saveOpen, setSaveOpen] = useState(false)
  const [name, setName] = useState('')
  const [loadedId, setLoadedId] = useState(null)

  function handleSave() {
    onSave(name.trim() || suggestedName.trim() || 'Untitled frame')
    setSaveOpen(false)
    setName('')
  }

  function handleLoad(f) {
    onLoad(f)
    setLoadedId(f.id)
    setTimeout(() => setLoadedId(null), 1200)
  }

  return (
    <div className="bg-app-800/60 border border-app-border rounded-xl">
      <div className="flex items-center justify-between px-3.5 py-2.5">
        <span className="flex items-center gap-2 text-xs font-medium text-slate-400">
          <Bookmark size={13} className="text-brand-400" />
          Saved frames
          {library.length > 0 && <span className="text-slate-600">({library.length})</span>}
        </span>
        <button
          onClick={() => setSaveOpen((o) => !o)}
          className="flex items-center gap-1.5 text-xs text-brand-500 hover:text-brand-400 transition-colors"
        >
          <BookmarkPlus size={13} />
          Save current
        </button>
      </div>

      {saveOpen && (
        <div className="flex gap-2 px-3.5 pb-3">
          <input
            type="text"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            placeholder={suggestedName || 'Frame name'}
            className="flex-1 bg-app-700 border border-app-border rounded-lg px-2.5 py-1.5
              text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
          />
          <button
            onClick={handleSave}
            className="px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium transition-colors"
          >
            Save
          </button>
        </div>
      )}

      {library.length > 0 && (
        <div className="border-t border-app-border/60 max-h-44 overflow-y-auto">
          {library.map((f) => (
            <div
              key={f.id}
              className={`group flex items-center gap-2 px-3.5 py-2 border-b border-app-border/40
                last:border-b-0 transition-colors ${loadedId === f.id ? 'bg-brand-glow' : 'hover:bg-app-700/50'}`}
            >
              <button
                onClick={() => handleLoad(f)}
                title="Load this frame"
                className="flex-1 flex items-center gap-2.5 text-left min-w-0"
              >
                <FolderOpen size={13} className="text-slate-600 group-hover:text-brand-400 transition-colors flex-shrink-0" />
                <span className="text-xs text-slate-300 truncate">{f.name}</span>
                <span className="text-[10px] text-slate-600 font-mono flex-shrink-0">
                  {kindMeta(f.kind).label.toLowerCase()}
                </span>
              </button>
              {loadedId === f.id && (
                <span className="text-[10px] text-brand-400 font-medium flex-shrink-0">Loaded ✓</span>
              )}
              <button
                onClick={() => onDelete(f.id)}
                title="Delete"
                className="p-1 rounded text-slate-700 hover:text-red-400 hover:bg-red-900/20
                  transition-colors flex-shrink-0 opacity-0 group-hover:opacity-100"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {library.length === 0 && !saveOpen && (
        <p className="px-3.5 pb-3 text-[11px] text-slate-600 leading-snug">
          Save the current frame to reuse it when launching tasks without rebuilding it.
        </p>
      )}
    </div>
  )
}
