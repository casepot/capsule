/**
 * ES Module mock for node:child_process
 * Uses jest.unstable_mockModule() pattern
 */

import { jest } from '@jest/globals';
import { EventEmitter } from 'node:events';

export function createChildProcessMock() {
  const mockProcesses = new Map();
  
  const spawn = jest.fn((command, args, options) => {
    const mockProcess = new EventEmitter();
    mockProcess.stdout = new EventEmitter();
    mockProcess.stderr = new EventEmitter();
    mockProcess.stdin = {
      write: jest.fn(),
      end: jest.fn()
    };
    mockProcess.kill = jest.fn((signal) => {
      mockProcess.killed = true;
      // Emit 'exit' event, not 'close'
      mockProcess.emit('exit', signal === 'SIGKILL' ? 9 : 15, signal);
    });
    mockProcess.pid = Math.floor(Math.random() * 10000);
    mockProcess.killed = false;
    
    // Store for test access
    mockProcesses.set(mockProcess.pid, mockProcess);
    spawn.lastProcess = mockProcess;
    
    return mockProcess;
  });
  
  const execFileSync = jest.fn((command, args, options) => {
    if (command === 'which') {
      const cmd = args[0];
      
      // Check for shell metacharacters that indicate command injection
      const shellMetacharacters = /[;&|><`$()]/;
      if (shellMetacharacters.test(cmd)) {
        // 'which' would fail for commands with metacharacters
        throw new Error(`Command not found: ${cmd}`);
      }
      
      // Simulate command not found for unknown commands
      if (['claude', 'codex', 'gemini', 'npm', 'node'].includes(cmd)) {
        return Buffer.from(`/usr/local/bin/${cmd}`);
      }
      throw new Error(`Command not found: ${cmd}`);
    }
    return Buffer.from('');
  });
  
  const exec = jest.fn((command, options, callback) => {
    const cb = callback || options;
    const mockProcess = new EventEmitter();
    mockProcess.stdout = new EventEmitter();
    mockProcess.stderr = new EventEmitter();
    
    if (cb) {
      process.nextTick(() => cb(null, '', ''));
    }
    
    return mockProcess;
  });
  
  const execFile = jest.fn((file, args, options, callback) => {
    const cb = callback || options;
    const mockProcess = new EventEmitter();
    mockProcess.stdout = new EventEmitter();
    mockProcess.stderr = new EventEmitter();
    
    if (cb) {
      process.nextTick(() => cb(null, '', ''));
    }
    
    return mockProcess;
  });
  
  const fork = jest.fn((modulePath, args, options) => {
    const mockProcess = new EventEmitter();
    mockProcess.send = jest.fn();
    mockProcess.kill = jest.fn();
    mockProcess.pid = Math.floor(Math.random() * 10000);
    
    return mockProcess;
  });
  
  const execSync = jest.fn((command, options) => {
    return Buffer.from('');
  });
  
  const spawnSync = jest.fn((command, args, options) => {
    return {
      pid: Math.floor(Math.random() * 10000),
      output: [null, Buffer.from(''), Buffer.from('')],
      stdout: Buffer.from(''),
      stderr: Buffer.from(''),
      status: 0,
      signal: null,
      error: undefined
    };
  });
  
  return {
    spawn,
    execFileSync,
    exec,
    execFile,
    fork,
    execSync,
    spawnSync,
    // Utility methods for tests
    getProcess: (pid) => mockProcesses.get(pid),
    clearProcesses: () => mockProcesses.clear()
  };
}