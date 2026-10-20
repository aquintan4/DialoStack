/** LLM tab: provider/model selection plus Gemini, Claude, OpenAI or Ollama connection settings. */
import { Cloud, HardDrive, KeyRound, Sparkles } from 'lucide-react'
import { Field, NumberField, SectionCard, Select, ToggleField, inputCls } from '../../components/ui'

// Suggested models per provider; the first one is the default (same as server.py DEFAULT_LLM_MODELS).
const MODELS = {
  gemini: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
  claude: ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-fable-5-1'],
  openai: ['gpt-6-luna', 'gpt-6.1-sol', 'gpt-6-astra'],
  ollama: ['qwen2.5', 'qwen3.5:9b', 'qwen3.5:4b', 'qwen2.5:14b', 'llama3.1', 'llama3.1:8b', 'mistral', 'phi3.5', 'deepseek-r1'],
}
const CLAUDE_EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max']
const OPENAI_EFFORTS = ['none', 'low', 'medium', 'high', 'xhigh', 'max']

export function LLMTab({ llm, update }) {
  const modelList = MODELS[llm.provider] || MODELS.gemini

  // A model name only makes sense for its own provider: switch to the new default.
  function changeProvider(provider) {
    update({ provider, model: (MODELS[provider] || MODELS.gemini)[0] })
  }

  return (
    <div className="space-y-4">
      <SectionCard
        icon={Sparkles}
        title="Language model"
        description="Provider and model that reason over the dialogue"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Provider">
            <Select value={llm.provider} onChange={e => changeProvider(e.target.value)}>
              <option value="gemini">Gemini (Google)</option>
              <option value="claude">Claude (Anthropic)</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (local)</option>
            </Select>
          </Field>
          <Field label="Model">
            <input type="text" value={llm.model}
              onChange={e => update({ model: e.target.value })}
              placeholder={modelList[0]}
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

      {llm.provider === 'claude' && (
        <SectionCard
          icon={KeyRound}
          title="Claude"
          description="Claude API credentials"
        >
          <div className="grid grid-cols-2 gap-4">
            <Field label="API Key"
              hint="A Claude API key from console.anthropic.com (a Claude.ai subscription does not include API access). If left empty the ANTHROPIC_API_KEY environment variable is used">
              <input type="password" value={llm.claude_api_key ?? ''}
                onChange={e => update({ claude_api_key: e.target.value })}
                placeholder="sk-ant-…" autoComplete="off"
                className={inputCls} />
            </Field>
            <Field label="Effort"
              hint="How much the model thinks before answering. Low keeps spoken replies fast">
              <Select value={llm.claude_effort ?? 'low'} onChange={e => update({ claude_effort: e.target.value })}>
                {CLAUDE_EFFORTS.map(e => <option key={e} value={e}>{e}</option>)}
              </Select>
            </Field>
          </div>
        </SectionCard>
      )}

      {llm.provider === 'openai' && (
        <SectionCard
          icon={KeyRound}
          title="OpenAI"
          description="OpenAI API credentials, or any OpenAI-compatible server"
        >
          <div className="grid grid-cols-2 gap-4">
            <Field label="API Key"
              hint="An API key from platform.openai.com. If left empty the OPENAI_API_KEY environment variable is used">
              <input type="password" value={llm.openai_api_key ?? ''}
                onChange={e => update({ openai_api_key: e.target.value })}
                placeholder="sk-…" autoComplete="off"
                className={inputCls} />
            </Field>
            <Field label="Reasoning effort"
              hint="How much the model reasons before answering. None keeps spoken replies fast">
              <Select value={llm.openai_reasoning_effort ?? 'none'}
                onChange={e => update({ openai_reasoning_effort: e.target.value })}>
                {OPENAI_EFFORTS.map(e => <option key={e} value={e}>{e}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Base URL"
            hint="Optional. An OpenAI-compatible server (vLLM, LM Studio, OpenRouter…). Empty uses api.openai.com">
            <input type="text" value={llm.openai_base_url ?? ''}
              onChange={e => update({ openai_base_url: e.target.value })}
              placeholder="https://api.openai.com/v1" className={inputCls} />
          </Field>
        </SectionCard>
      )}

      {llm.provider === 'gemini' && (
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
      )}

      {llm.provider === 'ollama' && (
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
          <ToggleField label="Thinking"
            hint="Let reasoning models (qwen3.5, deepseek-r1…) think before answering. Slower; leave off for spoken dialogue"
            value={llm.ollama_think ?? false} onChange={v => update({ ollama_think: v })} />
          <div className="px-3 py-2.5 bg-app-950 border border-app-border rounded">
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
