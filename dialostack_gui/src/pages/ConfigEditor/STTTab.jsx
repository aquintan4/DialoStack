/** STT tab: Whisper model, input audio capture and voice activity detection. */
import { AudioLines, Ear, Mic } from 'lucide-react'
import { Field, NumberField, SectionCard, Select, SliderField, ToggleField, inputCls } from '../../components/ui'

const STT_SIZES = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']
const STT_LANGS = ['es', 'en', 'fr', 'de', 'pt', 'ca', 'it']
const CPU_COMPUTES = ['int8', 'int8_float32', 'float32']
const CUDA_COMPUTES = ['float16', 'int8_float16', 'int8', 'float32']

export function STTTab({ stt, update }) {
  const computeTypes = stt.device === 'cuda' ? CUDA_COMPUTES : CPU_COMPUTES

  return (
    <div className="space-y-4">
      <SectionCard
        icon={Mic}
        title="Whisper model"
        description="Speech recognition (faster-whisper)"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Model size"
            hint="Larger = more accurate but slower. small is a good balance on CPU">
            <Select value={stt.model_size} onChange={e => update({ model_size: e.target.value })}>
              {STT_SIZES.map(s => <option key={s} value={s}>{s}</option>)}
            </Select>
          </Field>
          <Field label="Compute device">
            <Select value={stt.device}
              onChange={e => {
                const dev = e.target.value
                update({ device: dev, compute_type: dev === 'cuda' ? 'float16' : 'int8' })
              }}>
              <option value="cpu">CPU</option>
              <option value="cuda">GPU (CUDA)</option>
            </Select>
          </Field>
          <Field label="Compute type"
            hint="Numeric precision of the inference; int8 is the fastest on CPU">
            <Select value={stt.compute_type} onChange={e => update({ compute_type: e.target.value })}>
              {computeTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </Select>
          </Field>
          {stt.device === 'cpu' && (
            <NumberField label="CPU threads" min={1} max={16}
              value={stt.cpu_threads} onChange={v => update({ cpu_threads: v })} />
          )}
        </div>
      </SectionCard>

      <SectionCard
        icon={AudioLines}
        title="Input audio"
        description="Microphone and capture format"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="ASR language" hint="Two-letter ISO code (es, en, fr...)">
            <input type="text" value={stt.language}
              onChange={e => update({ language: e.target.value })}
              placeholder="es" className={inputCls} list="stt-langs" />
            <datalist id="stt-langs">
              {STT_LANGS.map(l => <option key={l} value={l} />)}
            </datalist>
          </Field>
          <Field label="Sample rate">
            <Select value={stt.sample_rate} onChange={e => update({ sample_rate: Number(e.target.value) })}>
              <option value={16000}>16000 Hz</option>
              <option value={22050}>22050 Hz</option>
              <option value={44100}>44100 Hz</option>
            </Select>
          </Field>
          <Field label="Input device"
            hint="Microphone name as reported by sounddevice. Empty = the system one">
            <input type="text" value={stt.input_device}
              onChange={e => update({ input_device: e.target.value })}
              placeholder="(default)" className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      <SectionCard
        icon={Ear}
        title="Voice activity detection (VAD)"
        description="When the user is considered to be speaking"
      >
        <SliderField
          label="VAD threshold"
          hint="Lower = more sensitive: detects voice more easily but with more false positives"
          value={stt.vad_threshold}
          onChange={v => update({ vad_threshold: v })}
          min={0.1} max={0.95} step={0.05} />
        <div className="grid grid-cols-2 gap-4">
          <NumberField label="Grace period" unit="s" min={0.1} max={3.0} step={0.1}
            hint="Silence that closes the phrase once voice has been detected"
            value={stt.grace_period} onChange={v => update({ grace_period: v })} />
          <NumberField label="Max phrase duration" unit="s" min={1} max={60} step={0.5}
            value={stt.max_phrase_secs} onChange={v => update({ max_phrase_secs: v })} />
        </div>
        <ToggleField label="Silent mode" hint="Suppresses the STT node logs in the console"
          value={stt.silent_mode} onChange={v => update({ silent_mode: v })} />
      </SectionCard>
    </div>
  )
}
