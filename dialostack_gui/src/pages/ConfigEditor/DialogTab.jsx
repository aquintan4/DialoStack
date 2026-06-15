/** Dialogue tab: language, prompts, timeouts/limits and conversation logging. */
import { FileText, Languages, Timer } from 'lucide-react'
import { Field, NumberField, SectionCard, Select, SliderField, ToggleField, inputCls } from '../../components/ui'

const LANGUAGES = ['Spanish', 'English', 'French', 'German', 'Portuguese', 'Catalan', 'Italian']

export function DialogTab({ dialog, update }) {
  const acksText = Array.isArray(dialog.ack_phrases) ? dialog.ack_phrases.join('\n') : ''

  function handleAcks(text) {
    const phrases = text.split('\n').filter(s => s.trim())
    update({ ack_phrases: phrases.length > 0 ? phrases : [''] })
  }

  return (
    <div className="space-y-4">
      <SectionCard
        icon={Languages}
        title="Language and phrases"
        description="How the robot speaks during the conversation"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Dialogue language">
            <Select value={dialog.language} onChange={e => update({ language: e.target.value })}>
              {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Timeout prompt"
            hint="What the robot says when the user has gone a while without responding">
            <input type="text" value={dialog.timeout_prompt}
              onChange={e => update({ timeout_prompt: e.target.value })}
              placeholder="Are you still there?" className={inputCls} />
          </Field>
        </div>
        <Field label="Acknowledgment phrases"
          hint="One per line. The robot says a random one after successfully extracting a slot">
          <textarea
            value={acksText}
            onChange={e => handleAcks(e.target.value)}
            rows={5}
            spellCheck={false}
            className={`${inputCls} resize-none font-mono text-xs leading-relaxed`}
          />
        </Field>
      </SectionCard>

      <SectionCard
        icon={Timer}
        title="Timeouts and limits"
        description="When to insist and when to abort the task"
      >
        <div className="grid grid-cols-3 gap-4">
          <NumberField label="Response wait" unit="s" min={5} max={120}
            hint="Maximum time waiting for the user to speak"
            value={dialog.wait_timeout} onChange={v => update({ wait_timeout: v })} />
          <NumberField label="LLM timeout" unit="s" min={10} max={300}
            value={dialog.llm_timeout} onChange={v => update({ llm_timeout: v })} />
          <NumberField label="TTS timeout" unit="s" min={5} max={120}
            value={dialog.tts_timeout} onChange={v => update({ tts_timeout: v })} />
          <NumberField label="Consecutive timeouts" min={1} max={10}
            hint="Consecutive expired waits before aborting"
            value={dialog.max_timeouts} onChange={v => update({ max_timeouts: v })} />
          <NumberField label="Not understood" min={1} max={10}
            hint="Consecutive unintelligible responses before aborting"
            value={dialog.max_unclear} onChange={v => update({ max_unclear: v })} />
          <NumberField label="Attempts per slot" min={1} max={10}
            hint="Times the same value is asked for before giving up"
            value={dialog.max_attempts} onChange={v => update({ max_attempts: v })} />
        </div>
        <SliderField
          label="Maximum turns in history"
          hint="How many turns the LLM session remembers before forgetting the old ones"
          value={dialog.history_max_turns}
          onChange={v => update({ history_max_turns: v })}
          min={20} max={500} step={10} />
      </SectionCard>

      <SectionCard
        icon={FileText}
        title="Logging"
        description="Conversation log on disk"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Log path" hint="Leave empty to disable logging">
            <input type="text" value={dialog.conversation_log_path}
              onChange={e => update({ conversation_log_path: e.target.value })}
              placeholder="/tmp/dialog_conversations.log"
              className={inputCls} />
          </Field>
          <NumberField label="Rotate when exceeding" unit="MB" min={0} max={1000}
            hint="0 = never rotate"
            value={dialog.conversation_log_max_mb} onChange={v => update({ conversation_log_max_mb: v })} />
        </div>
        <ToggleField label="Silent mode" hint="Suppresses the dialogue node logs in the console"
          value={dialog.silent_mode} onChange={v => update({ silent_mode: v })} />
      </SectionCard>
    </div>
  )
}
