import { Plus, X } from 'lucide-react'
import { emptyQuestion } from '../../../lib/frames'

/**
 * Question bank editor (quiz mode). Shared by the Frame Builder and the
 * LaunchDrawer to avoid duplicating the question/answer logic.
 */
export function QuizEditor({ questions, onChange }) {
  const update = (i, field, value) =>
    onChange(questions.map((q, idx) => (idx === i ? { ...q, [field]: value } : q)))
  const remove = (i) => onChange(questions.filter((_, idx) => idx !== i))
  const add = () => onChange([...questions, emptyQuestion()])

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Quiz questions
        </h2>
        <button
          onClick={add}
          className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400 transition-colors"
        >
          <Plus size={13} />
          Add
        </button>
      </div>

      {questions.length === 0 && (
        <p className="text-xs text-slate-600 italic">No questions - add at least one.</p>
      )}

      {questions.map((q, i) => (
        <div key={i} className="bg-app-800 border border-app-border rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">Question {i + 1}</span>
            <button onClick={() => remove(i)} className="text-slate-600 hover:text-red-400 transition-colors">
              <X size={12} />
            </button>
          </div>
          <input
            type="text"
            value={q.question}
            onChange={(e) => update(i, 'question', e.target.value)}
            placeholder="What is the capital of France?"
            className="w-full bg-app-700 border border-app-border rounded-md px-2.5 py-1.5
              text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
          />
          <input
            type="text"
            value={q.answer}
            onChange={(e) => update(i, 'answer', e.target.value)}
            placeholder="Paris"
            className="w-full bg-app-700 border border-app-border rounded-md px-2.5 py-1.5
              text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
          />
        </div>
      ))}
    </div>
  )
}
