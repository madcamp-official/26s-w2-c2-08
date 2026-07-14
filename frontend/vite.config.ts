import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, '..', '')
  const apiHost = environment.APP_HOST || '127.0.0.1'
  const apiPort = environment.APP_PORT || '8000'

  return {
    plugins: [react()],
    envDir: '..',
    server: {
      proxy: {
        '/api': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: true,
      clearMocks: true,
      restoreMocks: true,
    },
  }
})
