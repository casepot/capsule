export default {
  testEnvironment: 'node',
  transform: {},
  testMatch: [
    '**/tests/**/*.test.js',
    '**/test/**/*.test.js'
  ],
  collectCoverageFrom: [
    'lib/**/*.js',
    'scripts/**/*.js',
    '!**/node_modules/**',
    '!**/test/**',
    '!**/tests/**'
  ],
  verbose: true,
  testTimeout: 10000,
  coverageThreshold: {
    global: {
      branches: 10,
      functions: 20,
      lines: 10,
      statements: 10
    }
  }
};