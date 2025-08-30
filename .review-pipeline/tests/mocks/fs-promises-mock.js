/**
 * ES Module mock for node:fs/promises
 * Uses jest.unstable_mockModule() pattern
 */

import { jest } from '@jest/globals';

export function createFSPromisesMock() {
  const fileStore = new Map();
  
  const readFile = jest.fn(async (path, encoding) => {
    // Default responses for common files
    if (path.includes('pipeline.schema.json')) {
      return JSON.stringify({
        type: 'object',
        properties: {
          providers: { 
            type: 'object',
            properties: {
              enabled: { type: 'array', items: { type: 'string' } },
              default: { type: 'string' }
            }
          },
          testing: { type: 'object' },
          security: { type: 'object' }
        },
        additionalProperties: true
      });
    }
    
    if (path.includes('project.schema.json')) {
      return JSON.stringify({
        type: 'object',
        properties: {
          providers: { type: 'object' },
          testing: { type: 'object' }
        },
        additionalProperties: true
      });
    }
    
    if (path.includes('env.mapping.json')) {
      return JSON.stringify({
        REVIEW_PROVIDER: 'providers.default',
        TEST_CMD: 'testing.command',
        TEST_TIMEOUT: 'testing.timeout'
      });
    }
    
    if (path.includes('pipeline.config.json')) {
      return JSON.stringify({
        providers: {
          enabled: ['claude', 'codex', 'gemini']
        },
        testing: {
          timeout: 300000
        }
      });
    }
    
    if (path.includes('claude.manifest.json')) {
      return JSON.stringify({
        id: 'claude',
        name: 'Claude',
        cli: {
          command: 'claude',
          arguments: []
        },
        required_flags: {
          review: {
            flags: ['--output-format', 'json']
          }
        }
      });
    }
    
    if (path.includes('codex.manifest.json')) {
      return JSON.stringify({
        id: 'codex',
        name: 'Codex',
        cli: {
          command: 'codex',
          arguments: []
        }
      });
    }
    
    if (path.includes('gemini.manifest.json')) {
      return JSON.stringify({
        id: 'gemini',
        name: 'Gemini',
        cli: {
          command: 'gemini',
          arguments: []
        }
      });
    }
    
    // Check custom store
    if (fileStore.has(path)) {
      const content = fileStore.get(path);
      return encoding ? content : Buffer.from(content);
    }
    
    throw new Error(`ENOENT: no such file or directory, open '${path}'`);
  });
  
  const writeFile = jest.fn(async (path, content, encoding) => {
    fileStore.set(path, content.toString());
    return undefined;
  });
  
  const access = jest.fn(async (path, mode) => {
    // Simulate file exists for known paths
    if (path.includes('.manifest.json') || 
        path.includes('config.json') ||
        fileStore.has(path)) {
      return undefined;
    }
    throw new Error(`ENOENT: no such file or directory, access '${path}'`);
  });
  
  const mkdir = jest.fn(async (path, options) => {
    return undefined;
  });
  
  const rm = jest.fn(async (path, options) => {
    if (fileStore.has(path)) {
      fileStore.delete(path);
    }
    return undefined;
  });
  
  const stat = jest.fn(async (path) => {
    if (fileStore.has(path)) {
      return {
        isFile: () => true,
        isDirectory: () => false,
        size: fileStore.get(path).length,
        mtime: new Date()
      };
    }
    throw new Error(`ENOENT: no such file or directory, stat '${path}'`);
  });
  
  const readdir = jest.fn(async (path) => {
    if (path.includes('providers')) {
      return ['claude.manifest.json', 'codex.manifest.json', 'gemini.manifest.json'];
    }
    return [];
  });
  
  const fsMock = {
    readFile,
    writeFile,
    access,
    mkdir,
    rm,
    stat,
    readdir,
    constants: {
      F_OK: 0,
      R_OK: 4,
      W_OK: 2,
      X_OK: 1
    }
  };
  
  // Add utility methods
  const utilityMethods = {
    setFile: (path, content) => fileStore.set(path, content),
    getFile: (path) => fileStore.get(path),
    clearFiles: () => fileStore.clear()
  };
  
  // Return both named exports and default export
  return {
    ...fsMock,
    ...utilityMethods,
    default: fsMock
  };
}