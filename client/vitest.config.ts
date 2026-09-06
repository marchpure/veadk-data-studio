import { defineConfig, mergeConfig } from 'vitest/config'

import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig({ command: 'serve', mode: 'test' }),
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/features/openviking/**/*.test.{ts,tsx}'],
      setupFiles: ['src/features/openviking/test-setup.ts'],
    },
  }),
)
