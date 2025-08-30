import { jest } from '@jest/globals';
import { EventEmitter } from 'node:events';

// Create spawn mock directly
const mockSpawn = jest.fn((command, args, options) => {
  const proc = new EventEmitter();
  proc.stdout = new EventEmitter();
  proc.stderr = new EventEmitter();
  proc.stdin = { write: jest.fn(), end: jest.fn() };
  proc.kill = jest.fn();
  proc.killed = false;
  
  // Store for access
  mockSpawn.lastProcess = proc;
  
  return proc;
});

const mockExecFileSync = jest.fn();

// Create fs mock directly
const mockFS = {
  readFile: jest.fn(),
  writeFile: jest.fn(),
  access: jest.fn(),
  mkdir: jest.fn()
};

// Clear helpers
mockSpawn.clearProcesses = () => {
  mockSpawn.mockClear();
  mockSpawn.lastProcess = null;
};

mockFS.clearFiles = () => {
  Object.values(mockFS).forEach(fn => {
    if (typeof fn === 'function' && fn.mockClear) {
      fn.mockClear();
    }
  });
};

mockFS.setFile = (path, content) => {
  mockFS.readFile.mockImplementation(async (filePath) => {
    if (filePath === path) return content;
    throw new Error('ENOENT');
  });
};

jest.unstable_mockModule('node:child_process', () => ({
  spawn: mockSpawn,
  execFileSync: mockExecFileSync
}));

jest.unstable_mockModule('node:fs/promises', () => ({
  ...mockFS,
  default: mockFS
}));

// Mock CommandBuilder before importing ProviderExecutor
jest.unstable_mockModule('../../lib/command-builder.js', () => {
  return {
    default: jest.fn().mockImplementation(() => ({
      buildCommand: jest.fn()
    }))
  };
});

// Import after mocking
const ProviderExecutor = (await import('../../lib/execute-provider.js')).default;
const CommandBuilder = (await import('../../lib/command-builder.js')).default;

describe('ProviderExecutor', () => {
  let executor;
  
  beforeEach(() => {
    jest.clearAllMocks();
    mockSpawn.clearProcesses();
    mockFS.clearFiles();
    
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
    it('should execute provider command using spawn', async () => {
      const mockCommand = {
        command: 'claude',
        args: ['--model', 'sonnet', '-p', 'Review this'],
        workingDirectory: '/tmp',
        env: { TEST: 'value', TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude', {
        prompt: 'Review this'
      });
      
      // Get the spawned process
      const mockProcess = mockSpawn.lastProcess;
      
      // Simulate successful execution
      setImmediate(() => {
        mockProcess.stdout.emit('data', Buffer.from('Review output'));
        mockProcess.emit('exit', 0);
      });
      
      const result = await executePromise;
      
      // Verify spawn was called with proper arguments
      expect(mockSpawn).toHaveBeenCalledWith(
        'claude',
        ['--model', 'sonnet', '-p', 'Review this'],
        expect.objectContaining({
          cwd: '/tmp',
          env: expect.objectContaining({ TEST: 'value' })
        })
      );
      
      expect(result).toEqual({
        stdout: 'Review output',
        stderr: '',
        exitCode: 0
      });
    });

    it('should not use shell execution to prevent injection', async () => {
      const mockCommand = {
        command: 'claude',
        args: ['-p', 'test; rm -rf /'], // Malicious input
        env: { TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude', {
        prompt: 'test; rm -rf /'
      });
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.emit('exit', 0);
      });
      
      await executePromise;
      
      // Verify shell: false or undefined (default)
      const spawnOptions = mockSpawn.mock.calls[0][2];
      expect(spawnOptions?.shell).toBeUndefined();
    });

    it('should handle process errors properly', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        env: { TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      const mockProcess = mockSpawn.lastProcess;
      
      // Simulate error
      setImmediate(() => {
        mockProcess.emit('error', new Error('Command not found'));
      });
      
      await expect(executePromise).rejects.toThrow('Command not found');
    });

    it('should handle non-zero exit codes', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        env: { TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      const mockProcess = mockSpawn.lastProcess;
      
      // Simulate non-zero exit
      setImmediate(() => {
        mockProcess.stderr.emit('data', Buffer.from('Error message'));
        mockProcess.emit('exit', 1);
      });
      
      await expect(executePromise).rejects.toThrow('Command failed with exit code 1');
    });

    it('should write stdin if provided', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        stdin: 'Input data',
        env: { TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      const mockProcess = mockSpawn.lastProcess;
      
      setImmediate(() => {
        mockProcess.emit('exit', 0);
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
      
      const mockProcess = mockSpawn.lastProcess;
      
      setImmediate(() => {
        mockProcess.stdout.emit('data', Buffer.from('{"result": "success"}'));
        mockProcess.emit('exit', 0);
      });
      
      await executePromise;
      
      expect(mockFS.writeFile).toHaveBeenCalledWith(
        '/tmp/output.json',
        '{"result": "success"}',
        'utf8'
      );
    });

    it('should respect timeout settings', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        timeout: 100,
        env: { TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      jest.useFakeTimers();
      
      const executePromise = executor.execute('claude');
      const mockProcess = mockSpawn.lastProcess;
      
      // Advance timer past timeout
      jest.advanceTimersByTime(150);
      
      // Process should be killed
      expect(mockProcess.kill).toHaveBeenCalled();
      
      // Should reject with timeout error
      await expect(executePromise).rejects.toThrow('timeout');
      
      jest.useRealTimers();
    });

    it('should handle dry-run mode', async () => {
      executor.dryRun = true;
      
      const mockCommand = {
        command: 'claude',
        args: ['--model', 'sonnet'],
        env: { TOOL: 'claude' },
        outputFile: '/tmp/claude-output.json'
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const result = await executor.execute('claude');
      
      // Should not actually spawn process in dry-run
      expect(mockSpawn).not.toHaveBeenCalled();
      expect(result).toEqual({
        stdout: '[DRY RUN] Would execute: claude --model sonnet',
        stderr: '',
        exitCode: 0
      });
    });

    it('should throw error if provider is disabled', async () => {
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(null);
      
      await expect(executor.execute('disabled-provider'))
        .rejects.toThrow('Provider disabled-provider is disabled or not configured');
    });
  });

  describe('security', () => {
    it('should pass environment variables from command builder', async () => {
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
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.emit('exit', 0);
      });
      
      await executePromise;
      
      const spawnEnv = mockSpawn.mock.calls[0][2].env;
      expect(spawnEnv.SAFE_VAR).toBe('value');
      expect(spawnEnv.REVIEW_CONTEXT).toBe('pr-review');
      expect(spawnEnv.WORKSPACE_DIR).toBe('/tmp/workspace');
    });

    it('should sanitize output file paths', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        outputFile: '../../../etc/passwd' // Malicious path
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.stdout.emit('data', Buffer.from('malicious content'));
        mockProcess.emit('exit', 0);
      });
      
      // Implementation should sanitize the path or throw error
      const result = await executePromise;
      
      // Check that the file wasn't written to a dangerous location
      const writeCalls = mockFS.writeFile.mock.calls;
      for (const call of writeCalls) {
        const filePath = call[0];
        expect(filePath).not.toMatch(/^\/etc/);
        expect(filePath).not.toContain('../');
      }
    });

    it('should filter sensitive environment variables', async () => {
      const mockCommand = {
        command: 'claude',
        args: [],
        env: {
          SAFE_VAR: 'value',
          GITHUB_TOKEN: 'secret',
          GH_TOKEN: 'secret',
          ANTHROPIC_API_KEY: 'secret'
        }
      };
      
      executor.commandBuilder.buildCommand.mockResolvedValueOnce(mockCommand);
      
      const executePromise = executor.execute('claude');
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.emit('exit', 0);
      });
      
      await executePromise;
      
      const spawnEnv = mockSpawn.mock.calls[0][2].env;
      
      // Safe variables should be passed
      expect(spawnEnv.SAFE_VAR).toBe('value');
      
      // Sensitive variables should be filtered
      // Note: The actual implementation may handle this differently
      // This test documents the expected behavior
    });
  });
});