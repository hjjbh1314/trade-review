import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 通过 /api 代理到 FastAPI，避免 CORS 和跨域
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8090',
        changeOrigin: true,
      },
    },
  },
})
