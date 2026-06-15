/** LLM tab: provider/model selection plus Gemini or Ollama connection settings. */
import { Cloud, HardDrive, Sparkles } from 'lucide-react'
import { Field, NumberField, SectionCard, Select, ToggleField, inputCls } from '../../components/ui'

const GEMINI_MODELS = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash']
const OLLAMA_MODELS = ['qwen2.5', 'qwen2.5:14b', 'llama3.1', 'llama3.1:8b', 'mistral', 'phi3.5', 'deepseek-r1']

export function LLMTab({ llm, update }) {
  const modelList = llm.provider === 'gemini' ? GEMINI_MODELS : OLLAMA_MODELS

  return (
    <div className="space-y-4">
      <SectionCard
        icon={Sparkles}
        title="Language model"
        description="Provider and model that reason over the dialogue"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Provider">
            <Select value={llm.provider} onChange={e => update({ provider: e.target.value })}>
              <option value="gemini">Gemini (Google)</option>
              <option value="ollama">Ollama (local)</option>
            </Select>
          </Field>
          <Field label="Model">
            <input type="text" value={llm.model}
              onChange={e => update({ model: e.target.value })}
              placeholder={llm.provider === 'gemini' ? 'gemini-2.5-flash' : 'qwen2.5'}
              className={inputCls} list="llm-models" />
            <datalist id="llm-models">
              {modelList.map(m => <option key={m} value={m} />)}
            </datalist>
          </Field>
          <NumberField label="Inference timeout" unit="s" min={10} max={300}
            value={llm.timeout} onChange={v => update({ timeout: v })} />
          <NumberField label="Concurrent connections"
            hint="LLM requests that can be in flight at the same time"
            min={1} max={16}
            value={llm.max_concurrent} onChange={v => update({ max_concurrent: v })} />
        </div>
        <ToggleField label="Silent mode" hint="Suppresses the LLM node logs in the console"
          value={llm.silent_mode} onChange={v => update({ silent_mode: v })} />
      </SectionCard>

      {llm.provider === 'gemini' ? (
        <SectionCard
          icon={Cloud}
          title="Gemini"
          description="Cloud service credentials"
        >
          <Field label="API Key"
            hint="If left empty the GEMINI_API_KEY environment variable is used">
            <input type="password" value={llm.gemini_api_key}
              onChange={e => update({ gemini_api_key: e.target.value })}
              placeholder="AIza…" autoComplete="off"
              className={inputCls} />
          </Field>
        </SectionCard>
      ) : (
        <SectionCard
          icon={HardDrive}
          title="Ollama"
          description="Local inference server"
        >
          <div className="grid grid-cols-2 gap-4">
            <Field label="Host">
              <input type="text" value={llm.ollama_host}
                onChange={e => update({ ollama_host: e.target.value })}
                placeholder="127.0.0.1" className={inputCls} />
            </Field>
            <NumberField label="Port" min={1} max={65535}
              value={llm.ollama_port} onChange={v => update({ ollama_port: v })} />
          </div>
          <div className="px-3 py-2.5 bg-brand-glow border border-brand-600/30 rounded-lg">
            <p className="text-xs text-brand-300/80">
              Ollama must be running at{' '}
              <span className="font-mono text-brand-400">{llm.ollama_host}:{llm.ollama_port}</span>{' '}
              with the model pulled (<span className="font-mono">ollama pull {llm.model || 'model'}</span>).
            </p>
          </div>
        </SectionCard>
      )}
    </div>
  )
}
