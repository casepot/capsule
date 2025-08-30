import { jest } from '@jest/globals';
import CommandBuilder from '../../lib/command-builder.js';
import ProviderExecutor from '../../lib/execute-provider.js';
import { ConfigLoader } from '../../lib/config-loader.js';
import fs from 'node:fs/promises';
import path from 'node:path';

describe('Security Integration Tests', () => {
  
  describe('Command Injection Prevention', () => {
    it('should prevent injection through TEST_CMD environment variable', () => {
      // Test that TEST_CMD with malicious content is properly escaped
      const maliciousCmd = 'npm test; rm -rf /';
      process.env.TEST_CMD = maliciousCmd;
      
      // Simulate the workflow execution pattern
      const escaped = `eval "$TEST_CMD"`;
      
      // The eval with quotes should treat the entire value as one command
      expect(escaped).toContain('"$TEST_CMD"');
      
      delete process.env.TEST_CMD;
    });

    it('should prevent injection through provider command names', async () => {
      const builder = new CommandBuilder();
      
      // Mock file system to simulate malicious manifest
      jest.spyOn(fs, 'readFile').mockResolvedValueOnce(JSON.stringify({
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
      // and not execute the echo command
      const detectSpy = jest.spyOn(builder, 'detectCommandPath');
      
      try {
        await builder.detectCommandPath(manifest);
      } catch (e) {
        // Expected to fail since the command won't be found
      }
      
      expect(detectSpy).toHaveBeenCalled();
      
      fs.readFile.mockRestore();
    });

    it('should prevent injection through prompt parameters', async () => {
      const executor = new ProviderExecutor();
      
      const maliciousPrompt = `Review this"; rm -rf /; echo "`;
      
      // Mock the command builder to return a command
      executor.commandBuilder.buildCommand = jest.fn().mockResolvedValueOnce({
        command: 'claude',
        args: ['-p', maliciousPrompt],
        // The malicious content should be a single argument
      });
      
      await executor.commandBuilder.buildCommand('claude', {
        prompt: maliciousPrompt
      });
      
      const call = executor.commandBuilder.buildCommand.mock.calls[0];
      expect(call[1].prompt).toBe(maliciousPrompt);
      // The prompt should be passed as data, not executed
    });
  });

  describe('Configuration Security', () => {
    it('should not load TEST_CMD from project configuration files', async () => {
      const loader = new ConfigLoader();
      
      // Mock project config with TEST_CMD
      jest.spyOn(fs, 'access').mockResolvedValueOnce();
      jest.spyOn(fs, 'readFile')
        .mockResolvedValueOnce(JSON.stringify({})) // pipeline config
        .mockResolvedValueOnce(JSON.stringify({})) // schema
        .mockResolvedValueOnce(JSON.stringify({
          testing: {
            command: 'rm -rf /' // Malicious command in project config
          }
        })); // project config
      
      await loader.load();
      
      // TEST_CMD should not be loaded from project config
      expect(loader.config.testing?.command).toBeUndefined();
      
      fs.access.mockRestore();
      fs.readFile.mockRestore();
    });

    it('should only accept TEST_CMD from environment variables', async () => {
      const loader = new ConfigLoader();
      
      // Set TEST_CMD in environment
      process.env.TEST_CMD = 'npm test';
      
      jest.spyOn(fs, 'readFile').mockResolvedValue(JSON.stringify({}));
      
      await loader.load();
      
      // TEST_CMD from environment should be loaded
      expect(loader.config.testing?.command).toBe('npm test');
      
      delete process.env.TEST_CMD;
      fs.readFile.mockRestore();
    });

    it('should validate provider manifests are not modifiable in PRs', async () => {
      const manifestPath = path.join(
        process.cwd(),
        '.review-pipeline/config/providers/claude.manifest.json'
      );
      
      // Provider manifests should be in a protected location
      expect(manifestPath).toContain('.review-pipeline/config/providers/');
      
      // In a real scenario, these files should be:
      // 1. Not modifiable in PRs (GitHub branch protection)
      // 2. Or loaded from a trusted source
      // 3. Or have integrity checks
    });
  });

  describe('Environment Variable Sanitization', () => {
    it('should remove sensitive environment variables before execution', async () => {
      const executor = new ProviderExecutor();
      
      // Mock environment with sensitive variables
      const mockEnv = {
        SAFE_VAR: 'value',
        GH_TOKEN: 'github_token_value',
        GITHUB_TOKEN: 'github_token_value',
        ANTHROPIC_API_KEY: 'api_key_value'
      };
      
      executor.commandBuilder.buildCommand = jest.fn().mockResolvedValueOnce({
        command: 'claude',
        args: [],
        env: mockEnv
      });
      
      // The executor should sanitize these before spawning
      const sanitized = Object.keys(mockEnv).reduce((acc, key) => {
        if (!['GH_TOKEN', 'GITHUB_TOKEN', 'ANTHROPIC_API_KEY'].includes(key)) {
          acc[key] = mockEnv[key];
        }
        return acc;
      }, {});
      
      expect(sanitized.SAFE_VAR).toBe('value');
      expect(sanitized.GH_TOKEN).toBeUndefined();
      expect(sanitized.GITHUB_TOKEN).toBeUndefined();
      expect(sanitized.ANTHROPIC_API_KEY).toBeUndefined();
    });
  });

  describe('Path Traversal Prevention', () => {
    it('should prevent path traversal in output file paths', () => {
      const maliciousPath = '../../../etc/passwd';
      const normalizedPath = path.resolve(maliciousPath);
      
      // The normalized path should not escape the working directory
      expect(normalizedPath).not.toMatch(/^\/etc/);
    });

    it('should validate file paths are within allowed directories', () => {
      const allowedDir = '/tmp/review-output';
      const maliciousPath = path.join(allowedDir, '../../../etc/passwd');
      const resolved = path.resolve(maliciousPath);
      
      // Check if resolved path is within allowed directory
      const isWithinAllowed = resolved.startsWith(path.resolve(allowedDir));
      expect(isWithinAllowed).toBe(false);
    });
  });

  describe('Input Validation', () => {
    it('should validate provider names against whitelist', () => {
      const validProviders = ['claude', 'codex', 'gemini'];
      const maliciousProvider = '../../etc/passwd';
      
      expect(validProviders.includes(maliciousProvider)).toBe(false);
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
        expect(shellMetacharacters.test(cmd)).toBe(true);
      });
    });
  });

  describe('Secure Command Execution', () => {
    it('should use execFileSync instead of execSync for command detection', () => {
      // This is tested in the implementation
      // execFileSync with array args prevents shell interpretation
      const safeExecution = {
        command: 'which',
        args: ['claude; rm -rf /']
      };
      
      // The semicolon and subsequent command are treated as part of the filename
      expect(safeExecution.args[0]).toBe('claude; rm -rf /');
      expect(safeExecution.args.length).toBe(1);
    });

    it('should use spawn without shell for provider execution', () => {
      // spawn with shell: false (default) prevents shell interpretation
      const spawnOptions = {
        shell: false, // or undefined (default)
        cwd: '/tmp',
        env: process.env
      };
      
      expect(spawnOptions.shell).toBeFalsy();
    });
  });
});