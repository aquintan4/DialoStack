/**
 * Strategies page: explains each dialogue strategy and lets you edit its canned
 * phrases (the deterministic lines the robot falls back to) for the ACTIVE
 * dialogue language. Mirrors the Prompts editor: defaults come from the engine,
 * only changed phrases are stored as overrides (config.phrases[language]) and
 * reach the engine as `phrases.*` params on start. Also links each strategy to
 * its Frame Builder editor.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, ExternalLink, Languages, RotateCcw, Upload } from 'lucide-react'
import { Field, ModifiedTag, SectionCard, inputCls } from '../../components/ui'
import { FileImportButton } from '../../components/FileImportButton'
import { useConfig } from '../../contexts/ConfigContext'
import { useFlash } from '../../hooks/useFlash'
import { api } from '../../lib/api'
import { downloadFile, fileStamp } from '../../lib/download'
import { STRATEGIES, ACK_KEY, phraseLabel } from '../../lib/strategies'
import { writeHandoff, HANDOFF_TO_BUILDER } from '../../lib/frames'

const sameAcks = (a, b) =>
  Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => x === b[i])

export function StrategiesEditor() {
  const { config, updateSection } = useConfig()
  const navigate = useNavigate()
  const language = config.dialog?.language || 'Spanish'
  const overrides = config.phrases?.[language] || {}

  const [defaults, setDefaults] = useState(null)
  const [status, setStatus] = useState('loading')   // 'loading' | 'ready' | 'error'
  const { message: toast, flash } = useFlash()

  useEffect(() => {
    let active = true
    setStatus('loading')
    api.phrases(language)
      .then((d) => {
        if (!active) return
        setDefaults(d.phrases || {})
        setStatus(d.available ? 'ready' : 'error')
      })
      .catch(() => active && setStatus('error'))
    return () => { active = false }
  }, [language])

  const setOverrides = (next) => updateSection('phrases', { [language]: next })

  const valueOf = (key) => (key in overrides ? overrides[key] : defaults?.[key] ?? (key === ACK_KEY ? [] : ''))
  const isModified = (key) =>
    key in overrides && (key === ACK_KEY ? !sameAcks(overrides[key], defaults?.[key]) : overrides[key] !== defaults?.[key])

  function setPhrase(key, value) {
    const def = defaults?.[key]
    const next = { ...overrides }
    const blank = key === ACK_KEY ? !value?.length : !String(value).trim()
    const isDefault = key === ACK_KEY ? sameAcks(value, def) : value === def
    if (blank || isDefault) delete next[key]
    else next[key] = value
    setOverrides(next)
  }
  const resetKey = (key) => { const n = { ...overrides }; delete n[key]; setOverrides(n) }
  const resetAll = () => setOverrides({})

  async function exportYaml(mode) {
    try {
      const { yaml } = await api.phrasesYaml(overrides, language, mode)
      downloadFile(`dialostack-phrases-${language}-${fileStamp()}.yaml`, yaml ?? '', 'text/yaml')
    } catch {
      flash('Could not generate the YAML (is the engine available?)')
    }
  }
  async function importFile(file) {
    if (!file) return
    try {
      const parsed = (await api.phrasesParse(await file.text()))?.phrases || {}
      const merged = { ...overrides }
      for (const [k, v] of Object.entries(parsed)) if (defaults && k in defaults) merged[k] = v
      setOverrides(merged)
      flash('Phrases imported')
    } catch {
      flash('Could not read the file')
    }
  }

  function buildInBuilder(kind) {
    // kind-only handoff: switch the Builder to this strategy without clobbering
    // an existing draft (FrameBuilder applies state only when present).
    writeHandoff(HANDOFF_TO_BUILDER, { kind })
    navigate('/builder')
  }

  const modifiedCount = Object.keys(overrides).length

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-app-border bg-app-900 flex-shrink-0">
        <div>
          <h1 className="text-sm font-semibold text-slate-100">Strategies</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            What each strategy does and the canned phrases it falls back to
          </p>
        </div>
        <div className="flex items-center gap-2">
          {toast && <span className="text-xs text-slate-400">{toast}</span>}
          <FileImportButton onFile={importFile} title="Import phrases (YAML or JSON)"
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-app-700 border border-app-border transition-all">
            <Upload size={13} /> Import
          </FileImportButton>
          <button onClick={() => exportYaml('overrides')}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-app-700 border border-app-border transition-all">
            <Download size={13} /> Export
          </button>
          <button onClick={resetAll} disabled={!modifiedCount}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all text-slate-500 border-transparent hover:text-red-400 hover:bg-app-700 hover:border-app-border disabled:opacity-40 disabled:cursor-not-allowed">
            <RotateCcw size={13} /> Reset all
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-5 space-y-4">
          {/* Active language banner */}
          <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg bg-app-800 border border-app-border">
            <Languages size={15} className="text-brand-400 flex-shrink-0" />
            <p className="text-xs text-slate-400">
              Editing phrases for <span className="font-medium text-slate-200">{language}</span>
              {modifiedCount > 0 && <span className="text-brand-400"> · {modifiedCount} overridden</span>}.
              {' '}Change the language in <span className="text-slate-300">Configuration → Dialogue</span>.
              {' '}Empty fields fall back to the engine default in this language.
            </p>
          </div>

          {status === 'loading' && <p className="text-xs text-slate-500 px-1">Loading engine defaults…</p>}
          {status === 'error' && (
            <p className="text-xs text-red-400/80 px-1">
              Could not read the engine default phrases. Is the workspace built and the GUI server running with ROS sourced?
            </p>
          )}

          {status === 'ready' && STRATEGIES.map((s) => (
            <SectionCard key={s.id} icon={Languages} title={s.label} description={s.summary}>
              <p className="text-xs text-slate-500 leading-relaxed -mt-1 mb-1">{s.desc}</p>
              {s.frameKind && (
                <button onClick={() => buildInBuilder(s.frameKind)}
                  className="inline-flex items-center gap-1.5 text-xs text-brand-400 hover:text-brand-300 mb-2 transition-colors">
                  <ExternalLink size={12} /> Build its frame in the Frame Builder
                </button>
              )}
              <div className="space-y-3">
                {s.keys.map((key) => (
                  <PhraseField key={key} label={phraseLabel(key)} value={valueOf(key)}
                    placeholder={defaults?.[key] ?? ''} modified={isModified(key)}
                    onChange={(v) => setPhrase(key, v)} onReset={() => resetKey(key)} />
                ))}
                {s.ack && (
                  <AckField value={valueOf(ACK_KEY)} placeholder={defaults?.[ACK_KEY] ?? []}
                    modified={isModified(ACK_KEY)}
                    onChange={(v) => setPhrase(ACK_KEY, v)} onReset={() => resetKey(ACK_KEY)} />
                )}
              </div>
            </SectionCard>
          ))}
        </div>
      </div>
    </div>
  )
}

function PhraseField({ label, value, placeholder, modified, onChange, onReset }) {
  return (
    <Field label={
      <span className="flex items-center justify-between gap-2">
        <span>{label}</span>
        {modified && <ModifiedTag onReset={onReset} />}
      </span>
    }>
      <input type="text" value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)} className={inputCls} />
    </Field>
  )
}

function AckField({ value, placeholder, modified, onChange, onReset }) {
  const text = Array.isArray(value) ? value.join('\n') : ''
  const ph = Array.isArray(placeholder) ? placeholder.join('\n') : ''
  return (
    <Field
      label={
        <span className="flex items-center justify-between gap-2 w-full">
          <span>Acknowledgments (one per line — a random one is said after filling a slot)</span>
          {modified && <ModifiedTag onReset={onReset} />}
        </span>
      }>
      <textarea value={text} placeholder={ph} rows={5} spellCheck={false}
        onChange={(e) => onChange(e.target.value.split('\n').map((s) => s.trim()).filter(Boolean))}
        className={`${inputCls} resize-none font-mono text-xs leading-relaxed`} />
    </Field>
  )
}
