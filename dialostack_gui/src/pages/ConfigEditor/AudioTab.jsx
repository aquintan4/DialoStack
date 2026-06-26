/** Audio tab: routing "flavour" — local mic/speaker vs ROS topics (AudioChunk). */
import { Radio, Waypoints } from 'lucide-react'
import { Field, NumberField, SectionCard, Select, inputCls } from '../../components/ui'

export function AudioTab({ audio, update }) {
  const isTopic = audio.mode === 'topic'

  return (
    <div className="space-y-4">
      <SectionCard
        icon={Radio}
        title="Audio routing"
        description="Where speech is captured and played back"
      >
        <Field
          label="Routing mode"
          hint="Local uses this machine's microphone and speaker. Topic exchanges
            raw audio over ROS (AudioChunk), so a robot plays/captures the sound."
        >
          <Select value={audio.mode} onChange={e => update({ mode: e.target.value })}>
            <option value="local">Local hardware (mic + speaker)</option>
            <option value="topic">ROS topics (AudioChunk)</option>
          </Select>
        </Field>

        {isTopic ? (
          <p className="text-xs text-slate-500 leading-relaxed">
            STT reads audio from the input topic and TTS publishes to the output
            topic. On the robot, run the bridge to map its mic/speaker to these
            topics:
            <span className="block mt-1 font-mono text-[11px] text-slate-400">
              ros2 launch speech_io audio_bridge.launch.py
            </span>
            Any node that produces/consumes AudioChunk on these topics works too;
            no bridge needed in that case.
          </p>
        ) : (
          <p className="text-xs text-slate-500 leading-relaxed">
            The STT input device and the TTS audio device (in their tabs) select
            the local hardware used.
          </p>
        )}
      </SectionCard>

      {isTopic && (
        <SectionCard
          icon={Waypoints}
          title="ROS topics"
          description="AudioChunk contract topics"
        >
          <div className="grid grid-cols-2 gap-4">
            <Field label="Input topic" hint="Mic audio in: bridge/robot -> STT">
              <input type="text" value={audio.in_topic}
                onChange={e => update({ in_topic: e.target.value })}
                placeholder="/audio_in" className={inputCls} />
            </Field>
            <Field label="Output topic" hint="Synthesized audio out: TTS -> bridge/robot">
              <input type="text" value={audio.out_topic}
                onChange={e => update({ out_topic: e.target.value })}
                placeholder="/audio_out" className={inputCls} />
            </Field>
          </div>
          <NumberField
            label="Topic latency pad" unit="s" min={0.0} max={5.0} step={0.1}
            hint="Extra seconds /is_speaking stays True after publishing, to cover
              network and playback delay on the remote speaker. Higher = safer
              turn-taking but a longer pause before listening again."
            value={audio.topic_latency_pad}
            onChange={v => update({ topic_latency_pad: v })} />
        </SectionCard>
      )}
    </div>
  )
}
