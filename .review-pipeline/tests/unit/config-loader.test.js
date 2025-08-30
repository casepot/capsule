import { jest } from '@jest/globals';
import { ConfigLoader } from '../../lib/config-loader.js';
import fs from 'node:fs/promises';
import path from 'node:path';

// Mock the fs module
jest.mock('node:fs/promises');

describe('ConfigLoader', () => {
  let configLoader;
  
  beforeEach(() => {
    jest.clearAllMocks();
    configLoader = new ConfigLoader({
      verbose: false
    });
  });

  describe('constructor', () => {
    it('should initialize with default options', () => {
      const loader = new ConfigLoader();
      expect(loader.options.verbose).toBe(false);
      expect(loader.config).toEqual({});
      expect(loader.errors).toEqual([]);
      expect(loader.warnings).toEqual([]);
    });

    it('should accept custom options', () => {
      const loader = new ConfigLoader({ verbose: true });
      expect(loader.options.verbose).toBe(true);
    });
  });

  describe('loadPipelineConfig', () => {
    it('should load and validate pipeline configuration', async () => {
      const mockConfig = {
        version: '1.0.0',
        pipeline: {
          timeout: 120,
          maxRetries: 3
        }
      };
      
      fs.readFile.mockResolvedValueOnce(JSON.stringify(mockConfig));
      
      // Mock schema loading
      fs.readFile.mockResolvedValueOnce(JSON.stringify({
        type: 'object',
        properties: {
          version: { type: 'string' },
          pipeline: { type: 'object' }
        }
      }));

      await configLoader.load();
      
      expect(fs.readFile).toHaveBeenCalled();
    });

    it('should handle missing pipeline config file gracefully', async () => {
      fs.readFile.mockRejectedValueOnce(new Error('ENOENT'));
      
      await configLoader.load();
      
      expect(configLoader.warnings.length).toBeGreaterThan(0);
    });
  });

  describe('loadProjectConfig', () => {
    it('should load project configuration if it exists', async () => {
      const mockProjectConfig = {
        providers: ['claude', 'codex'],
        timeout: 60
      };
      
      fs.access.mockResolvedValueOnce(); // File exists
      fs.readFile.mockResolvedValueOnce(JSON.stringify(mockProjectConfig));
      
      await configLoader.load();
      
      expect(fs.access).toHaveBeenCalled();
    });

    it('should skip project config if file does not exist', async () => {
      fs.access.mockRejectedValueOnce(new Error('ENOENT'));
      
      await configLoader.load();
      
      expect(configLoader.config.project).toBeUndefined();
    });
  });

  describe('loadEnvironmentVariables', () => {
    it('should not load TEST_CMD from project configuration', async () => {
      const mockProjectConfig = {
        testing: {
          command: 'malicious-command'
        }
      };
      
      fs.access.mockResolvedValueOnce();
      fs.readFile.mockResolvedValueOnce(JSON.stringify(mockProjectConfig));
      
      await configLoader.load();
      
      // TEST_CMD should only come from environment, not project config
      expect(configLoader.config.testing?.command).toBeUndefined();
    });

    it('should load TEST_CMD from environment variables only', async () => {
      process.env.TEST_CMD = 'npm test';
      
      await configLoader.load();
      
      expect(configLoader.config.testing?.command).toBe('npm test');
      
      delete process.env.TEST_CMD;
    });
  });

  describe('mergeConfigurations', () => {
    it('should properly merge configurations with correct precedence', async () => {
      const pipelineConfig = {
        timeout: 120,
        providers: ['claude']
      };
      
      const projectConfig = {
        timeout: 60,
        providers: ['codex', 'gemini']
      };
      
      // Mock file reads
      fs.readFile.mockResolvedValueOnce(JSON.stringify(pipelineConfig));
      fs.access.mockResolvedValueOnce();
      fs.readFile.mockResolvedValueOnce(JSON.stringify(projectConfig));
      
      await configLoader.load();
      
      // Project config should override pipeline config
      expect(configLoader.config.timeout).toBe(60);
    });
  });

  describe('validation', () => {
    it('should validate configuration against schema', async () => {
      const invalidConfig = {
        timeout: 'not-a-number' // Should be a number
      };
      
      fs.readFile.mockResolvedValueOnce(JSON.stringify(invalidConfig));
      
      // Mock schema that requires timeout to be a number
      fs.readFile.mockResolvedValueOnce(JSON.stringify({
        type: 'object',
        properties: {
          timeout: { type: 'number' }
        }
      }));
      
      await configLoader.load();
      
      expect(configLoader.errors.length).toBeGreaterThan(0);
    });

    it('should apply default values from schema', async () => {
      const config = {};
      
      const schema = {
        type: 'object',
        properties: {
          timeout: { 
            type: 'number',
            default: 120
          }
        }
      };
      
      fs.readFile.mockResolvedValueOnce(JSON.stringify(config));
      fs.readFile.mockResolvedValueOnce(JSON.stringify(schema));
      
      await configLoader.load();
      
      expect(configLoader.config.timeout).toBe(120);
    });
  });

  describe('error handling', () => {
    it('should collect errors during loading', async () => {
      fs.readFile.mockRejectedValueOnce(new Error('Read error'));
      
      await configLoader.load();
      
      expect(configLoader.errors.length).toBeGreaterThan(0);
    });

    it('should continue loading despite errors', async () => {
      // First read fails, second succeeds
      fs.readFile.mockRejectedValueOnce(new Error('Read error'));
      fs.access.mockResolvedValueOnce();
      fs.readFile.mockResolvedValueOnce(JSON.stringify({ test: 'data' }));
      
      await configLoader.load();
      
      expect(configLoader.config).toBeDefined();
    });
  });
});