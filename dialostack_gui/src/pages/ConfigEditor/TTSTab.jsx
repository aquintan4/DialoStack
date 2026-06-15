/** TTS tab: Piper voice model and output audio device settings. */
import { Speaker, Volume2 } from 'lucide-react'
import { Field, SectionCard, Select, inputCls } from '../../components/ui'

export function TTSTab({ tts, update }) {
  return (
    <div className="space-y-4">
      <SectionCard
        icon={Volume2}
        title="Piper voice"
        description="Neural speech synthesis model"
      >
        <Field label="ONNX model path"
          hint="Piper .onnx file. The .onnx.json must be in the same folder">
          <input type="text" value={tts.model_path}
            onChange={e => update({ model_path: e.target.value })}
            placeholder="/home/user/models/es_ES-sharvard-medium.onnx"
            className={inputCls} />
        </Field>
      </SectionCard>

      <SectionCard
        icon={Speaker}
        title="Output audio"
        description="Playback device and format"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Sample rate"
            hint="Must match the Piper model's (22050 for medium models)">
            <Select value={tts.sample_rate} onChange={e => update({ sample_rate: Number(e.target.value) })}>
              <option value={22050}>22050 Hz</option>
              <option value={16000}>16000 Hz</option>
              <option value={24000}>24000 Hz</option>
            </Select>
          </Field>
          <Field label="Audio device"
            hint="ALSA name of the speaker: default, hw:0,0, plughw:1,0...">
            <input type="text" value={tts.audio_device}
              onChange={e => update({ audio_device: e.target.value })}
              placeholder="default" className={inputCls} />
          </Field>
        </div>
      </SectionCard>
    </div>
  )
}
