import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { api } from '../../lib/api'
import { useConfig } from '../../contexts/ConfigContext'
import { usePersistentState } from '../../hooks/usePersistentState'
import { useFlash } from '../../hooks/useFlash'
import { validateOverride, placeholders, groupPrompts } from '../../lib/prompts'
import { downloadFile, fileStamp } from '../../lib/download'
import { STORAGE } from '../../lib/storageKeys'
import { PromptsToolbar } from './PromptsToolbar'
import { PromptList } from './PromptList'
import { PromptEditorPanel } from './PromptEditorPanel'

/** Maps a list of keys to `undefined` (they disappear when serialized). */
const clearedMap = (keys) => Object.fromEntries(keys.map((k) => [k, undefined]))

/**
 * Prompts editor. Orchestrates: loads the engine defaults, governs the
 * overrides (in `config.prompts`), profiles and export/import; the UI lives in
 * PromptList / PromptEditorPanel / PromptsToolbar.
 */
export function PromptsEditor() {
  const { config, updateSection } = useConfig()
  const overrides = config.prompts || {}

  const [defaults, setDefaults] = useState({})
  const [status, setStatus] = useState('loading')   // loading | ready | unavailable
  const [selected, setSelected] = useState(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('')
  const [profiles, setProfiles] = usePersistentState(STORAGE.promptProfiles, [])
  const { message: toast, flash } = useFlash()

  const isOverridden = (key) => typeof overrides[key] === 'string'
  const overrideCount = Object.values(overrides).filter((v) => typeof v === 'string').length

  // Only real overrides (string, non-empty, different from the default).
  const validOverrides = useMemo(() => {
    const out = {}
    for (const [k, v] of Object.entries(overrides)) {
      if (typeof v === 'string' && v.trim() && defaults[k] != null && v !== defaults[k]) out[k] = v
    }
    return out
  }, [overrides, defaults])

  // Refreshes the editor with a prompt's effective value (override or default).
  const loadDraft = (key, map = overrides) =>
    setDraft(typeof map[key] === 'string' ? map[key] : (defaults[key] ?? ''))

  // ==== PROFILES ====
  function saveProfile(name) {
    const profile = { id: `pr${Date.now()}`, name, savedAt: Date.now(), overrides: validOverrides }
    setProfiles((prev) => [profile, ...prev.filter((p) => p.name !== name)])
    flash(`Profile "${name}" saved`)
  }

  function loadProfile(p) {
    // Replaces the whole set: clears the current ones and applies the profile's.
    const merge = clearedMap(Object.keys(overrides))
    for (const [k, v] of Object.entries(p.overrides || {})) {
      if (typeof v === 'string' && defaults[k] != null && validateOverride(v, defaults[k]) === null) merge[k] = v
    }
    updateSection('prompts', merge)
    if (selected) loadDraft(selected, merge)
    setError(null)
    flash(`Profile "${p.name}" loaded`)
  }

  const deleteProfile = (id) => setProfiles((prev) => prev.filter((p) => p.id !== id))

  // ==== EXPORT / IMPORT ====
  function exportJson() {
    downloadFile(`dialostack-prompts-${fileStamp()}.json`, JSON.stringify(validOverrides, null, 2), 'application/json')
  }

  async function exportYaml(mode) {
    try {
      const res = await api.promptsYaml(validOverrides, mode)
      const name = mode === 'full' ? `prompts-${fileStamp()}.yaml` : `prompt-overrides-${fileStamp()}.yaml`
      downloadFile(name, res.yaml ?? '', 'text/yaml')
    } catch {
      flash('Could not generate the YAML (is the engine/environment available?)')
    }
  }

  // Imports a prompts file (YAML or JSON). The server parses it (PyYAML) and
  // returns the {key: template} mapping; here we keep ONLY the keys that match a
  // known prompt, differ from its default and validate, then MERGE them in - the
  // overrides already set for other prompts are left untouched. Importing a full
  // file therefore brings in just the prompts that were actually changed.
  async function importFile(file) {
    let mapping
    try {
      mapping = (await api.promptsParse(await file.text()))?.prompts
    } catch { flash('Could not read the file'); return }
    if (!mapping || typeof mapping !== 'object' || !Object.keys(mapping).length) {
      flash('No prompts found in the file'); return
    }

    const merge = {}
    let ok = 0, unknown = 0, invalid = 0, same = 0
    for (const [k, v] of Object.entries(mapping)) {
      if (typeof v !== 'string') continue
      if (defaults[k] == null) { unknown += 1; continue }       // not a known prompt
      if (v === defaults[k]) { same += 1; continue }            // identical to default
      if (validateOverride(v, defaults[k]) !== null) { invalid += 1; continue }
      merge[k] = v; ok += 1
    }

    const skipped = [
      unknown && `${unknown} unknown`, invalid && `${invalid} invalid`, same && `${same} unchanged`,
    ].filter(Boolean).join(', ')

    if (ok === 0) { flash(`Nothing imported${skipped ? ` (${skipped})` : ''}`); return }
    updateSection('prompts', merge)
    if (selected && typeof merge[selected] === 'string') setDraft(merge[selected])
    flash(`Imported ${ok}${skipped ? `; skipped ${skipped}` : ''}`)
  }

  // Load the engine default templates once.
  useEffect(() => {
    let alive = true
    api.prompts()
      .then((res) => {
        if (!alive) return
        const d = res?.prompts || {}
        setDefaults(d)
        setStatus(res?.available ? 'ready' : 'unavailable')
        setSelected((prev) => prev ?? Object.keys(d)[0] ?? null)
      })
      .catch(() => alive && setStatus('unavailable'))
    return () => { alive = false }
  }, [])

  // When the selected prompt changes, load its effective value into the editor.
  useEffect(() => {
    if (!selected) return
    loadDraft(selected)
    setError(null)
    // overrides out of deps: only reload when the prompt or the defaults change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, defaults])

  const groups = useMemo(() => groupPrompts(Object.keys(defaults)), [defaults])
  const allowed = useMemo(
    () => (selected ? [...placeholders(defaults[selected] ?? ''), 'language'] : []),
    [selected, defaults],
  )

  function onDraftChange(text) {
    setDraft(text)
    const def = defaults[selected] ?? ''
    if (text === def) {
      setError(null)
      if (isOverridden(selected)) updateSection('prompts', { [selected]: undefined })
      return
    }
    const err = validateOverride(text, def)
    setError(err)
    // Only saved (and therefore only reaches the engine) if it is valid.
    if (!err) updateSection('prompts', { [selected]: text })
  }

  function resetCurrent() {
    setDraft(defaults[selected] ?? '')
    setError(null)
    updateSection('prompts', { [selected]: undefined })
  }

  function resetAll() {
    updateSection('prompts', clearedMap(Object.keys(overrides)))
    if (selected) setDraft(defaults[selected] ?? '')
    setError(null)
  }

  if (status === 'loading') {
    return (
      <div className="h-full flex items-center justify-center text-slate-600 text-sm gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading templates…
      </div>
    )
  }

  if (status === 'unavailable') {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 p-8 text-center">
        <AlertTriangle size={28} className="text-yellow-400" />
        <p className="text-sm text-slate-300 max-w-sm">
          Could not read the engine default templates.
        </p>
        <p className="text-xs text-slate-600 max-w-sm leading-relaxed">
          The editor needs the <span className="font-mono">ros2_dialog_manager</span> package in
          the environment. Start the GUI with the environment activated (<span className="font-mono">gui.sh</span>).
        </p>
      </div>
    )
  }

  const overridden = !!selected && isOverridden(selected)
  const modified = overridden && draft !== (defaults[selected] ?? '')

  return (
    <div className="flex h-full">
      <PromptList
        toolbar={(
          <PromptsToolbar
            profiles={profiles}
            count={overrideCount}
            onSaveProfile={saveProfile}
            onLoadProfile={loadProfile}
            onDeleteProfile={deleteProfile}
            onExportJson={exportJson}
            onExportYaml={exportYaml}
            onImportFile={importFile}
          />
        )}
        toast={toast}
        overrideCount={overrideCount}
        onResetAll={resetAll}
        filter={filter}
        onFilterChange={setFilter}
        groups={groups}
        selected={selected}
        onSelect={setSelected}
        isOverridden={isOverridden}
      />
      <PromptEditorPanel
        selected={selected}
        draft={draft}
        onDraftChange={onDraftChange}
        error={error}
        allowed={allowed}
        overridden={overridden}
        modified={modified}
        onReset={resetCurrent}
      />
    </div>
  )
}
