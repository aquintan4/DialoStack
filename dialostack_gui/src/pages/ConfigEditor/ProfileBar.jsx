/**
 * Configuration profiles bar: pick, save, update, import/export and delete
 * named snapshots of the whole config (e.g. "Spanish" / "English" with their
 * STT language and TTS voice). Applying a profile while the engine runs offers
 * a one-click restart so the new setup actually takes effect.
 */
import { useState } from 'react'
import {
  Bookmark, Check, ChevronDown, Download, Plus, RefreshCw, Save, Trash2, Upload, X,
} from 'lucide-react'
import { useConfig } from '../../contexts/ConfigContext'
import { useEngine } from '../../contexts/EngineContext'
import { usePersistentState } from '../../hooks/usePersistentState'
import { usePopover } from '../../hooks/usePopover'
import { FileImportButton } from '../../components/FileImportButton'
import { PopoverPanel } from '../../components/ui'
import { STORAGE } from '../../lib/storageKeys'
import { downloadFile } from '../../lib/download'
import {
  applyProfileConfig, describeProfile, matchesProfile,
  profileFromJson, profileToJson, snapshotConfig,
} from '../../lib/configProfiles'

const btn = `flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border border-app-border
  text-slate-400 hover:text-slate-200 hover:bg-app-700 transition-colors
  disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent`

const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const fileName = (name) => `dialostack-profile-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.json`

/** Dropdown listing the saved profiles: click to apply, hover to delete. */
function ProfilePicker({ profiles, active, modified, onApply, onDelete }) {
  const { open, setOpen, ref } = usePopover()
  return (
    <div className="relative min-w-0 flex-1" ref={ref}>
      <button onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-1.5 rounded border border-app-border
          bg-app-950 hover:border-app-500 transition-colors text-left">
        <Bookmark size={13} className="text-slate-500 flex-shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-slate-200 truncate">
            {active ? active.name : profiles.length ? 'No profile applied' : 'No profiles yet'}
          </span>
          {active && (
            <span className="block font-mono text-[10px] text-slate-500 truncate">
              {describeProfile(active.config)}
            </span>
          )}
        </span>
        {modified && (
          <span className="font-mono text-[10px] text-amber-500 border border-amber-800/60 rounded-sm px-1 flex-shrink-0"
            title="The current configuration differs from this profile">
            modified
          </span>
        )}
        <ChevronDown size={13} className="text-slate-500 flex-shrink-0" />
      </button>

      {open && (
        <PopoverPanel align="left" width="w-full">
          {profiles.length === 0 ? (
            <p className="px-2.5 py-2 text-xs text-slate-500 leading-snug">
              Set up the configuration below, then use <span className="text-slate-300">Save as</span> to
              store it under a name (e.g. "Spanish", "English").
            </p>
          ) : profiles.map((p) => (
            <div key={p.id} className="group flex items-center gap-2 rounded hover:bg-app-700 transition-colors">
              <button onClick={() => { onApply(p); setOpen(false) }}
                className="flex-1 min-w-0 flex items-center gap-2 px-2.5 py-2 text-left">
                <Check size={13} className={`flex-shrink-0 ${p.id === active?.id ? 'text-brand-400' : 'invisible'}`} />
                <span className="min-w-0">
                  <span className="block text-sm text-slate-200 truncate">{p.name}</span>
                  <span className="block font-mono text-[10px] text-slate-500 truncate">{describeProfile(p.config)}</span>
                </span>
              </button>
              <button onClick={() => onDelete(p)} title={`Delete "${p.name}"`}
                className="p-1.5 mr-1 rounded text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100
                  focus:opacity-100 transition-opacity flex-shrink-0">
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </PopoverPanel>
      )}
    </div>
  )
}

export function ProfileBar() {
  const { config, replaceConfig } = useConfig()
  const { engineState, startEngine, stopEngine } = useEngine()
  const [profiles, setProfiles] = usePersistentState(STORAGE.configProfiles, [])
  const [activeId, setActiveId] = usePersistentState(STORAGE.configActiveProfile, null)
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')
  const [notice, setNotice] = useState(null)   // { tone, text, restart? }
  const [confirmDelete, setConfirmDelete] = useState(null)

  const active = profiles.find((p) => p.id === activeId) ?? null
  const modified = !!active && !matchesProfile(config, active.config)
  const running = engineState.state === 'running'

  function flash(tone, text, extra = {}) {
    setNotice({ tone, text, ...extra })
  }

  function apply(profile) {
    const next = applyProfileConfig(config, profile.config)
    replaceConfig(next)
    setActiveId(profile.id)
    setConfirmDelete(null)
    flash('ok', `Profile "${profile.name}" applied.`, running ? { restart: next } : {})
  }

  function saveAs() {
    const clean = name.trim()
    if (!clean) return
    const existing = profiles.find((p) => p.name.toLowerCase() === clean.toLowerCase())
    const profile = { id: existing?.id ?? newId(), name: clean, config: snapshotConfig(config) }
    setProfiles(existing
      ? profiles.map((p) => (p.id === existing.id ? profile : p))
      : [...profiles, profile])
    setActiveId(profile.id)
    setNaming(false)
    setName('')
    flash('ok', existing ? `Profile "${clean}" overwritten.` : `Profile "${clean}" saved.`)
  }

  function update() {
    if (!active) return
    setProfiles(profiles.map((p) => (p.id === active.id ? { ...p, config: snapshotConfig(config) } : p)))
    flash('ok', `Profile "${active.name}" updated.`)
  }

  function remove(profile) {
    if (confirmDelete !== profile.id) {
      setConfirmDelete(profile.id)
      flash('warn', `Click delete again to remove "${profile.name}".`)
      return
    }
    setProfiles(profiles.filter((p) => p.id !== profile.id))
    if (profile.id === activeId) setActiveId(null)
    setConfirmDelete(null)
    flash('ok', `Profile "${profile.name}" deleted.`)
  }

  async function importFile(file) {
    try {
      const { name: n, config: c } = profileFromJson(await file.text(), file.name.replace(/\.json$/i, ''))
      const profile = { id: newId(), name: n, config: c }
      setProfiles([...profiles, profile])
      flash('ok', `Profile "${n}" imported. Select it to apply it.`)
    } catch (err) {
      flash('error', err.message)
    }
  }

  async function restart(next) {
    setNotice(null)
    await stopEngine()
    await startEngine(next)
  }

  const noticeTone = {
    ok: 'text-slate-400',
    warn: 'text-amber-500',
    error: 'text-red-400',
  }

  return (
    <section className="bg-app-900 border border-app-border rounded">
      <div className="flex items-center gap-2 px-4 py-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 mr-1 flex-shrink-0">
          Profile
        </span>

        {naming ? (
          <div className="flex-1 flex items-center gap-2">
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveAs(); if (e.key === 'Escape') setNaming(false) }}
              placeholder='Profile name, e.g. "English"'
              className="flex-1 bg-app-950 border border-app-border rounded px-2.5 py-1.5 text-sm
                text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600" />
            <button onClick={saveAs} disabled={!name.trim()} className={btn}><Check size={13} /> Save</button>
            <button onClick={() => setNaming(false)} className={btn} title="Cancel"><X size={13} /></button>
          </div>
        ) : (
          <>
            <ProfilePicker profiles={profiles} active={active} modified={modified}
              onApply={apply} onDelete={remove} />
            <button onClick={update} disabled={!modified} className={btn}
              title={active ? `Store the current configuration in "${active.name}"` : 'Apply a profile first'}>
              <Save size={13} /> Update
            </button>
            <button onClick={() => { setNaming(true); setName('') }} className={btn}
              title="Save the current configuration as a new profile">
              <Plus size={13} /> Save as
            </button>
            <button onClick={() => active && downloadFile(fileName(active.name), profileToJson(active), 'application/json')}
              disabled={!active} className={btn} title="Export the applied profile as JSON (API keys are never included)">
              <Download size={13} />
            </button>
            <FileImportButton onFile={importFile} accept=".json,application/json" className={btn}
              title="Import a profile from a JSON file">
              <Upload size={13} />
            </FileImportButton>
          </>
        )}
      </div>

      {notice && (
        <div className="flex items-center gap-3 px-4 py-2 border-t border-app-border text-xs">
          <span className={noticeTone[notice.tone]}>{notice.text}</span>
          {notice.restart && (
            <>
              <span className="text-slate-500">The engine is running with the previous settings.</span>
              <button onClick={() => restart(notice.restart)}
                className="flex items-center gap-1 text-slate-200 underline underline-offset-2 decoration-slate-500">
                <RefreshCw size={11} /> Restart engine
              </button>
            </>
          )}
          <button onClick={() => setNotice(null)} className="ml-auto text-slate-600 hover:text-slate-300" title="Dismiss">
            <X size={12} />
          </button>
        </div>
      )}
    </section>
  )
}
