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
  testTimeout: 10000
};