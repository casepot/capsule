import { jest } from '@jest/globals';
import ProviderExecutor from '../../lib/execute-provider.js';
import fs from 'node:fs/promises';
import { EventEmitter } from 'node:events';

// Mock modules - use manual mock for child_process
jest.mock('child_process', () => import('../../__mocks__/child_process.js'));
jest.mock('node:fs/promises');

// Import spawn after mocking
const { spawn } = await import('child_process');

// Mock CommandBuilder
jest.mock('../../lib/command-builder.js', () => {
  return jest.fn().mockImplementation(() => ({
    buildCommand: jest.fn()
  }));
});

describe('ProviderExecutor', () => {
  let executor;
  let mockProcess;
  
  beforeEach(() => {
    jest.clearAllMocks();
    
    // The mock spawn function already creates a mock process
    // We can access it via spawn.mockProcess after calling spawn()
    
    executor = new ProviderExecutor({
      verbose: false,
      dryRun: false
    });
  });

  describe('constructor', () => {
    it('should initialize with default options', () => {
      const exec = new ProviderExecutor();
      expect(exec.verbose).toBe(false);
      expect(exec.dryRun).toBe(false);
      expect(exec.commandBuilder).toBeDefined();
    });

    it('should accept custom options', () => {
      const exec = new ProviderExecutor({ 
        verbose: true,
        dryRun: true 
      });
      expect(exec.verbose).toBe(true);
      expect(exec.dryRun).toBe(true);
    });
  });

  describe('execute', () => {
    it('should execute provider command using spawn (not shell)', async () => {
      const mockCommand = {
        command: 'claude',
        args: ['--model', 'sonnet', '-p', 'Review this'],
        workingDirectory: '/tmp',
        env: { TEST: 'value' }
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude', {
        prompt: 'Review this'
      });
      
      // Simulate successful execution
      setImmediate(() => {
        mockProcess.emit('close', 0);
      });
      
      const result = await executePromise;
      
      // Verify spawn was called with proper arguments
      expect(spawn).toHaveBeenCalledWith(
        'claude',
        ['--model', 'sonnet', '-p', 'Review this'],
        expect.objectContaining({
          cwd: '/tmp',
          env: expect.objectContaining({ TEST: 'value' })
        })
      );
    });

    it('should not use shell execution to prevent injection', async () => {
      const mockCommand = {
        command: 'claude',
        args: ['-p', 'test; rm -rf /'], // Malicious input
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude', {
        prompt: 'test; rm -rf /'
      });
      
      setImmediate(() => {
        mockProcess.emit('close', 0);
      });
      
      await executePromise;
      
      // Verify shell: false or undefined (default)
      const spawnOptions = spawn.mock.calls[0][2];
      expect(spawnOptions.shell).toBeUndefined();
    });

    it('should handle process errors properly', async () => {
      const mockCommand = {
        command: 'claude',
        args: []
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      // Simulate error
      setImmediate(() => {
        mockProcess.emit('error', new Error('Command not found'));
      });
      
      await expect(executePromise).rejects.toThrow('Command not found');
    });

    it('should handle non-zero exit codes', async () => {
      const mockCommand = {
        command: 'claude',
        args: []
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      // Simulate non-zero exit
      setImmediate(() => {
        mockProcess.stderr.emit('data', Buffer.from('Error message'));
        mockProcess.emit('close', 1);
      });
      
      await expect(executePromise).rejects.toThrow();
    });

    it('should write stdin if provided', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        stdin: 'Input data'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      setImmediate(() => {
        mockProcess.emit('close', 0);
      });
      
      await executePromise;
      
      expect(mockProcess.stdin.write).toHaveBeenCalledWith('Input data');
      expect(mockProcess.stdin.end).toHaveBeenCalled();
    });

    it('should save output to file if specified', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        outputFile: '/tmp/output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      setImmediate(() => {
        mockProcess.stdout.emit('data', Buffer.from('{"result": "success"}'));
        mockProcess.emit('close', 0);
      });
      
      await executePromise;
      
      expect(fs.writeFile).toHaveBeenCalledWith(
        '/tmp/output.json',
        '{"result": "success"}'
      );
    });

    it('should respect timeout settings', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        timeout: 1000
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      // Don't emit close event, let it timeout
      jest.useFakeTimers();
      
      setTimeout(() => {
        mockProcess.emit('close', 0);
      }, 2000);
      
      jest.runAllTimers();
      
      // The promise should handle timeout appropriately
      await expect(executePromise).resolves.toBeDefined();
      
      jest.useRealTimers();
    });

    it('should handle dry-run mode', async () => {
      executor.dryRun = true;
      
      const mockCommand = {
        command: 'claude',
        args: ['--model', 'sonnet']
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const result = await executor.execute('claude');
      
      // Should not actually spawn process in dry-run
      expect(spawn).not.toHaveBeenCalled();
    });

    it('should throw error if provider is disabled', async () => {
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(null);
      
      await expect(executor.execute('disabled-provider'))
        .rejects.toThrow('Provider disabled-provider is disabled or not configured');
    });
  });

  describe('security', () => {
    it('should pass environment variables from command builder', async () => {
      // Note: Environment sanitization happens in shell scripts (run-provider-review.sh)
      // not in the executor itself. This test verifies the executor passes env correctly.
      const mockCommand = {
        command: 'claude',
        args: [],
        env: {
          SAFE_VAR: 'value',
          REVIEW_CONTEXT: 'pr-review',
          WORKSPACE_DIR: '/tmp/workspace'
        }
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      setImmediate(() => {
        mockProcess.emit('close', 0);
      });
      
      await executePromise;
      
      const spawnEnv = spawn.mock.calls[0][2].env;
      expect(spawnEnv.SAFE_VAR).toBe('value');
      expect(spawnEnv.REVIEW_CONTEXT).toBe('pr-review');
      expect(spawnEnv.WORKSPACE_DIR).toBe('/tmp/workspace');
    });

    it('should prevent path traversal in output files', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        outputFile: '../../../etc/passwd' // Malicious path
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      setImmediate(() => {
        mockProcess.stdout.emit('data', Buffer.from('malicious content'));
        mockProcess.emit('close', 0);
      });
      
      // Should either throw or sanitize the path
      await expect(executePromise).rejects.toThrow();
    });
  });
});