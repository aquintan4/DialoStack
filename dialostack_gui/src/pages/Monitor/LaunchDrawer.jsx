import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Eraser, Rocket, Send, X } from 'lucide-react'
import { Field, NumberField, Select, inputCls } from '../../components/ui'
import { usePersistentState } from '../../hooks/usePersistentState'
import { QuizEditor } from '../FrameBuilder/editors/QuizEditor'
import {
  emptyQuestion, compileFields, stateFromFields, kindMeta,
  LIBRARY_KEY, INJECT_TO_LAUNCH, HANDOFF_TO_BUILDER,
  readHandoff, writeHandoff, clearHandoff,
} from '../../lib/frames'
import { STORAGE } from '../../lib/storageKeys'
import { LAUNCH_DEFAULT, MODES, jsonFieldError } from './launch/goal'
import { PresetsSection } from './launch/PresetsSection'
import { CopyTaskMenu } from './launch/CopyTaskMenu'
import { JsonDisclosure, EditInBuilderLink } from './launch/JsonDisclosure'

/**
 * Side panel to configure and launch a dialogue task.
 * The draft persists in localStorage: it survives tab changes (e.g. going to
 * Configuration to start the engine) and reloads.
 *
 * The UI pieces live in ./launch/*; only the orchestration remains here:
 * draft state, goal construction, and the bridge to the library/Builder.
 */
export function LaunchDrawer({ open, onClose, onSend, isActive, rosStatus }) {
  const [form, setForm] = usePersistentState(STORAGE.launchForm, LAUNCH_DEFAULT)
  const [frameSchema, setFrameSchema] = usePersistentState(STORAGE.launchSchema, '')
  const [resources, setResources] = usePersistentState(STORAGE.launchResources, '')
  const [quizQuestions, setQuizQuestions] = usePersistentState(STORAGE.launchQuiz, [emptyQuestion()])
  const [schemaOpen, setSchemaOpen] = usePersistentState(STORAGE.launchSchemaOpen, false)
  const [resourcesOpen, setResourcesOpen] = usePersistentState(STORAGE.launchResourcesOpen, false)
  const [presets, setPresets] = usePersistentState(STORAGE.taskPresets, [])
  const [library] = usePersistentState(LIBRARY_KEY, [])
  const navigate = useNavigate()

  // Close with Escape
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // Inject from the Builder ("Use in launch"): when the drawer opens, the frame
  // is dumped into the correct field and mode.
  useEffect(() => {
    if (!open) return
    const inj = readHandoff(INJECT_TO_LAUNCH)
    if (inj?.kind) {
      applyFrame(inj)
      clearHandoff(INJECT_TO_LAUNCH)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const isQuiz = form.dialog_mode === 'quiz'
  const schemaError = useMemo(() => jsonFieldError(frameSchema, 'object'), [frameSchema])
  const resourcesError = useMemo(() => jsonFieldError(resources, 'array'), [resources])

  if (!open) return null

  function buildResourcesJson() {
    if (isQuiz) {
      const items = quizQuestions.filter((q) => q.question.trim() && q.answer.trim())
      if (items.length === 0) return ''
      return JSON.stringify([{
        name: 'questions',
        description: 'Quiz question bank',
        content: JSON.stringify(items),
      }])
    }
    return resources.trim()
  }

  // Action goal from the current draft. Shared by the send and the copy
  // (ros2 command / JSON), so they do not diverge.
  function buildGoal() {
    return {
      task_description: form.task_description.trim(),
      frame_schema_json: frameSchema.trim(),
      initial_frame_json: '',
      max_turns: Number(form.max_turns) || 10,
      dialog_mode: form.dialog_mode,
      resources_json: buildResourcesJson(),
      domain: form.domain.trim(),
    }
  }

  function handleSend() {
    onSend(buildGoal())
    onClose()
  }

  function clearDraft() {
    setForm(LAUNCH_DEFAULT)
    setFrameSchema('')
    setResources('')
    setQuizQuestions([emptyQuestion()])
  }

  function savePreset(name) {
    const preset = { id: `p${Date.now()}`, name, savedAt: Date.now(), form, frameSchema, resources, quizQuestions }
    // Same name: overwritten; the most recent one on top
    setPresets((prev) => [preset, ...prev.filter((p) => p.name !== name)])
  }

  function loadPreset(p) {
    setForm({ ...LAUNCH_DEFAULT, ...p.form })
    setFrameSchema(p.frameSchema || '')
    setResources(p.resources || '')
    setQuizQuestions(p.quizQuestions?.length ? p.quizQuestions : [emptyQuestion()])
  }

  function deletePreset(id) {
    setPresets((prev) => prev.filter((p) => p.id !== id))
  }

  // Applies a frame (from the library or an inject) to the form: sets the mode
  // and fills the goal fields that correspond to its kind.
  function applyFrame({ kind, state } = {}) {
    if (!kind) return
    setForm((f) => ({ ...f, dialog_mode: kind }))
    if (kind === 'quiz') {
      setQuizQuestions(state?.questions?.length ? state.questions : [emptyQuestion()])
      return
    }
    for (const f of compileFields(kind, state)) {
      if (f.field === 'frame_schema_json') {
        setFrameSchema(f.json)
        setSchemaOpen(true)
      } else if (f.field === 'resources_json') {
        // Empty optional resources (slot_filling): do not clutter the textarea with "[]".
        if (f.optional && f.json.trim() === '[]') continue
        setResources(f.json)
        setResourcesOpen(true)
      }
    }
  }

  // Handoff to the Builder: rebuilds the frame state from the launcher fields
  // and takes it to the Builder for editing (includes the resources).
  function editInBuilder(kind) {
    const state = kind === 'quiz'
      ? { questions: quizQuestions }
      : stateFromFields(kind, { frame_schema_json: frameSchema, resources_json: resources }).state
    writeHandoff(HANDOFF_TO_BUILDER, { kind, state })
    onClose()
    navigate('/builder')
  }

  const canSend =
    rosStatus === 'connected' &&
    form.task_description.trim().length > 0 &&
    !isActive &&
    !schemaError &&
    (isQuiz || !resourcesError)

  return (
    <div className="fixed inset-0 z-40">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="absolute right-0 top-0 h-full w-full max-w-md bg-app-900 border-l
        border-app-border shadow-2xl shadow-black/60 flex flex-col animate-slide-in-right">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-app-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-glow border border-brand-600/30
              flex items-center justify-center">
              <Rocket size={15} className="text-brand-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-100 leading-none">Launch task</h2>
              <p className="text-xs text-slate-600 mt-1">Define the dialogue objective</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-app-700 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Warning if there is no connection with the engine */}
        {rosStatus !== 'connected' && (
          <div className="flex items-center gap-2.5 mx-5 mt-4 px-3 py-2.5 rounded-lg
            bg-yellow-900/20 border border-yellow-700/40 flex-shrink-0">
            <AlertTriangle size={14} className="text-yellow-400 flex-shrink-0" />
            <p className="text-xs text-yellow-300/80 leading-snug">
              The engine is not available. Start it from{' '}
              <span className="font-medium text-yellow-300">Configuration</span> - your draft is saved automatically.
            </p>
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <PresetsSection
            presets={presets}
            onSave={savePreset}
            onLoad={loadPreset}
            onDelete={deletePreset}
            currentDescription={form.task_description}
          />

          <Field label="Task description" hint="Objective in natural language; the engine deduces the rest">
            <textarea
              rows={2}
              value={form.task_description}
              onChange={(e) => setForm((f) => ({ ...f, task_description: e.target.value }))}
              placeholder="E.g.: Pick up a cafeteria order"
              className={`${inputCls} resize-none`}
            />
          </Field>

          <Field label="Dialogue mode" hint="Auto-detect lets the engine classify the task">
            <Select
              value={form.dialog_mode}
              onChange={(e) => setForm((f) => ({ ...f, dialog_mode: e.target.value }))}
            >
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </Select>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Domain" hint="Context that guides the LLM's tone (optional)">
              <input
                type="text"
                value={form.domain}
                onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
                placeholder="cafeteria, hospital…"
                className={inputCls}
              />
            </Field>
            <NumberField
              label="Max. turns"
              min={1}
              max={50}
              value={form.max_turns}
              onChange={(v) => setForm((f) => ({ ...f, max_turns: v }))}
            />
          </div>

          {library.length > 0 && (
            <Field label="Use saved frame" hint="Fills the mode and payload from the Frame Builder library">
              <Select
                value=""
                onChange={(e) => {
                  const f = library.find((x) => x.id === e.target.value)
                  if (f) applyFrame(f)
                }}
              >
                <option value="">— Choose from the library ({library.length}) —</option>
                {library.map((f) => (
                  <option key={f.id} value={f.id}>{f.name} · {kindMeta(f.kind).label}</option>
                ))}
              </Select>
            </Field>
          )}

          {isQuiz && (
            <div className="space-y-2">
              <div className="flex justify-end">
                <EditInBuilderLink onClick={() => editInBuilder('quiz')} />
              </div>
              <QuizEditor questions={quizQuestions} onChange={setQuizQuestions} />
            </div>
          )}

          <div className="pt-2 border-t border-app-border/60 space-y-3">
            <p className="text-[11px] text-slate-600 uppercase tracking-wider font-semibold">Advanced</p>
            <JsonDisclosure
              label="Frame schema JSON"
              open={schemaOpen}
              onToggle={() => setSchemaOpen((o) => !o)}
              value={frameSchema}
              onChange={setFrameSchema}
              error={schemaError}
              rows={4}
              placeholder={'{"slots": [{"name": "slot_name", "type": "str"}]}'}
              action={<EditInBuilderLink
                onClick={() => editInBuilder('slot_filling')}
              />}
            />
            {!isQuiz && (
              <JsonDisclosure
                label="Resources JSON"
                open={resourcesOpen}
                onToggle={() => setResourcesOpen((o) => !o)}
                value={resources}
                onChange={setResources}
                error={resourcesError}
                rows={3}
                placeholder='[{"name": "...", "description": "...", "content": "..."}]'
                action={<EditInBuilderLink
                  onClick={() => editInBuilder('explanation')}
                />}
              />
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 px-5 py-4 border-t border-app-border flex-shrink-0">
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg
              bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed glow-blue"
          >
            <Send size={14} />
            Launch task
          </button>
          <CopyTaskMenu goal={buildGoal()} disabled={form.task_description.trim().length === 0} />
          <button
            onClick={clearDraft}
            title="Clear draft"
            className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg text-slate-500
              hover:text-slate-300 hover:bg-app-700 border border-transparent
              hover:border-app-border text-sm transition-all"
          >
            <Eraser size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
