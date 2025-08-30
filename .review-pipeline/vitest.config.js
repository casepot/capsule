import { defineConfig } from 'vitest/config';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    testTimeout: 10000,
    include: ['tests/**/*.test.js'],
    exclude: ['node_modules', 'tests/fixtures', 'tests/mocks'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['tests/**', 'node_modules/**', 'coverage/**']
    },
    setupFiles: [],
    pool: 'forks',
    isolate: true
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './lib')
    }
  }
});