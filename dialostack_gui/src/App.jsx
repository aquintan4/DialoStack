/**
 * Root application component: sets up the sidebar, the routed pages, and the
 * shared dialogue timeline plus the "New task" drawer state lifted to the top.
 */
import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { EngineNotices } from './components/EngineNotices'
import { Monitor } from './pages/Monitor'
import { FrameBuilder } from './pages/FrameBuilder'
import { PromptsEditor } from './pages/PromptsEditor'
import { StrategiesEditor } from './pages/StrategiesEditor'
import { ConfigEditor } from './pages/ConfigEditor'
import { useDialogTimeline } from './hooks/useDialogTimeline'

export default function App() {
  // Lifted here so the timeline survives tab switches
  const timeline = useDialogTimeline()
  // "New task" drawer - lifted so it can be opened from the sidebar
  const [launchOpen, setLaunchOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden relative">
        {/* Watermark: the logo mark, large and desaturated to a faint gray so it
            brands every page without competing with the content (.watermark in
            index.css adapts it to the theme) */}
        <div
          aria-hidden
          className="absolute inset-0 flex flex-col items-center justify-center gap-6
            pointer-events-none select-none pr-48"
        >
          <img
            src="/logo-mark.png"
            alt=""
            className="watermark w-[60%] max-w-[560px]"
          />
          <img
            src="/logo-wordmark-white.png"
            alt=""
            className="watermark w-[38%] max-w-[360px]"
          />
        </div>
        <div className="relative h-full">
          <Routes>
            <Route path="/" element={<Navigate to="/monitor" replace />} />
            <Route
              path="/monitor"
              element={
                <Monitor
                  timeline={timeline}
                  launchOpen={launchOpen}
                  setLaunchOpen={setLaunchOpen}
                />
              }
            />
            <Route path="/builder" element={<FrameBuilder />} />
            <Route path="/prompts" element={<PromptsEditor />} />
            <Route path="/strategies" element={<StrategiesEditor />} />
            <Route path="/config" element={<ConfigEditor />} />
          </Routes>
        </div>
      </main>
      <EngineNotices />
    </div>
  )
}
