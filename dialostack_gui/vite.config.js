import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In dev mode, /api/* is proxied to the Python API server (gui.sh starts it on 5175).
    proxy: {
      '/api': 'http://localhost:5175',
    },
  },
})
