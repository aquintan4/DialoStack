/**
 * Application entry point: mounts the React tree and wires up the router and
 * the engine, ROS, config and browser audio context providers.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ROSProvider } from './contexts/ROSContext'
import { ConfigProvider } from './contexts/ConfigContext'
import { EngineProvider } from './contexts/EngineContext'
import { BrowserAudioProvider } from './contexts/BrowserAudioContext'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <EngineProvider>
        <ROSProvider>
          <ConfigProvider>
            <BrowserAudioProvider>
              <App />
            </BrowserAudioProvider>
          </ConfigProvider>
        </ROSProvider>
      </EngineProvider>
    </BrowserRouter>
  </React.StrictMode>
)
