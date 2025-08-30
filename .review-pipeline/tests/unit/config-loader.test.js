import { describe, it, expect, beforeEach, vi } from 'vitest';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageDir = path.dirname(path.dirname(__dirname));

// Mock the file system
vi.mock('node:fs/promises', () => {
  const fileStore = new Map();
  
  return {
    default: {
      readFile: vi.fn(async (filePath) => {
        if (fileStore.has(filePath)) {
          return fileStore.get(filePath);
        }
        const error = new Error(`ENOENT: no such file or directory, open '${filePath}'`);
        error.code = 'ENOENT';
        throw error;
      }),
      writeFile: vi.fn().mockResolvedValue(undefined),
      access: vi.fn().mockResolvedValue(undefined),
      mkdir: vi.fn().mockResolvedValue(undefined),
      
      // Helper methods for testing
      setFile: (path, content) => fileStore.set(path, content),
      clearFiles: () => fileStore.clear(),
      getFiles: () => fileStore
    }
  };
});

// Mock Ajv for schema validation
vi.mock('ajv', () => ({
  default: vi.fn(() => ({
    compile: vi.fn(() => vi.fn(() => true))
  }))
}));

vi.mock('ajv-formats', () => ({
  default: vi.fn()
}));

describe('ConfigLoader', () => {
  let ConfigLoader;
  let fs;
  let configLoader;

  beforeEach(async () => {
    // Clear all mocks
    vi.clearAllMocks();
    
    // Get mocked fs
    fs = (await import('node:fs/promises')).default;
    fs.clearFiles();
    
    // Set up default mock files
    const pipelineConfigPath = path.join(packageDir, 'config', 'pipeline.config.json');
    const pipelineSchemaPath = path.join(packageDir, 'config', 'schemas', 'pipeline.schema.json');
    const projectSchemaPath = path.join(packageDir, 'config', 'schemas', 'project.schema.json');
    const envMappingPath = path.join(packageDir, 'config', 'env.mapping.json');
    
    fs.setFile(pipelineConfigPath, JSON.stringify({
      execution: {
        parallel: true,
        timeout_seconds: 120,
        fail_fast: false
      },
      providers: {
        claude: {
          enabled: true,
          model: 'sonnet',
          flags: {
            permission_mode: 'default',
            output_format: 'json'
          }
        },
        codex: {
          enabled: true,
          model: 'gpt-5'
        },
        gemini: {
          enabled: true,
          model: 'gemini-2.5-pro'
        }
      },
      testing: {
        enabled: true
      },
      gating: {
        enabled: true,
        must_fix_threshold: 1
      }
    }));
    
    fs.setFile(pipelineSchemaPath, JSON.stringify({
      type: 'object',
      properties: {
        execution: { type: 'object' },
        providers: { type: 'object' },
        testing: { type: 'object' },
        gating: { type: 'object' }
      }
    }));
    
    fs.setFile(projectSchemaPath, JSON.stringify({
      type: 'object',
      properties: {
        review_overrides: { type: 'object' },
        project: { type: 'object' },
        ci: { type: 'object' }
      }
    }));
    
    fs.setFile(envMappingPath, JSON.stringify({
      mappings: []
    }));
    
    // Import ConfigLoader after mocks are set up
    const module = await import('../../lib/config-loader.js');
    ConfigLoader = module.ConfigLoader || module.default;
    
    configLoader = new ConfigLoader();
  });

  describe('constructor', () => {
    it('should initialize with default values', () => {
      const loader = new ConfigLoader();
      expect(loader.config).toEqual({});
      expect(loader.errors).toEqual([]);
      expect(loader.warnings).toEqual([]);
    });
  });

  describe('load', () => {
    it('should load pipeline configuration', async () => {
      await configLoader.load();
      
      expect(configLoader.config).toBeDefined();
      expect(configLoader.config.providers).toBeDefined();
      expect(configLoader.config.providers.claude).toBeDefined();
      expect(configLoader.config.providers.claude.enabled).toBe(true);
    });

    it('should handle missing configuration files gracefully', async () => {
      fs.clearFiles();
      
      // Add only schema files (required)
      const pipelineSchemaPath = path.join(packageDir, 'config', 'schemas', 'pipeline.schema.json');
      const projectSchemaPath = path.join(packageDir, 'config', 'schemas', 'project.schema.json');
      
      fs.setFile(pipelineSchemaPath, JSON.stringify({ type: 'object' }));
      fs.setFile(projectSchemaPath, JSON.stringify({ type: 'object' }));
      
      await configLoader.load();
      
      // Should use minimal defaults
      expect(configLoader.config).toBeDefined();
      expect(configLoader.config.providers).toBeDefined();
    });
  });

  describe('getProviderConfig', () => {
    beforeEach(async () => {
      await configLoader.load();
    });

    it('should return provider-specific configuration', () => {
      const claudeConfig = configLoader.getProviderConfig('claude');
      
      expect(claudeConfig).toBeDefined();
      expect(claudeConfig.enabled).toBe(true);
      expect(claudeConfig.model).toBe('sonnet');
    });

    it('should throw error for unconfigured provider', () => {
      expect(() => configLoader.getProviderConfig('unknown'))
        .toThrow("Provider 'unknown' not configured");
    });
  });

  describe('isProviderEnabled', () => {
    beforeEach(async () => {
      await configLoader.load();
    });

    it('should return true for enabled providers', () => {
      expect(configLoader.isProviderEnabled('claude')).toBe(true);
      expect(configLoader.isProviderEnabled('codex')).toBe(true);
      expect(configLoader.isProviderEnabled('gemini')).toBe(true);
    });

    it('should return true for unknown providers (not explicitly disabled)', () => {
      // Implementation returns true if not explicitly disabled
      expect(configLoader.isProviderEnabled('unknown')).toBe(true);
    });
  });

  describe('getTestCommand', () => {
    it('should get test command from environment only', () => {
      // Without environment variable
      expect(configLoader.getTestCommand()).toBe('');
      
      // With environment variable
      process.env.TEST_CMD = 'npm test';
      expect(configLoader.getTestCommand()).toBe('npm test');
      
      delete process.env.TEST_CMD;
    });
  });
});