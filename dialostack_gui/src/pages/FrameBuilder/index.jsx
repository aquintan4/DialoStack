import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, ChevronRight, Rocket } from 'lucide-react'
import { JsonEditor } from './JSONPreview'
import { SlotsEditor } from './editors/SlotsEditor'
import { QuizEditor } from './editors/QuizEditor'
import { ResourcesEditor } from './editors/ResourcesEditor'
import { FrameLibrary } from './FrameLibrary'
import { usePersistentState } from '../../hooks/usePersistentState'
import { STORAGE } from '../../lib/storageKeys'
import {
  FRAME_KINDS, kindMeta, kindFields, emptyState, emptyDimension,
  compileFields, parseDimension,
  emptySlot, emptyQuestion, emptyResource,
  LIBRARY_KEY, HANDOFF_TO_BUILDER, INJECT_TO_LAUNCH,
  readHandoff, writeHandoff, clearHandoff,
} from '../../lib/frames'

/** Frame Builder page: visually builds a goal's frame and compiles it to JSON. */
export function FrameBuilder() {
  const navigate = useNavigate()

  // Active mode + one persistent draft per DIMENSION (slots/quiz/resources are
  // shared across modes: "resources" is a dimension, not a property of a mode).
  const [kind, setKind] = usePersistentState(STORAGE.builderKind, 'slot_filling')
  const [slots, setSlots] = usePersistentState(STORAGE.builderSlots, [emptySlot()])
  const [quiz, setQuiz] = usePersistentState(STORAGE.builderQuiz, [emptyQuestion()])
  const [resources, setResources] = usePersistentState(STORAGE.builderResources, [emptyResource()])
  const [library, setLibrary] = usePersistentState(LIBRARY_KEY, [])
  const [resourcesOpen, setResourcesOpen] = useState(false)

  const dim = { slots, questions: quiz, resources }

  // Editable state of the current mode: only the dimensions that mode produces.
  function currentState(k = kind) {
    const out = {}
    for (const f of kindFields(k)) out[f.key] = dim[f.key]
    return out
  }

  // Dumps a dimension's items into its draft (with a minimal element).
  function applyDimension(key, items) {
    const safe = items?.length ? items : emptyDimension(key)
    if (key === 'slots') setSlots(safe)
    else if (key === 'questions') setQuiz(safe)
    else setResources(safe)
  }

  // Dumps a full state (all its dimensions) into the drafts.
  function applyState(k, s) {
    for (const f of kindFields(k)) applyDimension(f.key, s?.[f.key])
  }

  // Inbound handoff: the Launcher or the Monitor requested editing a frame.
  useEffect(() => {
    const h = readHandoff(HANDOFF_TO_BUILDER)
    if (h?.kind) {
      setKind(h.kind)
      // A kind-only handoff (e.g. from the Strategies page) just focuses the
      // Builder on a strategy; it must not wipe the current draft.
      if (h.state) {
        applyState(h.kind, h.state)
        if (h.state.resources?.some((r) => r.name?.trim() || r.content?.trim())) setResourcesOpen(true)
      }
      clearHandoff(HANDOFF_TO_BUILDER)
    }
    // only on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ==== LIBRARY ====
  function saveFrame(name) {
    const frame = { id: `f${Date.now()}`, name, savedAt: Date.now(), kind, state: currentState() }
    setLibrary((prev) => [frame, ...prev.filter((f) => f.name !== name)])
  }
  function loadFrame(f) {
    setKind(f.kind)
    applyState(f.kind, f.state)
    if (f.state?.resources?.some((r) => r.name?.trim() || r.content?.trim())) setResourcesOpen(true)
  }
  const deleteFrame = (id) => setLibrary((prev) => prev.filter((f) => f.id !== id))

  // Suggested name when saving, based on the first element with content.
  const suggestedName =
    kind === 'quiz' ? (quiz.find((q) => q.question.trim())?.question.trim().slice(0, 40) || '')
      : kind === 'explanation' ? (resources.find((r) => r.name.trim())?.name.trim() || '')
        : (slots.find((s) => s.name.trim())?.name.trim() || '')

  // Send the current frame to the Launcher (outbound handoff) and return to the Monitor.
  function useInLaunch() {
    writeHandoff(INJECT_TO_LAUNCH, { kind, state: currentState() })
    navigate('/monitor')
  }

  function clearCurrent() {
    applyState(kind, emptyState(kind))
  }

  // Goal fields of the current mode, each with its parse/apply for the JSON editor.
  const fields = compileFields(kind, currentState()).map((f) => ({
    ...f,
    parse: (text) => parseDimension(f.key, text),
    onApply: (items) => applyDimension(f.key, items),
  }))

  const meta = kindMeta(kind)
  const goalFields = kindFields(kind).map((f) => f.field).join(' + ')

  return (
    <div className="flex h-full">

      {/* Left panel - mode editors */}
      <div className="flex flex-col w-[55%] border-r border-app-border overflow-hidden">

        <div className="px-6 py-4 border-b border-app-border bg-app-900 flex-shrink-0 space-y-3">
          <div>
            <h1 className="text-sm font-semibold text-slate-100">Frame Builder</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {meta.desc} - compiles to <span className="font-mono text-brand-500/80">{goalFields}</span>
            </p>
          </div>
          {/* Mode selector */}
          <div className="flex gap-1 p-1 bg-app-800 border border-app-border rounded-lg">
            {FRAME_KINDS.map((k) => (
              <button
                key={k.value}
                onClick={() => setKind(k.value)}
                className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  kind === k.value
                    ? 'bg-brand-600 text-white'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-app-700'
                }`}
              >
                {k.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          <FrameLibrary
            library={library}
            onSave={saveFrame}
            onLoad={loadFrame}
            onDelete={deleteFrame}
            suggestedName={suggestedName}
          />

          {kind === 'slot_filling' && (
            <>
              <SlotsEditor slots={slots} onChange={setSlots} />
              {/* Reference resources: optional in slot_filling - the engine
                  injects them as [CONTEXT] (menu, catalog...) to extract and compose. */}
              <div className="border-t border-app-border/60 pt-3">
                <button
                  onClick={() => setResourcesOpen((o) => !o)}
                  className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wider hover:text-slate-300 transition-colors"
                >
                  {resourcesOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  Reference resources
                  <span className="font-normal normal-case tracking-normal text-slate-600">optional · context</span>
                </button>
                {resourcesOpen && (
                  <div className="mt-3">
                    <ResourcesEditor resources={resources} onChange={setResources} />
                  </div>
                )}
              </div>
            </>
          )}
          {kind === 'quiz' && <QuizEditor questions={quiz} onChange={setQuiz} />}
          {kind === 'explanation' && <ResourcesEditor resources={resources} onChange={setResources} />}
        </div>

        <div className="flex items-center gap-2 px-6 py-4 border-t border-app-border bg-app-900 flex-shrink-0">
          <button
            onClick={useInLaunch}
            title="Bring this frame to the launch form"
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700
              text-white text-sm font-medium transition-colors glow-blue"
          >
            <Rocket size={14} />
            Use in launch
          </button>
          <button
            onClick={clearCurrent}
            className="text-xs text-slate-500 hover:text-slate-300 hover:bg-app-700
              border border-transparent hover:border-app-border px-3 py-1.5 rounded-lg transition-all"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Right panel - bidirectional JSON editor(s) */}
      <div className="flex-1 bg-app-950/60 flex flex-col overflow-hidden">
        <JsonEditor fields={fields} />
      </div>
    </div>
  )
}
