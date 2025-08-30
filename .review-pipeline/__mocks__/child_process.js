import { vi } from 'vitest';
import { EventEmitter } from 'node:events';

// Create a mock spawn function
export const spawn = vi.fn(() => {
  const mockProcess = new EventEmitter();
  mockProcess.stdout = new EventEmitter();
  mockProcess.stderr = new EventEmitter();
  mockProcess.stdin = {
    write: vi.fn(),
    end: vi.fn()
  };
  mockProcess.kill = vi.fn();
  
  // Store the mock process for test access
  spawn.mockProcess = mockProcess;
  
  return mockProcess;
});

// Export other child_process functions as mocks if needed
export const exec = vi.fn();
export const execFile = vi.fn();
export const fork = vi.fn();
export const execSync = vi.fn();
export const execFileSync = vi.fn();
export const spawnSync = vi.fn();