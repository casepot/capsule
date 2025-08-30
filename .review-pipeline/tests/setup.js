/**
 * Test setup file for Jest with ES modules support
 * This file is loaded before each test suite
 */

import { jest } from '@jest/globals';
import { EventEmitter } from 'node:events';

// Set up global test utilities
globalThis.createMockProcess = () => {
  const mockProcess = new EventEmitter();
  
  mockProcess.stdout = new EventEmitter();
  mockProcess.stderr = new EventEmitter();
  mockProcess.stdin = {
    write: jest.fn(),
    end: jest.fn()
  };
  mockProcess.kill = jest.fn();
  mockProcess.pid = Math.floor(Math.random() * 10000);
  
  return mockProcess;
};

// Helper to create mock file system responses
globalThis.createMockFS = () => {
  return {
    readFile: jest.fn(),
    writeFile: jest.fn(),
    access: jest.fn(),
    mkdir: jest.fn(),
    rm: jest.fn(),
    stat: jest.fn()
  };
};

// Helper to create mock config loader responses
globalThis.createMockConfig = (overrides = {}) => {
  return {
    providers: {
      enabled: ['claude', 'codex', 'gemini'],
      ...overrides.providers
    },
    testing: {
      command: 'npm test',
      ...overrides.testing
    },
    security: {
      maxTimeout: 300000,
      ...overrides.security
    },
    ...overrides
  };
};

// Helper to create mock provider manifest
globalThis.createMockManifest = (provider = 'claude', overrides = {}) => {
  return {
    id: provider,
    name: `${provider.charAt(0).toUpperCase() + provider.slice(1)} Provider`,
    cli: {
      command: provider,
      arguments: [],
      ...overrides.cli
    },
    required_flags: {
      review: {
        flags: ['--output-format', 'json'],
        ...overrides.required_flags?.review
      },
      ...overrides.required_flags
    },
    detection: overrides.detection || [],
    ...overrides
  };
};

// Helper for async test utilities
globalThis.waitForEmit = (emitter, event, timeout = 1000) => {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Timeout waiting for event: ${event}`));
    }, timeout);
    
    emitter.once(event, (...args) => {
      clearTimeout(timer);
      resolve(args);
    });
  });
};

// Clear all mocks after each test
afterEach(() => {
  jest.clearAllMocks();
});