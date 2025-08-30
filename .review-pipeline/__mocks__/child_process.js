import { jest } from '@jest/globals';
import { EventEmitter } from 'node:events';

// Create a mock spawn function
export const spawn = jest.fn(() => {
  const mockProcess = new EventEmitter();
  mockProcess.stdout = new EventEmitter();
  mockProcess.stderr = new EventEmitter();
  mockProcess.stdin = {
    write: jest.fn(),
    end: jest.fn()
  };
  mockProcess.kill = jest.fn();
  
  // Store the mock process for test access
  spawn.mockProcess = mockProcess;
  
  return mockProcess;
});

// Export other child_process functions as mocks if needed
export const exec = jest.fn();
export const execFile = jest.fn();
export const fork = jest.fn();
export const execSync = jest.fn();
export const execFileSync = jest.fn();
export const spawnSync = jest.fn();