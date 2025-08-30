import { describe, it, expect, beforeEach, vi } from 'vitest';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageDir = path.dirname(path.dirname(__dirname));

// Mock child_process
vi.mock('node:child_process', () => ({
  execFileSync: vi.fn((command, args) => {
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
  })
}));

// Mock fs/promises
vi.mock('node:fs/promises', () => {
  const fileStore = new Map();
  
  return {
    default: {
      readFile: vi.fn(async (filePath) => {
        if (fileStore.has(filePath)) {
          return fileStore.get(filePath);
        }
        throw new Error(`ENOENT: ${filePath}`);
      }),
      writeFile: vi.fn().mockResolvedValue(undefined),
      access: vi.fn().mockResolvedValue(undefined),
      mkdir: vi.fn().mockResolvedValue(undefined),
      
      // Helper methods
      setFile: (path, content) => fileStore.set(path, content),
      clearFiles: () => fileStore.clear(),
      getFiles: () => fileStore
    }
  };
});

// Mock ConfigLoader
vi.mock('../../lib/config-loader.js', () => ({
  default: vi.fn(() => ({
    load: vi.fn().mockResolvedValue(undefined),
    config: {},
    getProviderConfig: vi.fn((provider) => {
      const configs = {
        claude: {
          model: 'sonnet',
          timeout: 1500,
          flags: {
            permission_mode: 'default',
            output_format: 'json'
          }
        },
        codex: {
          model: 'gpt-5',
          timeout: 1500
        },
        gemini: {
          model: 'gemini-2.5-pro',
          timeout: 1500
        }
      };
      return configs[provider] || {};
    }),
    isProviderEnabled: vi.fn((provider) => {
      const enabled = ['claude', 'codex', 'gemini'];
      return enabled.includes(provider);
    })
  }))
}));

describe('CommandBuilder', () => {
  let CommandBuilder;
  let commandBuilder;
  let fs;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Get mocked fs
    fs = (await import('node:fs/promises')).default;
    fs.clearFiles();
    
    // Set up default mock files with absolute paths
    const claudeManifestPath = path.join(packageDir, 'config', 'providers', 'claude.manifest.json');
    const corePath = path.join(packageDir, 'prompts', 'review.core.md');
    
    fs.setFile(claudeManifestPath, JSON.stringify({
      id: 'claude',
      name: 'Claude',
      cli: {
        command: 'claude',
        arguments: []
      }
    }));
    
    fs.setFile(corePath, 'Core review prompt content');
    
    // Import after mocks are set up
    CommandBuilder = (await import('../../lib/command-builder.js')).default;
    
    commandBuilder = new CommandBuilder({
      verbose: false,
      packageDir: packageDir
    });
  });

  describe('constructor', () => {
    it('should initialize with default options', () => {
      const builder = new CommandBuilder();
      expect(builder.verbose).toBe(false);
      expect(builder.configLoader).toBeDefined();
    });
  });

  describe('detectCommandPath', () => {
    it('should detect command in PATH using execFileSync safely', async () => {
      const manifest = {
        cli: {
          command: 'claude'
        }
      };
      
      const result = await commandBuilder.detectCommandPath(manifest);
      
      expect(result).toBe('claude');
    });

    it('should return command name as fallback if not found', async () => {
      const manifest = {
        cli: {
          command: 'nonexistent'
        }
      };
      
      const result = await commandBuilder.detectCommandPath(manifest);
      
      // Implementation returns command name as fallback
      expect(result).toBe('nonexistent');
    });
  });

  describe('buildCommand', () => {
    it('should build command with proper structure', async () => {
      const command = await commandBuilder.buildCommand('claude', {});
      
      expect(command).toMatchObject({
        command: expect.any(String),
        args: expect.any(Array),
        env: expect.any(Object),
        timeout: expect.any(Number),
        outputFile: expect.any(String),
        workingDirectory: expect.any(String)
      });
    });

    it('should return null for disabled providers', async () => {
      commandBuilder.configLoader.isProviderEnabled.mockReturnValueOnce(false);
      
      const command = await commandBuilder.buildCommand('disabled-provider', {});
      expect(command).toBeNull();
    });

    it('should throw error for unknown provider', async () => {
      commandBuilder.configLoader.isProviderEnabled.mockReturnValueOnce(true);
      
      // Implementation throws ENOENT when manifest file doesn't exist
      await expect(commandBuilder.buildCommand('unknown', {}))
        .rejects.toThrow('ENOENT');
    });
  });

  describe('provider-specific build methods', () => {
    beforeEach(() => {
      // Add manifests for each provider
      const providers = ['claude', 'codex', 'gemini'];
      providers.forEach(provider => {
        const manifestPath = path.join(packageDir, 'config', 'providers', `${provider}.manifest.json`);
        fs.setFile(manifestPath, JSON.stringify({
          id: provider,
          name: provider,
          cli: {
            command: provider
          }
        }));
      });
    });

    it('should build Claude command correctly', async () => {
      const command = await commandBuilder.buildCommand('claude', {});
      
      expect(command.command).toBe('claude');
      expect(command.args).toContain('--model');
      expect(command.args).toContain('sonnet');
      expect(command.stdin).toBeNull();
      expect(command.env.TOOL).toBe('claude-code');
    });

    it('should build Codex command correctly', async () => {
      const command = await commandBuilder.buildCommand('codex', {});
      
      expect(command.command).toBe('codex');
      expect(command.args).toContain('exec');
      expect(command.args).toContain('-m');
      expect(command.args).toContain('gpt-5');
      expect(command.stdin).toBeNull();
      expect(command.env.TOOL).toBe('codex-cli');
    });

    it('should build Gemini command correctly', async () => {
      const command = await commandBuilder.buildCommand('gemini', {});
      
      expect(command.command).toBe('gemini');
      expect(command.args).toContain('-p');
      expect(command.args).toContain('-s');
      expect(command.args).toContain('--approval-mode=yolo');
      expect(command.stdin).toBeDefined();
      expect(command.env.TOOL).toBe('gemini-cli');
    });
  });
});