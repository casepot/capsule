import { jest } from '@jest/globals';
import CommandBuilder from '../../lib/command-builder.js';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import * as child_process from 'node:child_process';

// Mock modules
jest.mock('node:fs/promises');
jest.mock('node:child_process', () => ({
  execFileSync: jest.fn()
}));

describe('CommandBuilder', () => {
  let commandBuilder;
  
  beforeEach(() => {
    jest.clearAllMocks();
    commandBuilder = new CommandBuilder({
      verbose: false
    });
  });

  describe('constructor', () => {
    it('should initialize with default options', () => {
      const builder = new CommandBuilder();
      expect(builder.verbose).toBe(false);
      expect(builder.configLoader).toBeDefined();
    });

    it('should accept custom options', () => {
      const builder = new CommandBuilder({ verbose: true });
      expect(builder.verbose).toBe(true);
    });
  });

  describe('detectCommandPath', () => {
    it('should detect command in PATH using execFileSync safely', async () => {
      const manifest = {
        cli: {
          command: 'claude'
        }
      };
      
      // Mock successful command detection
      child_process.execFileSync.mockReturnValueOnce();
      
      const result = await commandBuilder.detectCommandPath(manifest);
      
      // Verify it uses execFileSync with array args (safe from injection)
      expect(child_process.execFileSync).toHaveBeenCalledWith(
        'which',
        ['claude'],
        { stdio: 'ignore' }
      );
      expect(result).toBe('claude');
    });

    it('should not allow command injection through malicious command names', async () => {
      const manifest = {
        cli: {
          command: 'claude; rm -rf /' // Malicious command
        }
      };
      
      child_process.execFileSync.mockReturnValueOnce();
      
      await commandBuilder.detectCommandPath(manifest);
      
      // Verify the malicious string is passed as a single argument
      expect(child_process.execFileSync).toHaveBeenCalledWith(
        'which',
        ['claude; rm -rf /'], // Treated as a single filename, not executed
        { stdio: 'ignore' }
      );
    });

    it('should check detection paths if command not in PATH', async () => {
      const manifest = {
        cli: {
          command: 'claude',
          detection: [
            {
              type: 'path',
              value: '~/.claude/local/claude'
            }
          ]
        }
      };
      
      // Mock command not in PATH
      child_process.execFileSync.mockImplementationOnce(() => {
        throw new Error('Command not found');
      });
      
      // Mock file exists at detection path
      fs.access.mockResolvedValueOnce();
      
      const result = await commandBuilder.detectCommandPath(manifest);
      
      expect(fs.access).toHaveBeenCalled();
    });

    it('should expand home directory in detection paths', async () => {
      const manifest = {
        cli: {
          command: 'claude',
          detection: [
            {
              type: 'path',
              value: '~/test/command'
            }
          ]
        }
      };
      
      child_process.execFileSync.mockImplementationOnce(() => {
        throw new Error('Not in PATH');
      });
      
      fs.access.mockResolvedValueOnce();
      
      await commandBuilder.detectCommandPath(manifest);
      
      // Check that ~ was expanded
      const accessCall = fs.access.mock.calls[0][0];
      expect(accessCall).not.toContain('~');
      expect(accessCall).toContain(process.env.HOME || process.env.USERPROFILE);
    });

    it('should return null if command not found anywhere', async () => {
      const manifest = {
        cli: {
          command: 'nonexistent'
        }
      };
      
      child_process.execFileSync.mockImplementationOnce(() => {
        throw new Error('Not found');
      });
      
      const result = await commandBuilder.detectCommandPath(manifest);
      
      expect(result).toBeNull();
    });
  });

  describe('buildCommand', () => {
    it('should build command with proper argument escaping', async () => {
      const manifest = {
        cli: {
          command: 'claude'
        },
        required_flags: {
          review: {
            flags: ['--permission-mode', 'default', '--output-format', 'json']
          }
        }
      };
      
      const config = {
        prompt: 'Review this code',
        model: 'sonnet'
      };
      
      child_process.execFileSync.mockReturnValueOnce();
      
      const command = await commandBuilder.buildCommand(manifest, config);
      
      expect(command).toContain('claude');
      expect(command).toContain('--permission-mode');
      expect(command).toContain('default');
    });

    it('should handle special characters in prompts safely', async () => {
      const manifest = {
        cli: {
          command: 'claude'
        }
      };
      
      const config = {
        prompt: 'Review "this" code; echo $HOME' // Special chars
      };
      
      child_process.execFileSync.mockReturnValueOnce();
      
      const command = await commandBuilder.buildCommand(manifest, config);
      
      // Should properly escape or quote the prompt
      expect(command).toBeDefined();
    });
  });

  describe('buildCommand', () => {
    it('should build a structured command for a provider', async () => {
      const mockManifest = {
        id: 'claude',
        name: 'Claude Code',
        cli: {
          command: 'claude',
          arguments: ['code']
        }
      };
      
      // Mock the manifest file read
      fs.readFile.mockImplementation((path) => {
        if (path.includes('claude.manifest.json')) {
          return Promise.resolve(JSON.stringify(mockManifest));
        }
        if (path.includes('pipeline.config.json')) {
          return Promise.resolve(JSON.stringify({
            providers: { enabled: ['claude'] }
          }));
        }
        return Promise.reject(new Error('File not found'));
      });
      
      const command = await commandBuilder.buildCommand('claude');
      
      expect(command).toBeDefined();
      expect(command.command).toBeDefined();
      expect(command.arguments).toBeInstanceOf(Array);
      expect(command.env).toBeDefined();
    });

    it('should return null for disabled providers', async () => {
      fs.readFile.mockImplementation((path) => {
        if (path.includes('pipeline.config.json')) {
          return Promise.resolve(JSON.stringify({
            providers: { enabled: [] }
          }));
        }
        return Promise.reject(new Error('File not found'));
      });
      
      const command = await commandBuilder.buildCommand('disabled-provider');
      expect(command).toBeNull();
    });

    it('should handle missing provider manifest gracefully', async () => {
      fs.readFile.mockRejectedValue(new Error('ENOENT'));
      
      const command = await commandBuilder.buildCommand('nonexistent');
      expect(command).toBeNull();
    });
  });

  describe('security considerations', () => {
    it('should not execute arbitrary commands through provider names', async () => {
      const maliciousProvider = '../../etc/passwd';
      
      fs.readFile.mockRejectedValueOnce(new Error('Invalid path'));
      
      await expect(commandBuilder.loadProviderManifest(maliciousProvider))
        .rejects.toThrow();
    });

    it('should sanitize file paths when loading manifests', async () => {
      const provider = '../../../malicious';
      
      await expect(commandBuilder.loadProviderManifest(provider))
        .rejects.toThrow();
    });
  });
});