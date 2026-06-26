/**
 * Monitor image viewer: a collapsible debug panel that renders frames from any
 * image topic on the graph (a lightweight, RViz-like peek). Not a core feature
 * of DialoStack - it exists to eyeball camera/vision topics while debugging.
 *
 * The user picks a topic from the ones currently advertised; CompressedImage is
 * shown via <img>, raw Image is decoded to a <canvas>. While hidden it neither
 * subscribes nor consumes bandwidth.
 */
import { useEffect, useRef, useState } from 'react'
import { Image as ImageIcon, RefreshCw, X } from 'lucide-react'
import { Select } from '../../components/ui'
import { useROS } from '../../contexts/ROSContext'
import { useImageTopics } from '../../hooks/useImageTopics'
import { useImageTopic } from '../../hooks/useImageTopic'

export function ImageViewer({ open, onClose, topicName, onTopicChange }) {
  const { status } = useROS()
  const { topics, loading, refresh } = useImageTopics()
  const canvasRef = useRef(null)
  // Natural dimensions of the current compressed frame (raw dims come from the hook).
  const [imgDims, setImgDims] = useState(null)

  const selected = topics.find((t) => t.name === topicName) || null
  const frame = useImageTopic(selected, { active: open, canvasRef })

  // Refresh the topic list every time the panel opens.
  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  if (!open) return null

  const connected = status === 'connected' || status === 'waiting'
  const width = selected?.kind === 'compressed' ? imgDims?.w : frame.width
  const height = selected?.kind === 'compressed' ? imgDims?.h : frame.height
  const hasFrame = selected?.kind === 'compressed' ? !!frame.src : frame.count > 0
  // The persisted topic may no longer be advertised: keep it selectable so the
  // selection is not silently dropped, but flag it.
  const missing = topicName && !selected

  return (
    <div className="w-80 border-l border-app-border bg-app-950/60 flex flex-col flex-shrink-0 overflow-hidden">

      {/* Header */}
      <div className="px-4 py-3 border-b border-app-border flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
          <ImageIcon size={13} className="text-brand-400" />
          Image topic
        </h2>
        <div className="flex items-center gap-1">
          <button
            onClick={refresh}
            title="Refresh topic list"
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-app-700 transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={onClose}
            title="Hide image viewer"
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-app-700 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Topic selector */}
      <div className="px-4 py-3 border-b border-app-border">
        <Select
          value={topicName || ''}
          onChange={(e) => onTopicChange(e.target.value)}
        >
          <option value="">{topics.length ? 'Select a topic...' : 'No image topics found'}</option>
          {missing && <option value={topicName}>{topicName} (not advertised)</option>}
          {topics.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name} {t.kind === 'compressed' ? '(compressed)' : '(raw)'}
            </option>
          ))}
        </Select>
      </div>

      {/* Image area */}
      <div className="flex-1 min-h-0 flex items-center justify-center p-3 bg-app-950">
        {!connected ? (
          <p className="text-xs text-slate-600 text-center">rosbridge not connected</p>
        ) : !selected ? (
          <p className="text-xs text-slate-600 text-center px-4">
            Pick an image topic to preview its frames.
          </p>
        ) : frame.error ? (
          <p className="text-xs text-red-400 text-center px-4">{frame.error}</p>
        ) : !hasFrame ? (
          <p className="text-xs text-slate-600 text-center px-4">
            Waiting for frames on <span className="font-mono break-all">{selected.name}</span>...
          </p>
        ) : null}

        {/* Both render targets stay mounted (hidden when unused) so the canvas
            ref exists before the first raw frame arrives. */}
        {selected?.kind === 'compressed' && frame.src && (
          <img
            src={frame.src}
            alt=""
            onLoad={(e) => setImgDims({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
            className="max-w-full max-h-full object-contain rounded"
          />
        )}
        <canvas
          ref={canvasRef}
          className={`max-w-full max-h-full object-contain rounded ${
            selected?.kind === 'raw' && hasFrame ? '' : 'hidden'
          }`}
        />
      </div>

      {/* Stats footer */}
      <div className="px-4 py-2 border-t border-app-border flex items-center justify-between text-[11px] text-slate-600 font-mono">
        <span>{width && height ? `${width}x${height}` : '-'}</span>
        <span>{selected ? `${frame.fps} fps` : ''}</span>
      </div>
    </div>
  )
}
