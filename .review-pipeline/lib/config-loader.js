#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageDir = path.dirname(__dirname);

/**
 * Configuration Loader for Review Pipeline
 * 
 * Loads and merges configuration from multiple sources:
 * 1. Pipeline defaults (pipeline.config.json)
 * 2. Project configuration (.reviewrc.json)
 * 3. Environment variable overrides
 * 4. Runtime overrides
 * 
 * Provides validation, type coercion, and error reporting
 */
export class ConfigLoader {
  constructor(options = {}) {
    this.options = {
      pipelineConfigPath: path.join(packageDir, 'config', 'pipeline.config.json'),
      projectConfigPath: path.join(process.cwd(), '.reviewrc.json'),
      envMappingPath: path.join(packageDir, 'config', 'env.mapping.json'),
      pipelineSchemaPath: path.join(packageDir, 'config', 'schemas', 'pipeline.schema.json'),
      projectSchemaPath: path.join(packageDir, 'config', 'schemas', 'project.schema.json'),
      verbose: false,
      ...options
    };
    
    this.ajv = new Ajv({ strict: false, allErrors: true, useDefaults: true });
    addFormats(this.ajv);
    
    this.config = {};
    this.errors = [];
    this.warnings = [];
  }

  /**
   * Load complete configuration
   */
  async load() {
    try {
      // Load schemas
      await this.loadSchemas();
      
      // Load pipeline defaults
      const pipelineConfig = await this.loadPipelineConfig();
      
      // Load project config if exists
      const projectConfig = await this.loadProjectConfig();
      
      // Merge configurations
      this.config = this.mergeConfigs(pipelineConfig, projectConfig);
      
      // Apply environment overrides
      await this.applyEnvironmentOverrides();
      
      // Validate final configuration
      await this.validateConfig();
      
      return this.config;
    } catch (error) {
      this.errors.push(`Failed to load configuration: ${error.message}`);
      throw error;
    }
  }

  /**
   * Load JSON schemas for validation
   */
  async loadSchemas() {
    try {
      const pipelineSchema = JSON.parse(await fs.readFile(this.options.pipelineSchemaPath, 'utf8'));
      const projectSchema = JSON.parse(await fs.readFile(this.options.projectSchemaPath, 'utf8'));
      
      this.pipelineValidator = this.ajv.compile(pipelineSchema);
      this.projectValidator = this.ajv.compile(projectSchema);
    } catch (error) {
      throw new Error(`Failed to load schemas: ${error.message}`);
    }
  }

  /**
   * Load pipeline default configuration
   */
  async loadPipelineConfig() {
    try {
      const config = JSON.parse(await fs.readFile(this.options.pipelineConfigPath, 'utf8'));
      
      // Validate against schema
      if (!this.pipelineValidator(config)) {
        const errors = this.ajv.errorsText(this.pipelineValidator.errors, { separator: '\n  - ' });
        throw new Error(`Pipeline config validation failed:\n  - ${errors}`);
      }
      
      if (this.options.verbose) {
        console.log('Loaded pipeline config:', this.options.pipelineConfigPath);
      }
      
      return config;
    } catch (error) {
      // If pipeline config doesn't exist, create minimal defaults
      if (error.code === 'ENOENT') {
        this.warnings.push('Pipeline config not found, using minimal defaults');
        return this.getMinimalDefaults();
      }
      throw error;
    }
  }

  /**
   * Load project-specific configuration
   */
  async loadProjectConfig() {
    try {
      const config = JSON.parse(await fs.readFile(this.options.projectConfigPath, 'utf8'));
      
      // Validate against schema
      if (!this.projectValidator(config)) {
        const errors = this.ajv.errorsText(this.projectValidator.errors, { separator: '\n  - ' });
        this.warnings.push(`Project config validation warnings:\n  - ${errors}`);
      }
      
      if (this.options.verbose) {
        console.log('Loaded project config:', this.options.projectConfigPath);
      }
      
      return config;
    } catch (error) {
      // Project config is optional
      if (error.code === 'ENOENT') {
        if (this.options.verbose) {
          console.log('No project config found, using defaults');
        }
        return {};
      }
      this.warnings.push(`Failed to load project config: ${error.message}`);
      return {};
    }
  }

  /**
   * Apply environment variable overrides
   */
  async applyEnvironmentOverrides() {
    try {
      const envMapping = JSON.parse(await fs.readFile(this.options.envMappingPath, 'utf8'));
      
      for (const mapping of envMapping.mappings || []) {
        const raw = process.env[mapping.env];
        if (raw === undefined) continue;           // not set
        if (typeof raw === 'string' && raw.trim() === '') continue; // ignore empty strings

        const value = this.coerceValue(raw, mapping.type);

        // Skip invalid numeric coercions (NaN)
        if ((mapping.type === 'integer' || mapping.type === 'number') && Number.isNaN(value)) {
          continue;
        }
        // For booleans, only accept explicit truthy/falsey strings; empty already skipped
        if (mapping.type === 'boolean' && typeof value !== 'boolean') {
          continue;
        }

        this.setNestedProperty(this.config, mapping.path, value);
        if (this.options.verbose) {
          console.log(`Applied env override: ${mapping.env}=${value} -> ${mapping.path}`);
        }
      }
    } catch (error) {
      // Environment mapping is optional
      if (error.code !== 'ENOENT') {
        this.warnings.push(`Failed to load env mappings: ${error.message}`);
      }
    }
  }

  /**
   * Merge configurations with proper precedence
   */
  mergeConfigs(pipeline, project) {
    const merged = JSON.parse(JSON.stringify(pipeline)); // Deep clone
    
    // Apply project overrides
    if (project.testing) {
      merged.testing = { ...(merged.testing || {}), ...project.testing };
    }
    
    if (project.review_overrides) {
      // Merge execution overrides
      if (project.review_overrides.execution) {
        merged.execution = { ...merged.execution, ...project.review_overrides.execution };
      }
      
      // Merge provider overrides
      if (project.review_overrides.providers) {
        for (const [provider, overrides] of Object.entries(project.review_overrides.providers)) {
          if (merged.providers[provider]) {
            merged.providers[provider] = { ...merged.providers[provider], ...overrides };
          }
        }
      }
      
      // Merge review patterns
      if (project.review_overrides.include_patterns) {
        merged.review = merged.review || {};
        merged.review.include_patterns = project.review_overrides.include_patterns;
      }
      if (project.review_overrides.exclude_patterns) {
        merged.review = merged.review || {};
        merged.review.exclude_patterns = project.review_overrides.exclude_patterns;
      }
    }
    
    // Add project metadata
    if (project.project) {
      merged.project = project.project;
    }
    
    // Add CI settings
    if (project.ci) {
      merged.ci = project.ci;
    }
    
    return merged;
  }

  /**
   * Validate final configuration
   */
  async validateConfig() {
    // Re-validate merged config against pipeline schema
    if (!this.pipelineValidator(this.config)) {
      const errors = this.ajv.errorsText(this.pipelineValidator.errors, { separator: '\n  - ' });
      throw new Error(`Final config validation failed:\n  - ${errors}`);
    }
  }

  /**
   * Get provider-specific configuration
   */
  getProviderConfig(provider) {
    const providerConfig = this.config.providers?.[provider];
    if (!providerConfig) {
      throw new Error(`Provider '${provider}' not configured`);
    }
    
    // Apply timeout override if set
    const timeout = providerConfig.timeout_override || this.config.execution?.timeout_seconds || 120;
    
    return {
      ...providerConfig,
      timeout
    };
  }

  /**
   * Get test command with proper defaults
   */
  getTestCommand() {
    // SECURITY: Only use TEST_CMD from environment (repository variables)
    // Never load test commands from project config to prevent arbitrary code execution
    return process.env.TEST_CMD || '';
  }

  /**
   * Check if a provider is enabled
   */
  isProviderEnabled(provider) {
    return this.config.providers?.[provider]?.enabled !== false;
  }

  /**
   * Get all enabled providers
   */
  getEnabledProviders() {
    const providers = [];
    for (const [name, config] of Object.entries(this.config.providers || {})) {
      if (config.enabled !== false) {
        providers.push(name);
      }
    }
    return providers;
  }

  /**
   * Export configuration as JSON
   */
  toJSON() {
    return JSON.stringify(this.config, null, 2);
  }

  /**
   * Get configuration summary for display
   */
  getSummary() {
    const providers = this.getEnabledProviders();
    const parallel = this.config.execution?.parallel !== false;
    const timeout = this.config.execution?.timeout_seconds || 120;
    
    return {
      providers: providers.map(p => ({
        name: p,
        model: this.config.providers[p].model,
        timeout: this.config.providers[p].timeout_override || timeout
      })),
      execution: {
        parallel,
        timeout,
        fail_fast: this.config.execution?.fail_fast || false
      },
      testing: {
        enabled: this.config.testing?.enabled !== false,
        command: this.getTestCommand()
      },
      gating: {
        enabled: this.config.gating?.enabled !== false,
        must_fix_threshold: this.config.gating?.must_fix_threshold || 1
      },
      warnings: this.warnings,
      errors: this.errors
    };
  }

  /**
   * Utility: Set nested property
   */
  setNestedProperty(obj, path, value) {
    const parts = path.split('.');
    let current = obj;
    
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      if (!(part in current)) {
        current[part] = {};
      }
      current = current[part];
    }
    
    current[parts[parts.length - 1]] = value;
  }

  /**
   * Utility: Coerce string value to type
   */
  coerceValue(value, type) {
    switch (type) {
      case 'boolean':
        return value === 'true' || value === '1' || value === 'yes';
      case 'integer':
        return parseInt(value, 10);
      case 'number':
        return parseFloat(value);
      case 'array':
        return value.split(',').map(s => s.trim());
      default:
        return value;
    }
  }

  /**
   * Get minimal default configuration
   */
  getMinimalDefaults() {
    return {
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
          model: 'gpt-5',
          reasoning_effort: 'low',
          sandbox_mode: 'read-only'
        },
        gemini: {
          enabled: true,
          model: 'gemini-2.5-pro'
        }
      },
      testing: {
        enabled: true,
        command: 'pytest tests/'
      },
      gating: {
        enabled: true,
        must_fix_threshold: 1
      }
    };
  }
}

/**
 * CLI usage when run directly
 */
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const command = process.argv[2];
  const configPath = process.argv[3];
  
  const loader = new ConfigLoader({
    projectConfigPath: configPath || path.join(process.cwd(), '.reviewrc.json'),
    // Keep 'validate' verbose for diagnostics; 'show' should output JSON only
    verbose: command === 'validate'
  });
  
  try {
    await loader.load();
    
    switch (command) {
      case 'show':
        // Output JSON only for downstream tools (jq) to consume
        process.stdout.write(loader.toJSON());
        break;
        
      case 'validate':
        console.log('✅ Configuration is valid');
        if (loader.warnings.length > 0) {
          console.log('\nWarnings:');
          loader.warnings.forEach(w => console.log(`  - ${w}`));
        }
        break;
        
      case 'summary':
        const summary = loader.getSummary();
        console.log('Configuration Summary:\n');
        console.log(JSON.stringify(summary, null, 2));
        break;
        
      default:
        console.log('Usage: config-loader.js [show|validate|summary] [config-path]');
        process.exit(1);
    }
  } catch (error) {
    console.error('❌ Configuration error:', error.message);
    if (loader.errors.length > 0) {
      console.error('\nErrors:');
      loader.errors.forEach(e => console.error(`  - ${e}`));
    }
    process.exit(1);
  }
}

export default ConfigLoader;
