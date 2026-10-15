import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Same-origin /api/* → FastAPI (avoids browser CORS during `npm run dev`)
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '') || '/',
      },
      // FastAPI mounts repo `assets/` at /static (synth heroes, outputs)
      '/static': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Path U: FastAPI WebSocket war room (same host as Vite dev → upgrade to backend)
      '/ws': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
