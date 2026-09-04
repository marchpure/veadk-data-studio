import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig(() => {
  const apiTarget = process.env.VITE_API_URL || 'http://localhost:8000'

  const suppressUrls = process.env.FRONTEND_PORT ? {
    name: 'suppress-urls',
    configureServer(server: { printUrls: () => void }) {
      server.printUrls = () => {}
    }
  } : null

  return {
    plugins: [react(), suppressUrls].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
        "#": path.resolve(__dirname, "./src/features/openviking"),
        "@ov-server": path.resolve(__dirname, "./src/features/openviking/types/ov-server"),
      },
    },
    build: {
      // Let Vite bundle Tauri client APIs so dynamic imports resolve in production builds.
      rollupOptions: {},
    },
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        }
      }
    }
  }
})
