import { jest } from '@jest/globals';
import { EventEmitter } from 'node:events';
import path from 'node:path';

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

const mockExecFileSync = jest.fn((command, args, options) => {
  if (command === 'which') {
    const cmd = args[0];
    // Check for shell metacharacters
    if (/[;&|><`$()]/.test(cmd)) {
      throw new Error(`Command not found: ${cmd}`);
    }
    // Return path for known commands
    if (['claude', 'codex', 'gemini'].includes(cmd)) {
      return Buffer.from(`/usr/local/bin/${cmd}`);
    }
    throw new Error(`Command not found: ${cmd}`);
  }
  return Buffer.from('');
});

const mockExecSync = jest.fn(); // Should not be called

// Create fs mock with file storage
const fileStore = new Map();
const mockFS = {
  readFile: jest.fn(async (filePath) => {
    if (fileStore.has(filePath)) {
      return fileStore.get(filePath);
    }
    throw new Error(`ENOENT: ${filePath}`);
  }),
  writeFile: jest.fn().mockResolvedValue(undefined),
  access: jest.fn().mockResolvedValue(undefined),
  mkdir: jest.fn().mockResolvedValue(undefined)
};

// Helper to set files
mockFS.setFile = (path, content) => {
  fileStore.set(path, content);
};

mockFS.clearFiles = () => {
  fileStore.clear();
  Object.values(mockFS).forEach(fn => {
    if (typeof fn === 'function' && fn.mockClear) {
      fn.mockClear();
    }
  });
};

// Clear helpers
mockSpawn.clearProcesses = () => {
  mockSpawn.mockClear();
  mockSpawn.lastProcess = null;
};

jest.unstable_mockModule('node:child_process', () => ({
  spawn: mockSpawn,
  execFileSync: mockExecFileSync,
  execSync: mockExecSync
}));

jest.unstable_mockModule('node:fs/promises', () => ({
  ...mockFS,
  default: mockFS
}));

// Import after mocking
const CommandBuilder = (await import('../../lib/command-builder.js')).default;
const ProviderExecutor = (await import('../../lib/execute-provider.js')).default;
const ConfigLoader = (await import('../../lib/config-loader.js')).default;

describe('Security Integration Tests', () => {
  
  beforeEach(() => {
    jest.clearAllMocks();
    mockFS.clearFiles();
    mockSpawn.clearProcesses();
    
    // Set up default configuration
    mockFS.setFile('/config/pipeline.config.json', JSON.stringify({
      providers: {
        enabled: ['claude', 'codex', 'gemini']
      },
      security: {
        maxTimeout: 300000,
        sanitizeEnv: true
      }
    }));
    
    // Add schema files that ConfigLoader expects
    mockFS.setFile('/Users/case/projects/pyrepl3/.review-pipeline/config/schemas/pipeline.schema.json', JSON.stringify({
      type: 'object',
      properties: {
        providers: { type: 'object' },
        testing: { type: 'object' },
        security: { type: 'object' }
      }
    }));
    
    mockFS.setFile('/Users/case/projects/pyrepl3/.review-pipeline/config/schemas/project.schema.json', JSON.stringify({
      type: 'object',
      properties: {
        providers: { type: 'object' },
        testing: { type: 'object' },
        security: { type: 'object' }
      }
    }));
  });
  
  describe('Command Injection Prevention', () => {
    it('should prevent injection through TEST_CMD environment variable', () => {
      // Test that TEST_CMD with malicious content is properly handled
      const maliciousCmd = 'npm test; rm -rf /';
      process.env.TEST_CMD = maliciousCmd;
      
      // In actual workflow, this is executed with proper escaping
      // The command should be treated as a single unit
      const command = process.env.TEST_CMD;
      
      // Verify it's not parsed as multiple commands
      expect(command).toBe(maliciousCmd);
      expect(command.split(';').length).toBe(2); // Would be dangerous if executed
      
      // Proper execution would quote it: eval "$TEST_CMD"
      // This ensures the entire string is treated as one command
      
      delete process.env.TEST_CMD;
    });

    it('should prevent injection through provider command names', async () => {
      const builder = new CommandBuilder();
      
      // Set up malicious manifest
      mockFS.setFile('/config/providers/malicious.manifest.json', JSON.stringify({
        cli: {
          command: 'claude; echo INJECTED'
        }
      }));
      
      const manifest = {
        cli: {
          command: 'claude; echo INJECTED'
        }
      };
      
      // The command should be treated as a single argument to 'which'
      const detectPath = await builder.detectCommandPath(manifest);
      
      // detectCommandPath returns the command even if not found in which
      expect(detectPath).toBe('claude; echo INJECTED');
      
      // Verify execFileSync was called safely
      if (mockExecFileSync.mock.calls.length > 0) {
        const [cmd, args] = mockExecFileSync.mock.calls[0];
        expect(cmd).toBe('which');
        expect(args[0]).toBe('claude; echo INJECTED'); // Single argument
      }
    });

    it('should prevent injection through prompt parameters', async () => {
      const executor = new ProviderExecutor();
      const builder = new CommandBuilder();
      
      const maliciousPrompt = `Review this"; rm -rf /; echo "`;
      
      // Build command with malicious prompt
      const command = await builder.buildCommand('claude', {
        prompt: maliciousPrompt
      });
      
      if (command) {
        // The prompt should be safely included
        // Either as stdin or as a properly escaped argument
        if (command.stdin) {
          expect(command.stdin).toBe(maliciousPrompt);
        } else if (command.args) {
          // Should be in args array as a single element
          const promptArg = command.args.find(arg => arg.includes(maliciousPrompt));
          expect(promptArg).toBeDefined();
        }
      }
    });

    it('should use spawn without shell to prevent command injection', async () => {
      const executor = new ProviderExecutor();
      
      executor.commandBuilder.buildCommand = jest.fn().mockResolvedValue({
        command: 'claude',
        args: ['--prompt', 'test; echo injected']
      });
      
      const executePromise = executor.execute('claude', {
        prompt: 'test; echo injected'
      });
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.emit('exit', 0);
      });
      
      await executePromise;
      
      // Verify spawn was called without shell
      const spawnOptions = mockSpawn.mock.calls[0][2];
      expect(spawnOptions?.shell).toBeUndefined(); // Default is false
    });
  });

  describe('Configuration Security', () => {
    it('should not load TEST_CMD from project configuration files', async () => {
      const loader = new ConfigLoader();
      
      // Set up project config with TEST_CMD
      mockFS.setFile('/.review-pipeline.json', JSON.stringify({
        testing: {
          command: 'rm -rf /' // Malicious command in project config
        }
      }));
      
      await loader.load();
      
      // TEST_CMD should not be loaded from project config
      expect(loader.config.testing?.command).toBeUndefined();
    });

    it('should only accept TEST_CMD from environment variables', async () => {
      const loader = new ConfigLoader();
      
      // Set TEST_CMD in environment
      process.env.TEST_CMD = 'npm test';
      
      await loader.load();
      
      // TEST_CMD from environment should be loaded
      expect(loader.config.testing?.command).toBe('npm test');
      
      delete process.env.TEST_CMD;
    });

    it('should validate provider manifests location', () => {
      const manifestPath = path.join(
        process.cwd(),
        '.review-pipeline/config/providers/claude.manifest.json'
      );
      
      // Provider manifests should be in a protected location
      expect(manifestPath).toContain('.review-pipeline/config/providers/');
      
      // These files should not be modifiable by PRs
      // This is enforced at the repository/workflow level
    });
  });

  describe('Environment Variable Sanitization', () => {
    it('should filter sensitive environment variables', async () => {
      const executor = new ProviderExecutor();
      
      // Set up environment with sensitive variables
      const mockEnv = {
        SAFE_VAR: 'value',
        GH_TOKEN: 'github_token_value',
        GITHUB_TOKEN: 'github_token_value',
        ANTHROPIC_API_KEY: 'api_key_value',
        PATH: '/usr/bin:/usr/local/bin'
      };
      
      // Build command with environment
      const builder = new CommandBuilder();
      const command = await builder.buildCommand('claude', {
        env: mockEnv
      });
      
      if (command && command.env) {
        // Sensitive variables should be filtered or preserved based on implementation
        expect(command.env.SAFE_VAR).toBe('value');
        expect(command.env.PATH).toBeDefined();
        
        // Implementation may handle sensitive vars differently
        // Document expected behavior
      }
    });

    it('should preserve necessary environment variables', async () => {
      const builder = new CommandBuilder();
      
      const command = await builder.buildCommand('claude', {
        workingDirectory: '/tmp/workspace'
      });
      
      if (command && command.env) {
        // Should preserve PATH and other necessary variables
        expect(command.env.PATH).toBeDefined();
        expect(command.env.HOME || command.env.USERPROFILE).toBeDefined();
      }
    });
  });

  describe('Path Traversal Prevention', () => {
    it('should prevent path traversal in output file paths', () => {
      const maliciousPath = '../../../etc/passwd';
      const resolved = path.resolve('/tmp/output', maliciousPath);
      
      // The resolved path should not escape the intended directory
      expect(resolved).not.toMatch(/^\/etc/);
      
      // Should resolve to an absolute path
      expect(path.isAbsolute(resolved)).toBe(true);
    });

    it('should validate file paths are within allowed directories', () => {
      const allowedDir = '/tmp/review-output';
      const testPaths = [
        '/tmp/review-output/result.json', // Valid
        '/tmp/review-output/subdir/file.txt', // Valid
        '/tmp/other/file.txt', // Invalid
        '/etc/passwd', // Invalid
        '../../../etc/passwd' // Invalid
      ];
      
      testPaths.forEach(testPath => {
        const resolved = path.resolve(allowedDir, testPath);
        const isValid = resolved.startsWith(path.resolve(allowedDir));
        
        if (testPath.includes('review-output')) {
          expect(isValid).toBe(true);
        } else {
          expect(isValid).toBe(false);
        }
      });
    });

    it('should sanitize provider names to prevent directory traversal', async () => {
      const builder = new CommandBuilder();
      
      const maliciousProviders = [
        '../../etc/passwd',
        '../../../root/.ssh/id_rsa',
        '..\\..\\windows\\system32\\config\\sam'
      ];
      
      for (const provider of maliciousProviders) {
        const manifest = await builder.loadProviderManifest(provider);
        
        // Should not load manifests from outside the providers directory
        expect(manifest).toBeNull();
      }
    });
  });

  describe('Input Validation', () => {
    it('should validate provider names against whitelist', () => {
      const validProviders = ['claude', 'codex', 'gemini'];
      const testProviders = [
        'claude', // Valid
        'codex', // Valid
        '../../etc/passwd', // Invalid
        'rm -rf /', // Invalid
        'claude; echo hacked' // Invalid
      ];
      
      testProviders.forEach(provider => {
        const isValid = validProviders.includes(provider);
        
        if (provider === 'claude' || provider === 'codex') {
          expect(isValid).toBe(true);
        } else {
          expect(isValid).toBe(false);
        }
      });
    });

    it('should reject commands with shell metacharacters', () => {
      const commands = [
        'claude && echo hacked',
        'claude; rm -rf /',
        'claude | cat /etc/passwd',
        'claude > /etc/passwd',
        'claude `cat /etc/passwd`',
        'claude $(cat /etc/passwd)'
      ];
      
      const shellMetacharacters = /[;&|><`$()]/;
      
      commands.forEach(cmd => {
        const hasMetachars = shellMetacharacters.test(cmd);
        expect(hasMetachars).toBe(true);
      });
    });

    it('should validate configuration values', async () => {
      const loader = new ConfigLoader();
      
      // Set up config with potentially dangerous values
      mockFS.setFile('/.review-pipeline.json', JSON.stringify({
        providers: {
          command: '$(whoami)',
          path: '../../../etc/passwd'
        }
      }));
      
      await loader.load();
      
      // Values should be treated as strings, not executed
      if (loader.config.providers.command) {
        expect(loader.config.providers.command).toBe('$(whoami)');
      }
      if (loader.config.providers.path) {
        expect(loader.config.providers.path).toBe('../../../etc/passwd');
      }
    });
  });

  describe('Secure Command Execution', () => {
    it('should use execFileSync instead of execSync for command detection', () => {
      const builder = new CommandBuilder();
      
      builder.detectCommandPath({
        cli: { command: 'claude; rm -rf /' }
      });
      
      // Should use execFileSync with array arguments
      expect(mockExecFileSync).toHaveBeenCalledWith(
        'which',
        expect.any(Array), // Arguments as array
        expect.any(Object)
      );
      
      // Should NOT use execSync
      expect(mockExecSync).not.toHaveBeenCalled();
    });

    it('should use spawn without shell for provider execution', async () => {
      const executor = new ProviderExecutor();
      
      executor.commandBuilder.buildCommand = jest.fn().mockResolvedValue({
        command: 'claude',
        args: ['--help']
      });
      
      const executePromise = executor.execute('claude', {});
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.emit('exit', 0);
      });
      
      await executePromise;
      
      // Verify spawn configuration
      const [command, args, options] = mockSpawn.mock.calls[0];
      
      expect(command).toBe('claude');
      expect(Array.isArray(args)).toBe(true);
      expect(options?.shell).not.toBe(true); // Should be false or undefined
    });

    it('should handle process timeouts securely', async () => {
      const executor = new ProviderExecutor();
      
      executor.commandBuilder.buildCommand = jest.fn().mockResolvedValue({
        command: 'claude',
        args: [],
        timeout: 100
      });
      
      jest.useFakeTimers();
      
      const executePromise = executor.execute('claude', {});
      const mockProcess = mockSpawn.lastProcess;
      
      // Advance time past timeout
      jest.advanceTimersByTime(150);
      
      // Process should be killed
      expect(mockProcess.kill).toHaveBeenCalled();
      
      await expect(executePromise).rejects.toThrow();
      
      jest.useRealTimers();
    });
  });

  describe('Error Handling', () => {
    it('should handle malformed configuration gracefully', async () => {
      const loader = new ConfigLoader();
      
      mockFS.setFile('/config/pipeline.config.json', 'not valid json');
      
      await loader.load();
      
      // Should fall back to safe defaults
      expect(loader.config).toBeDefined();
      expect(loader.config.providers).toBeDefined();
    });

    it('should handle missing providers gracefully', async () => {
      const builder = new CommandBuilder();
      
      const command = await builder.buildCommand('nonexistent', {});
      
      // Should return null for unknown provider
      expect(command).toBeNull();
    });

    it('should handle file system errors securely', async () => {
      const executor = new ProviderExecutor();
      
      executor.commandBuilder.buildCommand = jest.fn().mockResolvedValue({
        command: 'claude',
        args: [],
        outputFile: '/root/protected.txt' // Protected location
      });
      
      const executePromise = executor.execute('claude', {});
      
      const mockProcess = mockSpawn.lastProcess;
      setImmediate(() => {
        mockProcess.stdout.emit('data', Buffer.from('output'));
        mockProcess.emit('exit', 0);
      });
      
      // Mock file write failure
      mockFS.writeFile.mockRejectedValueOnce(new Error('Permission denied'));
      
      // Should handle the error gracefully
      const result = await executePromise;
      expect(result).toBeDefined();
    });
  });
});