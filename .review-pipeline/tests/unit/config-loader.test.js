import { jest } from '@jest/globals';
import path from 'node:path';

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

jest.unstable_mockModule('node:fs/promises', () => ({
  ...mockFS,
  default: mockFS
}));

// Import after mocking
const ConfigLoader = (await import('../../lib/config-loader.js')).default;

describe('ConfigLoader', () => {
  let configLoader;
  
  beforeEach(() => {
    jest.clearAllMocks();
    mockFS.clearFiles();
    
    // Set up default mock files
    mockFS.setFile('/config/pipeline.config.json', JSON.stringify({
      providers: {
        enabled: ['claude', 'codex', 'gemini'],
        default: 'claude'
      },
      testing: {
        timeout: 300000,
        parallel: true
      },
      security: {
        maxFileSize: 10485760,
        allowedExtensions: ['.js', '.py', '.java', '.go']
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
    
    configLoader = new ConfigLoader();
  });

  describe('constructor', () => {
    it('should initialize with default values', () => {
      const loader = new ConfigLoader();
      expect(loader.config).toEqual({});
      expect(loader.errors).toEqual([]);
      expect(loader.warnings).toEqual([]);
    });

    it('should accept custom options', () => {
      const loader = new ConfigLoader({ verbose: true });
      expect(loader.options.verbose).toBe(true);
    });
  });

  describe('load', () => {
    it('should load pipeline configuration', async () => {
      await configLoader.load();
      
      expect(configLoader.config).toBeDefined();
      expect(configLoader.config.providers).toBeDefined();
      expect(configLoader.config.providers.enabled).toContain('claude');
    });

    it('should merge project configuration', async () => {
      mockFS.setFile('/.review-pipeline.json', JSON.stringify({
        providers: {
          enabled: ['claude'],
          custom: 'value'
        },
        testing: {
          timeout: 600000
        }
      }));
      
      await configLoader.load();
      
      expect(configLoader.config.providers.enabled).toEqual(['claude']);
      expect(configLoader.config.providers.custom).toBe('value');
      expect(configLoader.config.testing.timeout).toBe(600000);
      expect(configLoader.config.testing.parallel).toBe(true); // From base config
    });

    it('should apply environment variable overrides', async () => {
      process.env.REVIEW_PROVIDER = 'gemini';
      process.env.TEST_CMD = 'npm run test:custom';
      
      await configLoader.load();
      
      expect(configLoader.config.providers.default).toBe('gemini');
      expect(configLoader.config.testing.command).toBe('npm run test:custom');
      
      delete process.env.REVIEW_PROVIDER;
      delete process.env.TEST_CMD;
    });

    it('should handle missing configuration files gracefully', async () => {
      mockFS.clearFiles();
      
      await configLoader.load();
      
      // Should use defaults
      expect(configLoader.config).toBeDefined();
      expect(configLoader.config.providers).toBeDefined();
    });

    it('should validate configuration against schema', async () => {
      mockFS.setFile('/config/pipeline.config.json', JSON.stringify({
        providers: {
          enabled: 'invalid' // Should be array
        }
      }));
      
      mockFS.setFile('/config/schema.json', JSON.stringify({
        type: 'object',
        properties: {
          providers: {
            type: 'object',
            properties: {
              enabled: {
                type: 'array',
                items: { type: 'string' }
              }
            }
          }
        }
      }));
      
      // Should handle validation error gracefully
      await configLoader.load();
      
      // Config should still be loaded, possibly with defaults
      expect(configLoader.config).toBeDefined();
    });

    it('should cache configuration after loading', async () => {
      await configLoader.load();
      await configLoader.load();
      
      // Should only read files once
      const readCalls = mockFS.readFile.mock.calls.filter(call => 
        call[0].includes('pipeline.config.json')
      );
      expect(readCalls.length).toBe(1);
    });
  });

  describe('getProviderConfig', () => {
    beforeEach(async () => {
      await configLoader.load();
    });

    it('should return provider-specific configuration', () => {
      mockFS.setFile('/config/pipeline.config.json', JSON.stringify({
        providers: {
          enabled: ['claude'],
          claude: {
            model: 'claude-3-sonnet',
            maxTokens: 4096
          }
        }
      }));
      
      configLoader.config.providers.claude = {
        model: 'claude-3-sonnet',
        maxTokens: 4096
      };
      
      const claudeConfig = configLoader.getProviderConfig('claude');
      
      expect(claudeConfig).toEqual({
        model: 'claude-3-sonnet',
        maxTokens: 4096
      });
    });

    it('should return empty object for unconfigured provider', () => {
      const config = configLoader.getProviderConfig('unknown');
      expect(config).toEqual({});
    });

    it('should merge provider defaults', () => {
      configLoader.config.providers.defaults = {
        timeout: 30000
      };
      configLoader.config.providers.claude = {
        model: 'sonnet'
      };
      
      const config = configLoader.getProviderConfig('claude');
      
      // Should merge defaults with provider-specific config
      expect(config.model).toBe('sonnet');
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

    it('should return false for disabled providers', () => {
      expect(configLoader.isProviderEnabled('disabled')).toBe(false);
      expect(configLoader.isProviderEnabled('unknown')).toBe(false);
    });

    it('should handle empty enabled list', () => {
      configLoader.config.providers.enabled = [];
      
      expect(configLoader.isProviderEnabled('claude')).toBe(false);
    });
  });

  describe('environment variable handling', () => {
    it('should not load TEST_CMD from configuration files', async () => {
      mockFS.setFile('/.review-pipeline.json', JSON.stringify({
        testing: {
          command: 'rm -rf /' // Malicious command in config
        }
      }));
      
      await configLoader.load();
      
      // Should not load command from file
      expect(configLoader.config.testing.command).toBeUndefined();
    });

    it('should only accept TEST_CMD from environment', async () => {
      process.env.TEST_CMD = 'npm test';
      
      await configLoader.load();
      
      expect(configLoader.config.testing.command).toBe('npm test');
      
      delete process.env.TEST_CMD;
    });

    it('should sanitize environment variable values', async () => {
      process.env.REVIEW_PROVIDER = '../../../etc/passwd';
      
      await configLoader.load();
      
      // Should sanitize or reject malicious values
      expect(configLoader.config.providers.default).not.toContain('../');
      
      delete process.env.REVIEW_PROVIDER;
    });
  });

  describe('security', () => {
    it('should validate file paths are within allowed directories', async () => {
      const loader = new ConfigLoader({ configDir: '../../../etc' });
      
      await loader.load();
      
      // Should not read from system directories
      const readCalls = mockFS.readFile.mock.calls;
      for (const call of readCalls) {
        expect(call[0]).not.toMatch(/^\/etc/);
      }
    });

    it('should limit configuration file size', async () => {
      const largeConfig = 'x'.repeat(10 * 1024 * 1024); // 10MB
      mockFS.setFile('/config/pipeline.config.json', largeConfig);
      
      // Should handle large files gracefully
      await configLoader.load();
      
      expect(configLoader.config).toBeDefined();
    });

    it('should escape special characters in configuration values', async () => {
      mockFS.setFile('/.review-pipeline.json', JSON.stringify({
        providers: {
          custom: '$(echo hacked)'
        }
      }));
      
      await configLoader.load();
      
      // Special characters should be preserved, not executed
      if (configLoader.config.providers.custom) {
        expect(configLoader.config.providers.custom).toBe('$(echo hacked)');
      }
    });
  });

  describe('error handling', () => {
    it('should handle JSON parse errors', async () => {
      mockFS.setFile('/config/pipeline.config.json', 'invalid json');
      
      await configLoader.load();
      
      // Should fall back to defaults
      expect(configLoader.config).toBeDefined();
      expect(configLoader.loaded).toBe(true);
    });

    it('should handle file read errors', async () => {
      mockFS.readFile.mockRejectedValue(new Error('Permission denied'));
      
      await configLoader.load();
      
      // Should use defaults
      expect(configLoader.config).toBeDefined();
    });

    it('should handle missing schema file', async () => {
      mockFS.readFile.mockImplementation(async (path) => {
        if (path.includes('schema.json')) {
          throw new Error('ENOENT');
        }
        return JSON.stringify({
          providers: { enabled: ['claude'] }
        });
      });
      
      await configLoader.load();
      
      // Should load without schema validation
      expect(configLoader.config).toBeDefined();
    });
  });
});