/**
 * Application entry point: mounts the React tree and wires up the router and
 * the engine, ROS, and config context providers.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ROSProvider } from './contexts/ROSContext'
import { ConfigProvider } from './contexts/ConfigContext'
import { EngineProvider } from './contexts/EngineContext'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <EngineProvider>
        <ROSProvider>
          <ConfigProvider>
            <App />
          </ConfigProvider>
        </ROSProvider>
      </EngineProvider>
    </BrowserRouter>
  </React.StrictMode>
)
