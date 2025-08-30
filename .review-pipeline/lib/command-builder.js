#!/usr/bin/env node
/**
 * Command Builder - Constructs provider commands using layered configuration
 * 
 * Replaces generate-provider-command.js with a more secure, structured approach
 * that properly uses ConfigLoader for layered configuration and builds commands
 * as structured data rather than shell strings.
 */

import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import ConfigLoader from './config-loader.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default class CommandBuilder {
  constructor(options = {}) {
    this.packageDir = options.packageDir || path.dirname(__dirname);
    this.verbose = options.verbose || false;
    this.configLoader = new ConfigLoader();
  }

  /**
   * Load configuration using the layered system
   */
  async loadConfiguration() {
    await this.configLoader.load();
    return this.configLoader;
  }

  /**
   * Detect the actual command path for a provider
   */
  async detectCommandPath(manifest) {
    // First try the main command
    const mainCommand = manifest.cli?.command;
    if (mainCommand) {
      // Check if it's available in PATH
      try {
        const { execFileSync } = await import('node:child_process');
        // Use execFileSync with array args to prevent command injection
        execFileSync('which', [mainCommand], { stdio: 'ignore' });
        if (this.verbose) {
          console.error(`Found ${mainCommand} in PATH`);
        }
        return mainCommand;
      } catch {
        // Not in PATH, continue checking
        if (this.verbose) {
          console.error(`${mainCommand} not found in PATH, checking detection paths...`);
        }
      }
    }

    // Check detection paths
    if (manifest.cli?.detection) {
      for (const detection of manifest.cli.detection) {
        if (detection.type === 'path') {
          // Expand tilde to home directory
          const expandedPath = detection.value.replace(/^~/, os.homedir());
          try {
            await fs.access(expandedPath, constants.X_OK);
            if (this.verbose) {
              console.error(`Found ${mainCommand} at: ${expandedPath}`);
            }
            return expandedPath;
          } catch {
            // Path doesn't exist or not executable, continue
          }
        }
      }
    }

    // Fall back to the main command and hope it's in PATH
    return mainCommand || manifest.cli?.command;
  }

  /**
   * Build a complete command structure for a provider
   */
  async buildCommand(provider, options = {}) {
    // Load layered configuration
    const config = await this.loadConfiguration();
    
    // Check if provider is enabled
    if (!config.isProviderEnabled(provider)) {
      if (this.verbose) {
        console.error(`Provider ${provider} is disabled`);
      }
      return null;
    }

    // Get provider configuration with all overrides applied
    const providerConfig = config.getProviderConfig(provider);
    
    // Load provider manifest
    const manifestPath = path.join(this.packageDir, 'config', 'providers', `${provider}.manifest.json`);
    const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));

    // Build command based on provider type
    switch (provider) {
      case 'claude':
        return await this.buildClaudeCommand(providerConfig, manifest, options);
      case 'codex':
        return await this.buildCodexCommand(providerConfig, manifest, options);
      case 'gemini':
        return await this.buildGeminiCommand(providerConfig, manifest, options);
      default:
        throw new Error(`Unknown provider: ${provider}`);
    }
  }

  /**
   * Build Claude Code command structure
   */
  async buildClaudeCommand(config, manifest, options) {
    const model = config.model || 'opus';
    const timeout = config.timeout || 1500;
    
    // Detect the actual command path
    const commandPath = await this.detectCommandPath(manifest);
    
    // Build command arguments
    const args = [];
    
    // Model selection
    if (model) {
      args.push('--model', model);
    }
    
    // Permission mode
    if (config.flags?.permission_mode) {
      args.push('--permission-mode', config.flags.permission_mode);
    }
    
    // Output format
    if (config.flags?.output_format) {
      args.push('--output-format', config.flags.output_format);
    }
    
    // Additional flags
    if (config.additional_flags) {
      args.push(...config.additional_flags);
    }

    // Build the prompt (without injecting full context)
    const prompt = await this.buildPrompt('claude', config, options);
    
    // Prompt flag with actual prompt content
    args.push('-p', prompt);

    return {
      command: commandPath,
      args,
      stdin: null, // Claude takes prompt as argument, not stdin
      env: {
        ...process.env,
        TOOL: 'claude-code',
        MODEL: model,
        ANTHROPIC_API_KEY: '' // Ensure no API key (force OAuth)
      },
      timeout,
      outputFile: path.join(this.packageDir, 'workspace', 'reports', 'claude-code.json'),
      workingDirectory: path.join(this.packageDir, '..')
    };
  }

  /**
   * Build Codex CLI command structure
   */
  async buildCodexCommand(config, manifest, options) {
    const model = config.model || 'gpt-5';
    const timeout = config.timeout || 1500;
    const reasoning = config.reasoning_effort || 'high';
    const sandbox = config.sandbox_mode || 'read-only';
    const workdir = config.working_directory || '.';
    
    // Detect the actual command path
    const commandPath = await this.detectCommandPath(manifest);
    
    // Build command arguments
    const args = ['exec'];
    
    // Model
    args.push('-m', model);
    
    // Output file for last message
    const outputFile = path.join(this.packageDir, 'workspace', 'reports', 'codex-cli.raw.txt');
    args.push('--output-last-message', outputFile);
    
    // Sandbox mode
    args.push('-s', sandbox);
    
    // Working directory
    args.push('-C', workdir);
    
    // Reasoning effort
    args.push('-c', `model_reasoning_effort=${reasoning}`);
    
    // Additional config
    if (config.additional_config) {
      for (const [key, value] of Object.entries(config.additional_config)) {
        args.push('-c', `${key}=${value}`);
      }
    }

    // The prompt comes last (will be provided via argument, not stdin for Codex)
    const prompt = await this.buildPrompt('codex', config, options);
    args.push(prompt);

    return {
      command: commandPath,
      args,
      stdin: null, // Codex takes prompt as argument, not stdin
      env: {
        ...process.env,
        TOOL: 'codex-cli',
        MODEL: model,
        OPENAI_API_KEY: '' // Ensure no API key (force subscription)
      },
      timeout,
      outputFile: path.join(this.packageDir, 'workspace', 'reports', 'codex-cli.json'),
      rawOutputFile: outputFile,
      workingDirectory: path.join(this.packageDir, '..'),
      postProcess: true // Needs normalization from raw output
    };
  }

  /**
   * Build Gemini CLI command structure
   */
  async buildGeminiCommand(config, manifest, options) {
    const model = config.model || 'gemini-2.5-pro';
    const timeout = config.timeout || 1500;
    const flags = config.flags || {};
    
    // Detect the actual command path
    const commandPath = await this.detectCommandPath(manifest);
    
    // Build command arguments
    const args = [];
    
    // Model
    args.push('-m', model);
    
    // Non-interactive prompt mode (prompt via stdin)
    args.push('-p');
    
    // Enable sandbox mode by default for Gemini to allow tool use
    // This is needed for code review operations
    args.push('-s');
    
    // Use YOLO approval mode to auto-approve all tool actions
    // This allows Gemini to execute files and run commands without interaction
    args.push('--approval-mode=yolo');
    
    // Optional flags
    if (flags.yolo !== false) {
      // yolo flag is redundant with approval-mode=yolo but keep for compatibility
      args.push('-y');
    }
    if (flags.all_files) {
      args.push('-a');
    }
    if (flags.debug) {
      args.push('-d');
    }
    
    // Additional flags
    if (config.additional_flags) {
      args.push(...config.additional_flags);
    }

    // Build the prompt (without full context injection)
    const prompt = await this.buildPrompt('gemini', config, options);

    return {
      command: commandPath,
      args,
      stdin: prompt, // Gemini still takes prompt via stdin
      env: {
        ...process.env,
        TOOL: 'gemini-cli',
        MODEL: model,
        GEMINI_API_KEY: '' // Force OAuth by setting empty
      },
      timeout,
      outputFile: path.join(this.packageDir, 'workspace', 'reports', 'gemini-cli.json'),
      workingDirectory: path.join(this.packageDir, '..')
    };
  }

  /**
   * Build prompt WITHOUT injecting full context (for use with tools)
   */
  async buildPrompt(provider, config, options = {}) {
    const sections = [];

    // FIRST: Provider-specific prompt overlay
    const overlayPath = path.join(this.packageDir, 'prompts', `review.${provider}.md`);
    try {
      const overlay = await fs.readFile(overlayPath, 'utf8');
      sections.push(overlay);
    } catch (error) {
      if (this.verbose) {
        console.warn(`No provider overlay found at ${overlayPath}`);
      }
    }

    // SECOND: Core review prompt
    const corePath = path.join(this.packageDir, 'prompts', 'review.core.md');
    const corePrompt = await fs.readFile(corePath, 'utf8');
    sections.push(corePrompt);

    // THIRD: Inject PR context if available
    const prPath = path.join(this.packageDir, 'workspace', 'context', 'pr.json');
    try {
      const prData = JSON.parse(await fs.readFile(prPath, 'utf8'));
      sections.push('\n=== PULL REQUEST CONTEXT ===');
      sections.push(`Repository: ${prData.url?.split('/')[4] || 'unknown'}`);
      sections.push(`PR Number: ${prData.number}`);
      sections.push(`Branch: ${prData.headRefName} -> ${prData.baseRefName}`);
      sections.push(`Head SHA: ${prData.headRefOid}`);
      sections.push(`URL: ${prData.url}`);
      sections.push('Use these values for the "pr" field in your JSON output.');
      sections.push('=== END PR CONTEXT ===\n');
    } catch (error) {
      if (this.verbose) {
        console.warn(`Could not load PR context: ${error.message}`);
      }
    }

    // FOURTH: Provider-specific output instructions if needed
    if (provider === 'gemini') {
      sections.push('\nCRITICAL: Output ONLY the JSON object, no markdown code fences or other text.');
    }

    return sections.join('\n');
  }

  /**
   * Get default model for a provider
   */
  getDefaultModel(provider) {
    switch (provider) {
      case 'claude': return 'opus';
      case 'codex': return 'gpt-5';
      case 'gemini': return 'gemini-2.5-pro';
      default: return 'unknown';
    }
  }

  /**
   * Build a shell command string (for backward compatibility)
   * WARNING: This is less secure than structured commands
   */
  async buildShellCommand(provider, options = {}) {
    const cmd = await this.buildCommand(provider, options);
    if (!cmd) return null;

    // This is for backward compatibility only
    // New code should use structured commands
    const parts = [];
    
    // Environment variables
    for (const [key, value] of Object.entries(cmd.env)) {
      if (key !== 'PATH' && !key.startsWith('npm_')) {
        parts.push(`${key}="${value}"`);
      }
    }

    // Handle stdin if present
    if (cmd.stdin) {
      parts.push(`echo '${cmd.stdin.replace(/'/g, "'\\''")}'`);
      parts.push('|');
    }

    // Command and arguments
    parts.push(cmd.command);
    
    // Special handling for arguments
    for (const arg of cmd.args) {
      if (arg === 'STDIN_CONTENT' && cmd.stdin) {
        // Skip placeholder
        continue;
      }
      // Quote arguments that contain spaces
      if (arg.includes(' ')) {
        parts.push(`"${arg}"`);
      } else {
        parts.push(arg);
      }
    }

    // Output redirection
    if (cmd.outputFile) {
      parts.push('>', cmd.outputFile);
    }

    return parts.join(' ');
  }
}

// Allow direct execution for testing/compatibility
if (import.meta.url === `file://${process.argv[1]}`) {
  const provider = process.argv[2];
  if (!provider || !['claude', 'codex', 'gemini'].includes(provider)) {
    console.error('Usage: command-builder.js <claude|codex|gemini> [options]');
    process.exit(1);
  }

  const builder = new CommandBuilder({ verbose: process.argv.includes('--verbose') });
  
  if (process.argv.includes('--structured')) {
    // Output structured command (JSON)
    const cmd = await builder.buildCommand(provider);
    console.log(JSON.stringify(cmd, null, 2));
  } else {
    // Output shell command (backward compatibility)
    const cmd = await builder.buildShellCommand(provider);
    console.log(cmd);
  }
}